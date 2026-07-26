"""Scorecard emission, reproducibility, run_metadata, fingerprints, cross-precision."""

from __future__ import annotations

import decimal
import json
import tempfile
import unittest
from pathlib import Path

from tests import support
from goldset_triad import scorecard as sc
from goldset_triad.dataset import load_dataset
from goldset_triad.scoring import score


def _score_dev():
    ld = load_dataset("dev", support.DATASETS)
    agent = support.perfect_artifact("dev")
    result = score(ld.answer_key.expected_findings, agent, ld.invoice_index.inventory)
    prov = sc.Provenance("dev", ld.manifest.version, "f" * 64, ld.answer_key.sha256,
                         ld.invoice_index.sha256, ld.inputs_aggregate_sha256)
    return result, prov, ld


class ScorecardTests(unittest.TestCase):
    def test_json_parses_and_summary_emitted(self) -> None:
        result, prov, _ = _score_dev()
        card = sc.build_scorecard(result, prov, sc.RunMetadata("2026-07-26T10:00:00Z", 1, 2, 3))
        parsed = json.loads(sc.serialize(card))  # parses
        self.assertEqual(parsed["dataset"]["identifier"], "dev")
        self.assertIn("Scorecard", sc.human_summary(card, result))

    def test_records_dataset_identifier_and_version(self) -> None:
        result, prov, ld = _score_dev()
        card = sc.build_scorecard(result, prov, sc.RunMetadata("2026-07-26T10:00:00Z", 1, 2, 3))
        self.assertEqual(card["dataset"]["identifier"], "dev")
        self.assertEqual(card["dataset"]["version"], ld.manifest.version)

    def test_embeds_four_fingerprints(self) -> None:
        result, prov, _ = _score_dev()
        card = sc.build_scorecard(result, prov, sc.RunMetadata("2026-07-26T10:00:00Z", 1, 2, 3))
        fp = card["fingerprints"]
        self.assertEqual(set(fp), {"findings_artifact_sha256", "answer_key_sha256",
                                   "invoice_index_sha256", "inputs_aggregate_sha256"})

    def test_run_metadata_holds_only_timestamp_and_three_durations(self) -> None:
        result, prov, _ = _score_dev()
        card = sc.build_scorecard(result, prov, sc.RunMetadata("2026-07-26T10:00:00Z", 1, 2, 3))
        self.assertEqual(set(card["run_metadata"]),
                         {"run_timestamp", "load_ms", "score_ms", "total_ms"})

    def test_excluding_run_metadata_makes_two_runs_byte_identical(self) -> None:
        result, prov, _ = _score_dev()
        c1 = sc.build_scorecard(result, prov, sc.RunMetadata("2026-07-26T10:00:00Z", 1, 2, 3))
        c2 = sc.build_scorecard(result, prov, sc.RunMetadata("2026-07-26T23:59:59Z", 9, 8, 17))
        self.assertEqual(sc.deterministic_body(c1), sc.deterministic_body(c2))
        self.assertNotEqual(sc.serialize(c1), sc.serialize(c2))

    def test_counts_in_scored_body_and_alter_changes_bytes(self) -> None:
        result, prov, _ = _score_dev()
        card = sc.build_scorecard(result, prov, sc.RunMetadata("2026-07-26T10:00:00Z", 1, 2, 3))
        self.assertIn("invoice_count", card["workload"])
        self.assertIn("finding_count", card["workload"])
        before = sc.deterministic_body(card)
        card["workload"]["invoice_count"] += 1
        self.assertNotEqual(before, sc.deterministic_body(card))

    def test_undefined_metrics_emitted_as_null_never_zero_or_omitted(self) -> None:
        # dev-zero-defect empty artifact -> overall precision & recall null.
        ld = load_dataset("dev-zero-defect", support.DATASETS)
        result = score(ld.answer_key.expected_findings, (), ld.invoice_index.inventory)
        prov = sc.Provenance("dev-zero-defect", "1.0.0", "f" * 64, ld.answer_key.sha256,
                             ld.invoice_index.sha256, ld.inputs_aggregate_sha256)
        card = sc.build_scorecard(result, prov, sc.RunMetadata("2026-07-26T10:00:00Z", 1, 2, 3))
        self.assertIsNone(card["metrics"]["overall"]["precision"])
        self.assertIsNone(card["metrics"]["overall"]["recall"])
        # the key is present (not omitted)
        self.assertIn("precision", card["metrics"]["overall"])

    def test_ratios_emitted_at_declared_places(self) -> None:
        result, prov, _ = _score_dev()
        card = sc.build_scorecard(result, prov, sc.RunMetadata("2026-07-26T10:00:00Z", 1, 2, 3))
        self.assertEqual(card["metrics"]["overall"]["precision"], "1.0000")

    def test_cross_precision_byte_identical(self) -> None:
        result, prov, _ = _score_dev()
        rm = sc.RunMetadata("2026-07-26T10:00:00Z", 1, 2, 3)
        with decimal.localcontext() as ctx:
            ctx.prec = 12
            body_a = sc.deterministic_body(sc.build_scorecard(result, prov, rm))
        with decimal.localcontext() as ctx:
            ctx.prec = 50
            body_b = sc.deterministic_body(sc.build_scorecard(result, prov, rm))
        self.assertEqual(body_a, body_b)

    def test_summary_names_each_miss_and_false_flag(self) -> None:
        ld = load_dataset("dev", support.DATASETS)
        # Drop one expected, add one spurious.
        agent = support.perfect_artifact("dev")[1:] + (
            support.line(__import__("goldset_triad.schema", fromlist=["Category"]).Category.PRICE_VARIANCE,
                         "INV-2004", "1"),
        )
        result = score(ld.answer_key.expected_findings, agent, ld.invoice_index.inventory)
        prov = sc.Provenance("dev", "1.0.0", "f" * 64, ld.answer_key.sha256,
                             ld.invoice_index.sha256, ld.inputs_aggregate_sha256)
        card = sc.build_scorecard(result, prov, sc.RunMetadata("2026-07-26T10:00:00Z", 1, 2, 3))
        summary = sc.human_summary(card, result)
        self.assertGreaterEqual(len(result.missed), 1)
        self.assertGreaterEqual(len(result.false_flags), 1)
        for f in result.missed:
            self.assertIn(f.target.document_id, summary)
        self.assertIn("INV-2004", summary)  # the false flag's target


if __name__ == "__main__":
    unittest.main()
