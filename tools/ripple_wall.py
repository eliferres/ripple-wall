"""The wall itself: a fail-closed batch over the strings a foundational change must move.

Stdlib only, Python 3.9+. Driven through ./ripple-wall.sh in a clone, or the ripple-wall
command once installed; both take the same subcommands. A clone uses the map at its own
root; an install uses ripple-map.json in the current directory. RIPPLE_MAP and
RIPPLE_STATE_DIR override both, which is how the tests stay hermetic.
"""

__version__ = "1.1.0"

import fnmatch
import hashlib
import json
import os
import sys
import time

CHECKOUT_MAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ripple-map.json")
# An installed module has no map beside it, so the project it guards is wherever it runs.
MAP = os.environ.get("RIPPLE_MAP") or (
    CHECKOUT_MAP if os.path.isfile(CHECKOUT_MAP) else os.path.abspath("ripple-map.json"))
STATE = os.environ.get("RIPPLE_STATE_DIR") or os.path.join(os.path.dirname(os.path.abspath(MAP)), ".ripple")
BATCH = os.path.join(STATE, "batch.json")
BLOCKED = os.path.join(STATE, "blocked.json")
RECEIPTS = os.path.join(STATE, "receipts.jsonl")

# The wrapper exports its own $0 so a clone keeps saying ./ripple-wall.sh; installed, the
# console script's own name is what a reader can actually run.
PROG = os.environ.get("RIPPLE_PROG") or os.path.basename(sys.argv[0])

WAIVER_PREFIX = "unchanged because "
BLOCKED_PREFIX = "blocked-on-owner:"
WAIVER_MIN = 40  # a reason short enough to type without thinking is not a reason


def die(message, code=1):
    print(message)
    sys.exit(code)


def refuse(message):
    """State the wall cannot trust stops it: one line on stderr, exit 2."""
    print("RIPPLE WALL: " + message, file=sys.stderr)
    sys.exit(2)


MISSING = object()  # distinguishes "no file" from a file holding null

BATCH_KEYS = ("opened", "triggers", "answers", "snapshot")


def read_json(path, fallback):
    """A missing file means nothing recorded yet. A file that is there but will not parse
    is refused: reading it as empty would let a corrupt batch close as if none were open."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return fallback
    except (OSError, ValueError) as e:
        refuse("cannot read %s (%s). Refusing to guess what it held." % (path, e))


def read_batch():
    """The batch file as the wall wrote it, or None when there is no batch.

    Well-formed JSON of the wrong shape is refused too: read as no batch, it would
    let close pass over every string the real batch was guarding."""
    batch = read_json(BATCH, MISSING)
    if batch is MISSING:
        return None
    missing = [k for k in BATCH_KEYS if not isinstance(batch, dict) or k not in batch]
    if missing:
        refuse("%s is not a batch: no %s. Refusing to read it as no batch open."
               % (BATCH, ", ".join(missing)))
    return batch


def read_blocked():
    blocked = read_json(BLOCKED, [])
    if not isinstance(blocked, list) or any(
            not isinstance(item, dict) or not {"key", "line", "ts"} <= set(item) for item in blocked):
        refuse("%s is not a list of blocked items. Refusing to read it as nothing blocked." % BLOCKED)
    return blocked


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(value, f, ensure_ascii=False, indent=1)


def log(event, **fields):
    os.makedirs(STATE, exist_ok=True)
    with open(RECEIPTS, "a") as f:
        f.write(json.dumps(dict(ts=time.strftime("%F %T"), event=event, **fields), ensure_ascii=False) + "\n")


def load_map():
    """The map, checked for the shape the whole tool reads. It is hand-written, so a
    missing key is an ordinary mistake, and guessing past it is what this tool refuses."""
    if not os.path.exists(MAP):
        refuse("no map at %s. Run from the directory holding ripple-map.json, or set RIPPLE_MAP." % MAP)
    ripple_map = read_json(MAP, None)
    bad = map_fault(ripple_map)
    if bad:
        refuse("%s is not a map: %s. Refusing to guard a setup it cannot read." % (MAP, bad))
    return ripple_map


def map_fault(ripple_map):
    """The first thing wrong with a parsed map, in the reader's words, or None."""
    if not isinstance(ripple_map, dict) or not isinstance(ripple_map.get("surfaces"), dict):
        return "no surfaces object at the top level"
    for surface_id, surface in ripple_map["surfaces"].items():
        if not isinstance(surface, dict):
            return "surface %s is not an object" % surface_id
        for key in ("triggers", "strings"):
            if not isinstance(surface.get(key), list):
                return "surface %s has no %s list" % (surface_id, key)
        for string in surface["strings"]:
            missing = [k for k in ("id", "path", "why") if not isinstance(string, dict) or k not in string]
            if missing:
                return "a string under surface %s has no %s" % (surface_id, ", ".join(missing))
    return None


