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
from pathlib import Path
from typing import Any, Final

from .dataset import DatasetError

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


def _ordinal_of(name: str) -> int:
    """The D49 collision ordinal encoded in a scorecard's filename.

    Not an absence-becoming-a-number (D68): the writer omits the suffix *exactly when* the
    ordinal is 1 — `stem if ordinal == 1 else f"{stem}-{ordinal}"` — so reading absence as 1
    is the inverse of that encoding rather than a guess about missing data."""
    match = _SCORECARD_NAME.match(name)
    if match is None:
        raise DatasetError(
            f"{name} does not look like a scorecard emitted by this harness, so the ledger "
            f"cannot place it in run order; expected "
            f"scorecard-<identifier>-<YYYYMMDDTHHMMSSZ>[-<ordinal>].json"
        )
    suffix = match.group("ordinal")
    return 1 if suffix is None else int(suffix)


def _require(card: dict[str, Any], path: str, source: Path) -> Any:
    """Fetch a nested scorecard field, naming the scorecard and the field when absent.

    Deliberately no default. A missing field means the file is not the artifact this
    harness emits, and quietly substituting a value would put an invented number into the
    durable record's derived view."""
    node: Any = card
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise DatasetError(
                f"scorecard {source} has no '{path}' field, so it is not a scorecard this "
                f"harness emitted and no ledger record can be derived from it"
            )
        node = node[part]
    return node


def record_for(scorecard_path: Path) -> dict[str, Any]:
    """One ledger record, derived entirely from a scorecard and its filename."""
    try:
        card = json.loads(scorecard_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"scorecard {scorecard_path} is not valid JSON: {exc}")
    if not isinstance(card, dict):
        raise DatasetError(f"scorecard {scorecard_path} is not a JSON object")

    get = lambda path: _require(card, path, scorecard_path)  # noqa: E731
    return {
        # The filename, because the D49 ordinal lives nowhere else and two runs inside one
        # second are otherwise indistinguishable in this view.
        "scorecard": scorecard_path.name,
        "run_timestamp": get("run_metadata.run_timestamp"),
        "schema_version": get("schema_version"),
        "dataset_identifier": get("dataset.identifier"),
        "dataset_version": get("dataset.version"),
        "invoice_count": get("workload.invoice_count"),
        "finding_count": get("workload.finding_count"),
        "overall_precision": get("metrics.overall.precision"),
        "overall_recall": get("metrics.overall.recall"),
        "false_positive_count": get("metrics.false_positive_count"),
        "false_positive_rate": get("metrics.false_positive_rate"),
        # D9's actual purpose: a per-machine duration trend. The caveat travels with it —
        # a ledger spanning a laptop and a CI runner compares nothing.
        "load_ms": get("run_metadata.load_ms"),
        "score_ms": get("run_metadata.score_ms"),
        "total_ms": get("run_metadata.total_ms"),
    }


def serialize_record(record: dict[str, Any]) -> str:
    """One JSONL line, with the same stable key ordering the scorecard uses (U4), so an
    appended line and a rebuilt one are byte-identical rather than merely equivalent."""
    return json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n"


def scorecards_in(scorecard_dir: Path) -> list[Path]:
    """Every scorecard in the directory, in run order.

    Sorted by `(run_timestamp, ordinal)` and never by filename — see this module's
    docstring for why a filename sort puts run 10 before run 2 before run 1."""
    if not scorecard_dir.is_dir():
        return []
    cards = [p for p in scorecard_dir.glob("*.json") if p.is_file()]
    return sorted(cards, key=lambda p: (_stamp_of(p.name), _ordinal_of(p.name)))


def _stamp_of(name: str) -> str:
    match = _SCORECARD_NAME.match(name)
    if match is None:
        raise DatasetError(
            f"{name} does not look like a scorecard emitted by this harness, so the ledger "
            f"cannot place it in run order"
        )
    return match.group("stamp")


def rebuild_text(scorecard_dir: Path) -> str:
    """The whole ledger, regenerated from the scorecard directory alone (D9)."""
    return "".join(serialize_record(record_for(p)) for p in scorecards_in(scorecard_dir))


def write_ledger(path: Path, text: str) -> None:
    """`newline="\\n"` pinned for the reason every write in this project pins it (D49,
    D61): without it the same run emits CRLF on Windows and LF on Linux, so a rebuilt
    ledger would differ from an appended one by platform alone."""
    path.write_text(text, encoding="utf-8", newline="\n")


def append_record(scorecard_dir: Path, scorecard_path: Path) -> None:
    """Append one record for a completed run.

    Append-only by construction: opened in `"a"`, never rewritten, so an earlier run's line
    cannot be disturbed by a later one."""
    line = serialize_record(record_for(scorecard_path))
    with open(ledger_path(scorecard_dir), "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
