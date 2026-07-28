"""End-to-end CLI: a full scoring run, and the halts that write no scorecard."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import support
from goldset_triad import cli
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
        """E7 in full: halts, exits non-zero, **names the offending finding and field**,
        and writes no scorecard.

        The naming clause went unasserted for two phases (D86). This test checked the exit
        code and the absent scorecard — both of which a halt with a generic message also
        satisfies — while the criterion, and the observability requirement behind it, are
        about what the reader is told. The harness did name them correctly the whole time;
        nothing compared that to the promise. D81's rule, one criterion further on."""
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "bad.json"
            _write_findings(fp, [{"status": "DISCREPANCY", "category": "NOT_A_CATEGORY",
                                  "scope": "LINE", "target": {"document_id": "INV-2001", "line_id": "1"}}])
            out = Path(td) / "out"
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = main(["score", "--dataset", "dev", "--datasets-root",
                           str(support.DATASETS), "--findings", str(fp), "--out", str(out)])
            self.assertNotEqual(rc, 0)
            self.assertFalse(out.exists() and list(out.glob("*.json")))

            message = err.getvalue()
            self.assertIn("NOT_A_CATEGORY", message, "the halt must name the offending value")
            self.assertIn("finding #0", message, "the halt must name WHICH finding")
            self.assertIn("'category'", message, "the halt must name WHICH field")

    def test_missing_dataset_halts_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "f.json"
            _write_findings(fp, [])
            rc = main(["score", "--dataset", "nope", "--datasets-root",
                       str(support.DATASETS), "--findings", str(fp), "--out", str(Path(td) / "o")])
            self.assertNotEqual(rc, 0)

    def test_losing_the_filename_race_retries_instead_of_tracebacking(self) -> None:
        """The gap three sweeps recorded and none closed (D114).

        `_reserve_scorecard_paths` checks `.exists()`; `_write_new_file` then creates with
        mode `"x"`. Between those steps another process can take the name, and `"x"` raises
        `FileExistsError` — neither `DatasetError` nor `SchemaError`, so it escaped `main()`
        and surfaced as a traceback rather than a halt naming its cause.

        Simulated by taking the name at exactly that moment: the reservation is wrapped so
        that the first stem it hands back is occupied before the write reaches it."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            out.mkdir()
            findings = Path(td) / "f.json"
            _write_findings(findings, self._perfect_findings())

            real_reserve = cli._reserve_scorecard_paths
            stolen: list[Path] = []

            def steal_once(out_dir: Path, identifier: str, stamp: str):
                json_path, txt_path = real_reserve(out_dir, identifier, stamp)
                if not stolen:  # only the first reservation loses the race
                    stolen.append(json_path)
                    json_path.write_text("{}", encoding="utf-8", newline="\n")
                return json_path, txt_path

            with mock.patch.object(cli, "_reserve_scorecard_paths", steal_once):
                code = main(["score", "--dataset", "dev", "--datasets-root",
                             str(support.DATASETS), "--findings", str(findings),
                             "--out", str(out)])

            self.assertEqual(code, 0, "losing one race must not fail a correct run")
            self.assertTrue(stolen, "the fixture did not actually steal a name")
            cards = sorted(p for p in out.glob("scorecard-*.json") if p != stolen[0])
            self.assertEqual(
                len(cards), 1,
                f"the run must land on a different stem; found {[p.name for p in cards]}",
            )
            self.assertEqual(
                stolen[0].read_text(encoding="utf-8"), "{}",
                "the file that won the race must be untouched — D49's exclusive create is "
                "what makes the retry safe",
            )
            self.assertTrue(
                cards[0].with_suffix(".txt").is_file(),
                "both halves of the pair must land together",
            )

    def test_exhausting_the_retries_is_a_named_halt(self) -> None:
        """When every reservation is taken, it halts naming the cause rather than
        spinning. A bounded retry that never gives up is a hang wearing a fix's clothes."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            out.mkdir()
            findings = Path(td) / "f.json"
            _write_findings(findings, self._perfect_findings())

            real_reserve = cli._reserve_scorecard_paths

            def always_steal(out_dir: Path, identifier: str, stamp: str):
                json_path, txt_path = real_reserve(out_dir, identifier, stamp)
                json_path.write_text("{}", encoding="utf-8", newline="\n")
                return json_path, txt_path

            err = io.StringIO()
            with mock.patch.object(cli, "_reserve_scorecard_paths", always_steal), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(err):
                code = main(["score", "--dataset", "dev", "--datasets-root",
                             str(support.DATASETS), "--findings", str(findings),
                             "--out", str(out)])
            self.assertEqual(code, 2, "an unresolvable collision is a named halt, exit 2")
            self.assertIn("could not claim a scorecard filename", err.getvalue())
            self.assertIn("no existing scorecard was touched", err.getvalue())

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
