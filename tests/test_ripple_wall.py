"""Real files, real subprocess calls, no mocks.

Every case runs the shipped ripple-wall.sh against a throwaway setup in a temp
directory, so a passing suite means the tool works, not that it was called.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WALL = os.path.join(REPO, "ripple-wall.sh")

FIXTURE_MAP = {
    "version": 1,
    "surfaces": {
        "prompt": {
            "triggers": ["prompts/system.md"],
            "strings": [
                {"id": "docs", "path": "docs/agents.md", "why": "the docs repeat the rules"},
                {"id": "planner", "path": "agents/planner.yaml", "why": "the planner pins the rules"},
            ],
        },
        "roster": {
            "triggers": ["config/roster.json"],
            "strings": [{"id": "ci", "path": "ci/models.yml", "why": "CI names each model"}],
        },
    },
}

FIXTURE_FILES = {
    "prompts/system.md": "- read first\n",
    "docs/agents.md": "- read first\n",
    "agents/planner.yaml": "rules:\n  - read first\n",
    "config/roster.json": '{"models": ["mini"]}\n',
    "ci/models.yml": "matrix:\n  - mini\n",
}

GOOD_WAIVER = "unchanged because the planner never reads that rule"


class WallTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ripple-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        for name, body in FIXTURE_FILES.items():
            path = os.path.join(self.dir, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(body)
        with open(os.path.join(self.dir, "map.json"), "w") as f:
            json.dump(FIXTURE_MAP, f)

    def wall(self, *args):
        env = dict(os.environ, RIPPLE_MAP=os.path.join(self.dir, "map.json"))
        return subprocess.run(["bash", WALL] + list(args), cwd=self.dir, env=env,
                              capture_output=True, text=True)

    def append(self, name, text):
        with open(os.path.join(self.dir, name), "a") as f:
            f.write(text)

    def test_enumerate_lists_exactly_the_mapped_strings(self):
        out = self.wall("enumerate", "prompts/system.md").stdout
        self.assertIn("prompt/docs", out)
        self.assertIn("prompt/planner", out)
        self.assertNotIn("roster/ci", out)

    def test_enumerate_says_so_when_a_path_is_not_mapped(self):
        out = self.wall("enumerate", "docs/agents.md").stdout
        self.assertIn("none of those paths", out)

    def test_untriggered_path_opens_nothing(self):
        self.wall("open", "docs/agents.md")
        self.assertIn("no open batch", self.wall("status").stdout)

    def test_close_refuses_and_names_every_missing_string(self):
        self.append("prompts/system.md", "- cite files\n")
        self.wall("open", "prompts/system.md")
        result = self.wall("close")
        self.assertEqual(1, result.returncode)
        self.assertIn("MISSING prompt/docs", result.stdout)
        self.assertIn("MISSING prompt/planner", result.stdout)

    def test_close_refuses_until_the_last_string_moves(self):
        self.append("prompts/system.md", "- cite files\n")
        self.wall("open", "prompts/system.md")
        self.append("docs/agents.md", "- cite files\n")
        first = self.wall("close")
        self.assertEqual(1, first.returncode)
        self.assertNotIn("prompt/docs", first.stdout)
        self.append("agents/planner.yaml", "  - cite files\n")
        second = self.wall("close")
        self.assertEqual(0, second.returncode)
        self.assertIn("CLOSED clean", second.stdout)

    def test_short_waiver_is_refused(self):
        self.append("prompts/system.md", "- cite files\n")
        self.wall("open", "prompts/system.md")
        result = self.wall("waive", "prompt/planner", "unchanged because reasons")
        self.assertEqual(1, result.returncode)
        self.assertIn("at least", result.stdout)

    def test_waiver_without_the_prefix_is_refused(self):
        self.append("prompts/system.md", "- cite files\n")
        self.wall("open", "prompts/system.md")
        result = self.wall("waive", "prompt/planner", "not relevant, skipping this one for now")
        self.assertEqual(1, result.returncode)
        self.assertIn("must start", result.stdout)

    def test_waiver_on_an_unmapped_key_is_refused(self):
        self.append("prompts/system.md", "- cite files\n")
        self.wall("open", "prompts/system.md")
        result = self.wall("waive", "prompt/nonexistent", GOOD_WAIVER)
        self.assertEqual(1, result.returncode)
        self.assertIn("not a string on the open surfaces", result.stdout)

    def test_written_waiver_closes_the_batch(self):
        self.append("prompts/system.md", "- cite files\n")
        self.wall("open", "prompts/system.md")
        self.append("docs/agents.md", "- cite files\n")
        self.wall("waive", "prompt/planner", GOOD_WAIVER)
        result = self.wall("close")
        self.assertEqual(0, result.returncode)
        self.assertIn("1 moved, 1 answered", result.stdout)

    def test_blocked_on_owner_stays_flagged_after_the_batch_closes(self):
        self.append("prompts/system.md", "- cite files\n")
        self.wall("open", "prompts/system.md")
        self.append("docs/agents.md", "- cite files\n")
        self.wall("waive", "prompt/planner", "blocked-on-owner: only the owner can reword the rule")
        closed = self.wall("close")
        self.assertEqual(0, closed.returncode)
        self.assertIn("BLOCKED ON OWNER", closed.stdout)
        status = self.wall("status").stdout
        self.assertIn("no open batch", status)
        self.assertIn("prompt/planner", status)

    def test_two_triggers_in_one_batch_require_both_surfaces(self):
        self.append("prompts/system.md", "- cite files\n")
        self.append("config/roster.json", "\n")
        self.wall("open", "prompts/system.md")
        self.wall("open", "config/roster.json")
        missing = self.wall("close").stdout
        self.assertIn("MISSING prompt/docs", missing)
        self.assertIn("MISSING roster/ci", missing)

    def test_close_without_a_batch_is_an_error(self):
        result = self.wall("close")
        self.assertEqual(1, result.returncode)
        self.assertIn("no open batch", result.stdout)


class ShippedWalkthroughTest(unittest.TestCase):
    """The README walkthrough, run against a copy of the shipped demo setup."""

    RULE = "- Name the owner of every file you change.\n"

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ripple-demo-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        shutil.copytree(os.path.join(REPO, "demo"), os.path.join(self.dir, "demo"))
        shutil.copy(os.path.join(REPO, "ripple-map.json"), self.dir)

    def wall(self, *args):
        env = dict(os.environ, RIPPLE_MAP=os.path.join(self.dir, "ripple-map.json"))
        return subprocess.run(["bash", WALL] + list(args), cwd=self.dir, env=env,
                              capture_output=True, text=True)

    def append(self, name, text):
        with open(os.path.join(self.dir, name), "a") as f:
            f.write(text)

    def test_walkthrough(self):
        self.append("demo/prompts/system-prompt.md", self.RULE)
        self.assertIn("RIPPLE BATCH OPEN", self.wall("open", "demo/prompts/system-prompt.md").stdout)
        self.append("demo/docs/agents.md", self.RULE)
        self.append("demo/agents/planner.yaml", "  " + self.RULE)
        refused = self.wall("close")
        self.assertEqual(1, refused.returncode)
        self.assertIn("MISSING system-prompt/readme-rules", refused.stdout)
        self.assertIn("MISSING system-prompt/reviewer-config", refused.stdout)
        self.append("demo/README.md", self.RULE)
        self.wall("waive", "system-prompt/reviewer-config",
                  "unchanged because the reviewer only ever sees diffs, never file ownership")
        closed = self.wall("close")
        self.assertEqual(0, closed.returncode)
        self.assertIn("CLOSED clean", closed.stdout)


if __name__ == "__main__":
    unittest.main()