def short(path):
    return os.path.relpath(path, os.path.dirname(os.path.realpath(MAP)))


def resolve(path):
    """Map paths are written relative to the map, so a clone works from any directory."""
    expanded = os.path.expanduser(path)
    base = os.path.dirname(os.path.realpath(MAP))
    return os.path.realpath(expanded if os.path.isabs(expanded) else os.path.join(base, expanded))


def resolve_user(path):
    """Paths typed on the command line resolve against the caller's cwd, like any other tool."""
    return os.path.realpath(os.path.expanduser(path))


def surfaces_for(ripple_map, path):
    target = resolve(path)
    hits = []
    for surface_id, surface in ripple_map["surfaces"].items():
        for trigger in surface["triggers"]:
            pattern = resolve(trigger).rstrip("/")
            if target == pattern or target.startswith(pattern + os.sep) or fnmatch.fnmatch(target, pattern):
                hits.append(surface_id)
                break
    return sorted(hits)


def strings_for(ripple_map, surface_ids):
    """(key, path, why) for every string attached to these surfaces, in map order."""
    out = []
    for surface_id in surface_ids:
        for string in ripple_map["surfaces"][surface_id]["strings"]:
            out.append(("%s/%s" % (surface_id, string["id"]), resolve(string["path"]), string["why"]))
    return out


