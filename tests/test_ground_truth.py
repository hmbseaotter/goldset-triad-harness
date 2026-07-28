"""Ground-truth criteria: truth-source, correspondence, receipt-summing, policy,
the payable basis, and rounding discipline."""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from decimal import ROUND_HALF_UP, Decimal as Dc
from pathlib import Path
from typing import Callable

from tests import support
from goldset_triad import audit_key
from goldset_triad.audit_key import _CAP, _FLOOR, _RATE, _Line, _derive_line
from goldset_triad.dataset import load_dataset, load_invoice_index, resolve_manifest
from goldset_triad.scoring import score

PKG = support.SRC / "goldset_triad"


class TruthSourceTests(unittest.TestCase):
    def test_index_fingerprint_changes_when_index_edited(self) -> None:
        m = resolve_manifest("dev", support.DATASETS)
        before = load_invoice_index(m.invoice_index_path).sha256
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "d")
            ipath = manifest.parent / "dev_invoice_index.json"
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
            key = json.loads(key_file.read_text(encoding="utf-8"))
            key["expected_findings"].pop()  # remove one expectation
            key_file.write_text(json.dumps(key), encoding="utf-8", newline="\n")
            ld = load_dataset(str(manifest), support.DATASETS)
            new_score = score(ld.answer_key.expected_findings,
                              support.perfect_artifact("dev"), ld.invoice_index.inventory)
        # inputs (digest) unchanged, but the score changed (a now-unmatched flag).
        self.assertEqual(base.inputs_aggregate_sha256, ld.inputs_aggregate_sha256)
        self.assertNotEqual(base_score.false_positive_count, new_score.false_positive_count)

    def test_index_absent_from_agent_readable_inputs(self) -> None:
        # Matched on a substring rather than one exact filename: pinning the old name
        # made this pass vacuously the moment the index was renamed (D51), which is the
        # rot this whole sweep exists to catch. Any *_invoice_index.json under inputs/
        # is a leak of the extraction answer, whatever it is called.
        for ds in ("dev", "dev-synthetic", "dev-zero-defect"):
            inputs = support.DATASETS / ds / "inputs"
            leaked = [p for p in inputs.rglob("*.json") if "invoice_index" in p.name.lower()]
            self.assertEqual(leaked, [], f"{ds}: invoice index present in agent-readable inputs")
        # And the index the loader actually resolves must exist, so this is not vacuous.
        self.assertTrue(support.index_path("dev").is_file())

    def test_correspondence_in_key_absent_from_inputs(self) -> None:
        key = support.read_json(support.key_path("dev"))
        self.assertTrue(key["correspondence"])
        # No input file declares invoice->PO correspondence.
        for path in (support.DATASETS / "dev" / "inputs").rglob("*.json"):
            text = path.read_text(encoding="utf-8")
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


#: Every rule the shipped implementation applies, and therefore every entry the published
#: policy must carry (D119). Named rather than discovered: a policy key is a promise to an
#: agent, so adding one is a deliberate act — and D82's other half, that the universe is
#: asserted covered, is met by the bindings below exercising each one.
PUBLISHED_RULE_KEYS: tuple[str, ...] = (
    "categories",
    "materiality_threshold",
    "payable_quantity",
    "price_variance",
    "quantity_overbill",
    "tax_variance",
    "precision",
    "dataset_guarantees",
)


