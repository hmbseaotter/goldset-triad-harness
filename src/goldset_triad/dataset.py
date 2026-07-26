"""Ground-truth loading and dataset validation.

Resolves a dataset (by identifier or manifest path) into everything the scorer
needs, and validates the whole dataset at load. Validation is *dataset integrity*
— timestamps, tax-field presence, the zero-taxable/non-zero-tax contradiction —
and is deliberately kept apart from the scored domain rules: nothing here computes
a payable quantity, a materiality threshold, or a tax-variance decision. Those
live only in the key generator and the audit command (D35).

The scorer reads the answer key (expected findings) and the structured invoice
index (line inventory and invoice count). It NEVER parses an invoice document: the
invoices are supplier PDFs whose structured data comes from the index, so no
document parser sits on the scoring path (D34). The PDFs are still digested — by
raw bytes, never parsed — because they are inputs that move the score (D27).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from .schema import Finding, SchemaError, parse_finding
from .scoring import LineInventory

_TIMESTAMP_RE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class DatasetError(Exception):
    """A dataset is missing, unreadable, or malformed. Every instance names its
    specific cause, so a halt message is never generic (N-observability)."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path, what: str) -> Any:
    if not path.is_file():
        raise DatasetError(f"{what} not found or unreadable: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DatasetError(f"{what} not readable: {path} ({exc})") from exc
    try:
        # parse_float=Decimal so no monetary value is ever a float (D-value).
        return json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise DatasetError(f"{what} is not valid JSON: {path} ({exc})") from exc


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_timestamp(value: Any, where: str) -> None:
    """Reject any timestamp that is not `Z`-suffixed second-precision ISO-8601 (D6)."""
    if not isinstance(value, str) or not _TIMESTAMP_RE.match(value):
        raise DatasetError(
            f"timestamp at {where} is not Z-suffixed second-precision ISO-8601: {value!r}"
        )
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise DatasetError(f"timestamp at {where} is not a real instant: {value!r}") from exc


def _decimal(value: Any, where: str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except (ValueError, ArithmeticError):
            pass
    raise DatasetError(f"expected a numeric value at {where}, got {value!r}")


# ---------------------------------------------------------------------------
# Manifest resolution (D2, D17, D34)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Manifest:
    identifier: str
    version: str
    inputs_dir: Path
    key_path: Path
    invoice_index_path: Path
    manifest_path: Path


def resolve_manifest(dataset_ref: str, search_root: Path) -> Manifest:
    """Resolve a dataset by identifier or by path (D2).

    A path ending in a JSON file is taken as the manifest directly. Otherwise
    ``dataset_ref`` is an identifier resolved against ``search_root`` as
    ``<root>/<id>/manifest.json``. No dataset location is hardcoded — the search
    root is a parameter, so an out-of-tree held-out split needs only a path."""
    ref_path = Path(dataset_ref)
    if ref_path.suffix == ".json" and ref_path.is_file():
        manifest_path = ref_path
    else:
        manifest_path = search_root / dataset_ref / "manifest.json"
    if not manifest_path.is_file():
        raise DatasetError(
            f"dataset '{dataset_ref}' not found (looked for manifest at {manifest_path})"
        )
    raw = _read_json(manifest_path, "manifest")
    if not isinstance(raw, dict):
        raise DatasetError(f"manifest is not a JSON object: {manifest_path}")
    base = manifest_path.parent
    try:
        identifier = str(raw["identifier"])
        version = str(raw["version"])
        inputs_dir = (base / str(raw["inputs_dir"])).resolve()
        key_path = (base / str(raw["key_path"])).resolve()
        invoice_index_path = (base / str(raw["invoice_index_path"])).resolve()
    except KeyError as exc:
        raise DatasetError(
            f"manifest {manifest_path} is missing required field {exc}; it must name "
            "identifier, version, inputs_dir, key_path and invoice_index_path"
        ) from exc
    if not inputs_dir.is_dir():
        raise DatasetError(f"manifest inputs_dir does not exist: {inputs_dir}")
    return Manifest(
        identifier=identifier,
        version=version,
        inputs_dir=inputs_dir,
        key_path=key_path,
        invoice_index_path=invoice_index_path,
        manifest_path=manifest_path,
    )


# ---------------------------------------------------------------------------
# Answer key (D22, D35)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnswerKey:
    expected_findings: tuple[Finding, ...]
    correspondence: tuple[dict[str, Any], ...]
    sha256: str


def load_answer_key(path: Path) -> AnswerKey:
    """Load expected findings and the invoice->PO->receipt correspondence.

    The scorer uses only the expected findings; the correspondence exists for the
    key-audit command (D22) and is carried through but never consulted here."""
    if not path.is_file():
        # A missing/unreadable key must halt, never be treated as a pass (I4).
        raise DatasetError(f"answer key is unreadable: {path}")
    raw = _read_json(path, "answer key")
    if not isinstance(raw, dict):
        raise DatasetError(f"answer key is not a JSON object: {path}")
    findings_raw = raw.get("expected_findings")
    if not isinstance(findings_raw, list):
        raise DatasetError("answer key must carry an 'expected_findings' list")
    try:
        expected = tuple(parse_finding(item, i) for i, item in enumerate(findings_raw))
    except SchemaError as exc:
        raise DatasetError(f"answer key contains a malformed expected finding: {exc}") from exc
    correspondence_raw = raw.get("correspondence", [])
    if not isinstance(correspondence_raw, list):
        raise DatasetError("answer key 'correspondence', when present, must be a list")
    return AnswerKey(
        expected_findings=expected,
        correspondence=tuple(correspondence_raw),
        sha256=sha256_file(path),
    )


# ---------------------------------------------------------------------------
# Structured invoice index (D34)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InvoiceIndex:
    inventory: LineInventory
    raw: dict[str, Any]
    sha256: str


def load_invoice_index(path: Path) -> InvoiceIndex:
    """Load the complete invoice line inventory and validate invoice-side integrity.

    Builds the :class:`LineInventory` that target validation needs, covering clean
    lines as well as discrepant ones, and checks each invoice's timestamp and the
    presence of its tax field (D29, D34)."""
    if not path.is_file():
        raise DatasetError(f"structured invoice index is unreadable: {path}")
    raw = _read_json(path, "invoice index")
    if not isinstance(raw, dict):
        raise DatasetError(f"invoice index is not a JSON object: {path}")
    invoices = raw.get("invoices")
    if not isinstance(invoices, list) or not invoices:
        raise DatasetError("invoice index must carry a non-empty 'invoices' list")

    line_targets: set[tuple[str, str]] = set()
    documents: set[str] = set()
    for inv in invoices:
        if not isinstance(inv, dict):
            raise DatasetError("each invoice in the index must be an object")
        invoice_id = inv.get("invoice_id")
        if not isinstance(invoice_id, str) or not invoice_id:
            raise DatasetError("an invoice in the index has no 'invoice_id'")
        validate_timestamp(inv.get("timestamp"), f"invoice {invoice_id} timestamp")
        # The tax field must be present, never absent or null, so 'absent' is never
        # confusable with 'zero' (D29).
        if "tax" not in inv or inv.get("tax") is None:
            raise DatasetError(
                f"invoice {invoice_id} omits its tax field; it must be present, "
                "carrying zero where nothing is taxable (D29)"
            )
        _decimal(inv.get("tax"), f"invoice {invoice_id} tax")
        documents.add(invoice_id)
        lines = inv.get("lines")
        if not isinstance(lines, list) or not lines:
            raise DatasetError(f"invoice {invoice_id} has no lines")
        for ln in lines:
            if not isinstance(ln, dict):
                raise DatasetError(f"invoice {invoice_id} has a malformed line")
            line_id = ln.get("line_id")
            if not isinstance(line_id, str) or not line_id:
                raise DatasetError(
                    f"invoice {invoice_id} has a line with no explicit 'line_id' (D22)"
                )
            line_targets.add((invoice_id, line_id))

    inventory = LineInventory(
        line_targets=frozenset(line_targets),
        documents=frozenset(documents),
        invoice_count=len(invoices),
    )
    return InvoiceIndex(inventory=inventory, raw=raw, sha256=sha256_file(path))


# ---------------------------------------------------------------------------
# Input documents: PO and goods-receipt validation (D29, D31, D6)
# ---------------------------------------------------------------------------


def _validate_purchase_orders(inputs_dir: Path) -> None:
    po_dir = inputs_dir / "purchase_orders"
    if not po_dir.is_dir():
        raise DatasetError(f"inputs are missing a purchase_orders/ directory: {po_dir}")
    for po_path in sorted(po_dir.glob("*.json")):
        raw = _read_json(po_path, "purchase order")
        if not isinstance(raw, dict):
            raise DatasetError(f"purchase order is not a JSON object: {po_path}")
        po_number = str(raw.get("po_number", po_path.name))
        validate_timestamp(raw.get("timestamp"), f"purchase order {po_number} timestamp")
        if "tax" not in raw or raw.get("tax") is None:
            raise DatasetError(
                f"purchase order {po_number} omits its tax field; it must be present, "
                "carrying zero where nothing is taxable (D29)"
            )
        po_tax = _decimal(raw.get("tax"), f"purchase order {po_number} tax")
        lines = raw.get("lines")
        if not isinstance(lines, list) or not lines:
            raise DatasetError(f"purchase order {po_number} has no lines")
        # Taxable subtotal = sum of extended amounts on taxable lines. This is a
        # dataset-integrity check (D29), not a scored rule: it decides whether the
        # dataset is coherent, not whether a discrepancy exists.
        taxable_subtotal = Decimal(0)
        for ln in lines:
            if not isinstance(ln, dict):
                raise DatasetError(f"purchase order {po_number} has a malformed line")
            if ln.get("taxable") is True:
                taxable_subtotal += _decimal(
                    ln.get("extended"), f"PO {po_number} line extended"
                )
        if taxable_subtotal == 0 and po_tax > 0:
            raise DatasetError(
                f"purchase order {po_number} is malformed: it has no taxable lines "
                f"(taxable subtotal zero) yet charges tax {po_tax} (D29)"
            )


def _validate_goods_receipts(inputs_dir: Path) -> None:
    gr_dir = inputs_dir / "goods_receipts"
    if not gr_dir.is_dir():
        raise DatasetError(f"inputs are missing a goods_receipts/ directory: {gr_dir}")
    for gr_path in sorted(gr_dir.glob("*.json")):
        raw = _read_json(gr_path, "goods receipt")
        if not isinstance(raw, dict):
            raise DatasetError(f"goods receipt is not a JSON object: {gr_path}")
        grn = str(raw.get("grn_number", gr_path.name))
        validate_timestamp(raw.get("timestamp"), f"goods receipt {grn} timestamp")


def _po_tax_facts(inputs_dir: Path) -> dict[str, tuple[Decimal, Decimal]]:
    """po_number -> (tax, taxable_subtotal). Reread here rather than threaded through
    _validate_purchase_orders, which deliberately validates one PO at a time."""
    facts: dict[str, tuple[Decimal, Decimal]] = {}
    for po_path in sorted((inputs_dir / "purchase_orders").glob("*.json")):
        raw = _read_json(po_path, "purchase order")
        if not isinstance(raw, dict):
            continue
        po_number = str(raw.get("po_number", po_path.name))
        tax = _decimal(raw.get("tax"), f"purchase order {po_number} tax")
        subtotal = Decimal(0)
        lines = raw.get("lines")
        if isinstance(lines, list):
            for ln in lines:
                if isinstance(ln, dict) and ln.get("taxable") is True:
                    subtotal += _decimal(ln.get("extended"), f"PO {po_number} line extended")
        facts[po_number] = (tax, subtotal)
    return facts


def _validate_multi_po_tax_rates(answer_key: AnswerKey, inputs_dir: Path) -> None:
    """Reject a multi-PO invoice whose POs carry DIFFERING tax rates (D47).

    Which PO's rate governs an invoice spanning several is **unspecified**. Both the
    generator and the key auditor happen to test tax per (invoice, PO) pair and so flag
    if *any* rate says material — behaviour that was never decided, only implemented.
    Rather than let that silently produce a wrong key once multi-PO data exists, an
    invoice whose referenced POs disagree on rate is rejected as unspecified. Equal
    rates are unambiguous and stay allowed.

    Rates are compared by CROSS-MULTIPLICATION, not division: rate_a == rate_b iff
    tax_a * taxable_b == tax_b * taxable_a. Exact, and it needs no precision context.
    A zero taxable subtotal has no derivable rate, so such POs are compared only on
    whether they too are zero-rated.

    A TOLERANCE is required, and exact equality would be a bug. A PO's tax is a rate
    applied to a subtotal and then quantized to cents, so two POs authored at the same
    rate derive slightly different rates: at 8.7%, subtotals of 3312.51 and 912.00 give
    288.19 and 79.34, and cross-multiplying yields 262829.28 against 262814.54. The
    residual is bounded by the quantization: with |tax - rate*subtotal| <= half a cent on
    each side, the cross-multiplied difference cannot exceed half a cent times the sum of
    the subtotals. A genuinely different rate exceeds that by orders of magnitude, so the
    tolerance separates rounding from disagreement without weakening the check.
    """
    half_cent = Decimal("0.005")
    facts = _po_tax_facts(inputs_dir)
    by_invoice: dict[str, list[str]] = {}
    for entry in answer_key.correspondence:
        invoice_id = str(entry.get("invoice_id", ""))
        po_number = str(entry.get("po_number", ""))
        if not invoice_id or not po_number:
            continue
        seen = by_invoice.setdefault(invoice_id, [])
        if po_number not in seen:
            seen.append(po_number)

    for invoice_id, po_numbers in sorted(by_invoice.items()):
        if len(po_numbers) < 2:
            continue
        reference = po_numbers[0]
        ref_tax, ref_sub = facts.get(reference, (Decimal(0), Decimal(0)))
        for other in po_numbers[1:]:
            oth_tax, oth_sub = facts.get(other, (Decimal(0), Decimal(0)))
            if ref_sub == 0 or oth_sub == 0:
                # No derivable rate on at least one side; they agree only if both are
                # zero-rated (nothing taxable and nothing charged).
                same = ref_sub == 0 and oth_sub == 0 and ref_tax == 0 and oth_tax == 0
            else:
                residual = ref_tax * oth_sub - oth_tax * ref_sub
                if residual < 0:
                    residual = -residual
                same = residual <= half_cent * (ref_sub + oth_sub)
            if not same:
                raise DatasetError(
                    f"invoice {invoice_id} references purchase orders {reference} and "
                    f"{other}, whose tax rates differ. Tax attribution across multiple "
                    f"purchase orders is UNSPECIFIED (D47): expected tax would have to "
                    f"apportion each PO's rate over that PO's own invoiced taxable "
                    f"lines. Until that is specified and implemented, such a dataset is "
                    f"rejected rather than keyed by whichever purchase order happens to "
                    f"flag first."
                )


def _validate_correspondence_completeness(
    answer_key: AnswerKey, invoice_index: InvoiceIndex
) -> None:
    """Every invoice line in the index must have a correspondence entry (D48).

    The key audit derives expectations by walking the correspondence declared in the
    key it is auditing, so a key that omits BOTH a correspondence entry and the finding
    that entry would have produced is self-consistently wrong and passes the audit —
    the auditor never looks at that line. That hole cannot be closed from inside the
    audit, because the correspondence has no other source (D22). It can be closed here:
    if every line is covered, the audit has looked at every line.
    """
    if not answer_key.correspondence:
        return  # a key may legitimately declare none; nothing to check against
    covered = {
        (str(e.get("invoice_id", "")), str(e.get("invoice_line_id", "")))
        for e in answer_key.correspondence
    }
    missing = sorted(
        target
        for target in invoice_index.inventory.line_targets
        if target not in covered
    )
    if missing:
        shown = ", ".join(f"{i} line {ln}" for i, ln in missing[:5])
        more = "" if len(missing) <= 5 else f" (and {len(missing) - 5} more)"
        raise DatasetError(
            f"{len(missing)} invoice line(s) have no correspondence entry in the answer "
            f"key: {shown}{more}. The key audit walks the declared correspondence, so an "
            f"uncovered line is a line the audit never examines — an omission there is "
            f"self-consistent and would pass silently (D48)."
        )


# ---------------------------------------------------------------------------
# Aggregate inputs digest (D27)
# ---------------------------------------------------------------------------


def per_file_digests(inputs_dir: Path) -> list[tuple[str, str]]:
    """Per-file (relative-path, sha256) pairs, sorted byte-wise by path (D27).

    Paths are normalized relative to ``inputs_dir`` with forward slashes so a
    Windows and a Linux checkout of identical data digest identically; each file's
    raw bytes are hashed with no text transformation (the invoices are PDFs)."""
    entries: list[tuple[str, str]] = []
    for path in inputs_dir.rglob("*"):
        if path.is_file():
            rel = path.relative_to(inputs_dir).as_posix()
            entries.append((rel, sha256_bytes(path.read_bytes())))
    entries.sort(key=lambda e: e[0].encode("utf-8"))
    return entries


def aggregate_inputs_digest(inputs_dir: Path) -> str:
    """Hash the concatenation of (path, file-digest) pairs in byte-wise path order (D27)."""
    hasher = hashlib.sha256()
    for rel, digest in per_file_digests(inputs_dir):
        hasher.update(rel.encode("utf-8"))
        hasher.update(digest.encode("ascii"))
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# Top-level dataset load
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedDataset:
    manifest: Manifest
    answer_key: AnswerKey
    invoice_index: InvoiceIndex
    inputs_aggregate_sha256: str


def load_dataset(dataset_ref: str, search_root: Path) -> LoadedDataset:
    """Resolve and fully validate a dataset. Raises :class:`DatasetError` on any
    malformed input, naming the cause, and never emits a partial result."""
    manifest = resolve_manifest(dataset_ref, search_root)
    answer_key = load_answer_key(manifest.key_path)
    invoice_index = load_invoice_index(manifest.invoice_index_path)
    _validate_purchase_orders(manifest.inputs_dir)
    _validate_goods_receipts(manifest.inputs_dir)
    # Cross-artifact validations: these need the key and the index together, so they
    # cannot live in the per-artifact validators above (D47, D48).
    _validate_multi_po_tax_rates(answer_key, manifest.inputs_dir)
    _validate_correspondence_completeness(answer_key, invoice_index)
    inputs_digest = aggregate_inputs_digest(manifest.inputs_dir)
    return LoadedDataset(
        manifest=manifest,
        answer_key=answer_key,
        invoice_index=invoice_index,
        inputs_aggregate_sha256=inputs_digest,
    )