def digest(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def every_mapped_file(ripple_map):
    return sorted({resolve(s["path"]) for surface in ripple_map["surfaces"].values() for s in surface["strings"]})


def active_surfaces(ripple_map, batch):
    return sorted({s for trigger in batch["triggers"] for s in surfaces_for(ripple_map, trigger)})


def cmd_open(ripple_map, argv):
    if not argv:
        die("usage: %s open <changed-path>" % PROG)
    path = resolve_user(argv[0])
    triggered = surfaces_for(ripple_map, path)
    batch = read_batch()
    if not triggered and not batch:
        print("ripple: %s is not a foundational surface — nothing to open." % short(path))
        return 0
    if not batch:
        batch = {
            "opened": time.strftime("%F %T"),
            "triggers": [path],
            "answers": {},
            # The snapshot is what "did this string move" is measured against.
            "snapshot": {p: digest(p) for p in every_mapped_file(ripple_map)},
        }
        log("open", trigger=path, surfaces=triggered)
        print("RIPPLE BATCH OPEN — %s touched (%s)." % (short(path), ", ".join(triggered)))
        print("  Every mapped string must move or carry a written reason before this batch closes.")
        print("  Next: %s close" % PROG)
    elif path not in batch["triggers"] and triggered:
        batch["triggers"].append(path)
        log("extend", trigger=path, surfaces=triggered)
        print("ripple: batch extended — %s (%s)." % (short(path), ", ".join(triggered)))
    else:
        print("ripple: batch already open.")
    write_json(BATCH, batch)
    return 0


def cmd_status(ripple_map, argv):
    batch = read_batch()
    if batch:
        surfaces = active_surfaces(ripple_map, batch)
        print("RIPPLE BATCH OPEN since %s — surfaces: %s" % (batch["opened"], ", ".join(surfaces)))
        print("  triggers: %d   answers: %d" % (len(batch["triggers"]), len(batch["answers"])))
        print("  next: %s close   (a refusal names exactly what is missing)" % PROG)
    else:
        print("ripple: no open batch.")
    blocked = read_blocked()
    if blocked:
        print("BLOCKED ON OWNER (%d) — still open, still your problem:" % len(blocked))
        for item in blocked:
            print("  %s — %s  (since %s)" % (item["key"], item["line"], item["ts"]))
    return 0


def cmd_waive(ripple_map, argv):
    if len(argv) < 2:
        die('usage: %s waive <key> "unchanged because ..."' % PROG)
    key, line = argv[0], argv[1].strip()
    if line.startswith(WAIVER_PREFIX) or line.startswith(BLOCKED_PREFIX):
        if len(line) < WAIVER_MIN:
            die("RIPPLE WALL: that answer is %d characters. Say why in at least %d — a reason nobody can read "
                "later is the same as no reason." % (len(line), WAIVER_MIN))
    else:
        die('RIPPLE WALL: a waiver must start "%s" or "%s". Refusing to close a string on a shrug.'
            % (WAIVER_PREFIX.strip(), BLOCKED_PREFIX))
    batch = read_batch()
    if not batch:
        die("RIPPLE WALL: no open batch to answer into.")
    known = {k for k, _, _ in strings_for(ripple_map, active_surfaces(ripple_map, batch))}
    if key not in known:
        die("RIPPLE WALL: %s is not a string on the open surfaces. Known: %s" % (key, ", ".join(sorted(known))))
    batch["answers"][key] = line
    write_json(BATCH, batch)
    log("waive", key=key, line=line)
    print("ripple: answer recorded for %s" % key)
    return 0


def cmd_enumerate(ripple_map, argv):
    if not argv:
        die("usage: %s enumerate <path> [path ...]" % PROG)
    surfaces = sorted({s for p in argv for s in surfaces_for(ripple_map, resolve_user(p))})
    if not surfaces:
        print("ripple: none of those paths trigger a mapped surface.")
        return 0
    print("surfaces triggered: %s" % ", ".join(surfaces))
    for key, path, why in strings_for(ripple_map, surfaces):
        print("  %s — %s (%s)" % (key, short(path), why))
    return 0


def cmd_close(ripple_map, argv):
    label = argv[0] if argv else ""
    batch = read_batch()
    if not batch:
        die("RIPPLE WALL: no open batch.")
    surfaces = active_surfaces(ripple_map, batch)
    moved, answered, blocked, missing = [], [], [], []
    for key, path, why in strings_for(ripple_map, surfaces):
        answer = batch["answers"].get(key)
        current = digest(path)
        snap = batch["snapshot"].get(path)
        if current is None and snap is not None and not answer:
            missing.append((key, short(path) + " — the file has VANISHED since the batch opened", why))
        elif current is not None and current != snap:
            moved.append(key)
        elif answer and answer.startswith(BLOCKED_PREFIX):
            blocked.append((key, answer))
        elif answer:
            answered.append((key, answer))
        else:
            missing.append((key, short(path), why))
    if missing:
        print("RIPPLE WALL: batch CANNOT close — %d mapped string(s) unaccounted for:" % len(missing))
        for key, path, why in missing:
            print("  MISSING %s — %s (%s)" % (key, path, why))
        print('Update each one, or answer it: %s waive <key> "unchanged because ..."' % PROG)
        log("close-refused", label=label, missing=[k for k, _, _ in missing])
        return 1
    os.remove(BATCH)
    log("closed", label=label, surfaces=surfaces, moved=moved,
        answered=dict(answered), blocked=dict(blocked))
    if blocked:
        pending = read_blocked()
        pending += [{"key": k, "line": line, "label": label, "ts": time.strftime("%F %T")} for k, line in blocked]
        write_json(BLOCKED, pending)
        print("RIPPLE WALL: batch closed, %d item(s) BLOCKED ON OWNER and flagged until answered:" % len(blocked))
        for key, line in blocked:
            print("  %s — %s" % (key, line))
        return 0
    print("RIPPLE WALL: batch CLOSED clean — %d moved, %d answered, across %d surface(s)."
          % (len(moved), len(answered), len(surfaces)))
    return 0


COMMANDS = {"open": cmd_open, "status": cmd_status, "waive": cmd_waive,
            "enumerate": cmd_enumerate, "close": cmd_close}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    command = argv[0] if argv else "status"
    if command == "--version":
        print("ripple-wall %s" % __version__)
        return 0
    if command not in COMMANDS:
        die("%s: unknown command %r. Try: %s" % (PROG, command, " / ".join(COMMANDS)), 2)
    return COMMANDS[command](load_map(), argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
