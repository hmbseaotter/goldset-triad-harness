"""Scorecard emission — JSON plus a human-readable summary.

The JSON is serialized with a stable key ordering so that identical inputs yield
identical bytes (U4). The split between the scored body and ``run_metadata`` is
load-bearing: ``run_metadata`` holds *exactly* the non-deterministic fields (the
wall-clock run stamp and the elapsed durations) and nothing else, so excluding it
alone makes two runs byte-identical. Every deterministic field — including the
invoice and finding counts and all four fingerprints — lives in the scored body,
under the protection of that byte comparison (D18, D10, D27, D34).

Every ``Decimal`` is emitted as an exact string, and every undefined metric as
``null`` (D25). A JSON float cannot represent a value such as ``0.6667`` exactly,
which would defeat byte-identical reproducibility; a string is exact and keeps
``float`` off the emission path entirely.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .constants import RATIO_OUTPUT_PLACES, ROUNDING_MODE
from .schema import Category, Finding
from .scoring import ScoreResult

SCORECARD_SCHEMA_VERSION = "1"

_RATIO_QUANTUM = Decimal(1).scaleb(-RATIO_OUTPUT_PLACES)  # e.g. Decimal("0.0001")


@dataclass(frozen=True)
class Provenance:
    """What the scorecard records about the inputs it scored (D10, D27, D34)."""

    dataset_identifier: str
    dataset_version: str
    findings_artifact_sha256: str
    answer_key_sha256: str
    invoice_index_sha256: str
    inputs_aggregate_sha256: str


@dataclass(frozen=True)
class RunMetadata:
    """The non-deterministic envelope — and nothing else (D9, D18)."""

    run_timestamp: str  # UTC ISO-8601, 'Z' suffix, second precision
    load_ms: int
    score_ms: int
    total_ms: int


def _ratio_str(value: Decimal | None) -> str | None:
    """A reported ratio at the declared places, ROUND_HALF_UP — or None, emitted
    as JSON null, never zero and never an omitted key (D25, D28)."""
    if value is None:
        return None
    return str(value.quantize(_RATIO_QUANTUM, rounding=ROUNDING_MODE))


def _confidence_str(value: Decimal | None) -> str | None:
    """The agent's confidence, echoed exactly. Carried, never scored (D4); not a
    reported ratio, so it is not quantized — just rendered float-free."""
    if value is None:
        return None
    return format(value, "f")


def _finding_json(finding: Finding) -> dict[str, Any]:
    return {
        "status": finding.status.value,
        "category": finding.category.value,
        "scope": finding.scope.value,
        "target": {
            "document_id": finding.target.document_id,
            "line_id": finding.target.line_id,
        },
        "confidence": _confidence_str(finding.confidence),
        "reasoning": finding.reasoning,
    }


def build_scorecard(
    result: ScoreResult,
    provenance: Provenance,
    run_metadata: RunMetadata,
) -> dict[str, Any]:
    """Assemble the scorecard as a JSON-ready dict. Deterministic content only in
    the scored body; the non-deterministic envelope is ``run_metadata``."""
    per_category: dict[str, Any] = {}
    for m in result.category_metrics:
        per_category[m.category.value] = {
            "true_positives": m.true_positives,
            "false_positives": m.false_positives,
            "false_negatives": m.false_negatives,
            "precision": _ratio_str(m.precision),
            "recall": _ratio_str(m.recall),
        }

    return {
        "schema_version": SCORECARD_SCHEMA_VERSION,
        "dataset": {
            "identifier": provenance.dataset_identifier,
            "version": provenance.dataset_version,
        },
        "fingerprints": {
            "findings_artifact_sha256": provenance.findings_artifact_sha256,
            "answer_key_sha256": provenance.answer_key_sha256,
            "invoice_index_sha256": provenance.invoice_index_sha256,
            "inputs_aggregate_sha256": provenance.inputs_aggregate_sha256,
        },
        "workload": {
            "invoice_count": result.invoice_count,
            "finding_count": result.finding_count,
        },
        "metrics": {
            "overall": {
                "precision": _ratio_str(result.overall_precision),
                "recall": _ratio_str(result.overall_recall),
            },
            "false_positive_count": result.false_positive_count,
            "false_positive_rate": _ratio_str(result.false_positive_rate),
            "duplicate_contention_count": result.duplicate_contention_count,
            "nonexistent_target_count": result.nonexistent_target_count,
            "match_status_count": result.match_status_count,
            "per_category": per_category,
        },
        "missed": [_finding_json(f) for f in result.missed],
        "false_flags": [
            {**_finding_json(ff.finding), "reason": ff.reason.value}
            for ff in result.false_flags
        ],
        "run_metadata": {
            "run_timestamp": run_metadata.run_timestamp,
            "load_ms": run_metadata.load_ms,
            "score_ms": run_metadata.score_ms,
            "total_ms": run_metadata.total_ms,
        },
    }


def serialize(scorecard: dict[str, Any]) -> str:
    """Serialize with a stable key ordering so identical inputs yield identical
    bytes (U4). Ends with a trailing newline for a clean POSIX text file."""
    return (
        json.dumps(scorecard, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        + "\n"
    )


def deterministic_body(scorecard: dict[str, Any]) -> str:
    """The scorecard minus ``run_metadata``, serialized — this is what two runs on
    the same inputs must match byte for byte."""
    body = {k: v for k, v in scorecard.items() if k != "run_metadata"}
    return serialize(body)


def _target_str(finding: Finding) -> str:
    if finding.scope.value == "DOCUMENT":
        return f"{finding.target.document_id} (document)"
    return f"{finding.target.document_id} line {finding.target.line_id}"


def human_summary(scorecard: dict[str, Any], result: ScoreResult) -> str:
    """A human-readable summary that names each missed finding and each false flag
    individually, rather than reporting aggregate numbers alone (N2)."""
    lines: list[str] = []
    ds = scorecard["dataset"]
    lines.append(f"Scorecard - dataset {ds['identifier']} @ {ds['version']}")
    lines.append("=" * 60)
    wl = scorecard["workload"]
    lines.append(
        f"Workload: {wl['invoice_count']} invoice(s), {wl['finding_count']} finding(s) submitted"
    )
    m = scorecard["metrics"]
    lines.append(
        f"Overall precision: {m['overall']['precision']}   recall: {m['overall']['recall']}"
    )
    lines.append(
        f"False positives: {m['false_positive_count']}  "
        f"(rate {m['false_positive_rate']} per invoice)"
    )
    lines.append(
        f"Duplicate-contention flags: {m['duplicate_contention_count']}   "
        f"Non-existent-target flags: {m['nonexistent_target_count']}   "
        f"MATCH assertions: {m['match_status_count']}"
    )
    lines.append("")
    lines.append("Per-category (precision / recall):")
    for category in Category:
        row = m["per_category"][category.value]
        lines.append(
            f"  {category.value:<22} "
            f"TP {row['true_positives']}  FP {row['false_positives']}  "
            f"FN {row['false_negatives']}   "
            f"P {row['precision']}  R {row['recall']}"
        )

    lines.append("")
    if result.missed:
        lines.append(f"Missed findings ({len(result.missed)}):")
        for f in result.missed:
            lines.append(f"  - {f.category.value} on {_target_str(f)}")
    else:
        lines.append("Missed findings: none")

    lines.append("")
    if result.false_flags:
        lines.append(f"False flags ({len(result.false_flags)}):")
        for ff in result.false_flags:
            lines.append(
                f"  - {ff.finding.category.value} on {_target_str(ff.finding)} "
                f"[{ff.reason.value}]"
            )
    else:
        lines.append("False flags: none")

    return "\n".join(lines) + "\n"