def _rule_bindings() -> tuple[tuple[str, str, Callable[[], bool], str], ...]:
    """`(policy key, phrase the entry must contain, behaviour probe, what it asserts)`.

    Each probe runs the *shipped* rule implementation — `audit_key`, the independent
    derivation an agent could run and the one `audit()` compares against the generator's
    output on every split. Binding the published text to it means the prose and the code
    cannot drift apart silently, which is the whole of D53 applied one level up from the
    constants it covered."""
    from decimal import Decimal as D

    def line(ordered, received, invoiced, po_price, inv_price):
        return audit_key._Line(D(ordered), D(received), D(invoiced), D(po_price), D(inv_price))

    return (
        (
            "payable_quantity", "min(qty_ordered, qty_received)",
            lambda: audit_key._payable(D(10), D(4)) == 4 and audit_key._payable(D(4), D(10)) == 4,
            "payable is the lesser of ordered and received, whichever binds",
        ),
        (
            "materiality_threshold", "max($0.05, min(2% x basis, $25))",
            lambda: (audit_key._threshold(D("1")), audit_key._threshold(D("500")),
                     audit_key._threshold(D("100000")))
            == (D("0.05"), D("10.00"), D("25")),
            "the floor binds on tiny bases, the rate in between, the cap on large ones",
        ),
        (
            "materiality_threshold", "flag on >=",
            lambda: audit_key._material(D("10"), D("500"))
            and not audit_key._material(D("9.99"), D("500")),
            "the threshold boundary is inclusive",
        ),
        (
            "price_variance", "basis = payable_qty x po_unit_price",
            lambda: audit_key._derive_line(line(10, 10, 10, "100", "102")) == {"PRICE_VARIANCE"},
            "the variance is judged against the payable extended amount, not the ordered one",
        ),
        (
            "quantity_overbill", "category by which constraint bound the payable quantity",
            lambda: audit_key._derive_line(line(10, 6, 10, "100", "100")) == {"QTY_UNDER_SHIPMENT"}
            and audit_key._derive_line(line(10, 14, 12, "100", "100")) == {"QTY_OVER_SHIPMENT"}
            and audit_key._derive_line(line(10, 10, 12, "100", "100")) == {"QTY_INVOICE_INFLATED"},
            "under-shipment, over-shipment and a straight inflated invoice are told apart "
            "by what limited the payable quantity",
        ),
        (
            "tax_variance", "invoice's own taxable subtotal",
            lambda: not audit_key._derive_tax(D("80"), D("1000"), D("40"), D("500")),
            "the PO's rate is applied to the invoice's subtotal, so a half-sized invoice "
            "taxed at the same rate is clean",
        ),
        (
            "tax_variance", "zero taxable subtotal takes the degenerate $0.05 branch",
            lambda: audit_key._derive_tax(D(0), D(0), D("0.05"), D(0))
            and not audit_key._derive_tax(D(0), D(0), D("0.04"), D(0)),
            "with nothing taxable, any tax at or above the floor is a variance",
        ),
    )


