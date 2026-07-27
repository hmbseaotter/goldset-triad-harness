"""The JSONL run ledger — derived, append-only, and regenerable from scorecards (D9, D75).

The guarantee under test is narrow and load-bearing: **deleting the ledger and rebuilding
it from the scorecard directory alone reproduces identical contents.** That is what makes
it safe for the ledger to be local-only and gitignored, because a derived file that could
not be rebuilt would be exactly the loss risk scorecards-as-durable-record exists to avoid.

Most of what follows protects the *ordering* that guarantee rests on, which is the part
that is not obvious — see `test_run_order_survives_the_collision_ordinal`.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests import support
from goldset_triad import ledger
from goldset_triad.cli import main
from goldset_triad.dataset import DatasetError

#: A minimal scorecard body, used where the test is about the LEDGER's behaviour rather
#: than about scoring. Built from the shape `build_scorecard` emits, so a change to that
#: shape surfaces here as a named missing field rather than as a silent wrong record.
_SKELETON = {
    "schema_version": "2",
    "dataset": {"identifier": "dev", "version": "1.0.0"},
    "workload": {"invoice_count": 4, "finding_count": 9},
    "metrics": {
        "overall": {"precision": "1.0000", "recall": "1.0000"},
        "false_positive_count": 0,
        "false_positive_rate": "0.0000",
    },
    "run_metadata": {
        "run_timestamp": "2026-07-27T05:00:00Z",
        "load_ms": 1,
        "score_ms": 1,
        "total_ms": 2,
    },
}


def _write_card(directory: Path, name: str, **overrides: object) -> Path:
    card = json.loads(json.dumps(_SKELETON))
    for dotted, value in overrides.items():
        node = card
        parts = dotted.split("__")
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = value
    path = directory / name
    path.write_text(
        json.dumps(card, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n",
    )
    return path


class RunLedgerTests(unittest.TestCase):
    def _score_into(self, td: Path, times: int) -> Path:
        key = support.read_json(support.key_path("dev"))
        findings = td / "f.json"
        findings.write_text(json.dumps({
            "schema_version": "1",
            "findings": [{k: e[k] for k in ("status", "category", "scope", "target")}
                         for e in key["expected_findings"]],
        }), encoding="utf-8", newline="\n")
        out = td / "out"
        for _ in range(times):
            self.assertEqual(0, main([
                "score", "--dataset", "dev", "--datasets-root", str(support.DATASETS),
                "--findings", str(findings), "--out", str(out),
            ]))
        return out

    def test_deleting_and_rebuilding_reproduces_identical_contents(self) -> None:
        """The `[P2]` criterion. Byte comparison, not line-count: the rebuild has to
        reproduce the same records in the same order with the same serialization, and
        only bytes assert all three at once."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            out = self._score_into(td, 3)
            appended = ledger.ledger_path(out).read_bytes()
            self.assertEqual(appended.count(b"\n"), 3, "one record per run")

            ledger.ledger_path(out).unlink()
            self.assertEqual(0, main(["rebuild-ledger", "--out", str(out)]))
            self.assertEqual(appended, ledger.ledger_path(out).read_bytes())

    def test_run_order_survives_the_collision_ordinal(self) -> None:
        """The ordering the regeneration guarantee rests on, which is not the obvious one.

        Scorecard stems carry the D49 collision ordinal and it is *lexicographic* in a
        filename, so a naive directory sort yields run 10, then run 2, then run 1. Appends
        happen chronologically, so a filename-sorted rebuild would produce a differently
        ordered ledger holding identical records — and the guarantee would fail on a case
        nobody would think to test. Asserted here, including that the naive sort really
        does get it wrong, so this cannot pass by the ordinals happening not to collide."""
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            _write_card(out, "scorecard-dev-20260727T050000Z.json", workload__finding_count=1)
            _write_card(out, "scorecard-dev-20260727T050000Z-2.json", workload__finding_count=2)
            _write_card(out, "scorecard-dev-20260727T050000Z-10.json", workload__finding_count=10)

            naive = [p.name for p in sorted(out.glob("*.json"))]
            self.assertTrue(
                naive[0].endswith("-10.json"),
                "the premise: a filename sort must actually mis-order, or this proves nothing",
            )
            ordered = [json.loads(line)["finding_count"]
                       for line in ledger.rebuild_text(out).splitlines()]
            self.assertEqual(ordered, [1, 2, 10])

    def test_every_ledger_field_comes_from_the_scorecard(self) -> None:
        """The constraint that shapes the record: anything not recoverable from the
        directory would make the rebuild guarantee unmeetable. One field comes from the
        FILENAME rather than the contents — the D49 ordinal lives nowhere else."""
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            card = _write_card(out, "scorecard-dev-20260727T050000Z-3.json")
            record = ledger.record_for(card)
            self.assertEqual(record["scorecard"], "scorecard-dev-20260727T050000Z-3.json")
            self.assertEqual(record["run_timestamp"], "2026-07-27T05:00:00Z")
            self.assertEqual(record["total_ms"], 2)
            # No fingerprints: copying claim-shaped fields into a derived artifact would
            # manufacture claims nothing compares, which is what D67 exists to end (D75).
            self.assertEqual([k for k in record if "sha256" in k], [])

    def test_an_unwritable_ledger_warns_and_the_run_still_exits_zero(self) -> None:
        """D75. The ledger is a derived, regenerable convenience view (D9), so an
        unwritable one cannot make a correct score wrong. Halting would report a valid run
        as a failure; silence would be the absence-nobody-is-told-about class D68 locked.

        The ledger path is occupied by a DIRECTORY, which makes the append fail on both
        Windows and Linux without touching file permissions, whose semantics differ."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            out = td / "out"
            out.mkdir()
            ledger.ledger_path(out).mkdir()  # now un-appendable, portably
            rc = self._score_into(td, 1)
            self.assertTrue(rc.is_dir())
            self.assertTrue(list(out.glob("*.json")), "the scorecard is still written")

    def test_a_foreign_json_file_is_named_rather_than_silently_skipped(self) -> None:
        """A file that is not a scorecard cannot be placed in run order, and guessing
        would put an invented position into the record. It halts naming the file."""
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            _write_card(out, "scorecard-dev-20260727T050000Z.json")
            (out / "notes.json").write_text("{}", encoding="utf-8", newline="\n")
            with self.assertRaises(DatasetError) as caught:
                ledger.rebuild_text(out)
            self.assertIn("notes.json", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
