"""Key-audit command — an independent derivation that diffs against the key (D35).

The answer key is the riskiest artifact in the project: a wrong key produces
confidently wrong scores that no scoring test can catch, because the scoring tests
assert the scorer agrees with the key. This command is the defence. It re-derives
the expected findings from the structured inputs — invoice index, purchase orders,
goods receipts, and the invoice->PO->receipt correspondence declared in the key —
by a **separate implementation** of the domain rules, and diffs its derivation
against the declared key.

Two properties make this honest:

- It **never runs inside a scoring run**. Nothing in the scoring path imports this
  module; a derivation bug must never be able to become ground truth mid-score.
- It is a **consistency check, not a correctness proof**. The generator and this
  auditor share an author, so their independence is weak: this catches arithmetic
  slips, transcription errors and post-regeneration drift, not a shared
  misunderstanding of the rule itself.

The rules below are re-implemented here, deliberately not shared with the
generator. They make flagging decisions, so — like the generator — they use no
division (D28): the tax test is cross-multiplied.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .constants import DOCUMENT_LINE_SENTINEL
from .dataset import DatasetError, load_dataset, resolve_manifest

_FLOOR = Decimal("0.05")
_CAP = Decimal("25")
_RATE = Decimal("0.02")


# --- independent rule implementation (no shared code with the generator) --------


def _threshold(basis: Decimal) -> Decimal:
    proportional = basis * _RATE
    inner = proportional if proportional < _CAP else _CAP
    return inner if inner > _FLOOR else _FLOOR


def _material(magnitude: Decimal, basis: Decimal) -> bool:
    return magnitude >= _threshold(basis)


def _payable(ordered: Decimal, received: Decimal) -> Decimal:
    return ordered if ordered <= received else received


@dataclass(frozen=True)
class _Line:
    ordered: Decimal
    received: Decimal
    invoiced: Decimal
    po_price: Decimal
    inv_price: Decimal


def _derive_line(line: _Line) -> set[str]:
    """Derived line-scoped categories for one reconciled line."""
    out: set[str] = set()
    payable = _payable(line.ordered, line.received)
    basis = payable * line.po_price

    price_var = (line.inv_price - line.po_price) * payable
    magnitude = price_var if price_var >= 0 else -price_var
    if _material(magnitude, basis):
        out.add("PRICE_VARIANCE")

    if line.invoiced > payable:
        excess = line.invoiced - payable
        if _material(excess * line.po_price, basis):
            if line.received < line.ordered:
                out.add("QTY_UNDER_SHIPMENT")
            elif line.received > line.ordered:
                out.add("QTY_OVER_SHIPMENT")
            else:
                out.add("QTY_INVOICE_INFLATED")
    return out


def _derive_tax(
    po_tax: Decimal, po_taxable: Decimal, inv_tax: Decimal, inv_taxable: Decimal
) -> bool:
    if po_taxable == 0:
        magnitude = inv_tax if inv_tax >= 0 else -inv_tax
        return magnitude >= _threshold(Decimal(0))
    threshold = _threshold(inv_taxable)
    left = inv_tax * po_taxable - po_tax * inv_taxable
    left = left if left >= 0 else -left
    return left >= threshold * po_taxable


# --- input gathering ------------------------------------------------------------


def _dec(value: object, what: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 - any parse failure is a dataset error
        raise DatasetError(f"{what}: not a number ({value!r})") from exc


def _read(path: Path, what: str) -> object:
    if not path.is_file():
        raise DatasetError(f"{what} not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


@dataclass
class _Inputs:
    po_lines: dict[tuple[str, str], dict[str, object]]  # (po_number, po_line_no) -> line
    po_tax: dict[str, Decimal]
    po_taxable: dict[str, Decimal]
    received: dict[tuple[str, str], Decimal]  # (po_number, po_line_no) -> summed received
    inv_lines: dict[tuple[str, str], dict[str, object]]  # (invoice_id, line_id) -> line
    inv_tax: dict[str, Decimal]
    inv_taxable: dict[str, Decimal]


def _gather(inputs_dir: Path, index_path: Path) -> _Inputs:
    po_lines: dict[tuple[str, str], dict[str, object]] = {}
    po_tax: dict[str, Decimal] = {}
    po_taxable: dict[str, Decimal] = {}
    for po_path in sorted((inputs_dir / "purchase_orders").glob("*.json")):
        po = _read(po_path, "purchase order")
        assert isinstance(po, dict)
        pon = str(po["po_number"])
        po_tax[pon] = _dec(po["tax"], f"PO {pon} tax")
        subtotal = Decimal(0)
        for ln in po["lines"]:
            key = (pon, str(ln["line_no"]))
            po_lines[key] = ln
            if ln.get("taxable") is True:
                subtotal += _dec(ln["extended"], f"PO {pon} line extended")
        po_taxable[pon] = subtotal

    received: dict[tuple[str, str], Decimal] = {}
    for gr_path in sorted((inputs_dir / "goods_receipts").glob("*.json")):
        gr = _read(gr_path, "goods receipt")
        assert isinstance(gr, dict)
        pon = str(gr["po_number"])
        for ln in gr["lines"]:
            key = (pon, str(ln["po_line_no"]))
            received[key] = received.get(key, Decimal(0)) + _dec(
                ln["qty_received"], f"GR line received"
            )

    index = _read(index_path, "invoice index")
    assert isinstance(index, dict)
    inv_lines: dict[tuple[str, str], dict[str, object]] = {}
    inv_tax: dict[str, Decimal] = {}
    inv_taxable: dict[str, Decimal] = {}
    for inv in index["invoices"]:
        iid = str(inv["invoice_id"])
        inv_tax[iid] = _dec(inv["tax"], f"invoice {iid} tax")
        subtotal = Decimal(0)
        for ln in inv["lines"]:
            inv_lines[(iid, str(ln["line_id"]))] = ln
            if ln.get("taxable") is True:
                subtotal += _dec(ln["extended"], f"invoice {iid} line extended")
        inv_taxable[iid] = subtotal

    return _Inputs(
        po_lines=po_lines,
        po_tax=po_tax,
        po_taxable=po_taxable,
        received=received,
        inv_lines=inv_lines,
        inv_tax=inv_tax,
        inv_taxable=inv_taxable,
    )


# --- derivation + diff ----------------------------------------------------------

_Key = tuple[str, str, str, str, str]  # status, category, scope, doc, line


def _derive_expected(key: dict[str, object], inputs: _Inputs) -> set[_Key]:
    derived: set[_Key] = set()
    invoices_seen: set[tuple[str, str]] = set()
    correspondence = key.get("correspondence", [])
    assert isinstance(correspondence, list)
    for entry in correspondence:
        assert isinstance(entry, dict)
        iid = str(entry["invoice_id"])
        line_id = str(entry["invoice_line_id"])
        pon = str(entry["po_number"])
        pln = str(entry["po_line_no"])
        # Named causes rather than a bare KeyError. `audit()` resolves the manifest
        # directly and does NOT run the loader's validation, so it can still meet an
        # unresolved reference; reporting it as "audit error: KeyError ('PO-X','P1')"
        # would name a tuple instead of the fault (D50).
        try:
            inv_ln = inputs.inv_lines[(iid, line_id)]
        except KeyError:
            raise DatasetError(
                f"the answer key's correspondence names invoice line {iid} line "
                f"{line_id}, which the structured invoice index does not contain"
            ) from None
        try:
            po_ln = inputs.po_lines[(pon, pln)]
        except KeyError:
            raise DatasetError(
                f"the answer key's correspondence names line {pln} of purchase order "
                f"{pon}, which the inputs do not contain"
            ) from None
        line = _Line(
            ordered=_dec(po_ln["qty_ordered"], "ordered"),
            received=inputs.received.get((pon, pln), Decimal(0)),
            invoiced=_dec(inv_ln["qty_invoiced"], "invoiced"),
            po_price=_dec(po_ln["unit_price"], "po price"),
            inv_price=_dec(inv_ln["unit_price"], "inv price"),
        )
        for cat in _derive_line(line):
            derived.add(("DISCREPANCY", cat, "LINE", iid, line_id))
        invoices_seen.add((iid, pon))

    # Tax is per invoice; derive once per (invoice, PO) pair seen.
    for iid, pon in sorted(invoices_seen):
        if _derive_tax(
            inputs.po_tax.get(pon, Decimal(0)),
            inputs.po_taxable.get(pon, Decimal(0)),
            inputs.inv_tax.get(iid, Decimal(0)),
            inputs.inv_taxable.get(iid, Decimal(0)),
        ):
            derived.add(("DISCREPANCY", "TAX_VARIANCE", "DOCUMENT", iid, DOCUMENT_LINE_SENTINEL))
    return derived


def _key_set(key: dict[str, object]) -> set[_Key]:
    out: set[_Key] = set()
    for e in key["expected_findings"]:  # type: ignore[union-attr]
        assert isinstance(e, dict)
        t = e["target"]
        out.add(
            (
                str(e["status"]),
                str(e["category"]),
                str(e["scope"]),
                str(t["document_id"]),
                str(t["line_id"]),
            )
        )
    return out


def audit(dataset_ref: str, search_root: Path) -> list[str]:
    """Return a list of divergence messages; empty means consistent."""
    # Validity comes through the SAME front door as a scoring run (D62). This used to call
    # resolve_manifest alone, so every validator the loader runs -- reference resolution
    # (D50), correspondence completeness (D48, D56), multi-PO rates (D47), tax-field
    # presence (D29) -- was skipped here. A dataset that `score` refused with a named cause
    # could reach the auditor's arithmetic and surface as a bare KeyError, sending a reader
    # to debug the auditor over a defect in the data.
    #
    # This does NOT weaken the independence D35 requires. That independence is about
    # deriving FINDINGS by a separate implementation, which the code below still does, from
    # its own read of the artifacts. The loader applies no domain rule; it decides whether
    # the dataset is well-formed at all, and there is no value in two answers to that.
    load_dataset(dataset_ref, search_root)

    manifest = resolve_manifest(dataset_ref, search_root)
    key = _read(manifest.key_path, "answer key")
    if not isinstance(key, dict):
        # Was an `assert`, which `python -O` strips -- leaving the failure to surface later
        # as an unrelated TypeError deep in the derivation.
        raise DatasetError(f"answer key is not a JSON object: {manifest.key_path}")
    inputs = _gather(manifest.inputs_dir, manifest.invoice_index_path)
    declared = _key_set(key)
    derived = _derive_expected(key, inputs)

    messages: list[str] = []
    for missing in sorted(derived - declared):
        messages.append(
            f"DERIVED-BUT-ABSENT: {missing[1]} {missing[2]} on {missing[3]} "
            f"line {missing[4]} is derivable from the inputs but not in the key"
        )
    for extra in sorted(declared - derived):
        messages.append(
            f"IN-KEY-BUT-UNDERIVED: {extra[1]} {extra[2]} on {extra[3]} "
            f"line {extra[4]} is in the key but the auditor does not derive it"
        )
    return messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="goldset-triad-audit-key",
        description="Independently derive expectations and diff them against the answer key "
        "(a consistency check, not a proof of correctness).",
    )
    parser.add_argument("--dataset", required=True, help="dataset identifier or manifest path")
    parser.add_argument("--datasets-root", default="datasets", help="root for identifier resolution")
    args = parser.parse_args(argv)
    try:
        messages = audit(args.dataset, Path(args.datasets_root))
    except DatasetError as exc:
        # Already a named cause; pass it through as written.
        sys.stderr.write(f"audit error: {exc}\n")
        return 2
    except (KeyError, TypeError, ValueError, IndexError, ArithmeticError) as exc:
        # Residual data-shape faults the loader does not model (D62). The catch is
        # deliberately a list of families rather than `Exception`: a bare KeyError printed
        # alone is just a quoted string with no hint that the DATA is at fault, and
        # catching everything would swallow genuine auditor bugs, which must stay loud.
        sys.stderr.write(
            f"audit error: the dataset is malformed in a way the loader does not model - "
            f"{type(exc).__name__}: {exc}\n"
        )
        return 2
    if messages:
        sys.stderr.write(
            "KEY AUDIT FOUND DIVERGENCES (consistency check, not a correctness proof):\n"
        )
        for m in messages:
            sys.stderr.write(f"  - {m}\n")
        return 1
    sys.stdout.write(
        "key audit: consistent - every declared finding is independently derivable, "
        "and no derivable finding is missing (consistency check, not a correctness proof)\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
