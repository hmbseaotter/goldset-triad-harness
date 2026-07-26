"""Key-audit command — consistency on the shipped key, detection on a corrupt one."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests import support
from goldset_triad.audit_key import audit
from goldset_triad.dataset import DatasetError


class KeyAuditTests(unittest.TestCase):
    def test_shipped_dev_key_is_consistent(self) -> None:
        self.assertEqual(audit("dev", support.DATASETS), [])

    def test_corrupted_key_reports_divergence_naming_the_finding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "d")
            key_file = manifest.parent / "dev_answer_key.json"
            key = json.loads(key_file.read_text(encoding="utf-8"))
            removed = key["expected_findings"].pop(0)  # drop a finding
            key_file.write_text(json.dumps(key), encoding="utf-8", newline="\n")
            messages = audit(str(manifest), support.DATASETS)
        self.assertTrue(messages)
        joined = "\n".join(messages)
        self.assertIn(removed["target"]["document_id"], joined)

    def test_unresolved_reference_names_its_cause_not_a_keyerror(self) -> None:
        """D50 — the audit resolves the manifest directly and does NOT run the loader's
        validation, so it can still meet an unresolved reference. It used to surface as
        `audit error: KeyError ('PO-3001', 'P999')`, naming a tuple instead of the fault,
        against a requirement that every halt name its specific cause."""
        for field, bad, expected in (
            ("po_line_no", "P-GHOST", "purchase order"),
            ("invoice_line_id", "999-GHOST", "invoice index"),
        ):
            with tempfile.TemporaryDirectory() as td:
                manifest = support.copy_dataset("dev", Path(td) / "d")
                key_file = manifest.parent / "dev_answer_key.json"
                key = json.loads(key_file.read_text(encoding="utf-8"))
                key["correspondence"][0][field] = bad
                key_file.write_text(json.dumps(key), encoding="utf-8", newline="\n")
                with self.assertRaises(DatasetError) as ctx:
                    audit(str(manifest), support.DATASETS)
                message = str(ctx.exception)
                self.assertIn(bad, message)
                self.assertIn(expected, message)
                self.assertNotIn("KeyError", message)

    def test_audit_not_imported_by_any_scoring_module(self) -> None:
        # The audit command must never run inside a scoring run (D35).
        for mod in ("scoring", "scorecard", "dataset", "schema", "cli", "constants"):
            src = (support.SRC / "goldset_triad" / f"{mod}.py").read_text(encoding="utf-8")
            self.assertNotIn("audit_key", src, f"{mod}.py must not import audit_key")


if __name__ == "__main__":
    unittest.main()
