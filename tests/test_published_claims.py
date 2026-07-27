"""The README is a published claim, so it is bound to what is actually verified (D84).

D30 required that *"published claims about isolation SHALL state only what is verified"* —
and that requirement had **no acceptance criterion** for two phases, because nothing was
published yet. It went live the moment a README existed, which is the same shape as D66: a
rule recorded before the artifact it governs, waiting for the artifact to arrive and for
someone to remember.

D53 established the pattern this file follows. The published matching policy once carried a
hand-written threshold while the real constants lived elsewhere, so changing one would have
left the policy promising the other with nothing to notice. The fix was not to be careful; it
was to bind the published text to the shipped constants under a test. A README makes more
claims than a policy file does, and it is the artifact a reviewer actually reads — which is
precisely why it is the one where an overstatement costs most.

**What these tests are not.** They check that the README's claims match what the harness
verifies. They do not check that the README is well written, and they cannot: prose quality
is not a testable property, and pretending otherwise would be its own overstatement.
"""

from __future__ import annotations

import re
import tomllib
import unittest

from tests import support
from goldset_triad.audit_key import _CAP, _FLOOR, _RATE

README = support.REPO_ROOT / "README.md"

#: Every document outside the secret tier that shows a reader a shell command. Named
#: rather than globbed, because "whatever markdown happens to exist" is not a universe
#: (D82) — a new user-facing document must be added here deliberately.
COMMAND_DOCS = ("README.md", "docs/RUNBOOK.md", "ISOLATION_ATTESTATION.md")

#: The visible labels. A fenced block's language tag drives the syntax highlighter and is
#: invisible in every rendered markdown viewer, so a reader looking at the published page
#: cannot tell which shell a command is for without opening the raw file (D95).
SHELL_LABELS = {
    "powershell": "**Windows — PowerShell:**",
    "bash": "**Linux / macOS — bash:**",
}
_FENCE = re.compile(r"^(?P<prefix>\s*(?:>\s?)*)```(?P<lang>[a-zA-Z]*)\s*$")


class ShellLabelTests(unittest.TestCase):
    """Every shell block says, visibly, which shell it is for (D95).

    The fence language is for the highlighter. GitHub renders nothing above the block, so
    a reader of the published page has to *know* which of two adjacent blocks applies to
    them — and this project gives every command twice, once per shell, which makes that
    exactly the thing they cannot afford to guess."""

    def test_every_shell_block_carries_a_visible_label(self) -> None:
        unlabelled: list[str] = []
        for name in COMMAND_DOCS:
            path = support.REPO_ROOT / name
            self.assertTrue(path.is_file(), f"{name} is missing")
            lines = path.read_text(encoding="utf-8").split("\n")
            inside = False
            for number, line in enumerate(lines, start=1):
                fence = _FENCE.match(line)
                if fence and not inside:
                    inside = True
                    lang = fence.group("lang").lower()
                    if lang not in SHELL_LABELS:
                        continue
                    previous = ""
                    for earlier in reversed(lines[: number - 1]):
                        stripped = earlier.strip().lstrip("> ").strip()
                        if stripped:
                            previous = stripped
                            break
                    if previous != SHELL_LABELS[lang]:
                        unlabelled.append(f"{name}:{number} ({lang})")
                elif fence and inside:
                    inside = False
        self.assertEqual(
            unlabelled, [],
            f"{len(unlabelled)} shell block(s) with no visible shell label: {unlabelled}. "
            f"Add the matching line from SHELL_LABELS immediately above the fence — the "
            f"language tag is invisible once the page is rendered (D95).",
        )

    def test_the_scan_would_notice_an_unlabelled_block(self) -> None:
        """The premise: a scan that has only ever seen labelled blocks has not been shown
        to look. Exercised on synthetic text rather than on the real documents, which are
        (and must stay) fully labelled."""
        lines = ["Some prose.", "```bash", "echo hi", "```"]
        found = _FENCE.match(lines[1])
        self.assertIsNotNone(found)
        assert found is not None  # for the type checker; the assertion above is the gate
        self.assertEqual(found.group("lang"), "bash")
        self.assertNotEqual(lines[0], SHELL_LABELS["bash"],
                            "the fixture must genuinely lack a label")


def _flattened(text: str) -> str:
    """Prose with line wrapping and markdown quote markers collapsed to single spaces.

    Every phrase assertion below runs against this, never against the raw file, for a
    reason D55 recorded after being caught by it: **a phrase grep on a wrapped document
    silently under-reports.** A required sentence that happens to break across two lines
    reads as absent, so the check fails on the formatting rather than on the claim — or,
    far worse in the other direction, a forbidden phrase slips past a `assertNotRegex`
    simply by being wrapped.

    Found here rather than reasoned about: the industry-norm disclaimer was written into
    the README, and matched nothing, because the wrap fell between "claimed" and "to"."""
    without_quotes = re.sub(r"(?m)^\s*>\s?", "", text)
    return re.sub(r"\s+", " ", without_quotes)


class PublishedIsolationClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(README.is_file(), f"{README} is missing")
        self.raw = README.read_text(encoding="utf-8")
        self.text = _flattened(self.raw)

    def test_the_readme_states_only_what_isolation_verifies(self) -> None:
        """The `[P2]` criterion, closing D30's long-open gap.

        Three things must be said, and one must not. The positives are what D30 requires a
        published claim to state; the negative is the claim D30 was written to forbid —
        *"contamination structurally impossible, verified by automated probe"* — which would
        be false, because deny rules bind tool calls and a subprocess runs beneath that
        boundary."""
        for phrase, why in (
            ("Placement is checked automatically",
             "placement is the automated half and the primary control (D14, D30)"),
            ("Guard configuration is checked automatically",
             "the deny rules' coverage is the other automated half (D30)"),
            ("attested, not tested",
             "harness enforcement is a dated manual attestation, never executed code (D30)"),
            ("outside deny coverage by design",
             "a determined subprocess is out of reach, which is WHY placement is primary"),
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text, f"the README must state this: {why}")

        # The forbidden shape. Asserted as a pattern rather than one literal sentence,
        # because the defect is the claim, not its wording.
        for forbidden in (r"verified by (an )?automated probe",
                          r"contamination (is )?structurally impossible[^.]*verif",
                          r"proves the guards"):
            with self.subTest(forbidden=forbidden):
                self.assertNotRegex(
                    self.text, forbidden,
                    "the README claims enforcement is verified by code; a reachability "
                    "probe reports failure unconditionally and proves nothing (D30)",
                )

    def test_the_readme_threshold_matches_the_shipped_rule(self) -> None:
        """D53's binding, extended to the README.

        Derived from the shipped constants, never restated here, so this test cannot drift
        from the implementation any more than the policy file can. An agent competes against
        the published rule; if the README promises a threshold the harness does not apply,
        the agent is judged against one it was never told."""
        floor_token = f"${_FLOOR.normalize():f}"
        cap_token = f"${_CAP.normalize():f}"
        rate_token = f"{(_RATE * 100).normalize():f}%"
        for token in (floor_token, cap_token, rate_token):
            with self.subTest(token=token):
                self.assertIn(
                    token, self.text,
                    f"the README must publish {token}, which is what the shipped rule "
                    f"applies; a published threshold that drifts judges an agent against "
                    f"a rule it was never told (D53)",
                )

    def test_the_readme_does_not_claim_the_thresholds_are_an_industry_norm(self) -> None:
        """D16 recorded the thresholds *and* recorded that standard practice was never
        verified to a citable source. Publishing the reasoning is honest; publishing it as
        the industry's reasoning is a claim nobody checked."""
        self.assertRegex(
            self.text, r"not claimed to represent standard corporate practice",
            "the README must disclaim the industry-norm reading explicitly (D16)",
        )
        for forbidden in (r"industry[- ]standard threshold", r"standard AP tolerance"):
            with self.subTest(forbidden=forbidden):
                self.assertNotRegex(self.text, forbidden)


class WrappedPhraseScanTests(unittest.TestCase):
    """The premise the assertions above rest on, proven rather than assumed (D55).

    A scan that has only ever been run against text it happens to match has not been shown
    to look. Both directions matter: the flattener must find a required phrase that wraps,
    and it must also stop a forbidden phrase hiding behind a line break."""

    def test_a_wrapped_phrase_is_found_after_flattening_and_not_before(self) -> None:
        wrapped = "> They are not claimed\n> to represent standard corporate practice.\n"
        self.assertNotIn("not claimed to represent", wrapped,
                         "the premise: the raw form must genuinely fail to match")
        self.assertIn("not claimed to represent standard corporate practice",
                      _flattened(wrapped))


class PublishedCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = README.read_text(encoding="utf-8")
        self.text = _flattened(self.raw)

    def test_every_command_the_readme_names_is_one_that_exists(self) -> None:
        """D59's rule, applied to the README: a document that sends a reader to a command
        the package never declared sends them to command-not-found. The original defect was
        a `--help` string; a README is the same claim with a wider audience."""
        declared = set(
            tomllib.loads(
                (support.REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
            )["project"]["scripts"]
        )
        named = set(re.findall(r"\b(goldset-triad(?:-[a-z-]+)?)\b", self.text))
        unknown = sorted(named - declared - {"goldset-triad-harness"})
        self.assertEqual(
            unknown, [],
            f"the README names command(s) that no console script declares: {unknown}",
        )
        self.assertTrue(named, "the scan found no commands at all, so it checked nothing")

    def test_every_documented_command_is_given_for_both_shells(self) -> None:
        """Windows and Linux are both first-class, and every documented command is given
        for PowerShell and for bash — a stack constraint, not a courtesy. Counted in pairs
        rather than searched for, so a block added for one shell alone fails.

        Read off the RAW file, not the flattened prose: a fenced block is a line-structure
        fact, and the flattener that makes phrase matching safe destroys exactly the
        structure this one needs."""
        bash = len(re.findall(r"(?m)^```bash$", self.raw))
        powershell = len(re.findall(r"(?m)^```powershell$", self.raw))
        self.assertGreater(bash, 0, "the README documents no runnable command at all")
        self.assertEqual(
            bash, powershell,
            f"{bash} bash block(s) against {powershell} PowerShell block(s): every "
            f"documented command is given for both shells",
        )


if __name__ == "__main__":
    unittest.main()
