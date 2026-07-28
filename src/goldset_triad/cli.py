"""Command-line entry point for the scoring engine.

One shot: resolve a dataset, load the agent's findings, score, emit a scorecard,
exit. Any integrity failure halts with a named cause on stderr and a non-zero exit
code, writing no scorecard — a distorted score is worse than no score.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from . import ledger
from . import scorecard as sc
from .dataset import DatasetError, LoadedDataset, load_dataset, load_findings_artifact
from .schema import SchemaError
from .scoring import score
from .verify import Outcome, verify


def _utc_now_stamp() -> str:
    """The single wall-clock read in the whole harness — the scorecard run stamp,
    which lives in run_metadata and is excluded from the byte comparison (D6, D9)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_score(args: argparse.Namespace) -> int:
    findings_path = Path(args.findings)
    search_root = Path(args.datasets_root)

    t0 = time.perf_counter()
    loaded: LoadedDataset = load_dataset(args.dataset, search_root)
    # One loader, shared with verify's recompute path (D77). Two copies of this stood
    # here and in `verify._recompute`, in the one feature whose premise is that it
    # reproduces what scoring did.
    agent, findings_sha = load_findings_artifact(findings_path)
    t1 = time.perf_counter()

    result = score(loaded.answer_key.expected_findings, agent, loaded.invoice_index.inventory)
    t2 = time.perf_counter()

    provenance = sc.Provenance(
        dataset_identifier=loaded.manifest.identifier,
        dataset_version=loaded.manifest.version,
        findings_artifact_sha256=findings_sha,
        answer_key_sha256=loaded.answer_key.sha256,
        invoice_index_sha256=loaded.invoice_index.sha256,
        inputs_aggregate_sha256=loaded.inputs_aggregate_sha256,
    )
    run_metadata = sc.RunMetadata(
        run_timestamp=_utc_now_stamp(),
        load_ms=round((t1 - t0) * 1000),
        score_ms=round((t2 - t1) * 1000),
        total_ms=round((t2 - t0) * 1000),
    )
    card = sc.build_scorecard(result, provenance, run_metadata)
    card_json = sc.serialize(card)
    summary = sc.human_summary(card, result)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = run_metadata.run_timestamp.replace(":", "").replace("-", "")
    json_path, txt_path = _claim_scorecard_pair(
        out_dir, loaded.manifest.identifier, stamp, card_json, summary
    )

    # WHEN a run completes, one record is appended to the JSONL ledger. A failure here
    # warns and the run still exits zero: D9 makes the ledger a derived, regenerable
    # convenience view, so an unwritable one cannot make a correct score wrong. That is the
    # same shape as D9's own performance-breach exception, the one other place this harness
    # lets a warning coexist with success. Silence was rejected -- an absence nobody is told
    # about is the class D68 locked -- and so was halting, which would report a valid,
    # correctly-scored run as a failure because a local cache file could not be extended.
    try:
        ledger.append_record(out_dir, json_path)
    except (OSError, DatasetError) as exc:
        sys.stderr.write(
            f"warning: the run ledger could not be appended to: {exc}\n"
            f"warning: the score is unaffected and the scorecard is written. The ledger is a "
            f"derived view; `goldset-triad rebuild-ledger --out {out_dir}` regenerates it "
            f"from the scorecards alone (D9).\n"
        )

    sys.stdout.write(summary)
    sys.stdout.write(f"\nScorecard written to {json_path}\n")
    return 0


def run_rebuild_ledger(args: argparse.Namespace) -> int:
    """Regenerate the ledger from the scorecard directory alone (D9).

    The whole file is rewritten rather than reconciled, because that is what makes the
    guarantee testable: delete it, rebuild it, and the contents must be identical. A
    reconciling rebuild would pass that test while still being able to drift."""
    out_dir = Path(args.out)
    if not out_dir.is_dir():
        raise DatasetError(f"scorecard directory not found: {out_dir}")
    text = ledger.rebuild_text(out_dir)
    destination = Path(args.ledger) if args.ledger else ledger.ledger_path(out_dir)
    ledger.write_ledger(destination, text)
    runs = text.count("\n")
    sys.stdout.write(f"rebuilt {destination} from {runs} scorecard(s) in {out_dir}\n")
    return 0


