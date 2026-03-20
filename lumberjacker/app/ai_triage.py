"""AI Triage Engine for Lumberjacker.

Uses OpenRouter API to intelligently analyze log issues
and determine which should become tasks for Major Tom.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from .mqtt_tasks import MQTTTaskPublisher

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TRIAGE_LOG_PATH = "/share/lumberjacker/triage-log.json"

SYSTEM_PROMPT = """You are a Home Assistant log triage assistant. Analyze log issues and determine which ones should become tasks for Major Tom (an AI agent that can fix HA problems by editing configuration, automations, and integrations).

For each issue, determine:
1. actionable: boolean - Can this be fixed by an AI agent with access to HA config/automations?
2. suggested_action: string - What should the agent do? Be specific.
3. create_task: boolean - Should this become a formal task?
4. approval_level: "agent" | "human" - Who should approve? Use "human" for risky changes.
5. category: "investigation" | "action" | "notification" | "escalation"
6. priority: "P1" (urgent) | "P2" (high) | "P3" (normal) | "P4" (low)

ACTIONABLE issues (create task):
- Configuration errors in YAML that can be fixed
- Integration setup issues (missing config, wrong settings)
- Automation errors/failures (syntax, entity references)
- Auth token expirations that need refresh
- Deprecated settings that need updating
- Entity unavailable errors due to config issues

NOT ACTIONABLE issues (do not create task):
- Transient network blips (connection reset, timeout - often self-resolve)
- External service outages (cloud services down)
- Hardware failures (device offline, battery dead)
- Memory/CPU issues (system-level, not config-related)
- Third-party integration bugs (need upstream fix)
- Chromecast/media device disconnections (usually temporary)

