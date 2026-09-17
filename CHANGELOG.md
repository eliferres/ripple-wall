# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- Added a `pyproject.toml` so `pipx install git+https://github.com/eliferres/ripple-wall` installs a `ripple-wall` command that reads `ripple-map.json` from the current directory, plus `--version`.

### Fixed
- Fixed a corrupt or unreadable batch file reading as "no open batch", which let `close` pass: every command that reads the batch, the blocked list, or the map now exits 2 with one line on stderr naming the file and the parse error.
- Fixed a batch file that parses but is not a batch (`{}`, `[]`, `null`, or an object missing the keys the wall writes) reading as "no open batch", and the same check for the blocked list: both now exit 2 with one line on stderr.

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
