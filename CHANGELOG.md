# Changelog

## Unreleased

Nothing yet.

## [1.2.0](https://github.com/eliferres/ripple-wall/releases/tag/v1.2.0) - 2026-10-02

### Added
- Added `exclude_generated` to the map: backups, caches and build output that sit inside a trigger directory no longer open a batch; a blank entry, which would exclude every file, is refused as a map error.
- Added `close --all`, which lists every string the open batch asks for with its state (moved, answered, blocked or missing), closes nothing, and exits 1 when `close` would refuse.
- Added `when` conditions on map strings: `mentions_trigger` asks a string only when its file names the changed file, and `trigger_matches` only when the change matches given paths or globs, so a directory surface stops asking every file about copies that only concern a few; an empty or malformed condition is refused as a map error.
- Added attest strings for copies that are not files, such as rules pasted into a hosted dashboard: a map entry with `"kind": "attest"` and a `where` closes only on `attest <key> "done: ..."`, a sentence of at least 40 characters, and a refused close names that command when one is missing.
- Added a `pyproject.toml` so `pipx install git+https://github.com/eliferres/ripple-wall` installs a `ripple-wall` command that reads `ripple-map.json` from the current directory, plus `--version`.

### Fixed
- Fixed a string added to the map, or repointed, while a batch was open reading as moved and letting `close` pass: `open` now records the map's hash and `close` refuses if the map changed, saying how to recover.
- Fixed a `/` inside a surface or string id letting two strings share one key, so one answer closed both: such an id is now refused, exit 2.
- Fixed a trigger that is blank or not text being accepted: a blank one matched every file beside the map, and a number crashed; both are now refused with one line on stderr, exit 2.
- Fixed a map string whose `kind`, `id`, `path`, `where` or `why` is not text (a list, a number, null, or empty) crashing with a traceback: it is now refused with one line on stderr, exit 2.
- Fixed two strings with the same id under one surface sharing a single answer, so a waiver for one closed both: the map is now refused with exit 2, naming the key.
- Fixed a corrupt or unreadable batch file reading as "no open batch", which let `close` pass: every command that reads the batch, the blocked list, or the map now exits 2 with one line on stderr naming the file and the parse error.
- Fixed usage errors exiting 1 on stdout while an unknown subcommand exited 2: wrong usage now always prints one line on stderr and exits 2, matching the exit-code table the README now carries.
- Fixed a hand-written map of the wrong shape crashing with a Python traceback: a map with no `surfaces` object, a surface missing its `triggers` or `strings`, or a string missing `id`, `path` or `why` is now refused with one line on stderr naming what is missing, exit 2.
- Fixed the tool's guidance lines naming `./ripple-wall.sh`, a file an installed user's project does not have: run from a clone they still say `./ripple-wall.sh`, and run as the installed command they say `ripple-wall`.
- Fixed the demo transcript and the terminal picture in the README, which abridged the tool's output and left out the file edits the walkthrough makes, so the picture showed results no visible command produced. Both are now generated from a real run and checked by the test suite.
- Fixed a batch file that parses but is not a batch (`{}`, `[]`, `null`, or an object missing the keys the wall writes) reading as "no open batch", and the same check for the blocked list: both now exit 2 with one line on stderr.

### Changed
- Changed the README badge row to show the license, the lowest supported Python and that there are no dependencies, beside the CI status.
- Changed the demo picture to a smaller type size, so its rows are re-rendered at the width the session actually prints.
- Changed the install section to say that an editable install reads the clone's own map wherever it runs, and how to point it elsewhere.
- Changed the README shape: the walkthrough now sits directly after Quick start as "A batch from open to close", the map section is "Writing the map", the refusals section is "What close refuses" and ends with an exit-code table, and the file tour folds into one paragraph under Quick start.

## [1.1.0](https://github.com/eliferres/ripple-wall/releases/tag/v1.1.0) - 2026-09-03

### Added
- Added a terminal demo to the README's first screen, showing open, a close refused on two unaccounted strings, and waive then close.
- Added macos-latest to the CI matrix alongside ubuntu-latest.

## [1.0.1](https://github.com/eliferres/ripple-wall/releases/tag/v1.0.1) - 2026-08-31

### Fixed
- Fixed command-line paths to resolve against the caller's working directory, with every path comparison going through realpath, so the wall engages no matter where it is invoked from.
- Fixed blocked-on-owner answers to require the same 40-character reason as any waiver.
- Fixed a mapped file that vanishes mid-batch to be refused as missing instead of counted as moved.
- Fixed the README wording to match the actual exit behavior.

### Added
- Added three regression tests, bringing the total to 16.

## [1.0.0](https://github.com/eliferres/ripple-wall/releases/tag/v1.0.0) - 2026-08-31

First public release.