class PolicyTests(unittest.TestCase):
    """Both checks below iterate `known_splits()`, not `dev` alone (D67).

    They read `datasets/dev/matching_policy.json` and nothing else, so the policy published
    beside `dev-synthetic`, `dev-zero-defect` and — the one that matters — the **held-out**
    split was never compared to the shipped rule. All four are emitted by one generator run
    and are identical today, but that was an assumption nothing asserted: precisely D64a's
    shape, where a dev-only loop left the weightiest split outside the universe. An agent
    competes against the policy published with the split it is scored on, so a held-out
    policy that drifted would judge it against a threshold it was never told."""

    def test_matching_policy_declares_every_rule_the_harness_applies(self) -> None:
        """Every rule the scored implementation applies has a published entry (D119).

        This was `test_matching_policy_publishes_every_rule` and it tested six keyword
        substrings — `payable`, `materiality`, `price`, `quantity`, `tax`,
        `cross-multipl`. Its criterion (H13) read *"every generator rule appears in the
        published policy"*, which the check could not possibly establish: the generator is
        deny-guarded and out of tree, so nothing in this repository can enumerate its
        rules. A keyword scan cannot say "every" about a set it cannot see.

        What IS checkable, and is what the criterion now claims: every rule **the shipped
        implementation applies** has an entry, and (below) that entry describes what the
        implementation does. `audit_key` is the independent derivation an agent could run,
        and `audit()` compares it to the generator's output on every split — so binding the
        policy to it closes the one link that was loose."""
        for split in support.known_splits():
            with self.subTest(split=split.name):
                policy = support.read_json(split.policy)
                missing = [key for key in PUBLISHED_RULE_KEYS if key not in policy]
                self.assertEqual(
                    missing, [],
                    f"{split.name}: the policy omits {missing}. Each names a rule the "
                    f"harness applies; an agent competes against what it can read, so a "
                    f"rule with no entry is one it is judged on and never told (D35).",
                )
                self.assertEqual(set(policy["categories"]),
                                 {"PRICE_VARIANCE", "QTY_UNDER_SHIPMENT", "QTY_OVER_SHIPMENT",
                                  "QTY_INVOICE_INFLATED", "TAX_VARIANCE"},
                                 f"{split.name}: published categories differ")

    def test_every_published_rule_describes_what_the_code_does(self) -> None:
        """D53's binding, extended from the three numbers to the rules themselves (D119).

        D53 bound `$0.05`, `$25` and `2%` to `audit_key`'s constants, because a published
        threshold that drifts judges an agent against a rule it was never told. The *rules*
        stayed bound by keyword presence — so `_payable` could become `max(...)` in both
        the generator and the audit, the key would agree with the derivation, the numbers
        would still match, all six keywords would still be present, and the published rule
        would be false.

        Each case below exercises the shipped behaviour **and** asserts the policy states
        it, so the two cannot move apart. The phrase is matched against the entry for that
        rule, not the whole document, or a word appearing anywhere would satisfy it."""
        for split in support.known_splits():
            policy = support.read_json(split.policy)
            for rule_key, phrase, holds, describe in _rule_bindings():
                with self.subTest(split=split.name, rule=rule_key, asserts=describe):
                    self.assertTrue(
                        holds(),
                        f"the shipped implementation no longer does what "
                        f"{rule_key!r} publishes: {describe}",
                    )
                    entry = str(policy.get(rule_key, "")).lower()
                    self.assertIn(
                        phrase, entry,
                        f"{split.name}: the {rule_key!r} entry no longer says {phrase!r}, "
                        f"which is the behaviour the code applies ({describe})",
                    )

    def test_policy_numbers_match_the_shipping_rule_implementation(self) -> None:
        """The published thresholds must equal the ones the shipped code applies (D53).

        D46 bound the policy to the *generator's* constants, which removed drift at
        authoring time — but the generator does not ship, so nothing in the repository
        could detect the published rule diverging from the implementation a reader can
        actually run. The audit command ships and holds the same three constants, so
        binding the policy to those closes it in-repo and in CI.

        An agent competes against the published rule; if it disagrees with the rule the
        harness scores by, the agent is judged against a threshold it was never told."""
        # Derived from the constants, never restated: floor and cap as dollar amounts,
        # rate as the percentage the policy renders.
        floor_token = f"${_FLOOR.normalize():f}"
        cap_token = f"${_CAP.normalize():f}"
        rate_pct = (_RATE * 100).normalize()
        rate_token = f"{rate_pct:f}%"
        for split in support.known_splits():
            with self.subTest(split=split.name):
                policy = support.read_json(split.policy)
                stated = str(policy["materiality_threshold"])
                for token, label in ((floor_token, "floor"), (cap_token, "cap"),
                                     (rate_token, "rate")):
                    self.assertIn(
                        token, stated,
                        f"{split.name}: published policy does not state the {label} the "
                        f"shipped code uses ({token}); policy says: {stated!r}",
                    )


class RoundingTests(unittest.TestCase):
    def test_ratio_rounds_half_up_not_banker(self) -> None:
        quantum = Dc("0.0001")
        # 0.12345 at 4dp: HALF_UP -> 0.1235; banker's (HALF_EVEN) -> 0.1234.
        self.assertEqual(str(Dc("0.12345").quantize(quantum, rounding=ROUND_HALF_UP)), "0.1235")

    def test_no_quantize_in_a_flagging_decision(self) -> None:
        # Display rounding never enters a flagging decision (D23): the audit rule
        # functions call no .quantize / rounding.
        tree = ast.parse((PKG / "audit_key.py").read_text(encoding="utf-8"))
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
            text = path.read_text(encoding="utf-8")
            for marker in bad_markers:
                self.assertNotIn(marker, text, f"{path.name} loads out-of-tree data ({marker})")


if __name__ == "__main__":
    unittest.main()
