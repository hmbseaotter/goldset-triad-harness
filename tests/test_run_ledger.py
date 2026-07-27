"""The JSONL run ledger — derived, append-only, and regenerable from scorecards (D9, D75).

The guarantee under test is narrow and load-bearing: **deleting the ledger and rebuilding
it from the scorecard directory alone reproduces identical contents.** That is what makes
it safe for the ledger to be local-only and gitignored, because a derived file that could
not be rebuilt would be exactly the loss risk scorecards-as-durable-record exists to avoid.

Most of what follows protects the *ordering* that guarantee rests on, which is the part
that is not obvious — see `test_run_order_survives_the_collision_ordinal`.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tests import support
from goldset_triad import ledger
from goldset_triad.cli import _reserve_scorecard_paths, main
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

        **The warning is asserted, not assumed (D81).** This test checked only that the
        run exited zero and left a scorecard — both of which a *silent* append failure
        also satisfies. D75 chose "warn and continue" over "fail silently" on the grounds
        that an absence nobody is told about is a locked defect class, and then nothing
        checked that anybody was told. A decision whose whole substance is a message is
        not tested until the message is.

        The ledger path is occupied by a DIRECTORY, which makes the append fail on both
        Windows and Linux without touching file permissions, whose semantics differ."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            out = td / "out"
            out.mkdir()
            ledger.ledger_path(out).mkdir()  # now un-appendable, portably
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                scorecard_dir = self._score_into(td, 1)
            self.assertTrue(scorecard_dir.is_dir())
            self.assertTrue(list(out.glob("*.json")), "the scorecard is still written")

            warning = err.getvalue()
            self.assertIn("warning:", warning, "the failure must be reported, not swallowed")
            self.assertIn("run ledger could not be appended to", warning)
            # The remedy travels with the warning. A warning that names a problem and not
            # its fix leaves the reader with a scorecard they are unsure they can trust.
            self.assertIn("rebuild-ledger", warning)
            self.assertIn("the score is unaffected", warning)

    def test_three_splits_in_one_second_keep_their_run_order(self) -> None:
        """The condition the ordering guarantee actually broke on (D80).

        `test_run_order_survives_the_collision_ordinal` uses one identifier, so its
        ordinals are 1, 2, 10 and never tie. The ordinal was reserved per *stem*, and a
        stem carries the identifier — so three splits scored inside one second all took
        ordinal 1 and produced an identical sort key. Python's sort is stable, so order
        fell through to `glob` order: name-ordered on NTFS, hash-ordered on ext4. The
        rebuild would have reordered on Linux and held on the machine this was written
        on, which is the worst shape a portability defect can take.

        **The reservation is driven directly, with one fixed stamp.** Scoring three
        splits and hoping they land inside the same second is a timing dependency wearing
        a different hat — the class C62 locked — and it would skip on a slow machine,
        which is the condition under which it most needs to run."""
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            stamp = "20260727T050000Z"
            names: list[str] = []
            for identifier in ("dev", "dev-synthetic", "dev-zero-defect"):
                json_path, txt_path = _reserve_scorecard_paths(out, identifier, stamp)
                _write_card(out, json_path.name, dataset__identifier=identifier)
                txt_path.write_text("", encoding="utf-8", newline="\n")
                names.append(json_path.name)

            keys = [ledger.parse_scorecard_name(n).order_key for n in names]
            self.assertEqual(
                len(set(keys)), len(keys),
                f"the sort key must be TOTAL within one second: {list(zip(names, keys))}",
            )
            self.assertEqual(
                [k[1] for k in keys], [1, 2, 3],
                "and CHRONOLOGICAL, not merely distinct: the nth run in this second "
                "takes the nth ordinal, whatever split it scored",
            )

            # Appended in the order they were written, then rebuilt from the directory.
            for name in names:
                ledger.append_record(out, out / name)
            appended = ledger.ledger_path(out).read_bytes()
            ledger.ledger_path(out).unlink()
            ledger.write_ledger(ledger.ledger_path(out), ledger.rebuild_text(out))
            self.assertEqual(
                appended, ledger.ledger_path(out).read_bytes(),
                "appended chronologically and rebuilt from the directory must agree",
            )

    def test_a_neighbour_this_harness_did_not_emit_does_not_block_scoring(self) -> None:
        """Reservation skips what it cannot parse; the ledger still refuses it (D83).

        D80 widened the ordinal scan from one stem to the whole directory-second, and with
        it the blast radius: `_reserve_scorecard_paths` parsed every `scorecard-*.json`
        neighbour and propagated the failure, so a file the harness did not emit made
        `score` exit 2 — refusing to write the durable record — with a message blaming
        *the ledger*, a derived view the caller never invoked.

        D75 had already settled that direction: an unwritable ledger warns and the run
        exits zero, because a derived, regenerable view must not make a correct score fail.
        D80 crossed the same line through a different door.

        Both halves are asserted, because skipping everywhere would be the opposite
        defect: the ledger's own guarantee is that a rebuild reproduces the append order,
        and an order it cannot justify is not an order."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            out = td / "out"
            out.mkdir()
            # Matches the glob the reservation scans, not the name grammar it parses.
            (out / "scorecard-backup-copy.json").write_text(
                "{}", encoding="utf-8", newline="\n"
            )

            self._score_into(td, 1)
            emitted = [p.name for p in out.glob("scorecard-*.json")
                       if p.name != "scorecard-backup-copy.json"]
            self.assertEqual(len(emitted), 1, "the score is written beside the neighbour")

            # ...and the ledger still refuses to invent a run position for it.
            with self.assertRaises(DatasetError) as caught:
                ledger.rebuild_text(out)
            self.assertIn("scorecard-backup-copy.json", str(caught.exception))

    def test_a_hand_placed_duplicate_run_position_halts(self) -> None:
        """A residual tie is refused rather than resolved. The harness cannot produce
        one, so a tie means something else placed the file — and an order the ledger
        cannot justify is not an order."""
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            _write_card(out, "scorecard-alpha-20260727T050000Z.json")
            _write_card(out, "scorecard-beta-20260727T050000Z.json")
            with self.assertRaises(DatasetError) as caught:
                ledger.rebuild_text(out)
            message = str(caught.exception)
            self.assertIn("share run stamp", message)
            self.assertIn("scorecard-alpha-20260727T050000Z.json", message)
            self.assertIn("scorecard-beta-20260727T050000Z.json", message)

    def test_a_null_run_timestamp_is_rejected_not_carried(self) -> None:
        """Presence is not validity: `null` is present (D80). `_require` checked only
        that the key existed, so a scorecard carrying `"run_timestamp": null` produced a
        record with a null run timestamp — the field the whole run order rests on."""
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            card = _write_card(out, "scorecard-dev-20260727T050000Z.json",
                               run_metadata__run_timestamp=None)
            with self.assertRaises(DatasetError) as caught:
                ledger.record_for(card)
            self.assertIn("run_metadata.run_timestamp': null", str(caught.exception))

    def test_a_null_ratio_is_carried_through(self) -> None:
        """The converse, and the reason nullability had to be declared per field rather
        than banned outright: D40 emits an UNDEFINED metric as `null` rather than as zero
        or omitted, so a null precision is a value meaning "undefined on this split"."""
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            card = _write_card(out, "scorecard-dev-20260727T050000Z.json",
                               metrics__overall__precision=None)
            self.assertIsNone(ledger.record_for(card)["overall_precision"])

    def test_a_missing_scorecard_directory_is_named_not_answered_with_nothing(self) -> None:
        """An empty ledger and a mistyped path are not the same answer."""
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(DatasetError) as caught:
                ledger.rebuild_text(Path(t) / "no_such_directory")
            self.assertIn("scorecard directory not found", str(caught.exception))

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
