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
    path.write_text(json.dumps({"schema_version": "1", "findings": findings}), encoding="utf-8", newline="\n")


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
            card = json.loads(cards[0].read_text(encoding="utf-8"))
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

    def test_same_second_runs_do_not_overwrite_each_other(self) -> None:
        """D49 — scorecards are the durable record; none may be destroyed.

        The run stamp is second-precision because every timestamp this harness writes is
        (D6), so three runs inside one second used to derive one filename and leave one
        file. Note this test has NO sleep: an earlier reproducibility test slept 1.05s to
        get distinct stamps, which worked around the defect instead of exposing it."""
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "f.json"
            _write_findings(fp, self._perfect_findings())
            out = Path(td) / "o"
            for _ in range(3):
                rc = main(["score", "--dataset", "dev", "--datasets-root",
                           str(support.DATASETS), "--findings", str(fp), "--out", str(out)])
                self.assertEqual(rc, 0)
            self.assertEqual(len(list(out.glob("*.json"))), 3)
            self.assertEqual(len(list(out.glob("*.txt"))), 3)

    def test_writing_over_an_existing_scorecard_is_refused_by_the_os(self) -> None:
        """Exclusive creation, so overwriting is impossible rather than merely avoided."""
        from goldset_triad.cli import _write_new_file
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "card.json"
            _write_new_file(target, "first")
            with self.assertRaises(FileExistsError):
                _write_new_file(target, "second")
            self.assertEqual(target.read_text(encoding="utf-8"), "first")

    def test_scorecard_files_are_written_with_lf_endings(self) -> None:
        """D49 — the scorecard writer pins LF for the reason the generator does (D43).

        Unpinned, the same run emits CRLF on Windows and LF on Linux, so the scorecard
        bytes differ by platform and 'identical content on Windows and on Linux' is
        false for the artifact that is the durable record."""
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "f.json"
            _write_findings(fp, self._perfect_findings())
            out = Path(td) / "o"
            main(["score", "--dataset", "dev", "--datasets-root",
                  str(support.DATASETS), "--findings", str(fp), "--out", str(out)])
            for path in sorted(out.iterdir()):
                self.assertNotIn(b"\r\n", path.read_bytes(), f"{path.name} carries CRLF")

    def test_two_runs_byte_identical_apart_from_run_metadata(self) -> None:
        """No sleep: D49 made distinct run stamps unnecessary for distinct files.

        This test used to sleep 1.05s to force a distinct second, which is what let the
        same-second overwrite defect hide — the sibling test above says so. Once
        scorecards were given collision-free names the sleep became vestigial, and
        leaving it would keep a second of wall-clock and a false suggestion that
        distinct stamps are required for two runs to coexist."""
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "f.json"
            _write_findings(fp, self._perfect_findings())
            out = Path(td) / "o"
            main(["score", "--dataset", "dev", "--datasets-root", str(support.DATASETS),
                  "--findings", str(fp), "--out", str(out)])
            main(["score", "--dataset", "dev", "--datasets-root", str(support.DATASETS),
                  "--findings", str(fp), "--out", str(out)])
            cards = sorted(out.glob("*.json"))
            self.assertEqual(len(cards), 2)
            a = json.loads(cards[0].read_text(encoding="utf-8"))
            b = json.loads(cards[1].read_text(encoding="utf-8"))
            a.pop("run_metadata")
            b.pop("run_metadata")
            self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
