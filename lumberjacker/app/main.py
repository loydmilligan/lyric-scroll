#!/usr/bin/env python3
"""Lumberjacker - HA Log Watcher and Triage System.

Watches Home Assistant logs via Supervisor API, identifies real problems,
triages/prioritizes them, and outputs to a file for task creation.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from hashlib import md5
from pathlib import Path

import aiohttp
from aiohttp import web

from .ai_triage import AITriageEngine
from .mqtt_tasks import MQTTTaskPublisher

# Pattern to strip ANSI color codes from log lines
ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Paths
OPTIONS_PATH = Path("/data/options.json")
OUTPUT_PATH = Path("/share/lumberjacker/issues.json")
STATE_PATH = Path("/data/lumberjacker_state.json")
RESOLVED_ISSUES_PATH = Path("/share/lumberjacker/resolved-issues.json")

# Supervisor API
SUPERVISOR_URL = "http://supervisor/core/logs"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

# Triage review paths
TRIAGE_LOG_PATH = Path("/share/lumberjacker/triage-log.json")
PROCESS_IMPROVEMENTS_PATH = Path("/share/lumberjacker/process-improvements.json")


def load_options():
    """Load addon options from HA."""
    if OPTIONS_PATH.exists():
        return json.loads(OPTIONS_PATH.read_text())
    return {
        "check_interval": 60,
        "severity_threshold": "warning"
    }


# Severity levels (lower = more severe)
SEVERITY_LEVELS = {
    "critical": 0,
    "error": 1,
    "warning": 2,
    "info": 3,
    "debug": 4
}

# Priority scoring
PRIORITY_CRITICAL = "critical"
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"

# Log line pattern from Supervisor API: "2026-03-18 04:41:54.627 ERROR (Thread-22) [component] message"
LOG_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+"  # timestamp
    r"(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"          # severity
    r"\([^)]+\)\s+"                                    # thread info (ignored)
    r"\[([^\]]+)\]\s*"                                 # component in brackets
    r"(.*)$"                                           # message
)


class Issue:
    """A triaged log issue."""

    def __init__(self, severity: str, component: str, message: str, timestamp: str):
        hash_input = f"{component}:{message[:50]}".encode()
        self.id = f"issue-{md5(hash_input).hexdigest()[:8]}"
        self.severity = severity.lower()
        self.component = component
        self.message = message
        self.first_seen = timestamp
        self.last_seen = timestamp
        self.count = 1
        self.sample_entries = [f"{timestamp} {message}"]
        self.status = "open"
        self.priority = self._calculate_priority()
        self.category = self._categorize()
        # AI triage fields
        self.task_id: str | None = None
        self.ai_triaged_at: str | None = None
        self.ai_actionable: bool | None = None
        self.ai_suggested_action: str | None = None
        self.triage_count_at: int = 0
        # Resolution tracking fields
        self.resolved_at: str | None = None
        self.resolved_by: str | None = None
        self.final_count: int = 0

    def _calculate_priority(self) -> str:
        """Calculate priority based on severity and patterns."""
        if self.severity == "critical":
            return PRIORITY_CRITICAL
        if self.severity == "error":
            # Check for critical patterns
            critical_patterns = ["database", "startup", "fatal", "cannot start"]
            if any(p in self.message.lower() for p in critical_patterns):
                return PRIORITY_CRITICAL
            return PRIORITY_HIGH
        if self.severity == "warning":
            return PRIORITY_MEDIUM
        return PRIORITY_LOW

    def _categorize(self) -> str:
        """Categorize the issue."""
        msg_lower = self.message.lower()
        comp_lower = self.component.lower()

        if any(k in msg_lower for k in ["connect", "timeout", "unavailable", "api"]):
            return "integration"
        if any(k in comp_lower for k in ["automation", "script", "trigger"]):
            return "automation"
        if any(k in msg_lower for k in ["memory", "cpu", "disk", "database"]):
            return "system"
        if any(k in msg_lower for k in ["auth", "login", "token", "password"]):
            return "auth"
        if any(k in msg_lower for k in ["yaml", "config", "deprecated"]):
            return "config"
        return "other"

    def update(self, timestamp: str, message: str):
        """Update issue with new occurrence."""
        self.last_seen = timestamp
        self.count += 1
        if len(self.sample_entries) < 5:
            self.sample_entries.append(f"{timestamp} {message}")
        # Recalculate priority if count is high
        if self.count > 10 and self.priority == PRIORITY_MEDIUM:
            self.priority = PRIORITY_HIGH

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON output."""
        return {
            "id": self.id,
            "priority": self.priority,
            "category": self.category,
            "severity": self.severity,
            "component": self.component,
            "message": self.message[:200],
            "count": self.count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "sample_entries": self.sample_entries,
            "status": self.status,
            "task_id": self.task_id,
            "ai_triaged_at": self.ai_triaged_at,
            "ai_actionable": self.ai_actionable,
            "ai_suggested_action": self.ai_suggested_action,
            "triage_count_at": self.triage_count_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "final_count": self.final_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Issue":
        """Create Issue from dictionary (for state restoration)."""
        # Create a minimal issue and populate fields
        issue = cls.__new__(cls)
        issue.id = data.get("id", "")
        issue.severity = data.get("severity", "")
        issue.component = data.get("component", "")
        issue.message = data.get("message", "")
        issue.first_seen = data.get("first_seen", "")
        issue.last_seen = data.get("last_seen", "")
        issue.count = data.get("count", 1)
        issue.sample_entries = data.get("sample_entries", [])
        issue.status = data.get("status", "open")
        issue.priority = data.get("priority", PRIORITY_LOW)
        issue.category = data.get("category", "other")
        issue.task_id = data.get("task_id")
        issue.ai_triaged_at = data.get("ai_triaged_at")
        issue.ai_actionable = data.get("ai_actionable")
        issue.ai_suggested_action = data.get("ai_suggested_action")
        issue.triage_count_at = data.get("triage_count_at", 0)
        issue.resolved_at = data.get("resolved_at")
        issue.resolved_by = data.get("resolved_by")
        issue.final_count = data.get("final_count", 0)
        return issue


class LogWatcher:
    """Watches HA logs via Supervisor API and extracts issues."""

    def __init__(self, severity_threshold: str = "warning"):
        self.severity_threshold = SEVERITY_LEVELS.get(severity_threshold.lower(), 2)
        self.seen_lines: set[str] = set()  # Track processed lines by hash
        self.issues: dict[str, Issue] = {}
        self.session: aiohttp.ClientSession | None = None
        self._load_state()

    def _load_state(self):
        """Load previous state."""
        if STATE_PATH.exists():
            try:
                state = json.loads(STATE_PATH.read_text())
                self.seen_lines = set(state.get("seen_lines", []))
                # Limit stored hashes to prevent unbounded growth
                if len(self.seen_lines) > 10000:
                    self.seen_lines = set(list(self.seen_lines)[-5000:])
            except Exception:
                pass

        # Restore issues from output file
        if OUTPUT_PATH.exists():
            try:
                output_data = json.loads(OUTPUT_PATH.read_text())
                for issue_dict in output_data.get("issues", []):
                    issue = Issue.from_dict(issue_dict)
                    key = self._issue_key(issue.component, issue.message)
                    self.issues[key] = issue
                logger.info(f"Restored {len(self.issues)} issues from previous run")
            except Exception as e:
                logger.warning(f"Failed to restore issues: {e}")

    def _save_state(self):
        """Save current state."""
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Only keep recent hashes
        recent_hashes = list(self.seen_lines)[-5000:]
        STATE_PATH.write_text(json.dumps({
            "seen_lines": recent_hashes,
            "last_check": datetime.now().isoformat()
        }))

    def _line_hash(self, line: str) -> str:
        """Generate a hash for a log line."""
        return md5(line.encode()).hexdigest()[:16]

    def _issue_key(self, component: str, message: str) -> str:
        """Generate a key for deduplication."""
        # Normalize message by removing variable parts (numbers, UUIDs, etc.)
        normalized = re.sub(r'\b[0-9a-f-]{36}\b', '<uuid>', message)
        normalized = re.sub(r'\b\d+\b', '<n>', normalized)
        normalized = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '<ip>', normalized)
        return f"{component}:{normalized[:100]}"

    async def _fetch_logs(self) -> str:
        """Fetch logs from Supervisor API."""
        if not self.session:
            self.session = aiohttp.ClientSession()

        headers = {
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Content-Type": "text/plain",
        }

        try:
            async with self.session.get(SUPERVISOR_URL, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.text()
                else:
                    logger.error(f"Supervisor API returned {resp.status}")
                    return ""
        except Exception as e:
            logger.error(f"Error fetching logs from Supervisor: {e}")
            return ""

    async def check_logs(self) -> list[Issue]:
        """Check for new log entries via Supervisor API."""
        log_text = await self._fetch_logs()
        if not log_text:
            return []

        new_issues = []
        lines_processed = 0
        new_lines = 0
        matched_lines = 0
        severity_filtered = 0
        sample_logged = False

        for line in log_text.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Strip ANSI color codes
            line = ANSI_ESCAPE.sub('', line)

            lines_processed += 1

            # Skip already-seen lines
            line_hash = self._line_hash(line)
            if line_hash in self.seen_lines:
                continue

            self.seen_lines.add(line_hash)
            new_lines += 1

            # Log first few new lines for debugging (at INFO level to diagnose format issues)
            if not sample_logged and new_lines <= 3:
                logger.info(f"Sample line {new_lines}: {line[:200]}")
            if new_lines == 3:
                sample_logged = True

            match = LOG_PATTERN.match(line)
            if not match:
                continue

            matched_lines += 1
            severity, component, message = match.groups()
            severity_level = SEVERITY_LEVELS.get(severity.lower(), 3)

            # Filter by threshold
            if severity_level > self.severity_threshold:
                severity_filtered += 1
                continue

            # Use current time as timestamp since Supervisor API logs don't include it
            timestamp = datetime.now().isoformat()

            # Deduplicate
            key = self._issue_key(component, message)
            if key in self.issues:
                self.issues[key].update(timestamp, message)
            else:
                issue = Issue(severity, component, message, timestamp)
                self.issues[key] = issue
                new_issues.append(issue)

        if new_lines > 0:
            logger.info(f"Processed {lines_processed} lines, {new_lines} new, {matched_lines} matched pattern, {severity_filtered} below threshold, {len(new_issues)} new issues")

        self._save_state()
        self._write_output()

        return new_issues

    def _write_output(self):
        """Write triaged issues to output file for MT/Houston."""
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Sort by priority
        priority_order = {PRIORITY_CRITICAL: 0, PRIORITY_HIGH: 1, PRIORITY_MEDIUM: 2, PRIORITY_LOW: 3}
        sorted_issues = sorted(
            self.issues.values(),
            key=lambda i: (priority_order.get(i.priority, 4), -i.count)
        )

        output = {
            "generated_at": datetime.now().isoformat(),
            "total_issues": len(sorted_issues),
            "by_priority": {
                "critical": len([i for i in sorted_issues if i.priority == PRIORITY_CRITICAL]),
                "high": len([i for i in sorted_issues if i.priority == PRIORITY_HIGH]),
                "medium": len([i for i in sorted_issues if i.priority == PRIORITY_MEDIUM]),
                "low": len([i for i in sorted_issues if i.priority == PRIORITY_LOW])
            },
            "issues": [i.to_dict() for i in sorted_issues if i.status == "open"]
        }

        OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    def get_issues(self) -> list[dict]:
        """Get all issues as dicts."""
        return [i.to_dict() for i in self.issues.values()]

    def dismiss_issue(self, issue_id: str) -> bool:
        """Dismiss an issue."""
        for issue in self.issues.values():
            if issue.id == issue_id:
                issue.status = "dismissed"
                self._write_output()
                return True
        return False

    def resolve_issue(self, issue_id: str, task_id: str) -> bool:
        """Mark an issue as resolved and log to resolved issues file."""
        for issue in self.issues.values():
            if issue.id == issue_id:
                # Update issue status
                issue.status = "resolved"
                issue.resolved_at = datetime.now().isoformat()
                issue.resolved_by = task_id
                issue.final_count = issue.count

                # Calculate days active
                try:
                    first_dt = datetime.fromisoformat(issue.first_seen.replace('Z', '+00:00'))
                    resolved_dt = datetime.fromisoformat(issue.resolved_at)
                    days_active = (resolved_dt - first_dt).days
                except Exception:
                    days_active = 0

                # Create resolved issue record
                resolved_record = {
                    "resolved_at": issue.resolved_at,
                    "issue_id": issue.id,
                    "task_id": task_id,
                    "component": issue.component,
                    "message": issue.message[:200],
                    "first_seen": issue.first_seen,
                    "total_occurrences": issue.final_count,
                    "days_active": days_active,
                    "impact_note": f"Eliminated recurring error with {issue.final_count} occurrences over {days_active} days"
                }

                # Append to resolved issues log
                self._append_resolved_issue(resolved_record)

                # Update main output
                self._write_output()

                logger.info(f"Issue {issue_id} resolved by task {task_id} ({issue.final_count} occurrences)")
                return True
        return False

    def _append_resolved_issue(self, resolved_record: dict):
        """Append a resolved issue to the resolved issues log."""
        RESOLVED_ISSUES_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Load existing resolved issues
        if RESOLVED_ISSUES_PATH.exists():
            try:
                resolved_data = json.loads(RESOLVED_ISSUES_PATH.read_text())
            except Exception:
                resolved_data = {"resolved_issues": []}
        else:
            resolved_data = {"resolved_issues": []}

        # Append new record
        resolved_data["resolved_issues"].append(resolved_record)

        # Write back to file
        RESOLVED_ISSUES_PATH.write_text(json.dumps(resolved_data, indent=2))

    async def close(self):
        """Close the HTTP session."""
        if self.session:
            await self.session.close()


class WebServer:
    """Web UI for viewing triaged issues."""

    def __init__(self, watcher: LogWatcher, ai_engine: AITriageEngine | None = None):
        self.watcher = watcher
        self.ai_engine = ai_engine
        self.app = web.Application()
        self.setup_routes()

    def setup_routes(self):
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/api/issues", self.handle_issues)
        self.app.router.add_post("/api/issues/{id}/dismiss", self.handle_dismiss)
        self.app.router.add_post("/api/refresh", self.handle_refresh)
        self.app.router.add_get("/api/health", self.handle_health)
        self.app.router.add_post("/api/triage", self.handle_triage)
        self.app.router.add_get("/api/triage/status", self.handle_triage_status)
        self.app.router.add_post("/api/test-issues", self.handle_test_issues)
        self.app.router.add_get("/api/resolved", self.handle_resolved)
        # Triage review endpoints
        self.app.router.add_get("/api/triage-log", self.handle_get_triage_log)
        self.app.router.add_post("/api/triage-log/{triage_id}/review", self.handle_review_triage)
        self.app.router.add_post("/api/issues/{issue_id}/queue-review", self.handle_queue_review)
        self.app.router.add_get("/api/process-improvements", self.handle_get_process_improvements)
        self.app.router.add_post("/api/process-improvements", self.handle_add_process_improvement)

    async def handle_index(self, request):
        """Serve main UI."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Lumberjacker</title>
            <style>
                body { font-family: system-ui; background: #1a1a2e; color: #eee; padding: 2rem; margin: 0; }
                h1 { color: #e94560; margin: 0 0 0.5rem 0; }
                .subtitle { color: #888; margin-bottom: 2rem; }
                .stats { display: flex; gap: 1rem; margin-bottom: 2rem; }
                .stat { background: #16213e; padding: 1rem; border-radius: 8px; text-align: center; min-width: 80px; }
                .stat-value { font-size: 2rem; font-weight: bold; }
                .stat-label { font-size: 0.8rem; color: #888; }
                .kpi-section { margin-bottom: 2rem; }
                .kpi-title { color: #888; font-size: 0.9rem; margin-bottom: 0.5rem; }
                .kpi-cards { display: flex; gap: 1rem; flex-wrap: wrap; }
                .kpi-card { background: #16213e; padding: 1rem; border-radius: 8px; min-width: 150px; }
                .kpi-card-value { font-size: 1.5rem; font-weight: bold; color: #e94560; }
                .kpi-card-label { font-size: 0.8rem; color: #888; margin-top: 0.3rem; }
                .kpi-card-detail { font-size: 0.7rem; color: #666; margin-top: 0.2rem; }
                .critical .stat-value { color: #e94560; }
                .high .stat-value { color: #ff6b35; }
                .medium .stat-value { color: #f9a825; }
                .low .stat-value { color: #4caf50; }
                .issues { display: flex; flex-direction: column; gap: 0.5rem; }
                .issue { background: #16213e; padding: 1rem; border-radius: 8px; border-left: 4px solid #888; }
                .issue.critical { border-left-color: #e94560; }
                .issue.high { border-left-color: #ff6b35; }
                .issue.medium { border-left-color: #f9a825; }
                .issue.low { border-left-color: #4caf50; }
                .issue-header { display: flex; justify-content: space-between; margin-bottom: 0.5rem; }
                .issue-meta { font-size: 0.8rem; color: #888; }
                .issue-message { font-family: monospace; font-size: 0.9rem; word-break: break-word; }
                .badge { padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.7rem; text-transform: uppercase; margin-right: 0.3rem; }
                .badge-critical { background: #e94560; }
                .badge-high { background: #ff6b35; }
                .badge-medium { background: #f9a825; color: #000; }
                .badge-low { background: #4caf50; }
                .badge-triaged { background: #2196f3; }
                .badge-action { background: #ff9800; }
                .badge-task { background: #4caf50; }
                .badge-resolved { background: #9c27b0; }
                .badge-queued { background: #607d8b; }
                .empty { color: #888; font-style: italic; padding: 2rem; text-align: center; }
                .queue-review-btn { background: transparent; border: 1px solid #888; color: #888; padding: 0.2rem 0.5rem; border-radius: 4px; cursor: pointer; font-size: 0.7rem; margin-left: 0.3rem; }
                .queue-review-btn:hover { background: #333; border-color: #aaa; color: #aaa; }
                .queued-text { color: #888; font-size: 0.7rem; margin-left: 0.3rem; font-style: italic; }
                .refresh-btn { background: #e94560; border: none; color: white; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; margin-bottom: 1rem; }
                .refresh-btn:hover { background: #d63050; }
                .triage-btn { background: #4caf50; border: none; color: white; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; margin-bottom: 1rem; margin-left: 0.5rem; }
                .triage-btn:hover { background: #388e3c; }
                .triage-btn:disabled { background: #555; cursor: not-allowed; }
                .test-btn { background: #ff9800; border: none; color: white; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; margin-bottom: 1rem; margin-left: 0.5rem; }
                .test-btn:hover { background: #f57c00; }
                .status { color: #888; font-size: 0.8rem; margin-bottom: 1rem; }
            </style>
        </head>
        <body>
            <h1>Lumberjacker</h1>
            <p class="subtitle">HA Log Triage System (via Supervisor API)</p>
            <button class="refresh-btn" onclick="refresh()">Refresh Now</button>
            <button class="triage-btn" id="triageBtn" onclick="runTriage()" style="display:none;">Run AI Triage</button>
            <button class="test-btn" onclick="generateTestIssues()">Generate Test Issues</button>
            <div class="status" id="status"></div>
            <div class="kpi-section">
                <div class="kpi-title">TRIAGE METRICS</div>
                <div class="kpi-cards" id="kpiCards"></div>
            </div>
            <div class="stats" id="stats"></div>
            <div class="issues" id="issues"></div>
            <script>
                let triageLogEntries = [];

                async function loadTriageLog() {
                    try {
                        const res = await fetch('api/triage-log');
                        const data = await res.json();
                        triageLogEntries = data.entries || [];
                    } catch (err) {
                        console.error('Failed to load triage log:', err);
                        triageLogEntries = [];
                    }
                }

                async function loadIssues() {
                    await loadTriageLog();

                    const res = await fetch('api/issues');
                    const data = await res.json();

                    document.getElementById('status').textContent = `Last updated: ${data.generated_at || 'never'} | Total issues: ${data.total_issues || 0}`;

                    // Render KPI cards
                    const stats = data.triage_stats || {};
                    let kpiHtml = `
                        <div class="kpi-card">
                            <div class="kpi-card-value">${stats.total_triaged || 0}</div>
                            <div class="kpi-card-label">Triaged</div>
                            <div class="kpi-card-detail">${stats.actionable || 0} actionable</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-card-value">${stats.tasks_created || 0}</div>
                            <div class="kpi-card-label">Tasks Created</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-card-value">${stats.pending_review || 0}</div>
                            <div class="kpi-card-label">Pending Review</div>
                            <div class="kpi-card-detail">${stats.queued_for_review || 0} queued</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-card-value">${stats.resolved || 0}</div>
                            <div class="kpi-card-label">Resolved</div>
                            <div class="kpi-card-detail">${stats.total_occurrences_resolved || 0} occurrences eliminated</div>
                        </div>
                    `;

                    if (stats.in_progress_batch) {
                        kpiHtml += `
                            <div class="kpi-card">
                                <div class="kpi-card-value">${stats.in_progress_batch.current}/${stats.in_progress_batch.total}</div>
                                <div class="kpi-card-label">Current Batch</div>
                            </div>
                        `;
                    }

                    document.getElementById('kpiCards').innerHTML = kpiHtml;

                    document.getElementById('stats').innerHTML = `
                        <div class="stat critical"><div class="stat-value">${data.by_priority?.critical || 0}</div><div class="stat-label">Critical</div></div>
                        <div class="stat high"><div class="stat-value">${data.by_priority?.high || 0}</div><div class="stat-label">High</div></div>
                        <div class="stat medium"><div class="stat-value">${data.by_priority?.medium || 0}</div><div class="stat-label">Medium</div></div>
                        <div class="stat low"><div class="stat-value">${data.by_priority?.low || 0}</div><div class="stat-label">Low</div></div>
                    `;

                    const issues = data.issues || [];
                    if (issues.length === 0) {
                        document.getElementById('issues').innerHTML = '<div class="empty">No issues found. Logs are clean!</div>';
                        return;
                    }

                    document.getElementById('issues').innerHTML = issues.map(i => {
                        let badges = `<span class="badge badge-${i.priority}">${i.priority}</span>`;

                        if (i.ai_triaged_at) {
                            badges += '<span class="badge badge-triaged">Triaged</span>';
                        }
                        if (i.ai_actionable) {
                            badges += '<span class="badge badge-action">Action</span>';
                        }
                        if (i.task_id) {
                            badges += '<span class="badge badge-task">Task Created</span>';
                        }
                        if (i.resolved_at) {
                            badges += '<span class="badge badge-resolved">Resolved</span>';
                        }

                        // Check if this issue is queued for review in triage log
                        const triageEntry = triageLogEntries.find(e => e.issue_id === i.id);
                        const isQueued = triageEntry && triageEntry.review && triageEntry.review.queued;

                        // Add queue button or queued status if issue has been triaged
                        let queueControl = '';
                        if (i.ai_triaged_at) {
                            if (isQueued) {
                                queueControl = '<span class="queued-text">Queued</span>';
                            } else {
                                queueControl = `<button class="queue-review-btn" onclick="queueForReview('${i.id}')">Queue for Review</button>`;
                            }
                        }

                        return `
                            <div class="issue ${i.priority}">
                                <div class="issue-header">
                                    <span>${badges}${queueControl} <strong>${i.component}</strong></span>
                                    <span class="issue-meta">${i.count}x | ${i.category}</span>
                                </div>
                                <div class="issue-message">${escapeHtml(i.message)}</div>
                                <div class="issue-meta">First: ${i.first_seen} | Last: ${i.last_seen}</div>
                            </div>
                        `;
                    }).join('');
                }

                function escapeHtml(text) {
                    const div = document.createElement('div');
                    div.textContent = text;
                    return div.innerHTML;
                }

                async function refresh() {
                    document.getElementById('status').textContent = 'Refreshing...';
                    await fetch('api/refresh', {method: 'POST'});
                    await loadIssues();
                }

                async function runTriage() {
                    const btn = document.getElementById('triageBtn');
                    btn.disabled = true;
                    btn.textContent = 'Triaging...';
                    document.getElementById('status').textContent = 'Running AI triage...';

                    try {
                        const res = await fetch('api/triage', {method: 'POST'});
                        const data = await res.json();

                        if (data.error) {
                            document.getElementById('status').textContent = `Error: ${data.error}`;
                        } else if (data.status === 'no_issues') {
                            document.getElementById('status').textContent = 'No untriaged issues found.';
                        } else {
                            document.getElementById('status').textContent = `AI triage completed: ${data.triaged} issues triaged, ${data.tasks_created} tasks created.`;
                        }

                        await loadIssues();
                    } catch (err) {
                        document.getElementById('status').textContent = `Error: ${err.message}`;
                    } finally {
                        btn.disabled = false;
                        btn.textContent = 'Run AI Triage';
                    }
                }

                async function checkTriageStatus() {
                    try {
                        const res = await fetch('api/triage/status');
                        const data = await res.json();
                        if (data.enabled) {
                            document.getElementById('triageBtn').style.display = 'inline-block';
                        }
                    } catch (err) {
                        console.error('Failed to check triage status:', err);
                    }
                }

                async function generateTestIssues() {
                    document.getElementById('status').textContent = 'Generating test issues...';
                    try {
                        const res = await fetch('api/test-issues', {method: 'POST'});
                        const data = await res.json();
                        document.getElementById('status').textContent = `Generated ${data.count} test issues`;
                        await loadIssues();
                    } catch (err) {
                        document.getElementById('status').textContent = `Error: ${err.message}`;
                    }
                }

                async function queueForReview(issueId) {
                    document.getElementById('status').textContent = 'Queuing issue for review...';
                    try {
                        const res = await fetch(`api/issues/${issueId}/queue-review`, {method: 'POST'});
                        const data = await res.json();

                        if (data.error) {
                            document.getElementById('status').textContent = `Error: ${data.error}`;
                        } else {
                            document.getElementById('status').textContent = 'Issue queued for review';
                            await loadIssues();
                        }
                    } catch (err) {
                        document.getElementById('status').textContent = `Error: ${err.message}`;
                    }
                }

                loadIssues();
                checkTriageStatus();
                setInterval(loadIssues, 30000);
            </script>
        </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html")

    async def handle_issues(self, request):
        """API: Get triaged issues with triage stats."""
        if OUTPUT_PATH.exists():
            data = json.loads(OUTPUT_PATH.read_text())
        else:
            data = {"issues": [], "total_issues": 0, "by_priority": {}}

        # Calculate triage stats
        issues = data.get("issues", [])

        # Count triaged issues
        total_triaged = sum(1 for i in issues if i.get("ai_triaged_at"))
        actionable = sum(1 for i in issues if i.get("ai_actionable"))
        not_actionable = sum(1 for i in issues if i.get("ai_triaged_at") and not i.get("ai_actionable"))
        tasks_created = sum(1 for i in issues if i.get("task_id"))

        # Count pending review from triage log
        pending_review = 0
        queued_for_review = 0
        if TRIAGE_LOG_PATH.exists():
            try:
                triage_log = json.loads(TRIAGE_LOG_PATH.read_text())
                pending_review = sum(1 for e in triage_log.get("entries", []) if not e.get("reviewed", False))
                queued_for_review = sum(1 for e in triage_log.get("entries", []) if e.get("review", {}).get("queued", False))
            except Exception:
                pass

        # Check if triage is in progress (read from ai_engine if available)
        in_progress_batch = None
        # This will be populated by the AI engine when batching is active

        # Count resolved issues
        resolved_count = 0
        total_occurrences_resolved = 0
        if RESOLVED_ISSUES_PATH.exists():
            try:
                resolved_data = json.loads(RESOLVED_ISSUES_PATH.read_text())
                resolved_issues = resolved_data.get("resolved_issues", [])
                resolved_count = len(resolved_issues)
                total_occurrences_resolved = sum(issue.get("total_occurrences", 0) for issue in resolved_issues)
            except Exception:
                pass

        # Add triage stats to response
        data["triage_stats"] = {
            "total_triaged": total_triaged,
            "actionable": actionable,
            "not_actionable": not_actionable,
            "tasks_created": tasks_created,
            "pending_review": pending_review,
            "queued_for_review": queued_for_review,
            "in_progress_batch": in_progress_batch,
            "resolved": resolved_count,
            "total_occurrences_resolved": total_occurrences_resolved,
        }

        return web.json_response(data)

    async def handle_dismiss(self, request):
        """API: Dismiss an issue."""
        issue_id = request.match_info["id"]
        if self.watcher.dismiss_issue(issue_id):
            return web.json_response({"status": "dismissed"})
        return web.json_response({"error": "not found"}, status=404)

    async def handle_refresh(self, request):
        """API: Force refresh logs now."""
        await self.watcher.check_logs()
        return web.json_response({"status": "refreshed"})

    async def handle_health(self, request):
        """Health check."""
        return web.json_response({"status": "ok"})

    async def handle_triage(self, request):
        """API: Manually trigger AI triage."""
        if not self.ai_engine:
            return web.json_response(
                {"error": "AI triage not configured"},
                status=400
            )

        # Get untriaged open issues AND issues that need re-triaging
        to_triage = [
            issue for issue in self.watcher.issues.values()
            if issue.status == "open" and (
                issue.task_id is None or self.ai_engine.needs_retriage(issue)
            )
        ]

        if not to_triage:
            return web.json_response({"status": "no_issues", "triaged": 0})

        results = await self.ai_engine.triage(to_triage)
        self.watcher._write_output()  # Update output file

        return web.json_response({
            "status": "completed",
            "triaged": len(results),
            "tasks_created": sum(1 for r in results if r.get("create_task")),
        })

    async def handle_triage_status(self, request):
        """API: Get AI triage status."""
        if not self.ai_engine:
            return web.json_response({
                "enabled": False,
                "last_run": None,
                "tasks_created": 0,
            })

        return web.json_response({
            "enabled": True,
            "last_run": self.ai_engine.last_triage_at,
            "tasks_created": len(self.ai_engine.created_tasks),
        })

    async def handle_test_issues(self, request):
        """API: Generate test issues for testing triage system."""
        test_cases = [
            {
                "severity": "ERROR",
                "component": "hue",
                "message": "Unable to connect to bridge at 192.168.1.100",
            },
            {
                "severity": "WARNING",
                "component": "zwave_js",
                "message": "Node 15 is not responding to commands",
            },
            {
                "severity": "ERROR",
                "component": "mqtt",
                "message": "Connection lost to broker, reconnecting...",
            },
            {
                "severity": "WARNING",
                "component": "automation.morning_routine",
                "message": "Automation triggered but condition failed",
            },
            {
                "severity": "ERROR",
                "component": "homeassistant.core",
                "message": "Error setting up integration: timeout connecting to API",
            },
        ]

        timestamp = datetime.now().isoformat()
        created = 0

        for test_case in test_cases:
            issue = Issue(
                severity=test_case["severity"],
                component=test_case["component"],
                message=test_case["message"],
                timestamp=timestamp,
            )
            # Add to watcher's issue list
            key = self.watcher._issue_key(issue.component, issue.message)
            self.watcher.issues[key] = issue
            created += 1

        # Write to output file
        self.watcher._write_output()

        return web.json_response({
            "status": "created",
            "count": created,
        })

    async def handle_get_triage_log(self, request):
        """API: Get triage log with optional filters."""
        # Read triage log
        if not TRIAGE_LOG_PATH.exists():
            return web.json_response({"entries": []})

        try:
            triage_log = json.loads(TRIAGE_LOG_PATH.read_text())
        except Exception as e:
            logger.error(f"Failed to read triage log: {e}")
            return web.json_response({"error": "Failed to read triage log"}, status=500)

        # Extract query parameters
        reviewed = request.query.get("reviewed")  # "true", "false", "all"
        batch_id = request.query.get("batch_id")
        tag = request.query.get("tag")

        # Filter entries
        entries = triage_log.get("entries", [])
        filtered = []

        for entry in entries:
            # Filter by reviewed status
            if reviewed == "true" and not entry.get("reviewed", False):
                continue
            if reviewed == "false" and entry.get("reviewed", False):
                continue

            # Filter by batch_id
            if batch_id and entry.get("batch_id") != batch_id:
                continue

            # Filter by tag
            if tag and tag not in entry.get("tags", []):
                continue

            filtered.append(entry)

        return web.json_response({"entries": filtered})

    async def handle_review_triage(self, request):
        """API: Update triage entry with review data."""
        triage_id = request.match_info["triage_id"]

        # Parse request body
        try:
            review_data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        # Validate required fields
        if "verdict" not in review_data:
            return web.json_response({"error": "Missing 'verdict' field"}, status=400)

        valid_verdicts = ["correct", "minor_issues", "incorrect", "needs_tuning"]
        if review_data["verdict"] not in valid_verdicts:
            return web.json_response({"error": f"Invalid verdict. Must be one of: {valid_verdicts}"}, status=400)

        # Load triage log
        if not TRIAGE_LOG_PATH.exists():
            return web.json_response({"error": "Triage log not found"}, status=404)

        try:
            triage_log = json.loads(TRIAGE_LOG_PATH.read_text())
        except Exception as e:
            logger.error(f"Failed to read triage log: {e}")
            return web.json_response({"error": "Failed to read triage log"}, status=500)

        # Find and update the entry
        entries = triage_log.get("entries", [])
        entry_found = False

        for entry in entries:
            if entry.get("triage_id") == triage_id:
                # Update with review data
                entry["reviewed"] = True
                entry["reviewed_at"] = datetime.now().isoformat()
                entry["verdict"] = review_data["verdict"]

                if "rubric" in review_data:
                    entry["rubric"] = review_data["rubric"]

                if "notes" in review_data:
                    entry["notes"] = review_data["notes"]

                if "tags" in review_data:
                    # Merge tags
                    existing_tags = entry.get("tags", [])
                    new_tags = review_data["tags"]
                    entry["tags"] = list(set(existing_tags + new_tags))

                entry_found = True
                break

        if not entry_found:
            return web.json_response({"error": "Triage entry not found"}, status=404)

        # Write back to file
        try:
            TRIAGE_LOG_PATH.write_text(json.dumps(triage_log, indent=2))
        except Exception as e:
            logger.error(f"Failed to write triage log: {e}")
            return web.json_response({"error": "Failed to save review"}, status=500)

        return web.json_response({
            "status": "updated",
            "triage_id": triage_id,
        })

    async def handle_get_process_improvements(self, request):
        """API: Get process improvement items grouped by tag."""
        if not PROCESS_IMPROVEMENTS_PATH.exists():
            return web.json_response({"improvements": [], "by_tag": {}})

        try:
            data = json.loads(PROCESS_IMPROVEMENTS_PATH.read_text())
        except Exception as e:
            logger.error(f"Failed to read process improvements: {e}")
            return web.json_response({"error": "Failed to read process improvements"}, status=500)

        improvements = data.get("improvements", [])

        # Group by improvement_type
        by_tag = {}
        for item in improvements:
            improvement_type = item.get("improvement_type", "unknown")
            if improvement_type not in by_tag:
                by_tag[improvement_type] = []
            by_tag[improvement_type].append(item)

        return web.json_response({
            "improvements": improvements,
            "by_tag": by_tag,
            "total": len(improvements),
        })

    async def handle_queue_review(self, request):
        """API: Queue an issue for review."""
        issue_id = request.match_info["issue_id"]

        # Load triage log
        if not TRIAGE_LOG_PATH.exists():
            return web.json_response({"error": "Triage log not found"}, status=404)

        try:
            triage_log = json.loads(TRIAGE_LOG_PATH.read_text())
        except Exception as e:
            logger.error(f"Failed to read triage log: {e}")
            return web.json_response({"error": "Failed to read triage log"}, status=500)

        # Find the triage entry for this issue
        entries = triage_log.get("entries", [])
        entry_found = False

        for entry in entries:
            if entry.get("issue_id") == issue_id:
                # Ensure review object exists
                if "review" not in entry:
                    entry["review"] = {}

                # Set queued flag
                entry["review"]["queued"] = True
                entry["review"]["queued_at"] = datetime.now().isoformat()

                entry_found = True
                break

        if not entry_found:
            return web.json_response({"error": "Issue not found in triage log"}, status=404)

        # Write back to file
        try:
            TRIAGE_LOG_PATH.write_text(json.dumps(triage_log, indent=2))
        except Exception as e:
            logger.error(f"Failed to write triage log: {e}")
            return web.json_response({"error": "Failed to save queue status"}, status=500)

        return web.json_response({
            "status": "queued",
            "issue_id": issue_id,
        })

    async def handle_add_process_improvement(self, request):
        """API: Record a process improvement decision."""
        try:
            improvement_data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        # Validate required fields
        required = ["improvement_type", "description"]
        for field in required:
            if field not in improvement_data:
                return web.json_response({"error": f"Missing '{field}' field"}, status=400)

        valid_types = ["prompt_change", "pattern_add", "pattern_fix", "documentation"]
        if improvement_data["improvement_type"] not in valid_types:
            return web.json_response({"error": f"Invalid improvement_type. Must be one of: {valid_types}"}, status=400)

        # Set defaults
        improvement_data.setdefault("status", "proposed")
        improvement_data.setdefault("priority", "medium")
        improvement_data.setdefault("related_triage_ids", [])
        improvement_data["created_at"] = datetime.now().isoformat()

        # Generate ID
        improvement_data["id"] = f"pi-{md5(improvement_data['description'].encode()).hexdigest()[:8]}"

        # Load or create process improvements file
        if PROCESS_IMPROVEMENTS_PATH.exists():
            try:
                data = json.loads(PROCESS_IMPROVEMENTS_PATH.read_text())
            except Exception as e:
                logger.error(f"Failed to read process improvements: {e}")
                return web.json_response({"error": "Failed to read existing data"}, status=500)
        else:
            data = {"improvements": []}

        # Append new improvement
        data["improvements"].append(improvement_data)

        # Write to file
        try:
            PROCESS_IMPROVEMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            PROCESS_IMPROVEMENTS_PATH.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Failed to write process improvements: {e}")
            return web.json_response({"error": "Failed to save improvement"}, status=500)

        return web.json_response({
            "status": "created",
            "id": improvement_data["id"],
        })

    async def handle_resolved(self, request):
        """API: Get resolved issues with impact stats."""
        if not RESOLVED_ISSUES_PATH.exists():
            return web.json_response({
                "resolved_issues": [],
                "total_resolved": 0,
                "total_occurrences_eliminated": 0
            })

        try:
            resolved_data = json.loads(RESOLVED_ISSUES_PATH.read_text())
        except Exception as e:
            logger.error(f"Failed to read resolved issues: {e}")
            return web.json_response({"error": "Failed to read resolved issues"}, status=500)

        resolved_issues = resolved_data.get("resolved_issues", [])
        total_occurrences = sum(issue.get("total_occurrences", 0) for issue in resolved_issues)

        return web.json_response({
            "resolved_issues": resolved_issues,
            "total_resolved": len(resolved_issues),
            "total_occurrences_eliminated": total_occurrences
        })


async def main():
    """Main entry point."""
    options = load_options()
    logger.info(f"Lumberjacker starting with options: {options}")
    logger.info(f"Using Supervisor API at: {SUPERVISOR_URL}")
    logger.info(f"Supervisor token present: {bool(SUPERVISOR_TOKEN)}")

    # Initialize watcher
    watcher = LogWatcher(
        severity_threshold=options.get("severity_threshold", "warning")
    )

    # Initialize AI triage if configured
    ai_engine = None
    mqtt_publisher = None

    if options.get("ai_triage_enabled") and options.get("openrouter_api_key"):
        # Define callback for task resolution
        def handle_task_resolved(payload: dict):
            """Handle task resolution messages from MQTT."""
            task_id = payload.get("task_id")
            issue_id = payload.get("metadata", {}).get("issue_id")

            if not issue_id:
                logger.warning(f"Task {task_id} resolved but no issue_id in metadata")
                return

            logger.info(f"Handling resolution: task={task_id}, issue={issue_id}")
            watcher.resolve_issue(issue_id, task_id)

        # Initialize MQTT publisher
        mqtt_broker = options.get("mqtt_broker", "")
        if mqtt_broker:
            mqtt_publisher = MQTTTaskPublisher(
                broker=mqtt_broker,
                port=options.get("mqtt_port", 1883),
                username=options.get("mqtt_user", ""),
                password=options.get("mqtt_password", ""),
                on_task_resolved=handle_task_resolved,
            )
            if mqtt_publisher.connect():
                logger.info("MQTT task publisher connected")
            else:
                logger.warning("MQTT connection failed, tasks will not be published")
                mqtt_publisher = None

        # Initialize AI triage engine
        ai_engine = AITriageEngine(
            api_key=options["openrouter_api_key"],
            model=options.get("openrouter_model", "anthropic/claude-3-haiku"),
            mqtt_publisher=mqtt_publisher,
        )
        logger.info(f"AI triage enabled with model: {options.get('openrouter_model', 'anthropic/claude-3-haiku')}")
    else:
        logger.info("AI triage disabled (missing api key or not enabled)")

    # Initialize web server
    server = WebServer(watcher, ai_engine=ai_engine)

    # Do initial log check
    await watcher.check_logs()

    # Start periodic log checking
    async def check_loop():
        interval = options.get("check_interval", 60)
        while True:
            await asyncio.sleep(interval)
            await watcher.check_logs()

    asyncio.create_task(check_loop())

    # Start periodic AI triage if enabled
    async def triage_loop():
        if not ai_engine:
            return
        interval_minutes = options.get("triage_interval", 60)
        interval_seconds = interval_minutes * 60
        check_interval = options.get("check_interval", 60)
        # Wait for first watcher cycle to complete before starting triage
        initial_delay = check_interval + 10  # Add 10s buffer
        logger.info(f"AI triage loop starting (initial delay: {initial_delay}s, interval: {interval_minutes} minutes)")
        await asyncio.sleep(initial_delay)
        while True:
            logger.info("Checking for untriaged issues...")
            # Get untriaged open issues AND issues that need re-triaging
            to_triage = [
                issue for issue in watcher.issues.values()
                if issue.status == "open" and (
                    issue.task_id is None or ai_engine.needs_retriage(issue)
                )
            ]
            if to_triage:
                logger.info(f"Running AI triage on {len(to_triage)} issues")
                await ai_engine.triage(to_triage)
                watcher._write_output()  # Update output file with AI fields
            else:
                logger.info("No issues to triage, skipping AI triage")
            await asyncio.sleep(interval_seconds)

    if ai_engine:
        asyncio.create_task(triage_loop())

    # Start web server
    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8101)
    await site.start()

    logger.info("Lumberjacker running on port 8101")
    logger.info(f"Output file: {OUTPUT_PATH}")

    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await watcher.close()
        if ai_engine:
            await ai_engine.close()
        if mqtt_publisher:
            mqtt_publisher.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