def run_verify(args: argparse.Namespace) -> int:
    """Recompute a stored scorecard and report the first applicable outcome (D10, D66).

    Exit codes follow `check_isolation`: 0 when nothing differs, 1 when verify reached a
    verdict and that verdict is a difference, 2 when it could not reach one at all. The
    distinction matters — an unreadable scorecard is not a failed verification, it is a
    verification that never happened, and reporting the second as the first is the
    misdiagnosis D50 ruled worse than silence."""
    baseline = Path(args.baseline_inputs) if args.baseline_inputs else None
    result = verify(
        scorecard_path=Path(args.scorecard),
        dataset_ref=args.dataset,
        findings_path=Path(args.findings),
        search_root=Path(args.datasets_root),
        baseline_inputs=baseline,
    )
    if result.ok:
        # ASCII only on the console path. The Windows console decodes as cp1252 here, and
        # an em dash written to it is the same class of unstated platform dependency D61
        # found in text reads -- it is just cheaper to avoid than to pin.
        sys.stdout.write(f"verify: {result.outcome.value} - {result.causes[0]}\n")
        return 0
    stream = sys.stderr
    stream.write(f"VERIFY FAILED [{result.outcome.value}]\n")
    for cause in result.causes:
        stream.write(f"  {cause}\n")
    if result.outcome is Outcome.SCHEMA_UNRECOGNISED:
        stream.write(
            "  This is a shape mismatch, not a scoring difference. Re-score the inputs "
            "with this version of the harness to obtain a comparable scorecard (D66).\n"
        )
    if result.outcome is Outcome.SUMMARY_DIFFERS:
        stream.write(
            "  The JSON scorecard is intact and its numbers recompute exactly; only the "
            "human summary beside it differs. Re-render it by re-scoring, or treat the "
            "JSON as authoritative — it is the durable record (D9, D118).\n"
        )
    if result.outcome is Outcome.DATASET_MISMATCH:
        stream.write(
            "  Nothing about the score was checked. Re-run with --dataset naming the "
            "split the scorecard records, which is printed above (D79).\n"
        )
    return 1


