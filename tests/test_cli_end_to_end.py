"""End-to-end CLI: a full scoring run, and the halts that write no scorecard."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests import support
from goldset_triad.cli import main
from goldset_triad.dataset import per_file_digests, resolve_manifest


def _write_findings(path: Path, findings: list[dict]) -> None:
    path.write_text(json.dumps({"schema_version": "1", "findings": findings}))


class CliEndToEndTests(unittest.TestCase):
    def _perfect_findings(self) -> list[dict]:
        key = support.read_json(support.key_path("dev"))
        return [{k: e[k] for k in ("status", "category", "scope", "target")}
                for e in key["expected_findings"]]

    def test_happy_path_emits_scorecard_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "findings.json"
            _write_findings(fp, self._perfect_findings())
            out = Path(td) / "out"
            rc = main(["score", "--dataset", "dev", "--datasets-root",
                       str(support.DATASETS), "--findings", str(fp), "--out", str(out)])
            self.assertEqual(rc, 0)
            cards = list(out.glob("*.json"))
            self.assertEqual(len(cards), 1)
            card = json.loads(cards[0].read_text())
            self.assertEqual(card["metrics"]["overall"]["precision"], "1.0000")
            self.assertEqual(card["metrics"]["overall"]["recall"], "1.0000")
            self.assertTrue(list(out.glob("*.txt")))  # human summary too

    def test_malformed_findings_halts_nonzero_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "bad.json"
            _write_findings(fp, [{"status": "DISCREPANCY", "category": "NOT_A_CATEGORY",
                                  "scope": "LINE", "target": {"document_id": "INV-2001", "line_id": "1"}}])
            out = Path(td) / "out"
            rc = main(["score", "--dataset", "dev", "--datasets-root",
                       str(support.DATASETS), "--findings", str(fp), "--out", str(out)])
            self.assertNotEqual(rc, 0)
            self.assertFalse(out.exists() and list(out.glob("*.json")))

    def test_missing_dataset_halts_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "f.json"
            _write_findings(fp, [])
            rc = main(["score", "--dataset", "nope", "--datasets-root",
                       str(support.DATASETS), "--findings", str(fp), "--out", str(Path(td) / "o")])
            self.assertNotEqual(rc, 0)

    def test_run_does_not_modify_any_input_file(self) -> None:
        m = resolve_manifest("dev", support.DATASETS)
        before = dict(per_file_digests(m.inputs_dir))
        key_before = support.key_path("dev").read_bytes()
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "f.json"
            _write_findings(fp, self._perfect_findings())
            main(["score", "--dataset", "dev", "--datasets-root", str(support.DATASETS),
                  "--findings", str(fp), "--out", str(Path(td) / "o")])
        after = dict(per_file_digests(m.inputs_dir))
        self.assertEqual(before, after)
        self.assertEqual(key_before, support.key_path("dev").read_bytes())

    def test_two_runs_byte_identical_apart_from_run_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "f.json"
            _write_findings(fp, self._perfect_findings())
            out = Path(td) / "o"
            main(["score", "--dataset", "dev", "--datasets-root", str(support.DATASETS),
                  "--findings", str(fp), "--out", str(out)])
            import time
            time.sleep(1.05)  # ensure a distinct run stamp
            main(["score", "--dataset", "dev", "--datasets-root", str(support.DATASETS),
                  "--findings", str(fp), "--out", str(out)])
            cards = sorted(out.glob("*.json"))
            self.assertEqual(len(cards), 2)
            a = json.loads(cards[0].read_text())
            b = json.loads(cards[1].read_text())
            a.pop("run_metadata")
            b.pop("run_metadata")
            self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
