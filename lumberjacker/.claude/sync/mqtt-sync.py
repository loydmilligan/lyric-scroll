#!/usr/bin/env python3
"""MQTT-based agent sync for LJA (Lumberjacker Agent).

Usage:
    ./mqtt-sync.py send [file]    Send message(s) from outbox
    ./mqtt-sync.py receive        Receive messages to inbox
    ./mqtt-sync.py status         Check connection status

Multi-recipient Support:
    Messages can specify multiple recipients in the YAML frontmatter:
    - to: major-tom              (single recipient)
    - to: major-tom, gca         (comma-separated list)
    - to: [major-tom, gca]       (YAML array)
    - to: all                    (broadcast to all known agents)
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

# Paths
SCRIPT_DIR = Path(__file__).parent
OUTBOX = SCRIPT_DIR / "outbox"
INBOX = SCRIPT_DIR / "inbox"
ARCHIVE = SCRIPT_DIR / "archive"

# Known agents for "all" broadcast
KNOWN_AGENTS = ["major-tom", "gca", "houston", "lsa"]
AGENT_ID = "lja"

# Load config from .env
def load_env():
    env_file = SCRIPT_DIR / ".env"
    config = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    return config

ENV = load_env()
BROKER = ENV.get("MQTT_BROKER", "192.168.4.158")
PORT = int(ENV.get("MQTT_PORT", "1883"))
USER = ENV.get("MQTT_USER", "lja")
PASS = ENV.get("MQTT_PASS", "")

STATUS_TOPIC = f"agent-sync/{AGENT_ID}/status"
INTRO_TOPIC = f"agent-sync/intro/{AGENT_ID}"


def get_client():
    """Create and connect MQTT client."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{AGENT_ID}-sync", protocol=mqtt.MQTTv311)
    client.username_pw_set(USER, PASS)
    client.connect(BROKER, PORT, keepalive=60)
    return client


def parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from message content."""
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return {}

    frontmatter = {}
    for line in match.group(1).splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            frontmatter[key.strip()] = value.strip()
    return frontmatter


def parse_recipients(content: str) -> list[str]:
    """Parse recipient(s) from message frontmatter.

    Supports:
    - to: major-tom              (single)
    - to: major-tom, gca         (comma-separated)
    - to: [major-tom, gca]       (YAML array)
    - to: all                    (broadcast)
    """
    fm = parse_frontmatter(content)
    to_value = fm.get('to', 'major-tom')

    # Handle "all" keyword
    if to_value.lower() == "all":
        return KNOWN_AGENTS

    # Handle YAML array: [a, b, c]
    if to_value.startswith("[") and to_value.endswith("]"):
        items = to_value[1:-1].split(",")
        return [item.strip().strip("'\"") for item in items if item.strip()]

    # Handle comma-separated: a, b, c
    if "," in to_value:
        return [item.strip() for item in to_value.split(",") if item.strip()]

    # Single recipient
    return [to_value]


def is_intro_message(content: str) -> bool:
    """Check if message is an agent introduction."""
    fm = parse_frontmatter(content)
    return fm.get('type', '').lower() == 'intro'


def send_message(filepath: Path):
    """Send a single message file to one or more recipients."""
    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}")
        return False

    content = filepath.read_text()
    filename = filepath.name
    msg_id = filepath.stem

    # Check if this is an intro message
    is_intro = is_intro_message(content)

    # Parse recipients from frontmatter
    recipients = parse_recipients(content)

    payload = json.dumps({
        "filename": filename,
        "content": content,
        "from": AGENT_ID,
        "to": recipients,
        "is_intro": is_intro,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    })

    client = get_client()
    client.loop_start()

    if is_intro:
        # Intro messages go to the special intro topic (broadcast)
        topic = INTRO_TOPIC
        result = client.publish(topic, payload, retain=True, qos=1)
        result.wait_for_publish(timeout=5)
        print(f"Sent INTRO: {filename} -> {topic}")
    else:
        # Regular messages go to each recipient's topic
        for recipient in recipients:
            topic = f"agent-sync/{AGENT_ID}-to-{recipient}/{msg_id}"
            result = client.publish(topic, payload, retain=True, qos=1)
            result.wait_for_publish(timeout=5)
            print(f"Sent: {filename} -> {topic}")

    client.loop_stop()
    client.disconnect()

    # Move to archive
    dest = ARCHIVE / filename
    filepath.rename(dest)
    print(f"Archived: {filename}")

    return True


def send_all():
    """Send all messages in outbox."""
    files = list(OUTBOX.glob("*.md"))
    if not files:
        print("Outbox is empty.")
        return

    for f in sorted(files):
        send_message(f)

    print(f"Sent {len(files)} message(s).")


def receive_messages():
    """Receive messages from any agent addressed to LJA, plus intro broadcasts."""
    # Subscribe to all agent-sync messages and filter in callback
    # (MQTT + wildcard must be entire topic level, can't do "+-to-lja")
    recv_pattern = "agent-sync/#"

    received = []

    def on_message(client, userdata, msg):
        topic = msg.topic

        # Filter: only accept messages TO this agent or intro broadcasts
        is_to_me = f"-to-{AGENT_ID}/" in topic
        is_intro_topic = topic.startswith("agent-sync/intro/")

        if not is_to_me and not is_intro_topic:
            return

        try:
            payload = json.loads(msg.payload.decode())
            filename = payload.get("filename", f"msg-{int(time.time())}.md")
            content = payload.get("content", msg.payload.decode())
            is_intro = payload.get("is_intro", False)
            sender = payload.get("from", "unknown")

            # Skip our own intro messages
            if is_intro and sender == AGENT_ID:
                return

            dest = INBOX / filename
            archived = ARCHIVE / filename
            if not dest.exists() and not archived.exists():
                dest.write_text(content)
                msg_type = "INTRO" if is_intro else "message"
                print(f"Received {msg_type} from {sender}: {filename}")
                received.append(filename)
            else:
                print(f"Already have: {filename}")
        except json.JSONDecodeError:
            filename = f"raw-{int(time.time())}.md"
            dest = INBOX / filename
            dest.write_text(msg.payload.decode())
            print(f"Received raw: {filename}")
            received.append(filename)

    client = get_client()
    client.on_message = on_message
    client.subscribe(recv_pattern)
    print(f"Subscribed: {recv_pattern}")

    client.loop_start()
    time.sleep(2)
    client.loop_stop()
    client.disconnect()

    if not received:
        print("No new messages.")


def check_status():
    """Test MQTT connection."""
    print(f"Connecting to {BROKER}:{PORT} as {USER}...")

    try:
        client = get_client()
        client.loop_start()
        status_msg = f"LJA online {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
        result = client.publish(STATUS_TOPIC, status_msg, retain=True)
        result.wait_for_publish(timeout=5)
        client.loop_stop()
        client.disconnect()
        print("Connection OK")
        print(f"Published: {status_msg}")
    except Exception as e:
        print(f"Connection FAILED: {e}")
        sys.exit(1)


def main():
    INBOX.mkdir(exist_ok=True)
    OUTBOX.mkdir(exist_ok=True)
    ARCHIVE.mkdir(exist_ok=True)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "send":
        if len(sys.argv) > 2:
            send_message(Path(sys.argv[2]))
        else:
            send_all()
    elif cmd == "receive":
        receive_messages()
    elif cmd == "status":
        check_status()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
