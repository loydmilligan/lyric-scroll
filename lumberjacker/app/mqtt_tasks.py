"""MQTT Task Publisher for Lumberjacker.

Publishes tasks to agent-sync/tasks/pending for Ground Control approval.
Subscribes to agent-sync/tasks/status/# for approval notifications.
"""

import json
import logging
import time
from typing import Optional, Callable

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

TASKS_TOPIC = "agent-sync/tasks/pending"
STATUS_TOPIC = "agent-sync/tasks/status/#"


class MQTTTaskPublisher:
    """Publishes tasks to MQTT for Ground Control approval."""

    def __init__(
        self,
        broker: str,
        port: int = 1883,
        username: str = "",
        password: str = "",
        on_status_update: Optional[Callable[[dict], None]] = None,
    ):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.on_status_update = on_status_update
        self.client: Optional[mqtt.Client] = None
        self.connected = False

    def connect(self) -> bool:
        """Connect to MQTT broker."""
        if not self.broker:
            logger.warning("MQTT broker not configured")
            return False

        try:
            self.client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"lumberjacker-{int(time.time())}",
            )

            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)

            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect

            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()

            # Wait briefly for connection
            time.sleep(1)
            return self.connected

        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            return False

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Handle connection to broker."""
        if reason_code == 0:
            self.connected = True
            logger.info(f"Connected to MQTT broker at {self.broker}:{self.port}")
            # Subscribe to task status updates
            client.subscribe(STATUS_TOPIC)
            logger.info(f"Subscribed to {STATUS_TOPIC}")
        else:
            logger.error(f"MQTT connection failed with code: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Handle disconnection from broker."""
        self.connected = False
        logger.warning(f"Disconnected from MQTT broker: {reason_code}")

    def _on_message(self, client, userdata, msg):
        """Handle incoming messages (task status updates)."""
        try:
            payload = json.loads(msg.payload.decode())
            logger.info(f"Task status update: {payload.get('task_id')} -> {payload.get('status')}")
            if self.on_status_update:
                self.on_status_update(payload)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse status message: {e}")

    def publish_task(
        self,
        task_id: str,
        title: str,
        description: str,
        category: str = "investigation",
        priority: str = "P3",
        approval_level: str = "human",
        metadata: Optional[dict] = None,
    ) -> bool:
        """Publish a task to the pending queue.

        Args:
            task_id: Unique task identifier (e.g., "lj-issue-abc123")
            title: Short task title
            description: Detailed description with suggested action
            category: Task category (investigation|action|notification|escalation)
            priority: Priority level (P1=urgent, P2=high, P3=normal, P4=low)
            approval_level: Who approves (auto|agent|human)
            metadata: Additional metadata dict

        Returns:
            True if published successfully, False otherwise
        """
        if not self.client or not self.connected:
            logger.error("MQTT client not connected")
            return False

        task = {
            "task_id": task_id,
            "title": title,
            "description": description,
            "requesting_agent": "lja",
            "target": "major-tom",
            "approval_level": approval_level,
            "category": category,
            "priority": priority,
            "status": "pending",
            "metadata": {
                "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source": "lumberjacker",
                **(metadata or {}),
            },
        }

        try:
            result = self.client.publish(
                TASKS_TOPIC,
                json.dumps(task),
                retain=True,
                qos=1,
            )
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Published task: {task_id}")
                return True
            else:
                logger.error(f"Failed to publish task: {result.rc}")
                return False
        except Exception as e:
            logger.error(f"Error publishing task: {e}")
            return False

    def disconnect(self):
        """Disconnect from broker."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            logger.info("Disconnected from MQTT broker")
