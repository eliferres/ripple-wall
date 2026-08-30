#!/usr/bin/env bash
# OPTIONAL. Sample Claude Code PostToolUse hook: after the agent writes a file,
# tell the wall. If the file is mapped, a batch opens and the agent sees why.
#
# Fail-open on purpose: a broken hook must never block an edit. The wall itself
# is the fail-closed half, and it runs at close time.
set -u
WALL="$(cd "$(dirname "$0")/.." && pwd)/ripple-wall.sh"

payload="$(cat)"
path="$(printf '%s' "$payload" | python3 -c \
  'import json,sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))' 2>/dev/null)"

[ -n "$path" ] || exit 0
bash "$WALL" open "$path" 2>/dev/null || true
