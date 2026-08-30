#!/usr/bin/env bash
# The wall's front door. Everything it does lives in tools/ripple_wall.py (stdlib Python 3.9+).
#
#   open <path>          record a change to a foundational file; opens a batch if it is mapped
#   status               the open batch, plus anything still blocked on its owner
#   enumerate <path>...  dry run: every string a change to these paths must move
#   waive <key> "..."    answer a string with a written reason, or block it on its owner
#   close [label]        the fail-closed gate; refuses and names what is missing
set -eu
exec python3 "$(cd "$(dirname "$0")" && pwd)/tools/ripple_wall.py" "$@"
