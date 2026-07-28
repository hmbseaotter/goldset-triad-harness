"""Validity parity: a dataset `score` refuses, `audit` must also refuse, and by name (D62).

The gap this closes. `audit()` resolved the manifest and read the artifacts itself, never
calling the loader, so it skipped every validator a scoring run applies — reference
resolution (D50), correspondence completeness (D48, D56), multi-purchase-order rates (D47),
tax-field presence (D29). A dataset that `score` rejected with a named cause could reach the
auditor's arithmetic and come back as a bare `KeyError`: a quoted string with nothing to say
that the DATA was at fault, sending a reader to debug the auditor.

Severity is honest here — the failure mode is a confusing message, not a wrong score, which
is why this was the last of the four fixed. But the auditor is the project's defence against
the one failure it cannot otherwise detect, so an auditor that appears broken on malformed
data is a defence people stop trusting.

The parity asserted is deliberately one-directional: everything `score` refuses, `audit`
must refuse. The converse does not hold and must not be asserted — the auditor legitimately
rejects things the scorer never examines, because it derives from inputs the scorer never
reads.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tests import support
from goldset_triad import audit_key
from goldset_triad.dataset import DatasetError, load_dataset


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


def _write(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8", newline="\n")


def _drop_a_correspondence_row(root: Path) -> None:
    key = _read(root / "dev_answer_key.json")
    key["correspondence"].pop()
    _write(root / "dev_answer_key.json", key)


def _phantom_purchase_order(root: Path) -> None:
    key = _read(root / "dev_answer_key.json")
    key["correspondence"][0]["po_number"] = "PO-GHOST"
    _write(root / "dev_answer_key.json", key)


def _expectation_on_a_nonexistent_line(root: Path) -> None:
    key = _read(root / "dev_answer_key.json")
    key["expected_findings"][0]["target"]["line_id"] = "999-NO-SUCH-LINE"
    _write(root / "dev_answer_key.json", key)


def _duplicate_correspondence_row(root: Path) -> None:
    key = _read(root / "dev_answer_key.json")
    key["correspondence"].append(dict(key["correspondence"][0]))
    _write(root / "dev_answer_key.json", key)


def _empty_correspondence(root: Path) -> None:
    key = _read(root / "dev_answer_key.json")
    key["correspondence"] = []
    _write(root / "dev_answer_key.json", key)


def _purchase_order_missing_its_tax_field(root: Path) -> None:
    path = root / "inputs" / "purchase_orders" / "PO-3001.json"
    po = _read(path)
    po.pop("tax")
    _write(path, po)


def _tax_against_nothing_taxable(root: Path) -> None:
    path = root / "inputs" / "purchase_orders" / "PO-3004.json"  # fully exempt split
    po = _read(path)
    po["tax"] = "12.34"
    _write(path, po)


def _negative_taxable_subtotal(root: Path) -> None:
    """A PO whose taxable subtotal goes below zero, with tax kept exactly consistent.

    The variance is zero, so a correct derivation raises nothing — and before D117 the
    cross-multiplied tax test inverted below zero and flagged it anyway."""
    path = next((root / "inputs" / "purchase_orders").glob("*.json"))
    po = json.loads(path.read_text(encoding="utf-8"))
    subtotal = Decimal(0)
    for line in po["lines"]:
        if line.get("taxable") is True:
            line["extended"] = "-" + str(line["extended"]).lstrip("-")
            subtotal += Decimal(str(line["extended"]))
    po["tax"] = str((subtotal * Decimal("0.08")).quantize(Decimal("0.01")))
    _write(path, po)


def _taxable_flag_is_not_a_bool(root: Path) -> None:
    """`taxable: 1` — truthy, and not `True`.

    Both readers test the flag with `is True`, so this silently drops the line from the
    tax basis in each of them *identically*: the audit cannot catch what it shares."""
    path = next((root / "inputs" / "purchase_orders").glob("*.json"))
    po = json.loads(path.read_text(encoding="utf-8"))
    for line in po["lines"]:
        if line.get("taxable") is True:
            line["taxable"] = 1
            break
    _write(path, po)


def _invoice_line_omits_its_taxable_flag(root: Path) -> None:
    """The index side, which was never validated at all while the audit summed it."""
    path = root / "dev_invoice_index.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    del index["invoices"][0]["lines"][0]["taxable"]
    _write(path, index)


#: Each mutation makes the dev split invalid in a way the loader models.
MALFORMATIONS = [
    ("a dropped correspondence row", _drop_a_correspondence_row),
    ("a phantom purchase order", _phantom_purchase_order),
    ("an expectation on a nonexistent line", _expectation_on_a_nonexistent_line),
    ("a duplicated correspondence row", _duplicate_correspondence_row),
    ("an empty correspondence list", _empty_correspondence),
    ("a purchase order missing its tax field", _purchase_order_missing_its_tax_field),
    ("tax charged against nothing taxable", _tax_against_nothing_taxable),
    # D117 — the three the audit sweep found. Each is load-bearing arithmetic that both
    # readers consumed without either validating it.
    ("a negative taxable subtotal", _negative_taxable_subtotal),
    ("a taxable flag that is not a bool", _taxable_flag_is_not_a_bool),
    ("an invoice line omitting its taxable flag", _invoice_line_omits_its_taxable_flag),
]


class TaxDerivationPreconditionTests(unittest.TestCase):
    """The cross-multiplied tax test had an unstated precondition (D117).

    D28 forbids division on any flagging path, so `_derive_tax` compares
    `|variance| >= threshold` by multiplying both sides by `po_taxable`. That preserves
    the inequality only while `po_taxable > 0` — the zero case is handled separately, and
    the negative case inverts it, making `left` (an absolute value) always the greater and
    flagging **every** invoice regardless of its tax."""

    def test_a_zero_variance_invoice_does_not_flag(self) -> None:
        """The control. An invoice taxed at exactly the PO's rate has no variance, so
        nothing may flag — this is what the inversion broke."""
        self.assertFalse(
            audit_key._derive_tax(
                Decimal("80"), Decimal("1000"), Decimal("80"), Decimal("1000")
            )
        )

    def test_a_material_variance_still_flags(self) -> None:
        """The converse, so the guard cannot be satisfied by refusing to flag at all."""
        self.assertTrue(
            audit_key._derive_tax(
                Decimal("80"), Decimal("1000"), Decimal("120"), Decimal("1000")
            )
        )

    def test_a_negative_taxable_subtotal_is_refused_rather_than_inverted(self) -> None:
        """Kept in the arithmetic as well as the loader (D117).

        The loader now rejects a negative subtotal, so this is unreachable through
        `audit()`. The guard stays because a silent inversion must not depend on a caller
        two modules away having run first — and because the old behaviour was to return a
        confident, wrong `True`."""
        with self.assertRaises(DatasetError) as caught:
            audit_key._derive_tax(
                Decimal("-80"), Decimal("-1000"), Decimal("-80"), Decimal("-1000")
            )
        message = str(caught.exception)
        self.assertIn("negative taxable subtotal", message)
        self.assertIn("cross-multiplied", message)

    def test_the_zero_subtotal_case_is_untouched(self) -> None:
        """D28's own boundary (H45): with nothing taxable, any tax at or above the floor
        is a variance. The negative guard must not have moved this."""
        self.assertTrue(
            audit_key._derive_tax(Decimal(0), Decimal(0), Decimal("0.05"), Decimal(0))
        )
        self.assertFalse(
            audit_key._derive_tax(Decimal(0), Decimal(0), Decimal("0.04"), Decimal(0))
        )


class TaxableFlagShippedStateTests(unittest.TestCase):
    """Locked at zero (D68), which is what makes D117 cheap.

    Every line on every split this machine can see already carries a real bool and a
    non-negative subtotal, so the class closes before an instance exists rather than
    after one is found."""

    def test_every_shipped_line_declares_a_boolean_taxable_flag(self) -> None:
        checked = 0
        for split in support.known_splits():
            for po_path in sorted((split.inputs / "purchase_orders").glob("*.json")):
                po = json.loads(po_path.read_text(encoding="utf-8"))
                for line in po["lines"]:
                    checked += 1
                    with self.subTest(document=po_path.name, line=line.get("line_no")):
                        self.assertIsInstance(line.get("taxable"), bool)
            index = json.loads(split.index.read_text(encoding="utf-8"))
            for invoice in index["invoices"]:
                for line in invoice["lines"]:
                    checked += 1
                    with self.subTest(invoice=invoice["invoice_id"],
                                      line=line.get("line_id")):
                        self.assertIsInstance(line.get("taxable"), bool)
        self.assertGreater(
            checked, 20,
            "the scan found almost no lines, so it is passing over an empty set",
        )


class ValidityParityTests(unittest.TestCase):
    def test_everything_score_refuses_the_audit_also_refuses_by_name(self) -> None:
        for label, mutate in MALFORMATIONS:
            with self.subTest(malformation=label), tempfile.TemporaryDirectory() as td:
                manifest = support.copy_dataset("dev", Path(td) / "ds")
                mutate(manifest.parent)

                # The scoring path refuses, with a cause.
                with self.assertRaises(DatasetError, msg=f"{label}: score accepted it") as ctx:
                    load_dataset(str(manifest), Path(td))
                score_message = str(ctx.exception)
                self.assertTrue(score_message.strip(), f"{label}: score's error was empty")

                # The audit path must refuse too, without raising, and say something.
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    code = audit_key.main(["--dataset", str(manifest), "--datasets-root", td])
                audit_message = err.getvalue()

                self.assertEqual(
                    code, 2,
                    f"{label}: audit exited {code}; a malformed dataset is an error (2), "
                    f"not a divergence (1) and not success (0)",
                )
                self.assertIn("audit error", audit_message)
                self.assertNotIn(
                    "Traceback", audit_message,
                    f"{label}: audit surfaced a traceback instead of a named cause",
                )
                # Not a bare exception repr: a KeyError alone prints as a quoted key with
                # nothing to indicate the data is at fault.
                self.assertGreater(
                    len(audit_message.strip()), len("audit error: 'x'"),
                    f"{label}: audit's message says too little to act on: "
                    f"{audit_message!r}",
                )

    def test_the_shipped_splits_pass_both_doors(self) -> None:
        """Positive control: the parity check is not passing by refusing everything."""
        for name in support.DEV_DATASETS:
            with self.subTest(dataset=name):
                load_dataset(name, support.DATASETS)  # must not raise
                err, out = io.StringIO(), io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                    code = audit_key.main(
                        ["--dataset", name, "--datasets-root", str(support.DATASETS)]
                    )
                self.assertEqual(code, 0, f"{name}: audit reported {err.getvalue()}")

    def test_audit_still_derives_independently(self) -> None:
        """Routing validity through the loader must not make the auditor trust the key.

        The point of the audit (D35) is that it disagrees when the key is wrong. A corrupt
        expectation that is still structurally valid must therefore still be caught — if
        sharing the loader had made the auditor defer to the key, this would pass silently.
        """
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "ds")
            key = _read(manifest.parent / "dev_answer_key.json")
            # Retarget an expectation onto a different REAL line: structurally valid, so
            # the loader admits it, and wrong, so the auditor must object.
            targets = {
                (f["target"]["document_id"], f["target"]["line_id"])
                for f in key["expected_findings"]
            }
            loaded = load_dataset("dev", support.DATASETS)
            spare = sorted(loaded.invoice_index.inventory.line_targets - targets)
            self.assertTrue(spare, "fixture drift: every invoice line already carries a finding")
            key["expected_findings"][0]["target"]["document_id"] = spare[0][0]
            key["expected_findings"][0]["target"]["line_id"] = spare[0][1]
            _write(manifest.parent / "dev_answer_key.json", key)

            load_dataset(str(manifest), Path(td))  # structurally fine

            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = audit_key.main(["--dataset", str(manifest), "--datasets-root", td])
            self.assertEqual(code, 1, "the audit failed to notice a mis-targeted expectation")
            self.assertIn("DIVERGENCES", err.getvalue())


if __name__ == "__main__":
    unittest.main()
