"""Verify mode — recompute a stored scorecard and say, by name, what differs (D10).

D10's premise is that a scorecard never has to be *trusted*, because it can be
*recomputed*: identical inputs yield identical output (U4), so re-running is a
stronger integrity property than digging through git history. This module is where
that premise becomes a command.

**It cannot locate anything from the scorecard alone, and does not pretend to.**
A scorecard records the dataset identifier and version and four SHA-256
fingerprints — never a path. D10's phrasing, "recomputes from those fingerprints",
is not literally achievable: a digest confirms identity, it does not find a file.
So the dataset and the findings artifact are named again on the command line, and
the stored digests are used to *confirm* that what was handed over is what was
scored. The alternative — recording paths in the scorecard — collides with D18:
`run_metadata` holds exactly the non-deterministic fields, and a machine-specific
path is neither a run measurement nor deterministic, so it belongs in neither half.

**Outcomes are ranked, and the ranking is the point.** A difference has several
possible causes and they are not equally informative, so verify reports the *first*
that applies and stops:

1. **The schema version is unrecognised** (D66). Reported as its own outcome and
   nothing else is compared. Byte-identity is promised between runs on the same
   inputs, never across schema versions, so presenting the resulting differences as
   a scoring discrepancy would be the misdiagnosis this project keeps finding —
   aimed, here, at the one feature whose entire purpose is to say whether a score
   can be trusted.
2. **A fingerprint differs.** The inputs moved. That is not the same statement as
   "the score is wrong", and reporting the latter would send a reader to audit
   arithmetic when the answer is that they scored different data (D50).
3. **The scored body differs** on identical inputs. This is the real discrepancy:
   same inputs, different numbers.
4. **Identical.**

Every one of those is a halt naming a specific cause, never a diff dump — which is
why differences are reported as `metrics.per_category.PRICE_VARIANCE.recall:
stored X, recomputed Y` rather than as two blobs for the reader to compare.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Final

from .dataset import (
    DatasetError,
    LoadedDataset,
    load_dataset,
    per_file_digests,
    sha256_file,
)
from .schema import SchemaError, parse_findings_artifact
from .scorecard import (
    SCORECARD_SCHEMA_VERSION,
    Provenance,
    RunMetadata,
    build_scorecard,
)
from .scoring import score

#: How many named differences to print before summarising the rest. A halt names its
#: cause; a hundred lines of them is the diff dump the requirement rules out.
MAX_REPORTED: Final = 10

#: The recomputation needs a `RunMetadata` to build a scorecard, and every field in it
#: is excluded from the comparison by construction (D9, D18). A fixed value is used
#: rather than the clock so that `cli._utc_now_stamp` remains what it says it is: the
#: single wall-clock read in the whole harness. Verify writes no scorecard, so this
#: value never reaches disk; it still satisfies D6's format so it cannot become the one
#: timestamp in the project that does not.
_UNUSED_RUN_METADATA: Final = RunMetadata(
    run_timestamp="1970-01-01T00:00:00Z", load_ms=0, score_ms=0, total_ms=0
)

#: Stored-vs-recomputed fingerprint pairs, in the order they are reported. Ordered so a
#: reader meets the artifact they most likely changed first.
_FINGERPRINT_FIELDS: Final = (
    ("findings_artifact_sha256", "the findings artifact"),
    ("answer_key_sha256", "the answer key"),
    ("invoice_index_sha256", "the structured invoice index"),
    ("inputs_aggregate_sha256", "the dataset inputs"),
)


class Outcome(Enum):
    """What verify concluded. Distinct outcomes, never collapsed into "it differs"."""

    IDENTICAL = "identical"
    SCHEMA_UNRECOGNISED = "schema-unrecognised"
    FINGERPRINT_MISMATCH = "fingerprint-mismatch"
    SCORE_DIFFERS = "score-differs"


@dataclass(frozen=True)
class VerifyResult:
    outcome: Outcome
    causes: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.IDENTICAL


def _read_scorecard(path: Path) -> dict[str, Any]:
    """Load a stored scorecard, naming any way it fails to be one.

    ``parse_float=Decimal`` is pinned even though a well-formed scorecard contains no
    JSON floats — every monetary value and ratio is emitted as an exact string (D37)
    and every count as an integer. It matters precisely for the ill-formed case: a
    doctored scorecard whose ratio was edited from `"0.9000"` into `0.9` is then read
    as a `Decimal` rather than silently becoming a float on the comparison path."""
    if not path.is_file():
        raise DatasetError(f"scorecard not found or unreadable: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise DatasetError(f"scorecard {path} is not valid JSON: {exc}")
    if not isinstance(raw, dict):
        raise DatasetError(f"scorecard {path} is not a JSON object")
    return raw


def _differences(stored: Any, fresh: Any, path: str = "") -> list[str]:
    """Every value that differs, named by its key path.

    Recurses in sorted key order so two runs of verify report the same differences in
    the same order — the same reason the scorecard itself serializes with a stable key
    ordering (U4). A message names one field, so the reader is told *what* changed
    rather than handed two documents."""
    where = path or "<root>"
    if isinstance(stored, dict) and isinstance(fresh, dict):
        out: list[str] = []
        for key in sorted(set(stored) | set(fresh)):
            here = f"{path}.{key}" if path else str(key)
            if key not in stored:
                out.append(f"{here}: absent from the stored scorecard, recomputed as {fresh[key]!r}")
            elif key not in fresh:
                out.append(f"{here}: stored as {stored[key]!r}, absent on recompute")
            else:
                out.extend(_differences(stored[key], fresh[key], here))
        return out
    if isinstance(stored, list) and isinstance(fresh, list):
        if len(stored) != len(fresh):
            return [
                f"{where}: the stored scorecard holds {len(stored)} entr(y/ies), "
                f"the recomputation holds {len(fresh)}"
            ]
        out = []
        for position, (a, b) in enumerate(zip(stored, fresh)):
            out.extend(_differences(a, b, f"{path}[{position}]"))
        return out
    if stored != fresh:
        return [f"{where}: stored {stored!r}, recomputed {fresh!r}"]
    return []


def _inputs_diagnosis(inputs_dir: Path, baseline_inputs: Path | None) -> list[str]:
    """D27's per-file diagnosis, and an honest account of its limit (D74).

    D27 chose to store one aggregate digest per scorecard rather than ~75-150 per-file
    entries, and said a mismatch would be diagnosed by recomputing per-file digests and
    reporting which files diverged. That wording assumed both sides were in hand. In
    verify they are not: the scorecard stores the aggregate alone, so recomputing the
    per-file digests yields the current set with nothing to diverge *from*. Verify can
    therefore name the set but not the member — unless it is handed a reference copy,
    which is what ``--baseline-inputs`` is for."""
    current = per_file_digests(inputs_dir)
    if baseline_inputs is None:
        listing = [f"    {rel}  {digest}" for rel, digest in current[:MAX_REPORTED]]
        remainder = len(current) - len(listing)
        if remainder > 0:
            listing.append(f"    ... and {remainder} more file(s)")
        return [
            "the scorecard stores only the AGGREGATE inputs digest (D27 chose that over "
            "a per-file list in every durable record), so verify cannot say which file "
            "moved without a reference copy. Pass --baseline-inputs <dir> pointing at a "
            "pristine inputs directory to have the divergent files named exactly. The "
            "current per-file digests are:",
            *listing,
        ]

    if not baseline_inputs.is_dir():
        raise DatasetError(
            f"--baseline-inputs {baseline_inputs} is not a directory; omit it to list "
            f"the current per-file digests instead"
        )
    base = dict(per_file_digests(baseline_inputs))
    now = dict(current)
    causes: list[str] = []
    for rel in sorted(set(base) | set(now)):
        if rel not in now:
            causes.append(f"    {rel}: present in the baseline, absent from the scored inputs")
        elif rel not in base:
            causes.append(f"    {rel}: absent from the baseline, present in the scored inputs")
        elif base[rel] != now[rel]:
            causes.append(f"    {rel}: baseline {base[rel]}, scored inputs {now[rel]}")
    if not causes:
        return [
            f"every file under {inputs_dir} matches the baseline at {baseline_inputs}, yet "
            f"the aggregate differs from the stored one — so the inputs that were SCORED "
            f"are not the inputs either directory now holds"
        ]
    return [f"these files diverge from the baseline at {baseline_inputs}:", *causes]


def _recompute(
    dataset_ref: str, findings_path: Path, search_root: Path
) -> tuple[dict[str, Any], LoadedDataset]:
    if not findings_path.is_file():
        raise DatasetError(f"findings artifact not found: {findings_path}")
    loaded = load_dataset(dataset_ref, search_root)
    try:
        raw_findings = json.loads(
            findings_path.read_text(encoding="utf-8"), parse_float=Decimal
        )
    except json.JSONDecodeError as exc:
        raise SchemaError(f"findings artifact is not valid JSON: {exc}")
    agent = parse_findings_artifact(raw_findings)
    result = score(
        loaded.answer_key.expected_findings, agent, loaded.invoice_index.inventory
    )
    provenance = Provenance(
        dataset_identifier=loaded.manifest.identifier,
        dataset_version=loaded.manifest.version,
        findings_artifact_sha256=sha256_file(findings_path),
        answer_key_sha256=loaded.answer_key.sha256,
        invoice_index_sha256=loaded.invoice_index.sha256,
        inputs_aggregate_sha256=loaded.inputs_aggregate_sha256,
    )
    return build_scorecard(result, provenance, _UNUSED_RUN_METADATA), loaded


def verify(
    scorecard_path: Path,
    dataset_ref: str,
    findings_path: Path,
    search_root: Path,
    baseline_inputs: Path | None = None,
) -> VerifyResult:
    """Recompute the scored body and report the first applicable outcome."""
    stored = _read_scorecard(scorecard_path)

    # 1. Schema first, and alone (D66). A shape change and a scoring difference are
    #    indistinguishable once you start comparing fields, so the version is settled
    #    BEFORE anything is recomputed -- which also means an unrecognised scorecard
    #    costs no dataset load.
    if "schema_version" not in stored:
        return VerifyResult(
            Outcome.SCHEMA_UNRECOGNISED,
            (
                f"{scorecard_path} declares no schema_version at all, so its shape is "
                f"unknown; this harness emits version {SCORECARD_SCHEMA_VERSION!r}. No "
                f"comparison was attempted: differences against an unknown shape are not "
                f"scoring differences (D66).",
            ),
        )
    stored_version = str(stored["schema_version"])
    if stored_version != SCORECARD_SCHEMA_VERSION:
        return VerifyResult(
            Outcome.SCHEMA_UNRECOGNISED,
            (
                f"{scorecard_path} declares scorecard schema version "
                f"{stored_version!r}; this harness emits {SCORECARD_SCHEMA_VERSION!r}. "
                f"No comparison was attempted, and this is NOT a scoring discrepancy: "
                f"byte-identity is promised between runs on the same inputs, never "
                f"across schema versions (D66).",
            ),
        )

    recomputed, loaded = _recompute(dataset_ref, findings_path, search_root)

    stored_fingerprints = stored.get("fingerprints")
    if not isinstance(stored_fingerprints, dict):
        raise DatasetError(
            f"scorecard {scorecard_path} declares schema version {stored_version!r} but "
            f"carries no fingerprints block, so it does not have the shape it claims"
        )

    # 2. Whether the same inputs were scored at all. Reported before any body
    #    comparison, because "you scored different data" and "the numbers are wrong"
    #    are different findings and only one of them is about scoring (D50).
    fingerprint_causes: list[str] = []
    fresh_fingerprints = recomputed["fingerprints"]
    for field, what in _FINGERPRINT_FIELDS:
        was = stored_fingerprints.get(field)
        now = fresh_fingerprints[field]
        if was != now:
            fingerprint_causes.append(
                f"{what} does not match what was scored: the scorecard records "
                f"{was!r}, the artifact on disk digests to {now!r}"
            )
            if field == "inputs_aggregate_sha256":
                fingerprint_causes.extend(
                    _inputs_diagnosis(loaded.manifest.inputs_dir, baseline_inputs)
                )
    if fingerprint_causes:
        return VerifyResult(Outcome.FINGERPRINT_MISMATCH, tuple(fingerprint_causes))

    # 3. Same inputs, so any remaining difference IS a scoring difference. The
    #    `run_metadata` envelope is excluded on both sides: it holds exactly the
    #    non-deterministic fields, and excluding it alone is what makes two runs
    #    comparable at all (D9, D10, D18).
    #
    #    Compared as parsed structures rather than as re-serialized bytes, so each
    #    difference can be NAMED by its key path. JSON that parses to the same object is
    #    the same scorecard -- key order is fixed by the serializer (U4), so a
    #    reordering is not a change in what was scored, while a changed value is, and
    #    that is what this must catch and localize.
    stored_body = {k: v for k, v in stored.items() if k != "run_metadata"}
    fresh_body = {k: v for k, v in recomputed.items() if k != "run_metadata"}
    differences = _differences(stored_body, fresh_body)
    if differences:
        shown = differences[:MAX_REPORTED]
        if len(differences) > len(shown):
            shown.append(f"... and {len(differences) - len(shown)} further difference(s)")
        return VerifyResult(
            Outcome.SCORE_DIFFERS,
            (
                "the same inputs recompute to a different score, so the stored scorecard "
                "does not report what it claims to report:",
                *shown,
            ),
        )

    return VerifyResult(
        Outcome.IDENTICAL,
        (
            f"recomputed from the same inputs and every scored field matches; all four "
            f"fingerprints agree and schema version {stored_version!r} is current.",
        ),
    )
