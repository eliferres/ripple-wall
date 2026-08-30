"""The wall itself: a fail-closed batch over the strings a foundational change must move.

Stdlib only, Python 3.9+. Driven through ./ripple-wall.sh; run directly with the same
subcommands if you prefer. RIPPLE_MAP and RIPPLE_STATE_DIR override the defaults, which
is how the tests stay hermetic.
"""

import fnmatch
import hashlib
import json
import os
import sys
import time

MAP = os.environ.get("RIPPLE_MAP") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ripple-map.json")
STATE = os.environ.get("RIPPLE_STATE_DIR") or os.path.join(os.path.dirname(os.path.abspath(MAP)), ".ripple")
BATCH = os.path.join(STATE, "batch.json")
BLOCKED = os.path.join(STATE, "blocked.json")
RECEIPTS = os.path.join(STATE, "receipts.jsonl")

WAIVER_PREFIX = "unchanged because "
BLOCKED_PREFIX = "blocked-on-owner:"
WAIVER_MIN = 40  # a reason short enough to type without thinking is not a reason


def die(message, code=1):
    print(message)
    sys.exit(code)


def read_json(path, fallback):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return fallback


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(value, f, ensure_ascii=False, indent=1)


def log(event, **fields):
    os.makedirs(STATE, exist_ok=True)
    with open(RECEIPTS, "a") as f:
        f.write(json.dumps(dict(ts=time.strftime("%F %T"), event=event, **fields), ensure_ascii=False) + "\n")


def load_map():
    try:
        with open(MAP) as f:
            return json.load(f)
    except Exception as e:
        die("RIPPLE WALL: map unreadable at %s (%s). The wall will not run blind — fix the map first." % (MAP, e), 2)


def short(path):
    return os.path.relpath(path, os.path.dirname(os.path.abspath(MAP)))


def resolve(path):
    """Map paths are written relative to the map, so a clone works from any directory."""
    expanded = os.path.expanduser(path)
    base = os.path.dirname(os.path.abspath(MAP))
    return os.path.abspath(expanded if os.path.isabs(expanded) else os.path.join(base, expanded))


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
        die("usage: ripple-wall.sh open <changed-path>")
    path = resolve(argv[0])
    triggered = surfaces_for(ripple_map, path)
    batch = read_json(BATCH, None)
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
        print("  Next: ./ripple-wall.sh close")
    elif path not in batch["triggers"] and triggered:
        batch["triggers"].append(path)
        log("extend", trigger=path, surfaces=triggered)
        print("ripple: batch extended — %s (%s)." % (short(path), ", ".join(triggered)))
    else:
        print("ripple: batch already open.")
    write_json(BATCH, batch)
    return 0


def cmd_status(ripple_map, argv):
    batch = read_json(BATCH, None)
    if batch:
        surfaces = active_surfaces(ripple_map, batch)
        print("RIPPLE BATCH OPEN since %s — surfaces: %s" % (batch["opened"], ", ".join(surfaces)))
        print("  triggers: %d   answers: %d" % (len(batch["triggers"]), len(batch["answers"])))
        print("  next: ./ripple-wall.sh close   (a refusal names exactly what is missing)")
    else:
        print("ripple: no open batch.")
    blocked = read_json(BLOCKED, [])
    if blocked:
        print("BLOCKED ON OWNER (%d) — still open, still your problem:" % len(blocked))
        for item in blocked:
            print("  %s — %s  (since %s)" % (item["key"], item["line"], item["ts"]))
    return 0


def cmd_waive(ripple_map, argv):
    if len(argv) < 2:
        die('usage: ripple-wall.sh waive <key> "unchanged because ..."')
    key, line = argv[0], argv[1].strip()
    if line.startswith(WAIVER_PREFIX):
        if len(line) < WAIVER_MIN:
            die("RIPPLE WALL: that waiver is %d characters. Say why in at least %d — a reason nobody can read "
                "later is the same as no reason." % (len(line), WAIVER_MIN))
    elif not line.startswith(BLOCKED_PREFIX):
        die('RIPPLE WALL: a waiver must start "%s" or "%s". Refusing to close a string on a shrug.'
            % (WAIVER_PREFIX.strip(), BLOCKED_PREFIX))
    batch = read_json(BATCH, None)
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
        die("usage: ripple-wall.sh enumerate <path> [path ...]")
    surfaces = sorted({s for p in argv for s in surfaces_for(ripple_map, p)})
    if not surfaces:
        print("ripple: none of those paths trigger a mapped surface.")
        return 0
    print("surfaces triggered: %s" % ", ".join(surfaces))
    for key, path, why in strings_for(ripple_map, surfaces):
        print("  %s — %s (%s)" % (key, short(path), why))
    return 0


def cmd_close(ripple_map, argv):
    label = argv[0] if argv else ""
    batch = read_json(BATCH, None)
    if not batch:
        die("RIPPLE WALL: no open batch.")
    surfaces = active_surfaces(ripple_map, batch)
    moved, answered, blocked, missing = [], [], [], []
    for key, path, why in strings_for(ripple_map, surfaces):
        answer = batch["answers"].get(key)
        if digest(path) != batch["snapshot"].get(path):
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
        print('Update each one, or answer it: ./ripple-wall.sh waive <key> "unchanged because ..."')
        log("close-refused", label=label, missing=[k for k, _, _ in missing])
        return 1
    os.remove(BATCH)
    log("closed", label=label, surfaces=surfaces, moved=moved,
        answered=dict(answered), blocked=dict(blocked))
    if blocked:
        pending = read_json(BLOCKED, [])
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


def main(argv):
    command = argv[0] if argv else "status"
    if command not in COMMANDS:
        die("ripple-wall: unknown command %r. Try: %s" % (command, " / ".join(COMMANDS)), 2)
    return COMMANDS[command](load_map(), argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
