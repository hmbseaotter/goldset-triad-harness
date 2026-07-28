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
from .schema import Category, Finding, Scope
from .scoring import ScoreResult

# Bumped to "2" by D60, which added the `coverage` block and two per-category fields. The
# scored body's shape changed, so a consumer written against "1" must be told rather than
# left to discover it: byte-identity is promised between runs on the same inputs, never
# across schema versions.
SCORECARD_SCHEMA_VERSION = "2"

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
    exercised: list[str] = []
    unexercised: list[str] = []
    for m in result.category_metrics:
        # Every expectation in a category is either matched or missed, so tp + fn IS the
        # number of expectations the key holds there — and zero of them means the DATASET
        # does not exercise this category (D60). The scorecard states that rather than
        # leaving it to be inferred: a row of zeros with two nulls reads as "nothing to
        # report", when the truth is "this dataset cannot measure this".
        expected_count = m.true_positives + m.false_negatives
        (exercised if expected_count else unexercised).append(m.category.value)
        per_category[m.category.value] = {
            "true_positives": m.true_positives,
            "false_positives": m.false_positives,
            "false_negatives": m.false_negatives,
            "precision": _ratio_str(m.precision),
            "recall": _ratio_str(m.recall),
            "expected_count": expected_count,
            "exercised_by_dataset": bool(expected_count),
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
        # What this dataset can and cannot measure (D60). Deterministic — a property of the
        # answer key, not of the run — so it belongs in the scored body, not run_metadata.
        # The held-out split at [P1] exercises two of five categories; without this block a
        # reader sees three categories at null and reasonably concludes the agent was
        # flawless in them, when in fact they were never put to the test.
        "coverage": {
            "categories_total": len(exercised) + len(unexercised),
            "categories_exercised": exercised,
            "categories_not_exercised": unexercised,
            "expected_finding_count": sum(
                m.true_positives + m.false_negatives for m in result.category_metrics
            ),
            # A key with no expectations at all is the zero-defect control (D57): it
            # measures over-flagging only, and every recall figure on it is undefined by
            # construction rather than by omission.
            "measures_recall": bool(exercised),
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
    # Enum identity, not its value string (D118). `finding.scope.value == "DOCUMENT"`
    # stood here and would take the LINE branch silently if the enum's value were ever
    # renamed — the same stringly-typed comparison the rest of the package avoids
    # (`f.status is Status.MATCH`).
    if finding.scope is Scope.DOCUMENT:
        return f"{finding.target.document_id} (document)"
    return f"{finding.target.document_id} line {finding.target.line_id}"


def _display(ratio: str | None) -> str:
    """Render an undefined metric for a human reader (D60).

    The JSON emits `null`, which D25 fixed as the representation of "undefined" and which
    is exactly right for a machine. Interpolated into text, though, the same value printed
    as `None` — Python's repr leaking into the durable human record, where it reads as a
    bug rather than as a measurement that does not exist."""
    return "n/a" if ratio is None else ratio


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
        f"Overall precision: {_display(m['overall']['precision'])}   "
        f"recall: {_display(m['overall']['recall'])}"
    )
    lines.append(
        f"False positives: {m['false_positive_count']}  "
        f"(rate {_display(m['false_positive_rate'])} per invoice)"
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
        # Mark the unexercised rows in the row itself. A reader scanning this table takes
        # in the numbers, not a paragraph below it, and nulls on an untested category are
        # exactly what gets misread as a perfect score (D60).
        note = "" if row["exercised_by_dataset"] else "   [not exercised by this dataset]"
        # Every column is width-padded (D118). Nothing was, so `n/a` shifted the R column
        # three characters left of where `1.0000` put it, and any count above one digit
        # shifted everything after it. The legend calls this table something you read "at
        # a glance", which is exactly what ragged columns cost — and `[P3]`'s larger
        # dataset makes multi-digit counts certain rather than hypothetical.
        #
        # Widths: counts right-aligned so units line up, ratios left-aligned at the width
        # of `0.0000` so `n/a` pads rather than pulls.
        lines.append(
            f"  {category.value:<22} "
            f"TP {row['true_positives']:>4}  FP {row['false_positives']:>4}  "
            f"FN {row['false_negatives']:>4}   "
            f"P {_display(row['precision']):<6}  R {_display(row['recall']):<6}"
            f"{note}".rstrip()
        )

    cov = scorecard["coverage"]
    lines.append("")
    if not cov["measures_recall"]:
        lines.append(
            "COVERAGE: this dataset declares NO expected findings, so it measures "
            "over-flagging only. Every recall figure above is undefined by construction, "
            "not by omission."
        )
    elif cov["categories_not_exercised"]:
        lines.append(
            f"COVERAGE: this dataset exercises "
            f"{len(cov['categories_exercised'])} of {cov['categories_total']} categories "
            f"({cov['expected_finding_count']} expected finding(s)). NOT measured: "
            f"{', '.join(cov['categories_not_exercised'])}. Their null metrics mean the "
            f"data lacks these cases, NOT that the agent handled them correctly."
        )
    else:
        lines.append(
            f"COVERAGE: this dataset exercises all {cov['categories_total']} categories "
            f"({cov['expected_finding_count']} expected finding(s))."
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
