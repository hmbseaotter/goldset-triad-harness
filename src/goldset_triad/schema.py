"""Findings payload schema v1 — the stable port (D1, D20, D22).

Any agent that emits this payload can be scored. The schema is the interface, so
validation is strict and every rejection names the offending finding *and* the
specific field (I1): a vague "malformed input" would make a schema violation as
hard to diagnose as the bug it guards against.

Nothing here applies a domain rule. This module parses and validates structure
only; whether a finding is *correct* is decided by matching it against the key
(``scoring``), never by re-deriving it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from .constants import DOCUMENT_LINE_SENTINEL

SCHEMA_VERSION: Final = "1"


class Status(enum.Enum):
    """A finding either asserts a discrepancy or asserts correctness (D13)."""

    MATCH = "MATCH"
    DISCREPANCY = "DISCREPANCY"


class Category(enum.Enum):
    """The closed discrepancy enumeration (D11.3, D15). Owned by the harness so
    per-category precision/recall is well defined; an unknown category is a
    schema violation, never a near-miss scored as a name mismatch."""

    PRICE_VARIANCE = "PRICE_VARIANCE"
    QTY_UNDER_SHIPMENT = "QTY_UNDER_SHIPMENT"
    QTY_OVER_SHIPMENT = "QTY_OVER_SHIPMENT"
    QTY_INVOICE_INFLATED = "QTY_INVOICE_INFLATED"
    TAX_VARIANCE = "TAX_VARIANCE"


class Scope(enum.Enum):
    """Whether the finding is about one line or the whole document (D20).

    Made explicit rather than inferred from a sentinel so validation can reject a
    malformed finding instead of silently treating it as document-level, and so
    the match key can distinguish the two without a magic string carrying the
    meaning implicitly."""

    LINE = "LINE"
    DOCUMENT = "DOCUMENT"


class SchemaError(Exception):
    """A findings artifact, or a finding within it, is malformed.

    Carries the offending finding's index and the specific field so the halt
    message can name both (I1)."""

    def __init__(
        self,
        message: str,
        *,
        finding_index: int | None = None,
        field: str | None = None,
    ) -> None:
        self.finding_index = finding_index
        self.field = field
        location = ""
        if finding_index is not None:
            location = f" [finding #{finding_index}"
            if field is not None:
                location += f", field '{field}'"
            location += "]"
        elif field is not None:
            location = f" [field '{field}']"
        super().__init__(message + location)


@dataclass(frozen=True)
class Target:
    """The line a finding points at: the invoice under evaluation, plus a line id.

    For DOCUMENT scope the line id is the reserved sentinel; the document id names
    the invoice, never a PO or receipt (D22)."""

    document_id: str
    line_id: str


@dataclass(frozen=True)
class Finding:
    """One agent finding, or one expected finding from the key. Frozen: a scored
    record is never mutated.

    ``confidence`` and ``reasoning`` are carried but NEVER scored (D4). They may be
    absent; when present they are validated, but they never influence whether a
    finding matches."""

    status: Status
    category: Category
    scope: Scope
    target: Target
    confidence: Decimal | None = None
    reasoning: str | None = None

    def match_key(self) -> tuple[str, str, str, str, str]:
        """The strict match key: status + category + scope + target (D8, D20).

        The target contributes both document and line id. For DOCUMENT scope the
        line id is the sentinel, so a document-scoped and a line-scoped finding
        that agree on everything else still differ here — via ``scope`` and via
        the sentinel — and cannot match each other."""
        return (
            self.status.value,
            self.category.value,
            self.scope.value,
            self.target.document_id,
            self.target.line_id,
        )

    def canonical(self) -> str:
        """A total, order-independent ordering key for tie-breaking (D26).

        Includes the whole finding — confidence and reasoning too. D26 permits
        this: the tie-break decides only which of two identical-keyed findings is
        *labelled* the true positive, and cannot move any metric, so ordering by a
        field that is never scored does not amount to scoring it. Two byte-identical
        duplicates produce the same string and are resolved identically."""
        conf = "" if self.confidence is None else format(self.confidence, "f")
        reason = "" if self.reasoning is None else self.reasoning
        # Newline-free, field-delimited; the components cannot contain the
        # delimiter in a way that reorders the tuple, because status/category/scope
        # are enum values and ids are dataset-controlled tokens.
        return "\x1f".join(
            (
                self.status.value,
                self.category.value,
                self.scope.value,
                self.target.document_id,
                self.target.line_id,
                conf,
                reason,
            )
        )


def _require(obj: dict[str, Any], key: str, index: int) -> Any:
    if key not in obj:
        raise SchemaError("required field missing", finding_index=index, field=key)
    return obj[key]


def _parse_enum(
    enum_cls: type[enum.Enum], value: Any, field: str, index: int
) -> Any:
    if not isinstance(value, str):
        raise SchemaError(
            f"{field} must be a string", finding_index=index, field=field
        )
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(m.value for m in enum_cls)
        raise SchemaError(
            f"{field} '{value}' is not one of the closed enumeration ({allowed})",
            finding_index=index,
            field=field,
        ) from None


def _parse_target(value: Any, scope: Scope, index: int) -> Target:
    if not isinstance(value, dict):
        raise SchemaError(
            "target must be an object with 'document_id' and 'line_id'",
            finding_index=index,
            field="target",
        )
    document_id = _require(value, "document_id", index)
    if not isinstance(document_id, str) or not document_id:
        raise SchemaError(
            "target.document_id must be a non-empty string",
            finding_index=index,
            field="target.document_id",
        )
    line_id = _require(value, "line_id", index)
    if not isinstance(line_id, str) or not line_id:
        # Absent or empty is malformed for BOTH scopes: a document-scoped finding
        # must carry the sentinel explicitly, never be inferred from an empty id.
        raise SchemaError(
            "target.line_id must be a non-empty string; a document-scoped finding "
            f"must carry the reserved sentinel '{DOCUMENT_LINE_SENTINEL}'",
            finding_index=index,
            field="target.line_id",
        )
    if scope is Scope.DOCUMENT and line_id != DOCUMENT_LINE_SENTINEL:
        raise SchemaError(
            f"a DOCUMENT-scoped finding must carry line_id '{DOCUMENT_LINE_SENTINEL}', "
            f"not '{line_id}'",
            finding_index=index,
            field="target.line_id",
        )
    if scope is Scope.LINE and line_id == DOCUMENT_LINE_SENTINEL:
        raise SchemaError(
            f"a LINE-scoped finding must not use the reserved sentinel "
            f"'{DOCUMENT_LINE_SENTINEL}' as a line id",
            finding_index=index,
            field="target.line_id",
        )
    return Target(document_id=document_id, line_id=line_id)


def _parse_confidence(value: Any, index: int) -> Decimal | None:
    if value is None:
        return None
    # Findings JSON is loaded with parse_float=Decimal, so a JSON number arrives as
    # Decimal already; an int is fine too. Anything else is malformed.
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise SchemaError(
            "confidence, when present, must be a number between 0 and 1",
            finding_index=index,
            field="confidence",
        )
    conf = Decimal(value)
    if conf < 0 or conf > 1:
        raise SchemaError(
            "confidence must lie between 0 and 1 inclusive",
            finding_index=index,
            field="confidence",
        )
    return conf


def parse_finding(obj: Any, index: int) -> Finding:
    """Validate one finding object into a :class:`Finding`, or raise :class:`SchemaError`."""
    if not isinstance(obj, dict):
        raise SchemaError("finding must be a JSON object", finding_index=index)
    status = _parse_enum(Status, _require(obj, "status", index), "status", index)
    category = _parse_enum(
        Category, _require(obj, "category", index), "category", index
    )
    scope = _parse_enum(Scope, _require(obj, "scope", index), "scope", index)
    target = _parse_target(_require(obj, "target", index), scope, index)
    confidence = _parse_confidence(obj.get("confidence"), index)
    reasoning = obj.get("reasoning")
    if reasoning is not None and not isinstance(reasoning, str):
        raise SchemaError(
            "reasoning, when present, must be a string",
            finding_index=index,
            field="reasoning",
        )
    return Finding(
        status=status,
        category=category,
        scope=scope,
        target=target,
        confidence=confidence,
        reasoning=reasoning,
    )


def parse_findings_artifact(raw: Any) -> tuple[Finding, ...]:
    """Validate a whole findings artifact into a tuple of :class:`Finding`.

    The artifact is a JSON object ``{"schema_version": "1", "findings": [...]}``.
    An empty ``findings`` list is valid — that is exactly the zero-defect control's
    input."""
    if not isinstance(raw, dict):
        raise SchemaError(
            "findings artifact must be a JSON object with a 'findings' list"
        )
    version = raw.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise SchemaError(
            f"unsupported schema_version '{version}'; this harness scores v{SCHEMA_VERSION}",
            field="schema_version",
        )
    findings_raw = raw.get("findings")
    if not isinstance(findings_raw, list):
        raise SchemaError("'findings' must be a list", field="findings")
    return tuple(
        parse_finding(item, index) for index, item in enumerate(findings_raw)
    )
