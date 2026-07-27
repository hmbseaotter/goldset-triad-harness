"""The append-only JSONL run ledger — a derived view, regenerable from scorecards (D9).

D9 settled what this is and, just as importantly, what it is not. **Scorecards are the
durable record**: never overwritten (D49), committed, and the thing a reader is meant to
trust. The ledger is a *convenience view* over them — local-only, gitignored, and
**regenerable from the scorecard directory alone**, which is precisely why deleting it may
lose nothing. A derived file that could not be rebuilt would be the tamper-and-loss risk
this architecture exists to avoid.

**Every field comes from a scorecard, or the rebuild could not reproduce it.** That is the
constraint that shapes the record: not "what would be nice to have here" but "what can be
recovered from the directory". One field comes from the *filename* rather than the
contents — the D49 collision ordinal, which exists nowhere else.

**No fingerprints.** Adding the four digests was considered and rejected: D9 scopes this to
a per-machine duration and workload trend, the scorecard already carries provenance under
the byte-identical comparison, and copying claim-shaped fields into a derived artifact would
manufacture claims that nothing compares — the exact shape D67 exists to end. Provenance
questions are answered by the scorecard, and by `verify` (D74).

**Ordering is not obvious, and getting it wrong breaks the regeneration guarantee.**
Scorecard stems carry the D49 ordinal, and the ordinal is *lexicographic* in a filename, so
a naive directory sort yields run 10, then run 2, then run 1:

    scorecard-dev-20260727T033502Z-10.json
    scorecard-dev-20260727T033502Z-2.json
    scorecard-dev-20260727T033502Z.json

Appends happen in chronological order, so a rebuild that sorted by filename would produce a
*differently ordered* ledger with identical content — and "regenerating reproduces identical
contents" would fail on a case nobody would think to test. The sort key is therefore
`(run_timestamp, ordinal-as-integer)`, with the ordinal parsed as a number.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .jsonio import DatasetError, read_json_object

#: Named to match the pattern `.gitignore` already carries. A bare filename pattern with no
#: slash matches at any depth, so the ledger is ignored wherever the scorecard directory is.
LEDGER_FILENAME: Final = "run-ledger.jsonl"

#: `scorecard-<identifier>-<stamp>[-<ordinal>].json`. Anchored on the stamp's shape rather
#: than on dashes, because an identifier legitimately contains them (`dev-zero-defect`).
_SCORECARD_NAME = re.compile(
    r"^scorecard-(?P<identifier>.+)-(?P<stamp>\d{8}T\d{6}Z)(?:-(?P<ordinal>\d+))?\.json$"
)


def ledger_path(scorecard_dir: Path) -> Path:
    """The ledger belongs *in* the directory it describes.

    A ledger elsewhere would outlive the relationship: a run writing to a different
    output directory would append to a file describing a directory it no longer reads,
    and the regeneration guarantee is stated against *the scorecard directory alone*."""
    return scorecard_dir / LEDGER_FILENAME


@dataclass(frozen=True)
class ScorecardName:
    """A scorecard filename, parsed once (D80).

    There were two parsers — `_stamp_of` and `_ordinal_of` — each re-running the same
    regex and each raising its own message for the identical failure. Which one a reader
    saw depended on the order Python happened to evaluate a sort-key tuple, and it was
    the terser of the two: the message naming the expected filename shape, written to
    help, was unreachable from every call path that existed."""

    identifier: str
    stamp: str
    ordinal: int

    @property
    def order_key(self) -> tuple[str, int]:
        """Run order. See :func:`scorecards_in` for why it is not filename order."""
        return (self.stamp, self.ordinal)


def parse_scorecard_name(name: str) -> ScorecardName:
    """Split a scorecard filename into identifier, run stamp and D49 collision ordinal.

    Reading a missing ordinal suffix as 1 is not an absence-becoming-a-number (D68): the
    writer omits the suffix *exactly when* the ordinal is 1, so this is the inverse of an
    encoding rather than a guess about missing data."""
    match = _SCORECARD_NAME.match(name)
    if match is None:
        raise DatasetError(
            f"{name} does not look like a scorecard emitted by this harness, so the ledger "
            f"cannot place it in run order; expected "
            f"scorecard-<identifier>-<YYYYMMDDTHHMMSSZ>[-<ordinal>].json"
        )
    suffix = match.group("ordinal")
    return ScorecardName(
        identifier=match.group("identifier"),
        stamp=match.group("stamp"),
        ordinal=1 if suffix is None else int(suffix),
    )


#: The record's whole shape: `(ledger key, dotted scorecard path, may this be null?)`.
#:
#: A table rather than a hand-written dict literal, because the nullability is the part
#: that needed stating. `_require` checked *presence* and called that validation, so a
#: scorecard carrying `"run_timestamp": null` produced a ledger record with a null run
#: timestamp — the field the entire run order rests on — and nothing said so (D80).
#:
#: The three ratios genuinely may be null, and that is not an oversight: D40 requires an
#: undefined metric to be emitted as `null` rather than as zero or omitted, so a null
#: precision is a *value* meaning "undefined on this split", not an absence. The counts
#: and the timestamps have no such reading.
_LEDGER_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("run_timestamp", "run_metadata.run_timestamp", False),
    ("schema_version", "schema_version", False),
    ("dataset_identifier", "dataset.identifier", False),
    ("dataset_version", "dataset.version", False),
    ("invoice_count", "workload.invoice_count", False),
    ("finding_count", "workload.finding_count", False),
    ("overall_precision", "metrics.overall.precision", True),
    ("overall_recall", "metrics.overall.recall", True),
    ("false_positive_count", "metrics.false_positive_count", False),
    ("false_positive_rate", "metrics.false_positive_rate", True),
    # D9's actual purpose: a per-machine duration trend. The caveat travels with it —
    # a ledger spanning a laptop and a CI runner compares nothing.
    ("load_ms", "run_metadata.load_ms", False),
    ("score_ms", "run_metadata.score_ms", False),
    ("total_ms", "run_metadata.total_ms", False),
)


def _require(card: dict[str, Any], path: str, source: Path, *, nullable: bool) -> Any:
    """Fetch a nested scorecard field, naming the scorecard and the field when absent.

    Deliberately no default. A missing field means the file is not the artifact this
    harness emits, and quietly substituting a value would put an invented number into the
    durable record's derived view.

    ``nullable`` is required rather than defaulted so that adding a field forces the
    question to be answered. Presence is not validity: `null` is present."""
    node: Any = card
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise DatasetError(
                f"scorecard {source} has no '{path}' field, so it is not a scorecard this "
                f"harness emitted and no ledger record can be derived from it"
            )
        node = node[part]
    if node is None and not nullable:
        raise DatasetError(
            f"scorecard {source} carries '{path}': null. That field is never undefined in "
            f"a scorecard this harness emits — only the three ratios may be null, and only "
            f"because D40 emits an undefined metric as null rather than as zero — so no "
            f"ledger record can be derived from it"
        )
    return node


def record_for(scorecard_path: Path) -> dict[str, Any]:
    """One ledger record, derived entirely from a scorecard and its filename.

    The shared reader (D77) — this site did not even check the file existed, so a
    scorecard deleted between the directory listing and the read produced a traceback
    from a rebuild whose whole promise is that it can be re-run at any time."""
    card = read_json_object(scorecard_path, f"scorecard {scorecard_path}")
    record: dict[str, Any] = {
        # The filename, because the D49 ordinal lives nowhere else and two runs inside one
        # second are otherwise indistinguishable in this view.
        "scorecard": scorecard_path.name,
    }
    for key, dotted, nullable in _LEDGER_FIELDS:
        record[key] = _require(card, dotted, scorecard_path, nullable=nullable)
    return record


def serialize_record(record: dict[str, Any]) -> str:
    """One JSONL line, with the same stable key ordering the scorecard uses (U4), so an
    appended line and a rebuilt one are byte-identical rather than merely equivalent."""
    return json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n"


def scorecards_in(scorecard_dir: Path) -> list[Path]:
    """Every scorecard in the directory, in run order.

    Sorted by `(stamp, ordinal)` and never by filename — see this module's docstring for
    why a filename sort puts run 10 before run 2 before run 1.

    **And the key has to be total, which it was not (D80).** The ordinal was reserved
    per *stem*, and a stem carries the dataset identifier, so two splits scored inside
    one second both took ordinal 1 and produced an identical sort key. Python's sort is
    stable, so order then fell through to `glob` order — `os.scandir` order, which is
    name-ordered on NTFS and hash-ordered on ext4. Appends happen chronologically, so on
    Linux a rebuild could reorder them, and *"delete the ledger, rebuild it, get the same
    file"* — the guarantee that makes the ledger safe to delete — would fail on a machine
    nobody tested it on. The ordinal is now reserved across the whole directory-second
    (`cli._reserve_scorecard_paths`), which makes the key total *and* chronological.

    A residual tie can still be constructed by hand-placing files, so it halts rather
    than picking one: an order the ledger cannot justify is not an order."""
    if not scorecard_dir.is_dir():
        raise DatasetError(
            f"scorecard directory not found: {scorecard_dir}. An empty ledger and a "
            f"mistyped path are not the same answer"
        )
    keyed: list[tuple[ScorecardName, Path]] = [
        (parse_scorecard_name(p.name), p)
        for p in scorecard_dir.glob("*.json")
        if p.is_file()
    ]
    seen: dict[tuple[str, int], Path] = {}
    for parsed, path in sorted(keyed, key=lambda e: e[1].name):
        clash = seen.get(parsed.order_key)
        if clash is not None:
            raise DatasetError(
                f"{path.name} and {clash.name} share run stamp {parsed.stamp} and "
                f"ordinal {parsed.ordinal}, so the ledger cannot say which ran first. "
                f"The harness reserves one ordinal per directory-second (D80), so these "
                f"were not both written by it; remove or rename one"
            )
        seen[parsed.order_key] = path
    return [path for parsed, path in sorted(keyed, key=lambda e: e[0].order_key)]


def rebuild_text(scorecard_dir: Path) -> str:
    """The whole ledger, regenerated from the scorecard directory alone (D9)."""
    return "".join(serialize_record(record_for(p)) for p in scorecards_in(scorecard_dir))


def write_ledger(path: Path, text: str) -> None:
    """`newline="\\n"` pinned for the reason every write in this project pins it (D49,
    D61): without it the same run emits CRLF on Windows and LF on Linux, so a rebuilt
    ledger would differ from an appended one by platform alone.

    The write is guarded for the same reason the reads are (D77): `--ledger` takes a
    path from the caller, and a destination whose parent does not exist produced a bare
    `FileNotFoundError` rather than a halt naming what could not be written."""
    try:
        path.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise DatasetError(
            f"the run ledger could not be written to {path} ({exc}). The scorecards it "
            f"derives from are untouched; name a destination whose directory exists"
        ) from exc


def append_record(scorecard_dir: Path, scorecard_path: Path) -> None:
    """Append one record for a completed run.

    Append-only by construction: opened in `"a"`, never rewritten, so an earlier run's line
    cannot be disturbed by a later one."""
    line = serialize_record(record_for(scorecard_path))
    with open(ledger_path(scorecard_dir), "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
