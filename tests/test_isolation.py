"""Isolation — guard-configuration, placement, the D14 trap, and the attestation."""

from __future__ import annotations

import re
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import support
from goldset_triad import check_isolation as ci


class IsolationTests(unittest.TestCase):
    def test_guard_configuration_passes_on_shipped_settings(self) -> None:
        self.assertEqual(ci.check_guard_configuration(), [])

    def test_guard_configuration_fails_naming_uncovered_secret_path(self) -> None:
        thin = ["Read(**/gen_rules.py)", "Read(**/generate.py)",
                "Read(**/pdf_invoice.py)", "Read(**/discrepancy-plan.md)",
                "Read(**/holdout_answer_key.json)"]
        with mock.patch.object(ci, "_deny_rules", return_value=thin):
            failures = ci.check_guard_configuration()
        self.assertTrue(any("secret directory" in f for f in failures))

    def test_guard_configuration_rejects_covering_holdout_inputs(self) -> None:
        # The D14 trap: a rule covering the held-out INPUTS breaks evaluation.
        trap = ["Read(**/goldset-triad-secret/**)", "Read(**/holdout_answer_key.json)",
                "Read(**/gen_rules.py)", "Read(**/generate.py)",
                "Read(**/pdf_invoice.py)", "Read(**/discrepancy-plan.md)",
                "Read(**/goldset-triad-holdout/**)"]
        with mock.patch.object(ci, "_deny_rules", return_value=trap):
            failures = ci.check_guard_configuration()
        self.assertTrue(any("held-out INPUTS" in f for f in failures))

    def test_unanchored_generator_rule_is_rejected_as_over_broad(self) -> None:
        """D65 — over-blocking is its own failure class, not a milder under-coverage.

        `Bash(*generate.*)` denied `bash regenerate.sh`, `npm run pregenerate.build` and
        `git log --grep=generate.py`, because the stem appears inside ordinary words — and
        "regenerate" is this project's own workflow verb. Such a rule leaks nothing; it
        obstructs, and a guard that obstructs routine work is one people switch off."""
        over_broad = [r for r in ci._deny_rules(support.REPO_ROOT)
                      if not r.startswith("Bash(*generate.")] + ["Bash(*generate.*)"]
        with mock.patch.object(ci, "_deny_rules", return_value=over_broad):
            failures = ci.check_guard_configuration()
        self.assertTrue(any("unanchored" in f for f in failures), failures)

    def test_shipped_rules_deny_the_generator_but_allow_innocent_words(self) -> None:
        """Positive control alongside the negative: anchoring must not have broken the
        coverage it exists to preserve."""
        import fnmatch
        patterns = [r[len("Bash("):-1] for r in ci._deny_rules(support.REPO_ROOT)
                    if r.startswith("Bash(")]
        def denied(cmd: str) -> bool:
            return any(fnmatch.fnmatch(cmd, p) for p in patterns)

        for cmd in ("python generate.py", "python _generators/generate.py",
                    r"python D:\Claude_Stuff\goldset-triad-secret\_generators\gen_rules.py"):
            self.assertTrue(denied(cmd), f"should still be denied: {cmd}")
        for cmd in ("bash regenerate.sh", "npm run pregenerate.build",
                    "git log --grep=generate.py", "echo 'we regenerate. now'"):
            self.assertFalse(denied(cmd), f"should not be denied: {cmd}")

    def test_placement_passes_on_clean_tree(self) -> None:
        self.assertEqual(ci.check_placement(), [])

    def test_placement_fails_when_secret_artifact_planted(self) -> None:
        decoy = support.REPO_ROOT / "tmp_decoy_dir" / "holdout_answer_key.json"
        decoy.parent.mkdir(parents=True, exist_ok=True)
        decoy.write_text("{}", encoding="utf-8", newline="\n")
        try:
            failures = ci.check_placement()
        finally:
            decoy.unlink()
            decoy.parent.rmdir()
        self.assertTrue(any("holdout_answer_key.json" in f for f in failures))

    def test_placement_fails_on_an_untracked_held_out_scorecard(self) -> None:
        """The contamination axis, which the index check could not see (D104).

        D93 guarded held-out scorecards over *tracked* files, reasoning about publication.
        An untracked one sits on disk, readable by the agent under evaluation, and passed
        every shipped check — the exact property D93 cited when it rejected a `.gitignore`
        rule. Planted in a temporary tree rather than the real one, so a failure here can
        never be this machine's actual state."""
        with tempfile.TemporaryDirectory() as t:
            tree = Path(t)
            (tree / "scorecards").mkdir()
            (tree / "scorecards" / "scorecard-held-out-20260728T000000Z.json").write_text(
                "{}", encoding="utf-8", newline="\n"
            )
            failures = ci.check_placement(tree)
        self.assertTrue(
            any("held-out" in f and "answer-key content" in f for f in failures),
            f"an untracked held-out scorecard must be reported by placement; got {failures}",
        )

    def test_placement_leaves_dev_scorecards_alone(self) -> None:
        """The positive control, in both directions that matter.

        A rule flagging legitimate dev scorecards would be as broken as one missing held-out
        cards: the dev keys ship in this repository, so a dev scorecard reveals nothing that
        is not already committed beside it — and scorecards are the durable record D9 says
        to keep."""
        with tempfile.TemporaryDirectory() as t:
            tree = Path(t)
            (tree / "scorecards").mkdir()
            for name in ("scorecard-dev-20260728T000000Z.json",
                         "scorecard-dev-20260728T000000Z.txt",
                         "scorecard-dev-zero-defect-20260728T000000Z-2.json",
                         "scorecard-dev-synthetic-20260728T000000Z.json"):
                (tree / "scorecards" / name).write_text(
                    "{}", encoding="utf-8", newline="\n"
                )
            self.assertEqual(ci.check_placement(tree), [])

    def test_repository_contains_no_heldout_artifact(self) -> None:
        # No held-out key, generator, design artifact, or held-out input in the repo.
        self.assertEqual(ci.check_placement(), [])

    def test_attestation_record_exists_with_date_and_method(self) -> None:
        att = (support.REPO_ROOT / "ISOLATION_ATTESTATION.md").read_text(encoding="utf-8")
        self.assertIn("2026-", att)  # carries a date
        self.assertIn("Method:", att)  # names the method
        self.assertIn("canary", att.lower())

    def test_no_shipped_check_claims_to_test_enforcement_by_code(self) -> None:
        # check_isolation must not attempt to open the canary to prove refusal.
        src = (support.SRC / "goldset_triad" / "check_isolation.py").read_text(encoding="utf-8")
        self.assertNotIn("throwaway.json", src)