def _write_new_file(path: Path, text: str) -> None:
    """Create ``path`` and write ``text``, failing if it already exists.

    Mode ``"x"`` makes overwriting a prior scorecard impossible at the operating
    system level rather than merely unintended — scorecards are the durable record
    and the harness SHALL NOT overwrite one.

    ``newline="\\n"`` is pinned for the same reason it is pinned in the generator
    (D43): without it Python translates "\\n" to the platform default, so the same
    run would emit CRLF on Windows and LF on Linux. The scorecard bytes would then
    differ by platform, contradicting the requirement that identical inputs yield
    identical scorecard content on Windows and on Linux."""
    with open(path, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


#: How many times to re-reserve when another process claims the name first (D114). Each
#: retry costs one filesystem round trip and only happens when two runs genuinely collide,
#: so a small bound is enough to make the race vanishingly unlikely while still terminating
#: rather than spinning: if this many consecutive reservations are all taken, something
#: other than a race is going on and saying so beats retrying forever.
_CLAIM_ATTEMPTS: Final = 8


def _claim_scorecard_pair(
    out_dir: Path, identifier: str, stamp: str, card_json: str, summary: str
) -> tuple[Path, Path]:
    """Reserve a free stem and write both halves, retrying if another run gets there first.

    **The gap this closes.** `_reserve_scorecard_paths` checks `.exists()` and
    `_write_new_file` then creates with mode `"x"`. Between those two steps another process
    can take the name, and `"x"` raises `FileExistsError` — which is neither `DatasetError`
    nor `SchemaError`, so it escaped `main()` and surfaced as a traceback. That breaks the
    failure policy ("every halt names its specific cause and exits non-zero") in a project
    whose whole posture is that a defect must not present as a defect in something else.

    Three sweeps recorded this in the negative-space list and none fixed it. Recording a
    gap is the right move when closing it needs a decision; this one needed six lines, and
    the record was standing in for the fix.

    **The exclusive create stays.** D49 chose `"x"` so that overwriting a scorecard is
    impossible at the operating-system level rather than merely unintended, and that is
    exactly what makes the retry safe: the loser of a race is *told* it lost instead of
    silently destroying the winner's record. The retry re-reserves rather than incrementing
    blindly, so it cannot skip past a name another run has already released.

    **The `.txt` half can also lose**, and losing it after the `.json` landed would leave a
    half-written pair. So the pair is claimed together and the JSON is removed if the text
    half is taken — the same "never straddle two stems" rule `_reserve_scorecard_paths`
    already applies to the reservation."""
    for _attempt in range(_CLAIM_ATTEMPTS):
        json_path, txt_path = _reserve_scorecard_paths(out_dir, identifier, stamp)
        try:
            _write_new_file(json_path, card_json)
        except FileExistsError:
            continue
        try:
            _write_new_file(txt_path, summary)
        except FileExistsError:
            # Undo the half that landed. Removing a file this run created moments ago is
            # not the "never delete a scorecard" rule (D49) — nothing has read it, and
            # leaving it would publish a scorecard with no human summary beside it.
            json_path.unlink(missing_ok=True)
            continue
        return json_path, txt_path
    raise DatasetError(
        f"could not claim a scorecard filename in {out_dir} after {_CLAIM_ATTEMPTS} "
        f"attempts: another process took every name this run reserved. Nothing was "
        f"written and no existing scorecard was touched; re-run, or give this run its own "
        f"--out directory (D114)"
    )


def _reserve_scorecard_paths(out_dir: Path, identifier: str, stamp: str) -> tuple[Path, Path]:
    """Pick a stem whose .json and .txt are both free (D49), unique in its second (D80).

    The run stamp is second-precision, because every timestamp this harness writes
    is (D6) — so two runs inside the same second would otherwise derive the same
    filename and the second would silently destroy the first. An ordinal
    disambiguates without introducing a sub-second timestamp, which would break the
    second-precision rule. Both extensions are checked together so the pair never
    straddles two stems.

    **The ordinal is reserved across the whole directory-second, not per stem (D80).**
    It was per stem, and a stem carries the dataset identifier — so scoring `dev` and
    `dev-zero-defect` inside one second gave *both* files ordinal 1. Filenames stayed
    unique, which is all D49 asked for, but the ledger's `(stamp, ordinal)` run order
    then had a tie it could not break, and fell through to directory order: name-ordered
    on NTFS, hash-ordered on ext4. The ledger's regeneration guarantee would have failed
    on Linux and held on the machine it was written on. Reserving per second makes the
    ordinal mean *the nth run in this directory in this second*, which is what a run
    order needs it to mean."""
    base_stem = f"scorecard-{identifier}-{stamp}"
    taken: set[int] = set()
    for path in out_dir.glob("scorecard-*.json"):
        if not path.is_file():
            continue
        try:
            parsed = ledger.parse_scorecard_name(path.name)
        except DatasetError:
            # A neighbour this harness did not emit holds no ordinal in this second, and
            # it can never collide with a name generated below, which always matches the
            # grammar. Reservation therefore SKIPS what it cannot parse (D83).
            #
            # It did not. D80 widened this scan from one stem to the directory-second and,
            # in doing so, let the ledger's filename grammar halt a *scoring* run: the
            # harness refused to write the durable record because of an unrelated
            # neighbouring file, and blamed "the ledger", a derived view the caller never
            # invoked. D75 had already settled that direction — an unwritable ledger warns
            # and the run exits zero, because a derived, regenerable view must not make a
            # correct score fail. The halt stays where the order genuinely cannot be
            # justified, in `ledger.rebuild_text`.
            continue
        if parsed.stamp == stamp:
            taken.add(parsed.ordinal)
    for ordinal in range(1, 10_000):
        if ordinal in taken:
            continue
        stem = base_stem if ordinal == 1 else f"{base_stem}-{ordinal}"
        json_path = out_dir / f"{stem}.json"
        txt_path = out_dir / f"{stem}.txt"
        if not json_path.exists() and not txt_path.exists():
            return json_path, txt_path
    raise DatasetError(
        f"cannot reserve a scorecard filename in {out_dir}: 9999 runs already share "
        f"the run stamp '{stamp}'"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goldset-triad",
        description="Score an AP document-matching agent's findings against a golden dataset.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    score_p = sub.add_parser("score", help="score a findings artifact against a dataset")
    score_p.add_argument(
        "--dataset", required=True, help="dataset identifier or path to a manifest.json"
    )
    score_p.add_argument(
        "--findings", required=True, help="path to the agent's findings artifact (JSON)"
    )
    score_p.add_argument(
        "--datasets-root",
        default="datasets",
        help="root under which a dataset identifier resolves (default: datasets)",
    )
    score_p.add_argument(
        "--out", default="scorecards", help="directory for emitted scorecards (default: scorecards)"
    )
    score_p.set_defaults(func=run_score)

    verify_p = sub.add_parser(
        "verify",
        help="recompute a stored scorecard from its inputs and report any difference",
        description=(
            "Recompute the score from the dataset and findings artifact a scorecard "
            "claims to have scored, and report the first applicable outcome: an "
            "unrecognised schema version, a fingerprint mismatch, a scoring difference, "
            "or identical. The dataset and findings are named again because a scorecard "
            "records fingerprints, not paths — a digest confirms identity, it does not "
            "locate a file."
        ),
    )
    verify_p.add_argument("--scorecard", required=True, help="path to the stored scorecard JSON")
    verify_p.add_argument(
        "--dataset", required=True, help="dataset identifier or path to a manifest.json"
    )
    verify_p.add_argument(
        "--findings", required=True, help="path to the findings artifact that was scored"
    )
    verify_p.add_argument(
        "--datasets-root",
        default="datasets",
        help="root under which a dataset identifier resolves (default: datasets)",
    )
    verify_p.add_argument(
        "--baseline-inputs",
        default=None,
        help="a pristine inputs directory to diff against when the aggregate inputs "
             "digest differs; without it verify can name that the inputs moved but not "
             "which file, since the scorecard stores only the aggregate (D27, D74)",
    )
    verify_p.set_defaults(func=run_verify)

    ledger_p = sub.add_parser(
        "rebuild-ledger",
        help="regenerate the JSONL run ledger from the scorecard directory alone",
        description=(
            "Rewrite the run ledger from the scorecards in a directory. The ledger is a "
            "derived, local-only convenience view (D9): scorecards are the durable record, "
            "so deleting the ledger loses nothing and rebuilding it reproduces identical "
            "contents."
        ),
    )
    ledger_p.add_argument(
        "--out", default="scorecards",
        help="the scorecard directory to rebuild from (default: scorecards)",
    )
    ledger_p.add_argument(
        "--ledger", default=None,
        help=f"where to write it (default: <out>/{ledger.LEDGER_FILENAME})",
    )
    ledger_p.set_defaults(func=run_rebuild_ledger)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (DatasetError, SchemaError) as exc:
        # Every halt names its specific cause and exits non-zero, writing no
        # scorecard (failure & escalation policy).
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
