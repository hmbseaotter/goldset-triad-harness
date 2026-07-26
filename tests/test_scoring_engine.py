"""Scoring engine — matching, metrics, tie-break, diagnostics."""

from __future__ import annotations

import unittest
from decimal import Decimal

from tests import support
from tests.support import document, inventory, line
from goldset_triad.schema import Category, Status
from goldset_triad.scoring import FalseFlagReason, LineInventory, score


def _inv() -> LineInventory:
    return inventory(
        {("INV-1", "1"), ("INV-1", "2"), ("INV-1", "3"), ("INV-2", "1")},
        {"INV-1", "INV-2"}, 2)


class ScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inv = _inv()
        self.expected = (
            line(Category.PRICE_VARIANCE, "INV-1", "1"),
            line(Category.QTY_UNDER_SHIPMENT, "INV-1", "2"),
            document(Category.TAX_VARIANCE, "INV-1"),
        )

    def test_perfect_findings_score_precision_and_recall_one(self) -> None:
        r = score(self.expected, self.expected, self.inv)
        self.assertEqual(r.overall_precision, Decimal(1))
        self.assertEqual(r.overall_recall, Decimal(1))
        self.assertEqual(r.false_positive_count, 0)

    def test_omitting_one_finding_reduces_recall_by_one_over_count(self) -> None:
        # Two PRICE expectations; find one -> recall 1/2 in that category.
        expected = (line(Category.PRICE_VARIANCE, "INV-1", "1"),
                    line(Category.PRICE_VARIANCE, "INV-1", "2"))
        r = score(expected, (line(Category.PRICE_VARIANCE, "INV-1", "1"),), self.inv)
        pv = [m for m in r.category_metrics if m.category is Category.PRICE_VARIANCE][0]
        self.assertEqual(pv.recall, Decimal(1) / Decimal(2))
        self.assertEqual(pv.false_negatives, 1)

    def test_spurious_finding_is_false_positive_and_lowers_precision(self) -> None:
        agent = self.expected + (line(Category.PRICE_VARIANCE, "INV-1", "3"),)
        r = score(self.expected, agent, self.inv)
        self.assertEqual(r.false_positive_count, 1)
        self.assertEqual(r.overall_precision, Decimal(3) / Decimal(4))

    def test_contention_one_tp_one_fp_and_order_reversal_identical(self) -> None:
        a1 = line(Category.PRICE_VARIANCE, "INV-1", "1", confidence=Decimal("0.9"))
        a2 = line(Category.PRICE_VARIANCE, "INV-1", "1", confidence=Decimal("0.2"))
        exp = (line(Category.PRICE_VARIANCE, "INV-1", "1"),)
        fwd = score(exp, (a1, a2), self.inv)
        rev = score(exp, (a2, a1), self.inv)
        self.assertEqual(fwd.false_positive_count, 1)
        self.assertEqual(fwd.duplicate_contention_count, 1)
        tp = sum(m.true_positives for m in fwd.category_metrics)
        self.assertEqual(tp, 1)
        # Order-reversal invariance: identical false-flag labelling and metrics.
        self.assertEqual(
            [(ff.reason, ff.finding.canonical()) for ff in fwd.false_flags],
            [(ff.reason, ff.finding.canonical()) for ff in rev.false_flags],
        )

    def test_wrong_targetline_is_both_false_negative_and_false_positive(self) -> None:
        exp = (line(Category.PRICE_VARIANCE, "INV-1", "1"),)
        r = score(exp, (line(Category.PRICE_VARIANCE, "INV-1", "2"),), self.inv)
        pv = [m for m in r.category_metrics if m.category is Category.PRICE_VARIANCE][0]
        self.assertEqual(pv.true_positives, 0)
        self.assertEqual(pv.false_positives, 1)
        self.assertEqual(pv.false_negatives, 1)

    def test_nonexistent_target_is_false_positive_labelled(self) -> None:
        r = score((), (line(Category.PRICE_VARIANCE, "INV-9", "7"),), self.inv)
        self.assertEqual(r.nonexistent_target_count, 1)
        self.assertEqual(r.false_flags[0].reason, FalseFlagReason.NONEXISTENT_TARGET)

    def test_match_status_is_not_a_false_positive(self) -> None:
        r = score((), (line(Category.PRICE_VARIANCE, "INV-1", "1", status=Status.MATCH),), self.inv)
        self.assertEqual(r.false_positive_count, 0)
        self.assertEqual(r.match_status_count, 1)

    def test_line_and_document_findings_do_not_match_each_other(self) -> None:
        # Same category + document id, different scope -> not a match.
        exp = (document(Category.TAX_VARIANCE, "INV-1"),)
        agent = (line(Category.TAX_VARIANCE, "INV-1", "1"),)
        r = score(exp, agent, self.inv)
        tp = sum(m.true_positives for m in r.category_metrics)
        self.assertEqual(tp, 0)  # scope participates in the key
        self.assertEqual(r.false_positive_count, 1)  # the line flag matched nothing

    def test_zero_defect_empty_artifact_precision_and_recall_null(self) -> None:
        r = score((), (), self.inv)
        self.assertEqual(r.false_positive_count, 0)
        self.assertEqual(r.false_positive_rate, Decimal(0))
        self.assertIsNone(r.overall_precision)
        self.assertIsNone(r.overall_recall)

    def test_zero_defect_with_flags_precision_zero_recall_null(self) -> None:
        agent = (line(Category.PRICE_VARIANCE, "INV-1", "1"),
                 line(Category.PRICE_VARIANCE, "INV-1", "2"),
                 document(Category.TAX_VARIANCE, "INV-2"))
        r = score((), agent, self.inv)
        self.assertEqual(r.overall_precision, Decimal(0))
        self.assertIsNone(r.overall_recall)
        self.assertEqual(r.false_positive_rate, Decimal(3) / Decimal(2))


if __name__ == "__main__":
    unittest.main()
