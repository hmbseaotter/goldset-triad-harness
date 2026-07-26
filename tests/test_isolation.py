"""Isolation — guard-configuration, placement, the D14 trap, and the attestation."""

from __future__ import annotations

import unittest
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
        decoy.write_text("{}")
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
        src = (support.SRC / "goldset_triad" / "check_isolation.py").read_text()
        self.assertNotIn("throwaway.json", src)


if __name__ == "__main__":
    unittest.main()
