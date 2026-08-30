# Auto-opening a batch (optional)

The wall works fine run by hand. Wiring it to your editor or agent only
changes *when* the batch opens: at the moment of the edit, instead of
whenever you remember. Nothing here is required.

Both examples call the same thing: `./ripple-wall.sh open <path>`.

## Claude Code

`ripple-open.sh` in this folder is a ready PostToolUse hook. Point your
`settings.json` at it:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{ "type": "command", "command": "/abs/path/to/hooks/ripple-open.sh" }]
      }
    ]
  }
}
```

The hook reads the tool payload on stdin, pulls out the file path, and
hands it to the wall. Unmapped paths are a no-op.

## Any file watcher

```bash
# entr, fswatch, watchexec — same idea
find . -type f | entr -p ./ripple-wall.sh open /_
```

## Why the hook is fail-open and the wall is fail-closed

A hook that errors mid-edit teaches people to disable it, and then the
wall guards nothing. So the hook swallows its own failures: the worst
case is a batch that opens late. The refusal that actually protects you
lives in `close`, which runs when you decide you are done — and that one
never fails open.
