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
2. **This is not the dataset the scorecard scored** (D79). The scorecard records the
   dataset identifier and version, so verify can say *"you named a different split"*
   in one line. Without this the commonest operator error on a three-path command
   surfaced as three digest mismatches plus advice to fetch a pristine inputs
   directory — a reader sent to hunt a file that never moved.
3. **A fingerprint differs.** The inputs moved. That is not the same statement as
   "the score is wrong", and reporting the latter would send a reader to audit
   arithmetic when the answer is that they scored different data (D50).
4. **The scored body differs** on identical inputs. This is the real discrepancy:
   same inputs, different numbers.
5. **Identical.**

Every one of those is a halt naming a specific cause, never a diff dump — which is
why differences are reported as `metrics.per_category.PRICE_VARIANCE.recall:
stored X, recomputed Y` rather than as two blobs for the reader to compare, and why
every list of them is bounded by ``MAX_REPORTED`` with a count of the remainder.

**A missing field is a shape defect, not a difference.** Blocks and the fields inside
them are fetched with :func:`_required_field`, never with ``.get()``: a scorecard that
omits a fingerprint is malformed, while a scorecard whose fingerprint disagrees with the
artifact on disk is evidence, and reading the first through a default turned it into the
second and reported *"the scorecard records None"* (D79).
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
    load_findings_artifact,
    per_file_digests,
)
from .jsonio import read_json_object
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

#: Stored-vs-resolved dataset identity, checked before any digest (D79). Identifier
#: first: naming the wrong split is a different mistake from scoring a split that has
#: since been re-versioned, and the first is far commoner.
_DATASET_FIELDS: Final = (
    ("identifier", "dataset identifier"),
    ("version", "dataset version"),
)


class Outcome(Enum):
    """What verify concluded. Distinct outcomes, never collapsed into "it differs"."""

    IDENTICAL = "identical"
    SCHEMA_UNRECOGNISED = "schema-unrecognised"
    DATASET_MISMATCH = "dataset-mismatch"
    FINGERPRINT_MISMATCH = "fingerprint-mismatch"
    SCORE_DIFFERS = "score-differs"


def _bounded(causes: list[str], noun: str) -> list[str]:
    """At most ``MAX_REPORTED`` lines, then a count of the rest (D79).

    Applied at every site that can produce an unbounded list, because two of the four
    did not have it: the score-difference list was capped and the with-baseline per-file
    divergence list was not, so a one-byte change across a 150-file inputs tree printed
    one line per file — the diff dump this module's own docstring promises never to
    produce, in the branch a reader reaches only when something is already wrong."""
    if len(causes) <= MAX_REPORTED:
        return causes
    return [*causes[:MAX_REPORTED], f"... and {len(causes) - MAX_REPORTED} further {noun}"]


def _required_block(
    stored: dict[str, Any], name: str, path: Path, version: str
) -> dict[str, Any]:
    """A top-level block the declared schema promises, or a named shape failure."""
    block = stored.get(name)
    if not isinstance(block, dict):
        raise DatasetError(
            f"scorecard {path} declares schema version {version!r} but carries no "
            f"{name} block, so it does not have the shape it claims"
        )
    return block


def _required_field(
    block: dict[str, Any], block_name: str, field: str, path: Path, version: str
) -> Any:
    """A field inside a block, or a named shape failure — never a `None` stand-in.

    Separate from a *difference*, and that separation is the whole point. A scorecard
    that omits a fingerprint is malformed; a scorecard whose fingerprint disagrees with
    the artifact on disk is evidence. Reading the first through `.get()` turned it into
    the second and printed `the scorecard records None`, which is a scorecard being
    described as holding a value it does not hold (D79)."""
    if field not in block:
        raise DatasetError(
            f"scorecard {path} declares schema version {version!r} but its {block_name} "
            f"block has no {field!r}, so it does not have the shape it claims. An absent "
            f"field is a defect in the scorecard, not a disagreement between two values"
        )
    return block[field]


