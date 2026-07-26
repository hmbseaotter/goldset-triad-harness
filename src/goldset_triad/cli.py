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

from . import scorecard as sc
from .dataset import DatasetError, LoadedDataset, load_dataset, sha256_file
from .schema import SchemaError, parse_findings_artifact
from .scoring import score


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

    sys.stdout.write(summary)
    sys.stdout.write(f"\nScorecard written to {json_path}\n")
    return 0


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
