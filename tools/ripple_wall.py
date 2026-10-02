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
ATTEST_PREFIX = "done: "
WAIVER_MIN = 40  # a reason short enough to type without thinking is not a reason


def die(message, code=1):
    print(message)
    sys.exit(code)


def refuse(message):
    """A wall that cannot run says why in one line on stderr and exits 2: wrong usage,
    or state it cannot trust. Exit 1 is reserved for a refusal you can answer."""
    print(message, file=sys.stderr)
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
        refuse("RIPPLE WALL: cannot read %s (%s). Refusing to guess what it held." % (path, e))


def read_batch():
    """The batch file as the wall wrote it, or None when there is no batch.

    Well-formed JSON of the wrong shape is refused too: read as no batch, it would
    let close pass over every string the real batch was guarding."""
    batch = read_json(BATCH, MISSING)
    if batch is MISSING:
        return None
    missing = [k for k in BATCH_KEYS if not isinstance(batch, dict) or k not in batch]
    if missing:
        refuse("RIPPLE WALL: %s is not a batch: no %s. Refusing to read it as no batch open."
               % (BATCH, ", ".join(missing)))
    return batch


def read_blocked():
    blocked = read_json(BLOCKED, [])
    if not isinstance(blocked, list) or any(
            not isinstance(item, dict) or not {"key", "line", "ts"} <= set(item) for item in blocked):
        refuse("RIPPLE WALL: %s is not a list of blocked items. Refusing to read it as nothing blocked." % BLOCKED)
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
        refuse("RIPPLE WALL: no map at %s. Run from the directory holding ripple-map.json, or set RIPPLE_MAP." % MAP)
    ripple_map = read_json(MAP, None)
    bad = map_fault(ripple_map)
    if bad:
        refuse("RIPPLE WALL: %s is not a map: %s. Refusing to guard a setup it cannot read." % (MAP, bad))
    return ripple_map


# A file string closes when its file changes. An attest string has no file the wall can hash
# (a hosted dashboard, a setting in someone else's tool), so it names where the copy lives
# and closes only on a written "done: ..." from whoever updated it.
STRING_FIELDS = {"file": ("id", "path", "why"), "attest": ("id", "where", "why")}


def map_fault(ripple_map):
    """The first thing wrong with a parsed map, in the reader's words, or None."""
    if not isinstance(ripple_map, dict) or not isinstance(ripple_map.get("surfaces"), dict):
        return "no surfaces object at the top level"
    excluded = ripple_map.get("exclude_generated", [])
    if not isinstance(excluded, list) or not all(isinstance(p, str) for p in excluded):
        return "exclude_generated must be a list of paths or globs"
    for surface_id, surface in ripple_map["surfaces"].items():
        if not isinstance(surface, dict):
            return "surface %s is not an object" % surface_id
        for key in ("triggers", "strings"):
            if not isinstance(surface.get(key), list):
                return "surface %s has no %s list" % (surface_id, key)
        seen = set()
        for string in surface["strings"]:
            kind = string.get("kind", "file") if isinstance(string, dict) else "file"
            if not isinstance(kind, str) or kind not in STRING_FIELDS:
                return "a string under surface %s has kind %r; known kinds: %s" % (
                    surface_id, kind, ", ".join(STRING_FIELDS))
            missing = [k for k in STRING_FIELDS[kind] if not isinstance(string, dict) or k not in string]
            if missing:
                return "a string under surface %s has no %s" % (surface_id, ", ".join(missing))
            # Every field is text the wall joins into keys, paths and messages.
            wrong = [k for k in STRING_FIELDS[kind] if not isinstance(string[k], str) or not string[k]]
            if wrong:
                return "a string under surface %s has a %s that is not non-empty text" % (
                    surface_id, ", ".join(wrong))
            # Two strings under one key share one answer, so an attest meant for one would close both.
            if string["id"] in seen:
                return "two strings share the key %s/%s" % (surface_id, string["id"])
            seen.add(string["id"])
            if "when" in string:
                bad = when_fault(string["when"], kind)
                if bad:
                    return "string %s/%s: %s" % (surface_id, string["id"], bad)
    return None


def when_fault(when, kind):
    """What is wrong with a string's "when" condition, or None. A condition the wall
    misreads would silently stop asking a question, so anything unexpected is refused."""
    if not isinstance(when, dict) or not when or set(when) - {"trigger_matches", "mentions_trigger"}:
        return 'when must be an object holding trigger_matches and/or mentions_trigger'
    # An empty list matches no trigger, which would switch the string off for good.
    if "trigger_matches" in when and not (
            isinstance(when["trigger_matches"], list) and when["trigger_matches"]
            and all(isinstance(p, str) and p for p in when["trigger_matches"])):
        return "when.trigger_matches must be a non-empty list of paths or globs"
    if "mentions_trigger" in when:
        if when["mentions_trigger"] is not True:
            return "when.mentions_trigger must be true"
        if kind != "file":
            return "when.mentions_trigger needs a file to read; an attest string has none"
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