class GuardTemplateDriftTests(unittest.TestCase):
    """The stamped guard must still match its source of truth (D64).

    The template declares itself authoritative and instructs "edit here and re-stamp;
    never hand-edit the repo copy" — but the isolation check reads only the stamped copy,
    so editing the template and forgetting to re-stamp left the repository guarded by the
    older rules with nothing noticing. The instruction was the whole enforcement.

    Skips without the secret tier, as D14 requires the suite to pass from a clone. Reading
    the template leaks nothing: it contains deny rules, not answers."""

    def setUp(self) -> None:
        secret = support.find_secret_dir()
        if secret is None:
            self.skipTest("no secret tier on this machine; the template is out of reach")
        template = secret / "_guard-template.settings.json"
        if not template.is_file():
            self.skipTest(f"secret tier present but no guard template at {template}")
        self.template_rules = json.loads(
            template.read_text(encoding="utf-8"))["permissions"]["deny"]
        self.stamped_rules = json.loads(
            (support.REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
        )["permissions"]["deny"]

    def test_stamped_guard_matches_the_template(self) -> None:
        only_template = [r for r in self.template_rules if r not in self.stamped_rules]
        only_stamped = [r for r in self.stamped_rules if r not in self.template_rules]
        self.assertEqual(
            (only_template, only_stamped), ([], []),
            "the stamped .claude/settings.json has drifted from its source of truth; "
            "re-stamp from the template rather than hand-editing the copy. "
            f"only in template: {only_template}; only in stamped: {only_stamped}",
        )

    def test_rule_order_matches_too(self) -> None:
        """Order is not semantically load-bearing for deny rules, but an identical list in
        a different order means one file was hand-edited, which is what the drift check
        exists to catch."""
        self.assertEqual(self.template_rules, self.stamped_rules)


class RepoRootResolutionTests(unittest.TestCase):
    """Which tree gets inspected, once this became an installed command (D59).

    The root used to come solely from ``__file__``, which is the checkout only while the
    package runs in place. Installed, ``__file__`` points into site-packages and the tool
    announced "the deny-guards are unconfigured" — reporting an isolation failure when in
    fact it had been given nowhere to look. D50's rule applies: a check that misdiagnoses
    is worse than one that stays silent, and this one misdiagnosed in the alarming
    direction."""

    def _run(self, argv: list[str], *, package_root, cwd) -> tuple[int, str]:
        import contextlib
        import io

        err = io.StringIO()
        with mock.patch.object(ci, "REPO_ROOT", package_root), \
                mock.patch.object(Path, "cwd", staticmethod(lambda: cwd)), \
                contextlib.redirect_stderr(err):
            code = ci.main(argv)
        return code, err.getvalue()

    def test_no_checkout_anywhere_is_an_error_not_an_isolation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            nowhere = Path(td)
            code, err = self._run([], package_root=nowhere, cwd=nowhere)
        self.assertEqual(code, 2)
        self.assertIn("NOT an isolation failure", err)
        self.assertIn("nothing has been checked", err)
        # The old wording, which named a real failure that had not occurred.
        self.assertNotIn("deny-guards are unconfigured", err)

    def test_falls_back_to_the_current_directory_when_installed(self) -> None:
        """An installed copy run from inside a checkout inspects that checkout."""
        with tempfile.TemporaryDirectory() as td:
            code, _err = self._run([], package_root=Path(td), cwd=support.REPO_ROOT)
        self.assertEqual(code, 0)

    def test_explicit_repo_root_wins(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            nowhere = Path(td)
            code, _err = self._run(
                ["--repo-root", str(support.REPO_ROOT)],
                package_root=nowhere, cwd=nowhere,
            )
        self.assertEqual(code, 0)

    def test_a_nonexistent_repo_root_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "no-such-tree"
            code, err = self._run(
                ["--repo-root", str(missing)], package_root=Path(td), cwd=Path(td)
            )
        self.assertEqual(code, 2)
        self.assertIn("no-such-tree", err)

    def test_settings_presence_does_not_decide_where_to_look(self) -> None:
        """A missing settings file is a failure this tool must REPORT, so it cannot also
        be the signal that this tree is not worth inspecting — that would convert the
        failure into a silent redirect elsewhere."""
        with tempfile.TemporaryDirectory() as td:
            checkout = Path(td) / "fake-checkout"
            (checkout / "src" / "goldset_triad").mkdir(parents=True)
            (checkout / "pyproject.toml").write_text("", encoding="utf-8")
            self.assertTrue(ci.looks_like_checkout(checkout))  # no .claude/ at all
            code, err = self._run([], package_root=checkout, cwd=checkout)
        self.assertEqual(code, 2)
        self.assertIn("deny-guards are unconfigured", err)  # reported, not redirected


class GuardReachTests(unittest.TestCase):
    """Are this repository's deny rules the ones a session actually loaded? (D91)

    Found by re-running the attestation rather than by reading code. A tool-level read of
    the canary, which the dated record says was refused, **succeeded** — because the
    session was rooted one directory above the repository, so Claude Code loaded that
    directory's settings and this repository's deny rules were never in force. The rules
    had not failed to match; they had never been read. The same absence explains a
    generator invocation that ran unrefused (D90).

    Every case below is built in a temporary tree, because asserting against this machine's
    real layout would make the test pass or fail on where the checkout happens to sit."""

    def _workspace(self, root: Path, deny: list[str] | None) -> Path:
        """A repo inside a workspace whose settings carry ``deny`` (or no settings)."""
        repo = root / "workspace" / "repo"
        repo.mkdir(parents=True)
        if deny is not None:
            claude = root / "workspace" / ".claude"
            claude.mkdir(parents=True)
            (claude / "settings.json").write_text(
                json.dumps({"permissions": {"deny": deny}}),
                encoding="utf-8", newline="\n",
            )
        return repo

    def test_an_ancestor_without_secret_coverage_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            repo = self._workspace(Path(t), deny=["Read(**/something_else)"])
            warnings = ci.check_guard_reach(repo)
            self.assertTrue(
                any("workspace" in w and "not in force" in w for w in warnings),
                f"a session rooted at the workspace loads settings that do not cover the "
                f"secret tier, and that must be reported; got {warnings}",
            )

    def test_an_ancestor_that_does_cover_the_secret_tier_is_not_reported(self) -> None:
        """The positive control. A warning that fires on a correctly-guarded workspace
        would be noise, and D65 settled that a guard obstructing routine work is one
        people switch off."""
        with tempfile.TemporaryDirectory() as t:
            repo = self._workspace(
                Path(t), deny=[f"Read(**/{ci.SECRET_DIR_NAME}/**)"]
            )
            warnings = [w for w in ci.check_guard_reach(repo) if "workspace" in w]
            self.assertEqual(warnings, [], "a covering ancestor must not be reported")

    def test_the_advisory_states_a_condition_rather_than_judging_this_session(self) -> None:
        """It reads the filesystem; it cannot see where a session was rooted (D103).

        The original wording — *"A session rooted at X loads those instead of this
        repository's"* — is true and was read as a verdict on the reader's own session. The
        attestation then told them a `[guard-reach]` line meant they were mis-rooted and to
        stop until it cleared. It never clears: the ancestor exists and is meant to, so the
        procedure's gate could not be satisfied. A check that cannot observe a thing must
        not phrase its output as though it had."""
        with tempfile.TemporaryDirectory() as t:
            repo = self._workspace(Path(t), deny=["Read(**/something_else)"])
            warning = next(w for w in ci.check_guard_reach(repo) if "workspace" in w)
            self.assertIn(
                "IF a session is rooted at", warning,
                "the advisory must be conditional: it observed a file on disk, not the "
                "root of the session reading it",
            )
            self.assertIn(
                "not about your current session", warning,
                "and it must say so, because the document consuming it read it the other "
                "way for a whole revision",
            )

    def test_the_attestation_does_not_gate_on_the_advisory(self) -> None:
        """The consuming document, checked against the tool's actual capability.

        This is the half that failed: the message was defensible and the procedure built on
        it was not. Binding them here means a future rewording of either has to keep them
        agreeing (D53's pattern, applied to a procedure rather than a threshold)."""
        text = (support.REPO_ROOT / "ISOLATION_ATTESTATION.md").read_text(encoding="utf-8")
        flattened = re.sub(r"\s+", " ", text)
        self.assertNotRegex(
            flattened, r"no `\[guard-reach\]` line",
            "the attestation must not tell a reader to expect the advisory's ABSENCE: the "
            "command cannot see the session root, so that expectation is unsatisfiable "
            "wherever an ancestor legitimately carries its own settings (D103)",
        )
        self.assertIn(
            "It is not a verdict on your session", flattened,
            "the attestation must say what the advisory is not, since it previously said "
            "the opposite",
        )

    def test_a_reach_warning_never_changes_the_exit_code(self) -> None:
        """Advisory means advisory (D70's rule, applied to D91's finding). Where you open
        your editor is not a property of this repository, and failing the check over it
        would report a working habit as a security defect."""
        result = ci.IsolationResult(
            guard_failures=(), placement_failures=(),
            reach_warnings=("an ancestor does not cover the secret tier",),
        )
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
