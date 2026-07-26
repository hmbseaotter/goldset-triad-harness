"""Isolation — guard-configuration, placement, the D14 trap, and the attestation."""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
