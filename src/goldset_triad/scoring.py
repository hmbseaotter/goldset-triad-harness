"""The scoring engine — loads expected findings and matches; never derives (D35).

This module contains **no domain rule**. It does not compute a payable quantity,
apply a materiality threshold, or evaluate a tax comparison. Those belong to the
key generator and the published policy; a scorer that re-derived expectations
would grade the agent against its own implementation rather than against audited
ground truth, and any bug in that implementation would silently become truth.

Everything here is a pure function of (expected findings, agent findings, line
inventory). Results are keyed by match-key and contention is tie-broken by
canonical serialization, never by position in the findings artifact — so
reversing that artifact yields an identical result (U4, D26).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum

from .constants import DECIMAL_CONTEXT_PRECISION
from .schema import Category, Finding, Scope, Status


@dataclass(frozen=True)
class LineInventory:
    """The set of real targets a finding may point at, from the invoice index.

    Target validation distinguishes a line that exists from one that does not —
    which the expected findings alone cannot support, since a clean line has no
    expectation yet is still a valid target (D34)."""

    line_targets: frozenset[tuple[str, str]]
    """Valid (invoice_id, line_id) pairs — every invoice line, clean or not."""
    documents: frozenset[str]
    """Valid invoice ids, for document-scoped targets."""
    invoice_count: int
    """Number of invoices in the dataset — the false-positive-rate denominator."""

    def contains(self, finding: Finding) -> bool:
        if finding.scope is Scope.DOCUMENT:
            return finding.target.document_id in self.documents
        return (
            finding.target.document_id,
            finding.target.line_id,
        ) in self.line_targets


class FalseFlagReason(Enum):
    """Why an agent finding was counted as a false positive — surfaced so the
    summary can name it, and so duplicate contention and non-existent targets are
    distinguishable from an ordinary spurious flag (D26, I6)."""

    NO_MATCH = "no_match"
    DUPLICATE_CONTENTION = "duplicate_contention"
    NONEXISTENT_TARGET = "nonexistent_target"


@dataclass(frozen=True)
class FalseFlag:
    finding: Finding
    reason: FalseFlagReason


@dataclass(frozen=True)
class CategoryMetrics:
    category: Category
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: Decimal | None
    recall: Decimal | None


@dataclass(frozen=True)
class ScoreResult:
    category_metrics: tuple[CategoryMetrics, ...]
    overall_precision: Decimal | None
    overall_recall: Decimal | None
    false_positive_count: int
    false_positive_rate: Decimal
    duplicate_contention_count: int
    nonexistent_target_count: int
    match_status_count: int
    missed: tuple[Finding, ...]
    false_flags: tuple[FalseFlag, ...]
    invoice_count: int
    finding_count: int


def _ratio(numerator: int, denominator: int) -> Decimal | None:
    """A reported ratio, or None where it is undefined (D25).

    Division is permitted here because this is a *reported* value, not a flagging
    decision (D28). It runs under a pinned decimal context so that a run on an
    interpreter with a different ambient precision still produces byte-identical
    output; the value is rounded to the declared places only at emission."""
    if denominator == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = DECIMAL_CONTEXT_PRECISION
        return Decimal(numerator) / Decimal(denominator)


def score(
    expected: tuple[Finding, ...],
    agent: tuple[Finding, ...],
    inventory: LineInventory,
) -> ScoreResult:
    """Score ``agent`` findings against ``expected`` (loaded from the key).

    1:1 matching on the strict key; a MATCH-status entry is an assertion of
    correctness, ineligible to be a flag (D13); an unmatched expectation is a
    miss; an unmatched flag is a false positive, labelled by why."""

    finding_count = len(agent)

    # MATCH entries are set aside entirely (D13). They assert no discrepancy, so
    # they never match a discrepancy expectation and are never counted as false
    # positives — the missed expectation is already counted once as a miss.
    match_status = [f for f in agent if f.status is Status.MATCH]
    discrepancy_flags = [f for f in agent if f.status is Status.DISCREPANCY]

    # A flag whose target does not exist in the dataset is a false positive,
    # distinctly labelled, and cannot match any expectation (which always names a
    # real line). Set these aside before 1:1 matching.
    nonexistent: list[Finding] = []
    real_flags: list[Finding] = []
    for f in discrepancy_flags:
        (real_flags if inventory.contains(f) else nonexistent).append(f)

    # Group expectations and real flags by the strict match key.
    expected_by_key: dict[tuple[str, str, str, str, str], list[Finding]] = {}
    for e in expected:
        expected_by_key.setdefault(e.match_key(), []).append(e)
    flags_by_key: dict[tuple[str, str, str, str, str], list[Finding]] = {}
    for f in real_flags:
        flags_by_key.setdefault(f.match_key(), []).append(f)

    true_positives: list[Finding] = []
    missed: list[Finding] = []
    false_flags: list[FalseFlag] = []

    # Every non-existent-target flag is a false positive.
    for f in nonexistent:
        false_flags.append(FalseFlag(f, FalseFlagReason.NONEXISTENT_TARGET))

    duplicate_contention = 0
    all_keys = set(expected_by_key) | set(flags_by_key)
    for key in all_keys:
        exp = expected_by_key.get(key, [])
        # Order contenders by canonical serialization, NOT by input position, so
        # the choice of which flag is the true positive is independent of order.
        flags = sorted(flags_by_key.get(key, []), key=lambda f: f.canonical())
        matched = min(len(exp), len(flags))
        true_positives.extend(flags[:matched])
        # Surplus expectations on this key are misses.
        missed.extend(exp[matched:])
        # Surplus flags on a key that HAS an expectation are duplicate contention
        # (D26); on a key with no expectation they are ordinary spurious flags.
        for f in flags[matched:]:
            if exp:
                duplicate_contention += 1
                false_flags.append(FalseFlag(f, FalseFlagReason.DUPLICATE_CONTENTION))
            else:
                false_flags.append(FalseFlag(f, FalseFlagReason.NO_MATCH))

    metrics = _category_metrics(true_positives, false_flags, missed)

    total_tp = len(true_positives)
    total_fp = len(false_flags)
    total_fn = len(missed)

    fp_rate = _ratio(total_fp, inventory.invoice_count)
    assert fp_rate is not None  # invoice_count >= 1 is enforced at load

    return ScoreResult(
        category_metrics=metrics,
        overall_precision=(
            None if (total_tp + total_fp) == 0 else _ratio(total_tp, total_tp + total_fp)
        ),
        overall_recall=(
            None if (total_tp + total_fn) == 0 else _ratio(total_tp, total_tp + total_fn)
        ),
        false_positive_count=total_fp,
        false_positive_rate=fp_rate,
        duplicate_contention_count=duplicate_contention,
        nonexistent_target_count=len(nonexistent),
        match_status_count=len(match_status),
        missed=tuple(sorted(missed, key=lambda f: f.canonical())),
        false_flags=tuple(
            sorted(false_flags, key=lambda ff: (ff.reason.value, ff.finding.canonical()))
        ),
        invoice_count=inventory.invoice_count,
        finding_count=finding_count,
    )


def _category_metrics(
    true_positives: list[Finding],
    false_flags: list[FalseFlag],
    missed: list[Finding],
) -> tuple[CategoryMetrics, ...]:
    """Per-category precision and recall, with the D25 null rules applied per
    category: recall is null where the category has no expectations, and precision
    is null only where no flag was raised in it (otherwise it is the computed
    value, which may be zero)."""
    rows: list[CategoryMetrics] = []
    for category in Category:
        tp = sum(1 for f in true_positives if f.category is category)
        fp = sum(1 for ff in false_flags if ff.finding.category is category)
        fn = sum(1 for f in missed if f.category is category)
        precision = None if (tp + fp) == 0 else _ratio(tp, tp + fp)
        recall = None if (tp + fn) == 0 else _ratio(tp, tp + fn)
        rows.append(
            CategoryMetrics(
                category=category,
                true_positives=tp,
                false_positives=fp,
                false_negatives=fn,
                precision=precision,
                recall=recall,
            )
        )
    return tuple(rows)