def matches(path, patterns):
    """True when the path is one of these map patterns: an exact path, a directory, or a glob."""
    target = resolve(path)
    for pattern in patterns:
        pattern = resolve(pattern).rstrip("/")
        if target == pattern or target.startswith(pattern + os.sep) or fnmatch.fnmatch(target, pattern):
            return True
    return False


def generated(ripple_map, path):
    """Files a tool rewrites on its own schedule (backups, caches, build output) sit inside
    trigger directories but are nobody's edit; opening a batch on them is pure noise."""
    return matches(path, ripple_map.get("exclude_generated", []))


def surfaces_for(ripple_map, path):
    if generated(ripple_map, path):
        return []
    return sorted(sid for sid, surface in ripple_map["surfaces"].items() if matches(path, surface["triggers"]))


def asked(string, triggers):
    """Whether a string's "when" condition holds for the paths that opened its surface.

    A hooks/ directory surface asks every string of every hook, and most of those questions
    do not apply: a settings file wires a few hooks, not all of them. trigger_matches narrows
    a string to some triggers; mentions_trigger asks it only when its file names a trigger
    by file name. A file that cannot be read is asked anyway, so a deleted copy still fails."""
    when = string.get("when") or {}
    if "trigger_matches" in when and not any(matches(t, when["trigger_matches"]) for t in triggers):
        return False
    if when.get("mentions_trigger"):
        try:
            with open(resolve(string["path"]), encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            return True
        return any(os.path.basename(t) in text for t in triggers)
    return True


def strings_for(ripple_map, triggers):
    """(key, kind, target, why) for every string these paths ask for, in map order.
    The target is the resolved path of a file string, or the where text of an attest string."""
    out = []
    for surface_id in sorted({s for t in triggers for s in surfaces_for(ripple_map, t)}):
        mine = [t for t in triggers if surface_id in surfaces_for(ripple_map, t)]
        for string in ripple_map["surfaces"][surface_id]["strings"]:
            if not asked(string, mine):
                continue
            kind = string.get("kind", "file")
            target = string["where"] if kind == "attest" else resolve(string["path"])
            out.append(("%s/%s" % (surface_id, string["id"]), kind, target, string["why"]))
    return out


def shown(kind, target):
    return "attest: " + target if kind == "attest" else short(target)


def digest(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def every_mapped_file(ripple_map):
    return sorted({resolve(s["path"]) for surface in ripple_map["surfaces"].values()
                   for s in surface["strings"] if s.get("kind", "file") == "file"})


def active_surfaces(ripple_map, batch):
    return sorted({s for trigger in batch["triggers"] for s in surfaces_for(ripple_map, trigger)})


def cmd_open(ripple_map, argv):
    if not argv:
        refuse("usage: %s open <changed-path>" % PROG)
    path = resolve_user(argv[0])
    triggered = surfaces_for(ripple_map, path)
    batch = read_batch()
    if not triggered and not batch:
        if generated(ripple_map, path):
            print("ripple: %s is generated (exclude_generated) — nothing to open." % short(path))
        else:
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
        refuse('usage: %s waive <key> "unchanged because ..."' % PROG)
    key, line = argv[0], argv[1].strip()
    if line.startswith(WAIVER_PREFIX) or line.startswith(BLOCKED_PREFIX):
        if len(line) < WAIVER_MIN:
            die("RIPPLE WALL: that answer is %d characters. Say why in at least %d — a reason nobody can read "
                "later is the same as no reason." % (len(line), WAIVER_MIN))
    else:
        die('RIPPLE WALL: a waiver must start "%s" or "%s". Refusing to close a string on a shrug.'
            % (WAIVER_PREFIX.strip(), BLOCKED_PREFIX))
    record_answer(ripple_map, key, line, "waive")
    return 0


def cmd_attest(ripple_map, argv):
    if len(argv) < 2:
        refuse('usage: %s attest <key> "done: ..."' % PROG)
    key, line = argv[0], argv[1].strip()
    if not line.startswith(ATTEST_PREFIX):
        die('RIPPLE WALL: an attest must start "%s" and say what was done and where.' % ATTEST_PREFIX.strip())
    if len(line) < WAIVER_MIN:
        die("RIPPLE WALL: that attest is %d characters. Say what was done in at least %d." % (len(line), WAIVER_MIN))
    record_answer(ripple_map, key, line, "attest")
    return 0


def record_answer(ripple_map, key, line, event):
    """Write an answer into the open batch, refusing a key close would never read."""
    batch = read_batch()
    if not batch:
        die("RIPPLE WALL: no open batch to answer into.")
    kinds = {k: kind for k, kind, _, _ in strings_for(ripple_map, batch["triggers"])}
    if key not in kinds:
        die("RIPPLE WALL: %s is not a string on the open surfaces. Known: %s" % (key, ", ".join(sorted(kinds))))
    # "done:" on a file the wall can hash would be a claim it can check and the file contradicts.
    if event == "attest" and kinds[key] != "attest":
        die("RIPPLE WALL: %s is a file string: it closes when its file changes, or with waive." % key)
    batch["answers"][key] = line
    write_json(BATCH, batch)
    log(event, key=key, line=line)
    print("ripple: answer recorded for %s" % key)


def cmd_enumerate(ripple_map, argv):
    if not argv:
        refuse("usage: %s enumerate <path> [path ...]" % PROG)
    paths = [resolve_user(p) for p in argv]
    surfaces = sorted({s for p in paths for s in surfaces_for(ripple_map, p)})
    if not surfaces:
        print("ripple: none of those paths trigger a mapped surface.")
        return 0
    print("surfaces triggered: %s" % ", ".join(surfaces))
    for key, kind, target, why in strings_for(ripple_map, paths):
        print("  %s — %s (%s)" % (key, shown(kind, target), why))
    return 0


def string_states(ripple_map, batch):
    """(key, state, detail) for every string the open batch asks for, where state is moved,
    answered, blocked or MISSING. close and close --all read this one verdict, so the listing
    can never disagree with the close it previews."""
    states = []
    for key, kind, path, why in strings_for(ripple_map, batch["triggers"]):
        answer = batch["answers"].get(key)
        if kind == "file":
            current = digest(path)
            snap = batch["snapshot"].get(path)
            if current is None and snap is not None and not answer:
                states.append((key, "MISSING", "%s — the file has VANISHED since the batch opened (%s)"
                               % (short(path), why)))
                continue
            if current is not None and current != snap:
                states.append((key, "moved", short(path)))
                continue
        if answer and answer.startswith(BLOCKED_PREFIX):
            states.append((key, "blocked", answer))
        elif answer:
            states.append((key, "answered", answer))
        elif kind == "attest":
            states.append((key, "MISSING", "needs an attest: %s (%s)" % (path, why)))
        else:
            states.append((key, "MISSING", "%s (%s)" % (short(path), why)))
    return states


def cmd_close(ripple_map, argv):
    listing = "--all" in argv
    rest = [a for a in argv if a != "--all"]
    label = rest[0] if rest else ""
    batch = read_batch()
    if not batch:
        die("RIPPLE WALL: no open batch.")
    surfaces = active_surfaces(ripple_map, batch)
    states = string_states(ripple_map, batch)
    if listing:
        return list_states(states, surfaces)
    moved = [k for k, state, _ in states if state == "moved"]
    answered = [(k, d) for k, state, d in states if state == "answered"]
    blocked = [(k, d) for k, state, d in states if state == "blocked"]
    missing = [(k, d) for k, state, d in states if state == "MISSING"]
    if missing:
        print("RIPPLE WALL: batch CANNOT close — %d mapped string(s) unaccounted for:" % len(missing))
        for key, detail in missing:
            print("  MISSING %s — %s" % (key, detail))
        print('Update each one, or answer it: %s waive <key> "unchanged because ..."' % PROG)
        log("close-refused", label=label, missing=[k for k, _ in missing])
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



def list_states(states, surfaces):
    """close --all: every string and where it stands, so the whole batch can be read at
    once instead of one refusal at a time. Writes nothing; exits as close would."""
    print("RIPPLE BATCH LISTING — %d mapped string(s) across %d surface(s): %s. This lists; it closes nothing."
          % (len(states), len(surfaces), ", ".join(surfaces)))
    for key, state, detail in states:
        print("  %-9s %s — %s" % (state, key, detail))
    missing = sum(1 for _, state, _ in states if state == "MISSING")
    if missing:
        print("%d MISSING: close would refuse." % missing)
        return 1
    print("Nothing missing: close would pass.")
    return 0


COMMANDS = {"open": cmd_open, "status": cmd_status, "waive": cmd_waive, "attest": cmd_attest,
            "enumerate": cmd_enumerate, "close": cmd_close}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    command = argv[0] if argv else "status"
    if command == "--version":
        print("ripple-wall %s" % __version__)
        return 0
    if command not in COMMANDS:
        refuse("%s: unknown command %r. Try: %s" % (PROG, command, " / ".join(COMMANDS)))
    return COMMANDS[command](load_map(), argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
