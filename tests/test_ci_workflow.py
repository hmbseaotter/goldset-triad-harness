"""The CI workflow is a claim, so it gets a check (D67, D76).

The spec asserts that CI runs the pyright gate and the full test suite on push, and that
the same dataset and findings artifact yield identical scorecard content on Windows and on
Linux. Both are statements about a file that no test read — the shape D59 named (*anything
a tool says about itself is a claim, and every claim gets a check*) and that D67 turned into
a mechanism. Without this, the workflow could be gutted to a no-op while two acceptance
criteria went on claiming it ran.

**What this can and cannot show, stated plainly.** It checks that the gates are
*configured*, not that they *passed* — the run itself is the only thing that can show the
second, which is why the cross-platform criterion is covered by a documented CI result
rather than by this file. Claiming otherwise would be D30's rejected reachability probe in
new clothes: a check that looks like verification while proving something weaker.

**Asserted over the text rather than a parsed tree**, deliberately. The standard library
has no YAML parser, and pulling in a dependency to read one file would breach the
stack constraint for a test. The syntax itself is not this file's job: GitHub refuses to
run a malformed workflow, so a syntax error is loud and immediate, while a *silently
removed job* is exactly the quiet failure worth guarding.
"""

from __future__ import annotations

import unittest

from tests import support

WORKFLOW = support.REPO_ROOT / ".github" / "workflows" / "ci.yml"


class CiWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(
            WORKFLOW.is_file(),
            f"{WORKFLOW} is missing, yet two [P2] acceptance criteria claim CI runs",
        )
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_the_workflow_runs_both_gates_on_push(self) -> None:
        """The `[P2]` criterion: pyright and the full suite, on push, failing on error.

        `fails on any error` needs no assertion of its own — a GitHub Actions step fails
        the job on a non-zero exit, and both gates are plain commands whose exit codes are
        the gate. Asserting it here would restate the runner's semantics, not check them."""
        self.assertIn("on:", self.text)
        self.assertIn("push:", self.text)
        self.assertIn("python -m unittest discover", self.text)
        self.assertIn("pyright@", self.text)
        # Pinned rather than floating, so the gate cannot turn red from a release
        # elsewhere -- the unstated-dependency class D61 named.
        self.assertNotIn("npx --yes pyright\n", self.text)

    def test_the_workflow_compares_scorecards_across_two_platforms(self) -> None:
        """The cross-platform comparison exists and names both platforms.

        Configuration only: whether the two scorecards actually matched is a result, and
        results live in the run. Both platform names are asserted because a matrix silently
        narrowed to one would leave a job called `cross-platform` comparing a run to
        itself -- green, and measuring nothing, which is D73's shape."""
        self.assertIn("ubuntu-latest", self.text)
        self.assertIn("windows-latest", self.text)
        self.assertIn("deterministic_body", self.text)
        self.assertIn("cross-platform", self.text)

    def test_the_suite_skip_count_is_asserted_rather_than_eyeballed(self) -> None:
        """D14 puts the held-out split out of tree, so a clone must SKIP the
        tier-dependent tests. A test that vanished and a test that skipped are
        indistinguishable inside a green tick, so the workflow asserts a non-zero skip
        count. That assertion is itself a claim about the workflow, so it is checked."""
        self.assertIn("skipped=[1-9]", self.text)


if __name__ == "__main__":
    unittest.main()
