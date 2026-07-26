"""The arithmetic criteria — asserted through the shipped key and the shipped audit
rules. The key encodes every flagging decision (the generator applied the rules
and the independent auditor confirmed them), so a boundary decision is checked by
what the key does and does not contain."""

from __future__ import annotations

import decimal
import unittest
from decimal import Decimal as Dc

from tests import support
from tests.support import has_finding, perfect_artifact
from goldset_triad.audit_key import _derive_tax, _threshold
from goldset_triad.dataset import load_dataset
from goldset_triad.scoring import score


class KeyContentTests(unittest.TestCase):
    def test_all_five_categories_present_with_correct_scope(self) -> None:
        self.assertTrue(has_finding("dev", "PRICE_VARIANCE", "LINE", "INV-2001", "2"))
        self.assertTrue(has_finding("dev", "QTY_UNDER_SHIPMENT", "LINE", "INV-2002", "1"))
        self.assertTrue(has_finding("dev", "QTY_OVER_SHIPMENT", "LINE", "INV-2002", "2"))
        self.assertTrue(has_finding("dev", "QTY_INVOICE_INFLATED", "LINE", "INV-2002", "3"))
        self.assertTrue(has_finding("dev", "TAX_VARIANCE", "DOCUMENT", "INV-2003", "__DOCUMENT__"))

    def test_cent_aligned_boundary_flag_and_no_flag(self) -> None:
        # $500 basis -> 2% = $10.00 exactly. $10.00 flags (L3); $9.99 does not (L4).
        self.assertTrue(has_finding("dev", "PRICE_VARIANCE", "LINE", "INV-2001", "3"))
        self.assertFalse(has_finding("dev", "PRICE_VARIANCE", "LINE", "INV-2001", "4"))

    def test_nonaligned_boundary_flag_and_no_flag(self) -> None:
        # $333.33 basis -> 2% = $6.6666. $6.67 flags (L5); $6.66 does not (L6 of INV-2001).
        self.assertTrue(has_finding("dev", "PRICE_VARIANCE", "LINE", "INV-2001", "5"))
        self.assertFalse(has_finding("dev", "PRICE_VARIANCE", "LINE", "INV-2001", "6"))

    def test_hundred_thousand_line_twenty_six_dollar_variance_flags(self) -> None:
        # $100,000 extended, $26 variance -> $25 cap governs, 2% would be $2,000.
        self.assertTrue(has_finding("dev-synthetic", "PRICE_VARIANCE", "LINE", "INV-9001", "1"))
        ld = load_dataset("dev-synthetic", support.DATASETS)
        r = score(ld.answer_key.expected_findings, perfect_artifact("dev-synthetic"),
                  ld.invoice_index.inventory)
        self.assertEqual(sum(m.true_positives for m in r.category_metrics), 1)

    def test_both_wrong_line_yields_price_and_quantity(self) -> None:
        self.assertTrue(has_finding("dev", "PRICE_VARIANCE", "LINE", "INV-2002", "3"))
        self.assertTrue(has_finding("dev", "QTY_INVOICE_INFLATED", "LINE", "INV-2002", "3"))

    def test_short_shipment_billed_correctly_has_no_finding(self) -> None:
        # INV-2002 L5: ordered 24, received 20, invoiced 20 -> no discrepancy.
        self.assertFalse(has_finding("dev", "QTY_UNDER_SHIPMENT", "LINE", "INV-2002", "5"))
        self.assertFalse(has_finding("dev", "QTY_INVOICE_INFLATED", "LINE", "INV-2002", "5"))

    def test_cheap_one_unit_overbill_below_materiality_no_finding(self) -> None:
        # INV-2002 L4: 1-unit overbill worth $0.10 on a $0.20 threshold.
        self.assertFalse(has_finding("dev", "QTY_INVOICE_INFLATED", "LINE", "INV-2002", "4"))

    def test_price_error_on_taxable_line_yields_no_tax_finding(self) -> None:
        # INV-2001 has price variances on taxable lines but the tax is consistent
        # with the invoiced subtotal, so there is no TAX_VARIANCE.
        self.assertTrue(has_finding("dev", "PRICE_VARIANCE", "LINE", "INV-2001", "2"))
        self.assertFalse(has_finding("dev", "TAX_VARIANCE", "DOCUMENT", "INV-2001", "__DOCUMENT__"))

    def test_exempt_po_correct_zero_tax_has_no_finding(self) -> None:
        # INV-2004 is fully exempt, tax 0.00.
        self.assertFalse(has_finding("dev", "TAX_VARIANCE", "DOCUMENT", "INV-2004", "__DOCUMENT__"))

    def test_dev_has_exempt_po_and_the_two_boundary_bases_plausibly(self) -> None:
        po = support.read_json(support.DATASETS / "dev" / "inputs" / "purchase_orders" / "PO-3004.json")
        self.assertTrue(all(ln["taxable"] is False for ln in po["lines"]))  # fully exempt
        po1 = support.read_json(support.DATASETS / "dev" / "inputs" / "purchase_orders" / "PO-3001.json")
        extendeds = {ln["extended"] for ln in po1["lines"]}
        self.assertIn("500.00", extendeds)
        self.assertIn("333.33", extendeds)

    def test_hundred_thousand_only_in_synthetic(self) -> None:
        for ds in ("dev", "dev-zero-defect"):
            for po_path in (support.DATASETS / ds / "inputs" / "purchase_orders").glob("*.json"):
                po = support.read_json(po_path)
                for ln in po["lines"]:
                    self.assertNotEqual(ln["extended"], "100000.00")
        syn = support.read_json(support.DATASETS / "dev-synthetic" / "inputs" / "purchase_orders" / "PO-9001.json")
        self.assertIn("100000.00", {ln["extended"] for ln in syn["lines"]})

    def test_synthetic_labelled_and_loads_through_same_loader(self) -> None:
        m = support.read_json(support.DATASETS / "dev-synthetic" / "manifest.json")
        self.assertTrue(m["synthetic"])
        ld = load_dataset("dev-synthetic", support.DATASETS)  # same loader, no special path
        self.assertEqual(ld.manifest.identifier, "dev-synthetic")


