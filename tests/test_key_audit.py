"""Key-audit command — consistency on the shipped key, detection on a corrupt one."""

from __future__ import annotations

import ast
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
        """The audit command must never run inside a scoring run (D35).

        **The module list is discovered, not typed (D82).** It read
        `("scoring", "scorecard", "dataset", "schema", "cli", "constants")` — written when
        those were all the modules there were, and never revisited. Phase 2 added `verify`
        and `ledger`, and D77 added `jsonio`; all three were outside this check's universe
        while the rule it enforces plainly covers them. Same shape as D64a, D69, D73 and
        the numeric-default scanner above: the rule was right and its enforcement stopped
        at the boundary of what someone enumerated once."""
        package = support.SRC / "goldset_triad"
        examined = [p for p in sorted(package.glob("*.py")) if p.name != "audit_key.py"]
        self.assertGreater(
            len(examined), 5,
            "the package scan found almost nothing, so this check is passing over an "
            "empty set rather than over the scoring modules",
        )
        # Over the parsed IMPORTS, not over the raw text. A substring scan was what stood
        # here, and widening it to the whole package immediately caught `__init__.py`'s
        # module docstring, which names the audit command while describing the four-way
        # separation D35 requires. Prose about a rule is not a breach of it — and the
        # converse matters more: a text scan cannot tell an import from a mention, so it
        # was never checking what its name claimed.
        offenders: list[str] = []
        for path in examined:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""] + [alias.name for alias in node.names]
                else:
                    continue
                if any("audit_key" in name for name in names):
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(
            offenders, [],
            f"{offenders} import audit_key. The audit re-derives expectations "
            f"independently, and a scoring path that reached it would make the two agree "
            f"by construction rather than by check (D35).",
        )


if __name__ == "__main__":
    unittest.main()
