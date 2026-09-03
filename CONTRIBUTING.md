# Contributing

Welcome things:

- Hook or watcher recipes for harnesses that are not covered yet.
- New refusal cases, each with a test and a one-line why.
- Anything the README claims that turns out not to be true.

Ground rules: the wall stays stdlib-only and single-file, the map stays
plain JSON, and every change keeps `python -m unittest discover -s tests`
green. Tests use real files in temp directories, never mocks: a test
that only proves a function was called proves nothing about a wall.

One thing that will be declined: a way to close a batch without either
moving the string or writing a reason. Every escape hatch that has ever
been added to a wall like this became the default path within a week.
Structural proposals belong in an issue before a PR.