class ShippedTaxRuleTests(unittest.TestCase):
    """The D29 tax branch, unit-tested against the shipping audit implementation."""

    def test_zero_taxable_flags_at_five_cents(self) -> None:
        self.assertTrue(_derive_tax(Dc(0), Dc(0), Dc("0.05"), Dc(0)))
        self.assertFalse(_derive_tax(Dc(0), Dc(0), Dc("0.04"), Dc(0)))

    def test_zero_taxable_does_not_annihilate_invoiced_tax(self) -> None:
        self.assertTrue(_derive_tax(Dc(0), Dc(0), Dc("50.00"), Dc(0)))

    def test_exempt_with_zero_tax_is_clean(self) -> None:
        self.assertFalse(_derive_tax(Dc(0), Dc(0), Dc(0), Dc(0)))

    def test_nonterminating_rate_same_verdict_under_two_precisions(self) -> None:
        # po_tax/po_taxable = 1/3 (non-terminating). Cross-multiplied -> no division.
        args = (Dc(1), Dc(3), Dc("0.34"), Dc(1))
        with decimal.localcontext() as ctx:
            ctx.prec = 6
            a = _derive_tax(*args)
        with decimal.localcontext() as ctx:
            ctx.prec = 40
            b = _derive_tax(*args)
        self.assertEqual(a, b)

    def test_threshold_shape(self) -> None:
        self.assertEqual(_threshold(Dc(500)), Dc(10))       # 2% governs
        self.assertEqual(_threshold(Dc(100000)), Dc(25))    # cap governs
        self.assertEqual(_threshold(Dc(1)), Dc("0.05"))     # floor governs


if __name__ == "__main__":
    unittest.main()