@dataclass(frozen=True)
class VerifyResult:
    outcome: Outcome
    causes: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.IDENTICAL


def _read_scorecard(path: Path) -> dict[str, Any]:
    """Load a stored scorecard, naming any way it fails to be one (D77).

    The shared reader pins ``parse_float=Decimal`` for every caller. It matters here
    precisely for the ill-formed case: a well-formed scorecard contains no JSON floats
    — every monetary value and ratio is emitted as an exact string (D37) and every
    count as an integer — but a doctored scorecard whose ratio was edited from
    `"0.9000"` into `0.9` is then read as a `Decimal` rather than silently becoming a
    float on the comparison path."""
    return read_json_object(path, f"scorecard {path}")


def _differences(
    stored: Any,
    fresh: Any,
    path: str = "",
    *,
    left: str = "stored",
    right: str = "recomputed",
) -> list[str]:
    """Every value that differs, named by its key path.

    Recurses in sorted key order so two runs of verify report the same differences in
    the same order — the same reason the scorecard itself serializes with a stable key
    ordering (U4). A message names one field, so the reader is told *what* changed
    rather than handed two documents.

    ``left`` and ``right`` name the two sides. They default to verify's own vocabulary,
    and exist because this comparison has a second caller: CI's cross-platform job sets
    them to the platform names. Reporting *"stored 4, recomputed 5"* for a difference
    between Linux and Windows would name the wrong distinction entirely — a message that
    misidentifies what it compared is the misdiagnosis D50 ruled worse than silence."""
    where = path or "<root>"
    if isinstance(stored, dict) and isinstance(fresh, dict):
        out: list[str] = []
        for key in sorted(set(stored) | set(fresh)):
            here = f"{path}.{key}" if path else str(key)
            if key not in stored:
                out.append(f"{here}: absent from {left}, present in {right} as {fresh[key]!r}")
            elif key not in fresh:
                out.append(f"{here}: present in {left} as {stored[key]!r}, absent from {right}")
            else:
                out.extend(_differences(stored[key], fresh[key], here, left=left, right=right))
        return out
    if isinstance(stored, list) and isinstance(fresh, list):
        if len(stored) != len(fresh):
            return [
                f"{where}: {left} holds {len(stored)} entr(y/ies), "
                f"{right} holds {len(fresh)}"
            ]
        out = []
        for position, (a, b) in enumerate(zip(stored, fresh)):
            out.extend(
                _differences(a, b, f"{path}[{position}]", left=left, right=right)
            )
        return out
    if stored != fresh:
        return [f"{where}: {left} {stored!r}, {right} {fresh!r}"]
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
        listing = _bounded([f"    {rel}  {digest}" for rel, digest in current], "file(s)")
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
    return [
        f"{len(causes)} file(s) diverge from the baseline at {baseline_inputs}:",
        *_bounded(causes, "diverging file(s)"),
    ]


