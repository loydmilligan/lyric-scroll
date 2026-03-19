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

# Supervisor API
SUPERVISOR_URL = "http://supervisor/core/logs"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


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
                .badge { padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.7rem; text-transform: uppercase; }
                .badge-critical { background: #e94560; }
                .badge-high { background: #ff6b35; }
                .badge-medium { background: #f9a825; color: #000; }
                .badge-low { background: #4caf50; }
                .empty { color: #888; font-style: italic; padding: 2rem; text-align: center; }
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
            <div class="stats" id="stats"></div>
            <div class="issues" id="issues"></div>
            <script>
                async function loadIssues() {
                    const res = await fetch('api/issues');
                    const data = await res.json();

                    document.getElementById('status').textContent = `Last updated: ${data.generated_at || 'never'} | Total issues: ${data.total_issues || 0}`;

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

                    document.getElementById('issues').innerHTML = issues.map(i => `
                        <div class="issue ${i.priority}">
                            <div class="issue-header">
                                <span><span class="badge badge-${i.priority}">${i.priority}</span> <strong>${i.component}</strong></span>
                                <span class="issue-meta">${i.count}x | ${i.category}</span>
                            </div>
                            <div class="issue-message">${escapeHtml(i.message)}</div>
                            <div class="issue-meta">First: ${i.first_seen} | Last: ${i.last_seen}</div>
                        </div>
                    `).join('');
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

                loadIssues();
                checkTriageStatus();
                setInterval(loadIssues, 30000);
            </script>
        </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html")

    async def handle_issues(self, request):
        """API: Get triaged issues."""
        if OUTPUT_PATH.exists():
            return web.json_response(json.loads(OUTPUT_PATH.read_text()))
        return web.json_response({"issues": [], "total_issues": 0, "by_priority": {}})

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

        # Get untriaged open issues
        untriaged = [
            issue for issue in self.watcher.issues.values()
            if issue.status == "open" and issue.task_id is None
        ]

        if not untriaged:
            return web.json_response({"status": "no_issues", "triaged": 0})

        results = await self.ai_engine.triage(untriaged)
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
        # Initialize MQTT publisher
        mqtt_broker = options.get("mqtt_broker", "")
        if mqtt_broker:
            mqtt_publisher = MQTTTaskPublisher(
                broker=mqtt_broker,
                port=options.get("mqtt_port", 1883),
                username=options.get("mqtt_user", ""),
                password=options.get("mqtt_password", ""),
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
            # Get untriaged open issues
            untriaged = [
                issue for issue in watcher.issues.values()
                if issue.status == "open" and issue.task_id is None
            ]
            if untriaged:
                logger.info(f"Running AI triage on {len(untriaged)} untriaged issues")
                await ai_engine.triage(untriaged)
                watcher._write_output()  # Update output file with AI fields
            else:
                logger.info("No untriaged issues, skipping AI triage")
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
