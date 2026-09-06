#!/bin/bash
# rotate_logs.sh — Deterministic log rotation for Allie's VM
# Replaces the LLM-gated portion of SH5 watchdog for log management.
#
# Usage: crontab -e → 0 4 * * 0 bash ~/abbie-config/scripts/rotate_logs.sh
# Or called by SH5 watchdog as a pre-approved remediation action.

set -euo pipefail

LOG_MAX_MB=5
ARCHIVE_DAYS=14
CRON_OUTPUT_MAX_DAYS=7
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "[$TIMESTAMP] Starting log rotation..."

# ── 1. Rotate oversized JSONL logs ────────────────────────────────
ROTATED=0
for f in "$HOME"/.hermes/*.jsonl "$HOME"/.local/*.log; do
    [[ -f "$f" ]] || continue
    size_mb=$(du -m "$f" | cut -f1)
    if [[ "$size_mb" -gt "$LOG_MAX_MB" ]]; then
        mv "$f" "${f}.bak"
        touch "$f"
        ROTATED=$((ROTATED + 1))
        echo "  Rotated: $f ($size_mb MB)"
    fi
done

# ── 2. Clean stale cron outputs ──────────────────────────────────
CLEANED=0
if [[ -d "$HOME/.hermes/cron_outputs" ]]; then
    while IFS= read -r -d '' f; do
        # Don't delete state files (heartbeat_state, ops_score_latest)
        basename=$(basename "$f")
        if [[ "$basename" == *"state"* || "$basename" == *"latest"* ]]; then
            continue
        fi
        rm "$f"
        CLEANED=$((CLEANED + 1))
        echo "  Cleaned stale: $f"
    done < <(find "$HOME/.hermes/cron_outputs" -name "*.json" -mtime +$CRON_OUTPUT_MAX_DAYS -print0 2>/dev/null)
fi

# ── 3. Archive old daily logs ────────────────────────────────────
ARCHIVED=0
MEMORY_DIR="$HOME/abbie-config/memory"
ARCHIVE_DIR="$MEMORY_DIR/archive"
if [[ -d "$MEMORY_DIR" ]]; then
    mkdir -p "$ARCHIVE_DIR"
    while IFS= read -r -d '' f; do
        basename=$(basename "$f")
        # Skip archive.md itself
        [[ "$basename" == "archive.md" ]] && continue
        mv "$f" "$ARCHIVE_DIR/$basename"
        ARCHIVED=$((ARCHIVED + 1))
        echo "  Archived: $basename"
    done < <(find "$MEMORY_DIR" -maxdepth 1 -name "20*.md" -mtime +$ARCHIVE_DAYS -print0 2>/dev/null)
fi

# ── 4. SQLite VACUUM if health_data.db exists and is large ───────
VACUUMED=""
HEALTH_DB="$HOME/.hermes/health_data.db"
if [[ -f "$HEALTH_DB" ]]; then
    db_size_mb=$(du -m "$HEALTH_DB" | cut -f1)
    if [[ "$db_size_mb" -gt 30 ]]; then
        sqlite3 "$HEALTH_DB" "VACUUM;"
        new_size_mb=$(du -m "$HEALTH_DB" | cut -f1)
        VACUUMED="health_data.db: ${db_size_mb}MB → ${new_size_mb}MB"
        echo "  Vacuumed: $VACUUMED"
    fi
fi

# ── Summary ──────────────────────────────────────────────────────
echo ""
echo "[$TIMESTAMP] Log rotation complete:"
echo "  Logs rotated: $ROTATED"
echo "  Cron outputs cleaned: $CLEANED"
echo "  Daily logs archived: $ARCHIVED"
[[ -n "$VACUUMED" ]] && echo "  SQLite: $VACUUMED"
