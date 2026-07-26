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


#: Each mutation makes the dev split invalid in a way the loader models.
MALFORMATIONS = [
    ("a dropped correspondence row", _drop_a_correspondence_row),
    ("a phantom purchase order", _phantom_purchase_order),
    ("an expectation on a nonexistent line", _expectation_on_a_nonexistent_line),
    ("a duplicated correspondence row", _duplicate_correspondence_row),
    ("an empty correspondence list", _empty_correspondence),
    ("a purchase order missing its tax field", _purchase_order_missing_its_tax_field),
    ("tax charged against nothing taxable", _tax_against_nothing_taxable),
]


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
