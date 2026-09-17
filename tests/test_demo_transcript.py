"""The demo receipt: demo/transcript.json is what the walkthrough really prints.

Every entry is run with bash inside a throwaway copy of the repo, in order, so the
recorded output and exit codes cannot drift from the tool. demo/terminal.svg is checked
against the same transcript, row by row, so the picture cannot show a line nobody ran.

Regenerate after a real behavior change: UPDATE_DEMO_TRANSCRIPT=1 python -m unittest
discover -s tests   then re-render the picture.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSCRIPT = os.path.join(REPO, "demo", "transcript.json")
PICTURE = os.path.join(REPO, "demo", "terminal.svg")
SVG_NS = {"svg": "http://www.w3.org/2000/svg"}
FIRST_CONTENT_Y = 80  # rows above this are the window chrome, not session text
ELLIPSIS = "…"
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
SKIP = shutil.ignore_patterns(".git", "__pycache__", ".ripple", "*.pyc")


def run_walkthrough(commands):
    """Run each command line with bash in a fresh copy of the repo; return (out, status)."""
    root = tempfile.mkdtemp(prefix="ripple-receipt-")
    try:
        copy = os.path.join(root, "checkout")
        shutil.copytree(REPO, copy, ignore=SKIP)
        results = []
        for cmd in commands:
            done = subprocess.run(["bash", "-c", cmd], cwd=copy, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            results.append((stable(done.stdout, copy), done.returncode))
        return results
    finally:
        shutil.rmtree(root, True)


def stable(out, copy):
    """Strip what differs between machines: the copy's path, given and resolved, and clock times."""
    for path in (os.path.realpath(copy), copy):
        out = out.replace(path, "/path/to/checkout")
    return TIMESTAMP.sub("2026-09-03 12:00:00", out.rstrip("\n"))


def picture_rows():
    """(kind, text) for every session row of the SVG, kind being prompt, cont or out."""
    rows = []
    for text_el in ET.parse(PICTURE).getroot().findall("svg:text", SVG_NS):
        y = text_el.get("y")
        if y is None or int(y) < FIRST_CONTENT_Y:
            continue
        tspans = text_el.findall("svg:tspan", SVG_NS)
        if tspans:
            rows.append(("prompt", tspans[-1].text or ""))
        elif text_el.get("class") == "cmd":
            rows.append(("cont", (text_el.text or "")[4:]))
        else:
            rows.append(("out", text_el.text or ""))
    return rows


def untrimmed(shown, real):
    """True if the row is the real line, or the real line cut short with one ellipsis."""
    if shown == real:
        return True
    head = shown[: -len(ELLIPSIS)]
    return shown.endswith(ELLIPSIS) and shown.count(ELLIPSIS) == 1 and real.startswith(head)


class TranscriptTest(unittest.TestCase):
    def setUp(self):
        with open(TRANSCRIPT) as f:
            self.transcript = json.load(f)

    def test_every_recorded_command_still_prints_what_it_recorded(self):
        results = run_walkthrough([entry["cmd"] for entry in self.transcript])
        if os.environ.get("UPDATE_DEMO_TRANSCRIPT"):
            fresh = [{"cmd": entry["cmd"], "out": out, "status": status}
                     for entry, (out, status) in zip(self.transcript, results)]
            with open(TRANSCRIPT, "w") as f:
                json.dump(fresh, f, ensure_ascii=False, indent=2)
                f.write("\n")
            self.skipTest("demo/transcript.json regenerated from a real run")
        for entry, (out, status) in zip(self.transcript, results):
            self.assertEqual(entry["out"], out, "output of: %s" % entry["cmd"])
            self.assertEqual(entry["status"], status, "exit code of: %s" % entry["cmd"])


class PictureTest(unittest.TestCase):
    """Every row of demo/terminal.svg traces back to the transcript, in order."""

    def setUp(self):
        with open(TRANSCRIPT) as f:
            self.transcript = json.load(f)

    def sessions(self):
        """Group the picture rows into one (cmd chunks, output rows) block per command."""
        blocks = []
        for kind, text in picture_rows():
            if kind == "prompt":
                blocks.append(([text], []))
            else:
                self.assertTrue(blocks, "the picture starts with output, before any command")
                blocks[-1][0 if kind == "cont" else 1].append(text)
        return blocks

    def test_every_picture_row_comes_from_the_transcript(self):
        blocks = self.sessions()
        self.assertEqual(len(self.transcript), len(blocks),
                         "the picture shows %d commands, the transcript records %d"
                         % (len(blocks), len(self.transcript)))
        for entry, (chunks, shown) in zip(self.transcript, blocks):
            rejoined = " ".join(c[:-2] if c.endswith(" \\") else c for c in chunks)
            self.assertEqual(entry["cmd"], rejoined, "command row does not rebuild its cmd")
            real_lines = [l for l in entry["out"].splitlines() if l.strip()]
            self.assertLessEqual(len(shown), len(real_lines), "extra output rows under: %s" % entry["cmd"])
            for row, real in zip(shown, real_lines):
                self.assertTrue(untrimmed(row, real),
                                "picture row %r is not the start of real line %r" % (row, real))


if __name__ == "__main__":
    unittest.main()
