"""Cross-artifact dataset validation: multi-PO tax rates (D47), correspondence
completeness (D48).

Both checks need the answer key and the invoice index *together*, so neither can live in
the per-artifact validators. Both are negative tests by necessity: the shipped datasets
satisfy them, so the only way to prove a check works is to break a dataset deliberately.
A check that has only ever been observed passing has not been observed at all.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tests import support
from goldset_triad.dataset import DatasetError, load_dataset


def _write(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8", newline="\n")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


class MultiPoTaxRateTests(unittest.TestCase):
    """D47 — an invoice spanning POs with DIFFERING rates is unspecified, so rejected."""

    def test_shipped_datasets_have_no_multi_po_invoice(self) -> None:
        """The premise of D47: the rule is latent today, live at [P3]. If this ever
        fails, multi-PO data has arrived and the apportionment must be implemented."""
        for name in ("dev", "dev-synthetic", "dev-zero-defect"):
            key = _read(support.key_path(name))
            by_invoice: dict[str, set[str]] = {}
            for e in key.get("correspondence", []):
                by_invoice.setdefault(str(e["invoice_id"]), set()).add(str(e["po_number"]))
            for invoice_id, pos in by_invoice.items():
                self.assertEqual(
                    len(pos), 1,
                    f"{name}/{invoice_id} spans {sorted(pos)}; D47's apportionment is "
                    f"recorded but NOT implemented, so this dataset cannot be keyed",
                )

    def test_differing_rates_across_pos_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "ds")
            root = manifest.parent
            # Repoint one of INV-2001's lines at PO-3002, making it a two-PO invoice.
            # PO-3001 and PO-3002 both run 8.7%, so first make PO-3002's rate differ.
            po = _read(root / "inputs" / "purchase_orders" / "PO-3002.json")
            po["tax"] = "999.00"  # taxable subtotal unchanged -> a wildly different rate
            _write(root / "inputs" / "purchase_orders" / "PO-3002.json", po)

            key = _read(root / "dev_answer_key.json")
            for entry in key["correspondence"]:
                if entry["invoice_id"] == "INV-2001" and entry["invoice_line_id"] == "1":
                    entry["po_number"] = "PO-3002"
                    entry["po_line_no"] = "P1"
                    break
            else:  # pragma: no cover - fixture drift guard
                self.fail("INV-2001 line 1 not found in correspondence")
            _write(root / "dev_answer_key.json", key)

            with self.assertRaises(DatasetError) as ctx:
                load_dataset(str(manifest), Path(td))
            message = str(ctx.exception)
            self.assertIn("UNSPECIFIED", message)
            self.assertIn("INV-2001", message)
            self.assertIn("D47", message)

    def test_equal_rates_across_pos_is_allowed(self) -> None:
        """Same rate on both POs is unambiguous, so a multi-PO invoice must still load.
        Without this, the check could pass by rejecting every multi-PO invoice."""
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "ds")
            root = manifest.parent
            key = _read(root / "dev_answer_key.json")
            # PO-3001 and PO-3002 are both authored at 8.7%; point a line at the other
            # PO without altering any tax field.
            for entry in key["correspondence"]:
                if entry["invoice_id"] == "INV-2001" and entry["invoice_line_id"] == "1":
                    entry["po_number"] = "PO-3002"
                    entry["po_line_no"] = "P1"
                    break
            _write(root / "dev_answer_key.json", key)
            load_dataset(str(manifest), Path(td))  # must not raise


class CorrespondenceCompletenessTests(unittest.TestCase):
    """D48 — an invoice line with no correspondence entry is a line the audit never
    examines, so an omission there would be self-consistent and pass silently."""

    def test_missing_correspondence_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "ds")
            root = manifest.parent
            key = _read(root / "dev_answer_key.json")
            dropped = key["correspondence"].pop()
            _write(root / "dev_answer_key.json", key)

            with self.assertRaises(DatasetError) as ctx:
                load_dataset(str(manifest), Path(td))
            message = str(ctx.exception)
            self.assertIn("no correspondence entry", message)
            self.assertIn(str(dropped["invoice_id"]), message)
            self.assertIn("D48", message)

    def test_every_shipped_dataset_is_complete(self) -> None:
        """The invariant the mitigation relies on, asserted rather than assumed."""
        for name in ("dev", "dev-synthetic", "dev-zero-defect"):
            loaded = load_dataset(name, support.DATASETS)
            covered = {
                (str(e["invoice_id"]), str(e["invoice_line_id"]))
                for e in loaded.answer_key.correspondence
            }
            self.assertEqual(
                loaded.invoice_index.inventory.line_targets - covered, set(),
                f"{name} has invoice lines with no correspondence entry",
            )


if __name__ == "__main__":
    unittest.main()
