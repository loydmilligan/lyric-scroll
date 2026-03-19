"""MQTT client for agent task approval system."""

import asyncio
import json
import logging
import os
import time
from typing import Callable, Dict, List, Optional

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

# MQTT Configuration (from addon options via environment)
MQTT_BROKER = os.environ.get("MQTT_BROKER", "core-mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")

# Topics
TASKS_PENDING_TOPIC = "agent-sync/tasks/pending"
TASKS_STATUS_TOPIC = "agent-sync/tasks/status"


class AgentTask:
    """Represents an agent task awaiting approval."""

    def __init__(self, data: dict):
        self.task_id = data.get("task_id", "")
        self.title = data.get("title", "")
        self.description = data.get("description", "")
        self.requesting_agent = data.get("requesting_agent", "unknown")
        self.target = data.get("target", "")
        self.approval_level = data.get("approval_level", "human")
        self.category = data.get("category", "action")
        self.priority = data.get("priority", "P3")
        self.status = data.get("status", "pending")
        self.metadata = data.get("metadata", {})
        self.submitted_at = self.metadata.get("submitted_at", "")
        self.suggested_bucket = data.get("suggested_bucket", "work_queue")
        self.notes = data.get("notes", "")
        self.raw_data = data

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "requesting_agent": self.requesting_agent,
            "target": self.target,
            "approval_level": self.approval_level,
            "category": self.category,
            "priority": self.priority,
            "status": self.status,
            "submitted_at": self.submitted_at,
            "suggested_bucket": self.suggested_bucket,
            "notes": self.notes,
        }


class MQTTTaskClient:
    """MQTT client for receiving and managing agent tasks."""

    def __init__(self, on_tasks_update: Optional[Callable] = None):
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.pending_tasks: Dict[str, AgentTask] = {}  # Human approval queue
        self.agent_tasks: Dict[str, AgentTask] = {}    # Agent-level (Major Tom) queue
        self.completed_tasks: List[AgentTask] = []
        self.on_tasks_update = on_tasks_update
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self, loop: asyncio.AbstractEventLoop):
        """Start the MQTT client."""
        self._loop = loop

        try:
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id="ground-control",
                protocol=mqtt.MQTTv311
            )
            self.client.username_pw_set(MQTT_USER, MQTT_PASS)
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            logger.info(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT} as {MQTT_USER}")
            self.client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"[MQTT] Failed to start: {e}")

    def stop(self):
        """Stop the MQTT client."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("[MQTT] Disconnected")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Handle MQTT connection."""
        if reason_code == 0:
            self.connected = True
            logger.info("[MQTT] Connected successfully")
            # Subscribe to pending tasks
            client.subscribe(TASKS_PENDING_TOPIC)
            client.subscribe(f"{TASKS_PENDING_TOPIC}/#")
            logger.info(f"[MQTT] Subscribed to {TASKS_PENDING_TOPIC}")
        else:
            logger.error(f"[MQTT] Connection failed: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Handle MQTT disconnection."""
        self.connected = False
        logger.warning(f"[MQTT] Disconnected: {reason_code}")

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        try:
            payload = json.loads(msg.payload.decode())
            logger.info(f"[MQTT] Received task: {payload.get('task_id', 'unknown')}")

            task = AgentTask(payload)

            if task.status != "pending":
                return

            # Route to appropriate queue based on approval_level
            if task.approval_level == "human":
                self.pending_tasks[task.task_id] = task
                logger.info(f"[MQTT] Added to human queue: {task.task_id} - {task.title}")
            else:
                # Agent-level tasks (Major Tom queue)
                self.agent_tasks[task.task_id] = task
                logger.info(f"[MQTT] Added to agent queue: {task.task_id} - {task.title}")

            # Notify listeners
            if self.on_tasks_update and self._loop:
                self._loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self.on_tasks_update())
                )

        except json.JSONDecodeError:
            logger.error(f"[MQTT] Invalid JSON in message")
        except Exception as e:
            logger.error(f"[MQTT] Error processing message: {e}")

    def approve_task(self, task_id: str, bucket: str = "work_queue", approver: str = "human") -> Optional[AgentTask]:
        """Approve a pending task and return the task for adding to the task system."""
        if task_id not in self.pending_tasks:
            return None

        task = self.pending_tasks.pop(task_id)
        task.status = "approved"

        # Publish approval status with bucket assignment
        status_payload = {
            "task_id": task_id,
            "status": "approved",
            "approved_by": approver,
            "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "assigned_bucket": bucket,
            "original_task": task.raw_data,
        }

        if self.client and self.connected:
            topic = f"{TASKS_STATUS_TOPIC}/{task_id}"
            self.client.publish(topic, json.dumps(status_payload), retain=True, qos=1)
            logger.info(f"[MQTT] Published approval for {task_id} -> bucket: {bucket}")

        # Add to completed list
        self.completed_tasks.insert(0, task)
        # Keep only last 50 completed tasks
        self.completed_tasks = self.completed_tasks[:50]

        return task

    def reject_task(self, task_id: str, reason: str = "", rejector: str = "human") -> bool:
        """Reject a pending task."""
        if task_id not in self.pending_tasks:
            return False

        task = self.pending_tasks.pop(task_id)
        task.status = "rejected"

        # Publish rejection status
        status_payload = {
            "task_id": task_id,
            "status": "rejected",
            "rejected_by": rejector,
            "reason": reason,
            "rejected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "original_task": task.raw_data,
        }

        if self.client and self.connected:
            topic = f"{TASKS_STATUS_TOPIC}/{task_id}"
            self.client.publish(topic, json.dumps(status_payload), retain=True, qos=1)
            logger.info(f"[MQTT] Published rejection for {task_id}")

        # Add to completed list
        self.completed_tasks.insert(0, task)
        self.completed_tasks = self.completed_tasks[:50]

        return True

    def get_pending_tasks(self) -> List[dict]:
        """Get list of pending human-approval tasks."""
        return [task.to_dict() for task in self.pending_tasks.values()]

    def get_agent_tasks(self) -> List[dict]:
        """Get list of agent-level tasks (Major Tom queue)."""
        return [task.to_dict() for task in self.agent_tasks.values()]

    def get_completed_tasks(self) -> List[dict]:
        """Get list of recently completed tasks."""
        return [task.to_dict() for task in self.completed_tasks]

    def add_note_to_task(self, task_id: str, note: str) -> bool:
        """Add a note to an agent-level task."""
        if task_id in self.agent_tasks:
            self.agent_tasks[task_id].notes = note
            return True
        return False

    def get_status(self) -> dict:
        """Get MQTT client status."""
        return {
            "connected": self.connected,
            "broker": MQTT_BROKER,
            "pending_count": len(self.pending_tasks),
            "agent_count": len(self.agent_tasks),
            "completed_count": len(self.completed_tasks),
        }