Respond with JSON only, no explanation. Format:
{
  "triage_results": [
    {
      "issue_id": "...",
      "actionable": true/false,
      "reasoning": "brief explanation",
      "suggested_action": "what to do",
      "create_task": true/false,
      "approval_level": "agent" or "human",
      "category": "...",
      "priority": "P1/P2/P3/P4"
    }
  ]
}"""


class AITriageEngine:
    """AI-powered issue triage using OpenRouter API."""

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-3-haiku",
        mqtt_publisher: Optional["MQTTTaskPublisher"] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.mqtt_publisher = mqtt_publisher
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_triage_at: Optional[str] = None
        self.created_tasks: set[str] = set()

    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def _generate_triage_id(self, issue_id: str) -> str:
        """Generate a unique triage ID.

        Format: tr-{YYYYMMDD}-{HHMMSS}-{first 6 chars of issue id}
        """
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        issue_short = issue_id[:6] if len(issue_id) >= 6 else issue_id
        return f"tr-{timestamp}-{issue_short}"

    def needs_retriage(self, issue) -> bool:
        """Check if an issue needs re-triaging.

        An issue needs re-triage if ALL of:
        - It was previously triaged (ai_triaged_at is set)
        - It was marked NOT actionable (ai_actionable == False)
        - AND one of:
          - Count has increased by 10+ since last triage
          - OR 24+ hours have passed since last triage
        """
        # Not previously triaged
        if not issue.ai_triaged_at:
            return False

        # Was marked actionable (already has task or will get one)
        if issue.ai_actionable:
            return False

        # Check count increase
        count_delta = issue.count - issue.triage_count_at
        if count_delta >= 10:
            return True

        # Check time elapsed
        try:
            triaged_at = datetime.fromisoformat(issue.ai_triaged_at)
            hours_elapsed = (datetime.now() - triaged_at).total_seconds() / 3600
            if hours_elapsed >= 24:
                return True
        except (ValueError, TypeError):
            # If we can't parse the timestamp, don't re-triage based on time
            pass

        return False

    def _write_triage_log(self, batch_id: str, issues: list, results: list[dict], retriaged_issue_ids: set = None):
        """Write triage decisions to log file.

        Args:
            batch_id: Identifier for this triage batch
            issues: List of Issue objects that were triaged
            results: List of triage result dictionaries from AI
            retriaged_issue_ids: Set of issue IDs that are being re-triaged
        """
        if retriaged_issue_ids is None:
            retriaged_issue_ids = set()

        # Ensure directory exists
        os.makedirs(os.path.dirname(TRIAGE_LOG_PATH), exist_ok=True)

        # Load existing log
        existing_entries = []
        if os.path.exists(TRIAGE_LOG_PATH):
            try:
                with open(TRIAGE_LOG_PATH, 'r') as f:
                    existing_entries = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                logger.warning(f"Could not load existing triage log, starting fresh")
                existing_entries = []

        # Create new entries
        new_entries = []
        timestamp = datetime.now().isoformat()

        for result in results:
            issue_id = result.get("issue_id")
            issue = next((i for i in issues if i.id == issue_id), None)
            if not issue:
                continue

            entry = {
                "triage_id": self._generate_triage_id(issue_id),
                "timestamp": timestamp,
                "batch_id": batch_id,
                "is_retriage": issue_id in retriaged_issue_ids,
                "issue": {
                    "id": issue.id,
                    "severity": issue.severity,
                    "category": issue.category,
                    "component": issue.component,
                    "message": issue.message,
                    "count": issue.count,
                    "first_seen": issue.first_seen,
                    "last_seen": issue.last_seen,
                },
                "decision": {
                    "actionable": result.get("actionable", False),
                    "create_task": result.get("create_task", False),
                    "priority": result.get("priority", "P3"),
                    "category": result.get("category", "investigation"),
                    "approval_level": result.get("approval_level", "human"),
                    "suggested_action": result.get("suggested_action", ""),
                    "reasoning": result.get("reasoning", ""),
                },
                "review": {
                    "reviewed": False,
                    "reviewed_at": None,
                    "verdict": None,
                    "notes": None,
                    "tags": [],
                },
            }
            new_entries.append(entry)

        # Append and write back
        all_entries = existing_entries + new_entries

        try:
            with open(TRIAGE_LOG_PATH, 'w') as f:
                json.dump(all_entries, f, indent=2)
            logger.info(f"Wrote {len(new_entries)} triage log entries to {TRIAGE_LOG_PATH}")
        except Exception as e:
            logger.error(f"Failed to write triage log: {e}")

    async def triage(self, issues: list) -> list[dict]:
        """Triage a batch of issues using AI.

        Args:
            issues: List of Issue objects to triage

        Returns:
            List of triage results with task creation status
        """
        if not issues:
            return []

        if not self.api_key:
            logger.warning("OpenRouter API key not configured, skipping AI triage")
            return []

        await self._ensure_session()

        # Track which issues are being re-triaged
        retriaged_issue_ids = {issue.id for issue in issues if self.needs_retriage(issue)}
        if retriaged_issue_ids:
            logger.info(f"Re-triaging {len(retriaged_issue_ids)} recurring issues")

        # Generate batch ID for this triage run
        batch_id = datetime.now().strftime("batch-%Y%m%d-%H%M%S")

        # Process issues in batches to avoid timeout
        BATCH_SIZE = 10
        all_results = []
        total_batches = (len(issues) + BATCH_SIZE - 1) // BATCH_SIZE

        for batch_idx in range(0, len(issues), BATCH_SIZE):
            batch_num = (batch_idx // BATCH_SIZE) + 1
            batch = issues[batch_idx:batch_idx + BATCH_SIZE]
            batch_size = len(batch)

            logger.info(f"Processing batch {batch_num}/{total_batches} ({batch_size} issues)")

            # Build the prompt with issue data for this batch
            issues_data = []
            for issue in batch:
                issues_data.append({
                    "issue_id": issue.id,
                    "severity": issue.severity,
                    "category": issue.category,
                    "component": issue.component,
                    "message": issue.message[:500],  # Truncate long messages
                    "count": issue.count,
                    "first_seen": issue.first_seen,
                    "last_seen": issue.last_seen,
                    "sample_entries": issue.sample_entries[:3],  # Limit samples
                })

            user_prompt = json.dumps({"issues": issues_data}, indent=2)

            # Call OpenRouter API for this batch
            try:
                response = await self._call_openrouter(user_prompt)
                if not response:
                    logger.warning(f"No response for batch {batch_num}/{total_batches}, continuing")
                    continue

                results = response.get("triage_results", [])
                self.last_triage_at = datetime.now().isoformat()

                # Process results and create tasks
                for result in results:
                    issue_id = result.get("issue_id")
                    issue = next((i for i in batch if i.id == issue_id), None)
                    if not issue:
                        continue

                    # Update issue with AI fields
                    issue.ai_triaged_at = self.last_triage_at
                    issue.ai_actionable = result.get("actionable", False)
                    issue.ai_suggested_action = result.get("suggested_action", "")
                    issue.triage_count_at = issue.count  # Record count at triage time

                    # Create task if needed
                    if result.get("create_task") and issue.task_id is None:
                        await self._create_task(issue, result)

                # Write triage log for this batch
                self._write_triage_log(batch_id, batch, results, retriaged_issue_ids)

                all_results.extend(results)
                logger.info(f"Batch {batch_num}/{total_batches} complete: {len(results)} results")

            except Exception as e:
                logger.error(f"Batch {batch_num}/{total_batches} failed: {type(e).__name__}: {e}")
                logger.exception("Batch triage traceback:")
                continue

        logger.info(f"Triaged {len(issues)} issues in {total_batches} batches, {len(all_results)} total results")
        return all_results

    async def _call_openrouter(self, user_prompt: str) -> Optional[dict]:
        """Call OpenRouter API with the triage prompt."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/loydmilligan/ha-addons",
            "X-Title": "Lumberjacker HA Addon",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,  # Low temperature for consistent results
            "response_format": {"type": "json_object"},
        }

        try:
            async with self.session.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    try:
                        content = data["choices"][0]["message"]["content"]
                        return json.loads(content)
                    except (KeyError, IndexError) as e:
                        logger.error(f"Unexpected OpenRouter response structure: {data}")
                        return None
                elif resp.status == 429:
                    logger.warning("OpenRouter rate limited, will retry later")
                    return None
                else:
                    error = await resp.text()
                    logger.error(f"OpenRouter API error {resp.status}: {error}")
                    return None

        except aiohttp.ClientError as e:
            logger.error(f"Network error calling OpenRouter: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenRouter response: {e}")
            return None

    async def _create_task(self, issue, triage_result: dict):
        """Create a task via MQTT for an actionable issue."""
        if not self.mqtt_publisher or not self.mqtt_publisher.connected:
            logger.warning("MQTT not connected, cannot create task")
            return

        task_id = f"lj-{issue.id}"

        # Avoid duplicates
        if task_id in self.created_tasks:
            logger.debug(f"Task {task_id} already created, skipping")
            return

        # Build task title and description
        component_short = issue.component.split(".")[-1] if "." in issue.component else issue.component
        title = f"[{component_short}] {issue.message[:80]}"

        description = f"""**Issue Details:**
- Component: `{issue.component}`
- Severity: {issue.severity.upper()}
- Occurrences: {issue.count}
- First seen: {issue.first_seen}
- Last seen: {issue.last_seen}

**AI Analysis:**
{triage_result.get('reasoning', 'No reasoning provided')}

**Suggested Action:**
{triage_result.get('suggested_action', 'Review and address the issue')}

**Sample Log Entries:**
```
{chr(10).join(issue.sample_entries[:3])}
```
"""

        success = self.mqtt_publisher.publish_task(
            task_id=task_id,
            title=title,
            description=description,
            category=triage_result.get("category", "investigation"),
            priority=triage_result.get("priority", "P3"),
            approval_level=triage_result.get("approval_level", "human"),
            metadata={
                "issue_id": issue.id,
                "component": issue.component,
                "severity": issue.severity,
                "occurrence_count": issue.count,
            },
        )

        if success:
            issue.task_id = task_id
            self.created_tasks.add(task_id)
            logger.info(f"Created task {task_id} for issue {issue.id}")
