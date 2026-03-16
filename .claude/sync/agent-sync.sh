#!/bin/bash
# agent-sync.sh - Sync messages between GCA and Major Tom
#
# Run at start/end of session to:
# 1. Deliver outbox messages to other agent's inbox
# 2. Receive messages from other agent's outbox
# 3. Sync archives (append-only)
#
# Usage: ./agent-sync.sh [--dry-run]

set -euo pipefail

# === CONFIGURATION ===
# Adjust these paths for your setup

# GCA's sync directory (ha-addons repo on dev machine)
GCA_SYNC="${GCA_SYNC:-/home/mmariani/Projects/ha-addons/.claude/sync}"

# Major Tom's sync directory (ha-config repo)
# Option 1: Local clone of ha-config
MT_SYNC="${MT_SYNC:-/home/mmariani/Projects/ha-config/.claude/sync}"
# Option 2: If ha-config is mounted from HA
# MT_SYNC="${MT_SYNC:-/mnt/ha-config/.claude/sync}"

# === END CONFIGURATION ===

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "=== DRY RUN MODE ==="
fi

log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

copy_if_new() {
    local src="$1"
    local dest_dir="$2"
    local filename
    filename=$(basename "$src")
    local dest="$dest_dir/$filename"

    if [[ ! -f "$dest" ]]; then
        if $DRY_RUN; then
            log "WOULD COPY: $src -> $dest"
        else
            cp "$src" "$dest"
            log "COPIED: $filename -> $dest_dir/"
        fi
        return 0
    fi
    return 1
}

sync_directory() {
    local src_dir="$1"
    local dest_dir="$2"
    local direction="$3"
    local count=0

    if [[ ! -d "$src_dir" ]]; then
        log "SKIP: $src_dir does not exist"
        return
    fi

    mkdir -p "$dest_dir"

    for f in "$src_dir"/*.md 2>/dev/null; do
        [[ -f "$f" ]] || continue
        if copy_if_new "$f" "$dest_dir"; then
            ((count++)) || true
        fi
    done

    if [[ $count -eq 0 ]]; then
        log "$direction: No new files"
    else
        log "$direction: $count file(s) synced"
    fi
}

echo ""
echo "========================================"
echo "  Agent Sync - $(date '+%Y-%m-%d %H:%M')"
echo "========================================"
echo ""
echo "GCA sync:  $GCA_SYNC"
echo "MT sync:   $MT_SYNC"
echo ""

# Verify directories exist
if [[ ! -d "$GCA_SYNC" ]]; then
    echo "ERROR: GCA sync directory not found: $GCA_SYNC"
    exit 1
fi

if [[ ! -d "$MT_SYNC" ]]; then
    echo "WARNING: MT sync directory not found: $MT_SYNC"
    echo "Creating directory structure..."
    if ! $DRY_RUN; then
        mkdir -p "$MT_SYNC"/{inbox,outbox,archive}
    fi
fi

echo "--- Delivering Messages ---"

# GCA outbox -> MT inbox
sync_directory "$GCA_SYNC/outbox" "$MT_SYNC/inbox" "GCA -> MT"

# MT outbox -> GCA inbox
sync_directory "$MT_SYNC/outbox" "$GCA_SYNC/inbox" "MT -> GCA"

echo ""
echo "--- Syncing Archives ---"

# Sync archives both ways (append-only)
sync_directory "$GCA_SYNC/archive" "$MT_SYNC/archive" "GCA archive -> MT"
sync_directory "$MT_SYNC/archive" "$GCA_SYNC/archive" "MT archive -> GCA"

echo ""
echo "--- Inbox Status ---"

gca_inbox_count=$(find "$GCA_SYNC/inbox" -name "*.md" 2>/dev/null | wc -l)
mt_inbox_count=$(find "$MT_SYNC/inbox" -name "*.md" 2>/dev/null | wc -l)

echo "GCA inbox: $gca_inbox_count message(s)"
echo "MT inbox:  $mt_inbox_count message(s)"

if [[ $gca_inbox_count -gt 0 ]]; then
    echo ""
    echo "GCA has unread messages:"
    ls -1 "$GCA_SYNC/inbox/"*.md 2>/dev/null | xargs -I {} basename {} | sed 's/^/  - /'
fi

echo ""
echo "========================================"
echo "  Sync complete"
echo "========================================"
