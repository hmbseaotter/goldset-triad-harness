"""Ground-truth criteria: truth-source, correspondence, receipt-summing, policy,
the payable basis, and rounding discipline."""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from decimal import ROUND_HALF_UP, Decimal as Dc
from pathlib import Path

from tests import support
from goldset_triad.audit_key import _Line, _derive_line
from goldset_triad.dataset import load_dataset, load_invoice_index, resolve_manifest
from goldset_triad.scoring import score

PKG = support.SRC / "goldset_triad"


class TruthSourceTests(unittest.TestCase):
    def test_index_fingerprint_changes_when_index_edited(self) -> None:
        m = resolve_manifest("dev", support.DATASETS)
        before = load_invoice_index(m.invoice_index_path).sha256
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "d")
            ipath = manifest.parent / "invoice_index.json"
            ipath.write_bytes(ipath.read_bytes() + b" ")
            after = load_invoice_index(ipath).sha256
        self.assertNotEqual(before, after)

    def test_key_is_truth_not_inputs(self) -> None:
        # Replacing an expected finding in the key changes the score, with inputs
        # untouched — the key, not the inputs, is what the scorer treats as truth.
        base = load_dataset("dev", support.DATASETS)
        base_score = score(base.answer_key.expected_findings,
                            support.perfect_artifact("dev"), base.invoice_index.inventory)
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "d")
            key_file = manifest.parent / "dev_answer_key.json"
            key = json.loads(key_file.read_text())
            key["expected_findings"].pop()  # remove one expectation
            key_file.write_text(json.dumps(key))
            ld = load_dataset(str(manifest), support.DATASETS)
            new_score = score(ld.answer_key.expected_findings,
                              support.perfect_artifact("dev"), ld.invoice_index.inventory)
        # inputs (digest) unchanged, but the score changed (a now-unmatched flag).
        self.assertEqual(base.inputs_aggregate_sha256, ld.inputs_aggregate_sha256)
        self.assertNotEqual(base_score.false_positive_count, new_score.false_positive_count)

    def test_index_absent_from_agent_readable_inputs(self) -> None:
        for ds in ("dev", "dev-synthetic", "dev-zero-defect"):
            inputs = support.DATASETS / ds / "inputs"
            self.assertEqual(list(inputs.rglob("invoice_index.json")), [])

    def test_correspondence_in_key_absent_from_inputs(self) -> None:
        key = support.read_json(support.key_path("dev"))
        self.assertTrue(key["correspondence"])
        # No input file declares invoice->PO correspondence.
        for path in (support.DATASETS / "dev" / "inputs").rglob("*.json"):
            text = path.read_text()
            self.assertNotIn("correspondence", text)
            self.assertNotIn("invoice_line_id", text)

    def test_goods_receipts_are_separate_documents_not_in_po(self) -> None:
        gr_dir = support.DATASETS / "dev" / "inputs" / "goods_receipts"
        self.assertTrue(list(gr_dir.glob("*.json")))  # GRs are their own docs
        for po_path in (support.DATASETS / "dev" / "inputs" / "purchase_orders").glob("*.json"):
            po = support.read_json(po_path)
            self.assertNotIn("receipts", po)  # not co-located in the PO


class ReceiptSummingTests(unittest.TestCase):
    def test_received_quantity_is_summed_and_single_receipt_would_differ(self) -> None:
        # INV-2002 L6 / PO-3002 P6: delivered 10 + 10 = 20, ordered 20, invoiced 24.
        summed = _derive_line(_Line(Dc(20), Dc(20), Dc(24), Dc(28), Dc(28)))
        single = _derive_line(_Line(Dc(20), Dc(10), Dc(24), Dc(28), Dc(28)))
        self.assertEqual(summed, {"QTY_INVOICE_INFLATED"})   # received==ordered
        self.assertEqual(single, {"QTY_UNDER_SHIPMENT"})     # a single receipt: received<ordered
        self.assertNotEqual(summed, single)  # demonstrably different
        # And the shipped key uses the summed result.
        self.assertTrue(support.has_finding("dev", "QTY_INVOICE_INFLATED", "LINE", "INV-2002", "6"))


