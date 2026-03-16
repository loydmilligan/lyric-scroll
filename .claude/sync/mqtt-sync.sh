#!/bin/bash
# mqtt-sync.sh - MQTT-based agent sync for GCA
#
# Usage:
#   ./mqtt-sync.sh send <file>     Send a message from outbox
#   ./mqtt-sync.sh receive         Receive messages to inbox
#   ./mqtt-sync.sh status          Check connection status
#
# Requires: SSH access to pi, mosquitto container running

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTBOX="$SCRIPT_DIR/outbox"
INBOX="$SCRIPT_DIR/inbox"
ARCHIVE="$SCRIPT_DIR/archive"

# MQTT config
BROKER="localhost"  # localhost from inside container
MQTT_USER="gca"
MQTT_PASS="gca-agent-2026"

# Topics
SEND_TOPIC="agent-sync/gca-to-major-tom/messages"
RECV_TOPIC="agent-sync/major-tom-to-gca/messages"

# SSH to pi and run mosquitto command inside container
mqtt_cmd() {
    ssh pi "docker exec mosquitto $*"
}

send_message() {
    local file="$1"

    if [[ ! -f "$file" ]]; then
        echo "ERROR: File not found: $file"
        exit 1
    fi

    local filename
    filename=$(basename "$file")
    local content
    content=$(cat "$file")

    # Convert markdown to JSON payload
    local json_payload
    json_payload=$(cat <<EOF
{
  "filename": "$filename",
  "content": $(echo "$content" | jq -Rs .)
}
EOF
)

    echo "Sending: $filename"
    echo "$json_payload" | ssh pi "docker exec -i mosquitto mosquitto_pub \
        -h $BROKER -p 1883 \
        -u $MQTT_USER -P $MQTT_PASS \
        -t '$SEND_TOPIC' \
        -r \
        -s"

    echo "Sent and retained on topic: $SEND_TOPIC"

    # Move to archive
    mv "$file" "$ARCHIVE/"
    echo "Archived: $filename"
}

receive_messages() {
    echo "Checking for messages on: $RECV_TOPIC"

    # Subscribe with timeout, get retained message
    local msg
    msg=$(ssh pi "timeout 3 docker exec mosquitto mosquitto_sub \
        -h $BROKER -p 1883 \
        -u $MQTT_USER -P $MQTT_PASS \
        -t '$RECV_TOPIC' \
        -C 1 \
        --retained-only 2>/dev/null" || echo "")

    if [[ -z "$msg" ]]; then
        echo "No messages waiting."
        return
    fi

    # Parse JSON and save to inbox
    local filename
    filename=$(echo "$msg" | jq -r '.filename // empty')
    local content
    content=$(echo "$msg" | jq -r '.content // empty')

    if [[ -n "$filename" && -n "$content" ]]; then
        local dest="$INBOX/$filename"
        if [[ ! -f "$dest" ]]; then
            echo "$content" > "$dest"
            echo "Received: $filename"
        else
            echo "Already have: $filename"
        fi
    else
        echo "Received raw message (not in expected format):"
        echo "$msg"
    fi
}

check_status() {
    echo "Testing MQTT connection..."

    local test_topic="agent-sync/gca/status"
    local test_msg="GCA online $(date -Iseconds)"

    if ssh pi "docker exec mosquitto mosquitto_pub \
        -h $BROKER -p 1883 \
        -u $MQTT_USER -P $MQTT_PASS \
        -t '$test_topic' \
        -m '$test_msg'" 2>/dev/null; then
        echo "Connection OK"
        echo "Published status: $test_msg"
    else
        echo "Connection FAILED"
        exit 1
    fi
}

send_all_outbox() {
    echo "Sending all messages in outbox..."
    local count=0

    for f in "$OUTBOX"/*.md 2>/dev/null; do
        [[ -f "$f" ]] || continue
        send_message "$f"
        ((count++)) || true
    done

    if [[ $count -eq 0 ]]; then
        echo "Outbox is empty."
    else
        echo "Sent $count message(s)."
    fi
}

# Main
case "${1:-}" in
    send)
        if [[ -n "${2:-}" ]]; then
            send_message "$2"
        else
            send_all_outbox
        fi
        ;;
    receive)
        receive_messages
        ;;
    status)
        check_status
        ;;
    *)
        echo "Usage: $0 {send [file]|receive|status}"
        echo ""
        echo "Commands:"
        echo "  send [file]  Send specific file or all files in outbox"
        echo "  receive      Check for and download new messages"
        echo "  status       Test MQTT connection"
        exit 1
        ;;
esac
