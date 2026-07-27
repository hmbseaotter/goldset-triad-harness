"""Command-line entry point for the scoring engine.

One shot: resolve a dataset, load the agent's findings, score, emit a scorecard,
exit. Any integrity failure halts with a named cause on stderr and a non-zero exit
code, writing no scorecard — a distorted score is worse than no score.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from . import ledger
from . import scorecard as sc
from .dataset import DatasetError, LoadedDataset, load_dataset, sha256_file
from .schema import SchemaError, parse_findings_artifact
from .scoring import score
from .verify import Outcome, verify


def _utc_now_stamp() -> str:
    """The single wall-clock read in the whole harness — the scorecard run stamp,
    which lives in run_metadata and is excluded from the byte comparison (D6, D9)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_findings(path: Path) -> tuple[object, str]:
    if not path.is_file():
        raise DatasetError(f"findings artifact not found: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        raw = json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"findings artifact is not valid JSON: {exc}")
    return raw, sha256_file(path)


def run_score(args: argparse.Namespace) -> int:
    findings_path = Path(args.findings)
    search_root = Path(args.datasets_root)

    t0 = time.perf_counter()
    loaded: LoadedDataset = load_dataset(args.dataset, search_root)
    raw_findings, findings_sha = _load_findings(findings_path)
    agent = parse_findings_artifact(raw_findings)
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
    json_path, txt_path = _reserve_scorecard_paths(
        out_dir, f"scorecard-{loaded.manifest.identifier}-{stamp}"
    )
    _write_new_file(json_path, card_json)
    _write_new_file(txt_path, summary)

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


def _reserve_scorecard_paths(out_dir: Path, base_stem: str) -> tuple[Path, Path]:
    """Pick a stem whose .json and .txt are both free (D49).

    The run stamp is second-precision, because every timestamp this harness writes
    is (D6) — so two runs inside the same second would otherwise derive the same
    filename and the second would silently destroy the first. An ordinal
    disambiguates without introducing a sub-second timestamp, which would break the
    second-precision rule. Both extensions are checked together so the pair never
    straddles two stems."""
    for ordinal in range(1, 10_000):
        stem = base_stem if ordinal == 1 else f"{base_stem}-{ordinal}"
        json_path = out_dir / f"{stem}.json"
        txt_path = out_dir / f"{stem}.txt"
        if not json_path.exists() and not txt_path.exists():
            return json_path, txt_path
    raise DatasetError(
        f"cannot reserve a scorecard filename in {out_dir}: 9999 runs already share "
        f"the stem '{base_stem}'"
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