def _recompute(
    dataset_ref: str, findings_path: Path, search_root: Path
) -> tuple[dict[str, Any], LoadedDataset]:
    """Score again, through exactly the code the original run went through.

    `load_findings_artifact` is shared with `cli.run_score` rather than reimplemented
    (D77). A second copy stood here, and this is the worst place in the project for one:
    if the two ever validated differently, verify would compare a scorecard against a
    recomputation whose inputs it had accepted on different terms, and report the
    disagreement as a scoring difference."""
    loaded = load_dataset(dataset_ref, search_root)
    agent, findings_sha = load_findings_artifact(findings_path)
    result = score(
        loaded.answer_key.expected_findings, agent, loaded.invoice_index.inventory
    )
    provenance = Provenance(
        dataset_identifier=loaded.manifest.identifier,
        dataset_version=loaded.manifest.version,
        findings_artifact_sha256=findings_sha,
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
    # No `str()` here, and that is the point (D78). It stood here, and it made the gate
    # accept `{"schema_version": 2}` as if it were `"2"` -- after which the RAW value
    # went on into the body comparison below and surfaced as
    # `schema_version: stored 2, recomputed '2'` under the heading "the same inputs
    # recompute to a different score". A shape defect reported as a scoring difference
    # is the exact outcome D66 recorded this feature to prevent, produced by a coercion
    # that existed to be lenient. A gate that normalises what it accepts must carry the
    # normalised value forward or not normalise at all; this one does neither, so it
    # does not normalise.
    stored_version = stored["schema_version"]
    if not isinstance(stored_version, str):
        return VerifyResult(
            Outcome.SCHEMA_UNRECOGNISED,
            (
                f"{scorecard_path} declares its schema version as "
                f"{type(stored_version).__name__} {stored_version!r}; this harness emits "
                f"it as the string {SCORECARD_SCHEMA_VERSION!r}. A scorecard whose "
                f"version field is not even the right type is not a shape this harness "
                f"recognises, so no comparison was attempted and this is NOT a scoring "
                f"discrepancy (D66, D78).",
            ),
        )
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

    # 2. Whether this is even the dataset the scorecard scored (D79). The scorecard
    #    records the identifier and version, verify holds both before it compares a
    #    single digest, and it did not look. Naming the wrong split -- the likeliest
    #    operator error on a command taking three separate paths -- produced three
    #    digest mismatches and a paragraph advising the reader to fetch a pristine
    #    inputs directory, sending them to hunt a file that never moved. The one-line
    #    answer was in hand the whole time, which is what makes this the misdiagnosis
    #    D50 rules worse than silence rather than merely a thin report.
    stored_dataset = _required_block(stored, "dataset", scorecard_path, stored_version)
    fresh_dataset = recomputed["dataset"]
    dataset_causes: list[str] = []
    for field, what in _DATASET_FIELDS:
        was = _required_field(stored_dataset, "dataset", field, scorecard_path, stored_version)
        now = fresh_dataset[field]
        if was != now:
            dataset_causes.append(
                f"the {what} does not match: the scorecard was produced from "
                f"{was!r}, and --dataset {dataset_ref!r} resolves to {now!r}"
            )
    if dataset_causes:
        return VerifyResult(
            Outcome.DATASET_MISMATCH,
            (
                "this is not the dataset the scorecard was produced from, so nothing "
                "below it was compared -- fingerprints included, since digests of a "
                "different dataset differ for a reason that is not tampering:",
                *dataset_causes,
            ),
        )

    # 3. Whether the same inputs were scored at all. Reported before any body
    #    comparison, because "you scored different data" and "the numbers are wrong"
    #    are different findings and only one of them is about scoring (D50).
    stored_fingerprints = _required_block(
        stored, "fingerprints", scorecard_path, stored_version
    )
    fingerprint_causes: list[str] = []
    fresh_fingerprints = recomputed["fingerprints"]
    for field, what in _FINGERPRINT_FIELDS:
        # `_required_field`, never `.get()`. An ABSENT digest was read as `None` and
        # reported as "the scorecard records None, the artifact on disk digests to
        # '9f3...'" -- a scorecard missing a required field, described as though it held
        # one and disagreed. The block was shape-checked and its members were not (D79).
        was = _required_field(
            stored_fingerprints, "fingerprints", field, scorecard_path, stored_version
        )
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

    # 4. Same inputs, so any remaining difference IS a scoring difference. The
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
        return VerifyResult(
            Outcome.SCORE_DIFFERS,
            (
                f"the same inputs recompute to a different score in {len(differences)} "
                f"place(s), so the stored scorecard does not report what it claims to "
                f"report:",
                *_bounded(differences, "difference(s)"),
            ),
        )

    return VerifyResult(
        Outcome.IDENTICAL,
        (
            f"recomputed from the same inputs and every scored field matches; all four "
            f"fingerprints agree and schema version {stored_version!r} is current.",
        ),
    )
