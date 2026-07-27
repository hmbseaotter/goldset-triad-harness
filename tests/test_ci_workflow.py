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

import re
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
        the gate. Asserting it here would restate the runner's semantics, not check them.

        **Anchored (D81).** `assertIn("on:", text)` stood here and was satisfied by
        `runs-on:`, `python-version:` and `node-version:` — eight matching lines, none of
        them the trigger block. A check that passes for a reason unrelated to what it
        claims is the vacuous-probe shape D73 was, and it is the same unanchored-pattern
        class the shipped guards are themselves scanned for (C64)."""
        self.assertRegex(self.text, r"(?m)^on:$")
        self.assertRegex(self.text, r"(?m)^\s{2,}push:\s*$")
        self.assertIn("python -m unittest discover", self.text)
        # Pinned to an exact version rather than floating, so the gate cannot turn red
        # from a release elsewhere -- the unstated-dependency class D61 named. Asserted
        # POSITIVELY: `assertNotIn("npx --yes pyright\\n")` stood here and a bare
        # `npx pyright` sailed past it, so the check excluded one spelling of the defect
        # rather than requiring the fix.
        self.assertRegex(self.text, r"npx --yes pyright@\d+\.\d+\.\d+")

    def _matrix_platforms(self) -> list[str]:
        """The `os:` matrix entry, parsed on its own rather than searched for globally."""
        found = re.search(r"(?m)^\s*os:\s*\[(?P<items>[^\]]*)\]", self.text)
        self.assertIsNotNone(found, "the scorecard job declares no `os:` matrix at all")
        assert found is not None  # for the type checker; the assertion above is the gate
        return [item.strip() for item in found.group("items").split(",") if item.strip()]

    def test_the_workflow_compares_scorecards_across_two_platforms(self) -> None:
        """The cross-platform comparison exists and names both platforms.

        Configuration only: whether the two scorecards actually matched is a result, and
        results live in the run. Both platform names are asserted because a matrix silently
        narrowed to one would leave a job called `cross-platform` comparing a run to
        itself -- green, and measuring nothing, which is D73's shape.

        **Read off the matrix, not off the file (D81).** `assertIn("ubuntu-latest", text)`
        stood here, and `ubuntu-latest` appears on three other `runs-on:` lines — so the
        matrix could be narrowed to Windows alone and this check would still pass, in the
        exact direction its own docstring claimed to guard. It was one-directional while
        describing itself as two."""
        platforms = self._matrix_platforms()
        self.assertIn("ubuntu-latest", platforms)
        self.assertIn("windows-latest", platforms)
        self.assertIn("deterministic_body", self.text)
        self.assertIn("cross-platform", self.text)

    def test_the_suite_skip_count_is_asserted_rather_than_eyeballed(self) -> None:
        """D14 puts the held-out split out of tree, so a clone must SKIP the
        tier-dependent tests. A test that vanished and a test that skipped are
        indistinguishable inside a green tick, so the workflow asserts a non-zero skip
        count. That assertion is itself a claim about the workflow, so it is checked."""
        self.assertIn("skipped=[1-9]", self.text)

    def test_the_test_count_is_derived_rather_than_hand_maintained(self) -> None:
        """The workflow compares what ran against the traceability map's own enumeration
        (D81), not against a number somebody typed.

        A floor of `150` stood here while the suite held 207, so fifty-seven tests could
        have stopped running behind a green tick. A floor was the right instinct — an
        exact literal would be a second list to keep in step, which is the shape D54
        condemned — but the answer is not a looser literal, it is no literal: the
        traceability map already enumerates every test method under a failing check, so
        CI asks *it* how many there should be."""
        self.assertIn("all_test_methods", self.text)
        self.assertNotRegex(
            self.text, r'-lt \d+ \]',
            "no hand-typed test-count threshold: the count is derived from the "
            "traceability map's enumeration, which is maintained under a failing test",
        )

    def test_the_line_ending_check_can_fail(self) -> None:
        """H17's mechanism is asserted, not merely printed (D81).

        The step read `git check-attr` over every dataset artifact and piped the result
        into `sort | uniq -c` — and its own comment said anything but `text: unset` means
        a Linux checkout holds different bytes from a Windows one, which would move the
        aggregate inputs digest and present as tampering. It could not fail. An
        observation nobody is required to read is not a check, which is the same
        distinction D30 drew about the reachability probe."""
        self.assertIn("check-attr", self.text)
        self.assertRegex(
            self.text, r'(?s)check-attr.*?::error::.*?exit 1',
            "the line-ending step must exit non-zero on an unexpected attribute, not "
            "print a summary for a human to notice",
        )


if __name__ == "__main__":
    unittest.main()