class PayableBasisTests(unittest.TestCase):
    def test_two_percent_uses_payable_extended_not_ordered(self) -> None:
        # Ordered 100 @ $10 (ordered basis $1000, threshold $20), received 10
        # (payable basis $100, threshold $2). A $3 price variance at the payable
        # quantity is $3 * ... measured at payable qty 10 -> variance $30? Use a
        # per-unit delta that is material on the payable basis but not the ordered.
        # delta 0.25/unit: payable variance = 0.25*10 = 2.50 >= threshold(100)=2.00 FLAG;
        # ordered-basis threshold(1000)=20 would NOT flag 2.50.
        f = _Line(Dc(100), Dc(10), Dc(10), Dc("10.00"), Dc("10.25"))
        self.assertIn("PRICE_VARIANCE", _derive_line(f))  # payable basis flags
        # Same variance judged on the ordered extended ($1000) would pass:
        ordered_threshold = Dc("0.02") * (Dc(100) * Dc("10.00"))  # $20
        payable_variance = (Dc("10.25") - Dc("10.00")) * Dc(10)   # $2.50
        self.assertLess(payable_variance, ordered_threshold)


class PolicyTests(unittest.TestCase):
    def test_matching_policy_publishes_every_rule(self) -> None:
        policy = support.read_json(support.DATASETS / "dev" / "matching_policy.json")
        text = json.dumps(policy).lower()
        for needle in ("payable", "materiality", "price", "quantity", "tax", "cross-multipl"):
            self.assertIn(needle, text)
        self.assertEqual(set(policy["categories"]),
                         {"PRICE_VARIANCE", "QTY_UNDER_SHIPMENT", "QTY_OVER_SHIPMENT",
                          "QTY_INVOICE_INFLATED", "TAX_VARIANCE"})


class RoundingTests(unittest.TestCase):
    def test_ratio_rounds_half_up_not_banker(self) -> None:
        quantum = Dc("0.0001")
        # 0.12345 at 4dp: HALF_UP -> 0.1235; banker's (HALF_EVEN) -> 0.1234.
        self.assertEqual(str(Dc("0.12345").quantize(quantum, rounding=ROUND_HALF_UP)), "0.1235")

    def test_no_quantize_in_a_flagging_decision(self) -> None:
        # Display rounding never enters a flagging decision (D23): the audit rule
        # functions call no .quantize / rounding.
        tree = ast.parse((PKG / "audit_key.py").read_text())
        rule_fns = {"_threshold", "_material", "_payable", "_derive_line", "_derive_tax"}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in rule_fns:
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Attribute) and inner.attr == "quantize":
                        self.fail(f"{node.name} rounds inside a flagging decision")


class SuiteHygieneTests(unittest.TestCase):
    def test_suite_data_root_is_in_repo(self) -> None:
        # The full suite runs on the in-repo dev split alone, with no out-of-tree
        # path configured (the CI constraint, D14): the dataset root is inside the repo.
        self.assertTrue(support.DATASETS.resolve().is_relative_to(support.REPO_ROOT.resolve()))
        self.assertTrue((support.DATASETS / "dev" / "manifest.json").is_file())

    def test_no_test_loads_data_from_an_out_of_tree_path(self) -> None:
        # No test resolves a dataset from the secret/holdout tiers. Those tier names
        # may still appear as glob literals where the isolation guards are tested, so
        # this looks for an out-of-tree *load path* (a manifest/key file), not a bare
        # name. This scanner and the isolation tests name the tiers deliberately.
        allow = {Path(__file__).name, "test_isolation.py"}
        bad_markers = (
            "goldset-triad-secret\\", "goldset-triad-secret/held-out",
            "goldset-triad-holdout\\", "goldset-triad-holdout/inputs",
        )
        for path in (support.REPO_ROOT / "tests").glob("*.py"):
            if path.name in allow:
                continue
            text = path.read_text()
            for marker in bad_markers:
                self.assertNotIn(marker, text, f"{path.name} loads out-of-tree data ({marker})")


if __name__ == "__main__":
    unittest.main()
