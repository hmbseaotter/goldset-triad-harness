"""Every way a read can fail is named, and every read goes through one reader (D77).

D61 required each text read to state its encoding, and each one did. Nothing said what
happens when the stated encoding does not apply — and `UnicodeDecodeError` is a
`ValueError`, not an `OSError`, so `dataset`'s deliberate `except OSError`, placed
directly around a pinned-encoding read for exactly this class of problem, caught the
file being unreadable and missed the file not being text. Pointing the harness at a PDF,
a zip or a UTF-16 export produced a traceback rather than the named halt the failure
policy requires, on five separate read paths.

**The lock is the second test, not the first.** Asserting that today's five call sites
behave is a snapshot; asserting that only one function in the package reads text is what
stops a sixth arriving with its own subset of guards, which is how the five came to
disagree in the first place (D68's shape, applied to a read).
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests import support
from goldset_triad.cli import main
from goldset_triad.dataset import DatasetError, load_dataset

PACKAGE = support.SRC / "goldset_triad"

#: The one function permitted to read text, and the module it lives in. Named rather
#: than discovered, because "wherever the reads happen to be today" is not a rule.
SHARED_READER_MODULE = "jsonio.py"

#: Not text, and not decodable as UTF-8 under any interpretation: a UTF-16 BOM followed
#: by a lone high byte. Used everywhere below so each read path is tested on the same
#: input and any difference in the report is a difference in the reader, not the fixture.
NOT_UTF8 = b"\xff\xfe\x00\x01 this is not utf-8"


def _perfect_findings(target: Path, dataset: str = "dev") -> Path:
    key = support.read_json(support.key_path(dataset))
    target.write_text(
        json.dumps({
            "schema_version": "1",
            "findings": [{k: e[k] for k in ("status", "category", "scope", "target")}
                         for e in key["expected_findings"]],
        }, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n",
    )
    return target


def _run(argv: list[str]) -> tuple[int, str]:
    """Run the CLI, returning its exit code and what it wrote to stderr."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, err.getvalue()


class NonUtf8ReadTests(unittest.TestCase):
    """Every artifact the harness is pointed at, corrupted the same way.

    A traceback is not a halt: it names a byte offset inside the standard library rather
    than the artifact, exits 1 by interpreter accident rather than by the failure
    policy's 2, and reads as a defect in the harness rather than as a defect in what the
    harness was handed."""

    def test_a_non_utf8_findings_artifact_halts_naming_it(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            bad = td / "f.json"
            bad.write_bytes(NOT_UTF8)
            code, err = _run([
                "score", "--dataset", "dev", "--datasets-root", str(support.DATASETS),
                "--findings", str(bad), "--out", str(td / "out"),
            ])
            self.assertEqual(code, 2)
            self.assertIn("findings artifact is not UTF-8 text", err)
            self.assertIn(str(bad), err)
            self.assertFalse((td / "out").exists(), "no scorecard is written on a halt")

    def test_a_non_utf8_scorecard_halts_rather_than_failing_verification(self) -> None:
        """Exit 2, not 1. A scorecard that cannot be read is a verification that never
        happened, which is not a verification that failed (D50, D74)."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            findings = _perfect_findings(td / "findings.json")
            card = td / "card.json"
            card.write_bytes(NOT_UTF8)
            code, err = _run([
                "verify", "--scorecard", str(card), "--dataset", "dev",
                "--datasets-root", str(support.DATASETS), "--findings", str(findings),
            ])
            self.assertEqual(code, 2)
            self.assertIn("is not UTF-8 text", err)
            self.assertNotIn("VERIFY FAILED", err)

    def test_every_dataset_artifact_names_itself_by_role(self) -> None:
        """The answer key, the manifest and the invoice index each halt under their own
        name. A shared reader that reported "file is not UTF-8" for all three would send
        a reader to look at three files instead of one."""
        for artifact, role in (
            ("dev_answer_key.json", "answer key"),
            ("manifest.json", "manifest"),
            ("dev_invoice_index.json", "invoice index"),
        ):
            with self.subTest(artifact=artifact), tempfile.TemporaryDirectory() as t:
                td = Path(t)
                copied = td / "d"
                shutil.copytree(support.DATASETS / "dev", copied)
                (copied / artifact).write_bytes(NOT_UTF8)
                with self.assertRaises(DatasetError) as caught:
                    load_dataset(str(copied / "manifest.json"), support.DATASETS)
                message = str(caught.exception)
                self.assertIn(f"{role} is not UTF-8 text", message)
                self.assertIn(artifact, message)

    def test_the_three_read_failures_are_reported_apart(self) -> None:
        """Absent, unopenable and undecodable are three findings, not one.

        Collapsing them into "could not read" is the misdiagnosis D50 ruled worse than
        silence: the first is a wrong path, the second a permission or lock, the third a
        file that is not what the caller thinks it is."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            # The same artifact, absent and then undecodable, so the two messages are
            # produced by the same reader on the same role and differ only in the cause.
            absent_copy = td / "absent"
            shutil.copytree(support.DATASETS / "dev", absent_copy)
            (absent_copy / "dev_answer_key.json").unlink()
            with self.assertRaises(DatasetError) as absent:
                load_dataset(str(absent_copy / "manifest.json"), support.DATASETS)
            self.assertIn("answer key not found or unreadable", str(absent.exception))

            copied = td / "d"
            shutil.copytree(support.DATASETS / "dev", copied)
            (copied / "dev_answer_key.json").write_bytes(NOT_UTF8)
            with self.assertRaises(DatasetError) as undecodable:
                load_dataset(str(copied / "manifest.json"), support.DATASETS)
            self.assertIn("answer key is not UTF-8 text", str(undecodable.exception))
            self.assertNotIn("not found", str(undecodable.exception))


class OneReaderTests(unittest.TestCase):
    """The lock. Five call sites disagreed about which failures they guarded, and no
    caller could tell which protections applied without reading the callee."""

    def _text_read_sites(self) -> list[str]:
        """Every `.read_text(...)` call in the package, by module and line.

        `read_bytes` is deliberately not included: D27 digests inputs by raw bytes
        precisely so no decoding happens, and a digest of undecodable bytes is a correct
        digest. This lock is about reads that *interpret* a file."""
        sites: list[str] = []
        for path in sorted(PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "read_text"):
                    sites.append(f"{path.name}:{node.lineno}")
        return sites

    def test_only_the_shared_reader_reads_text(self) -> None:
        stray = [s for s in self._text_read_sites()
                 if not s.startswith(f"{SHARED_READER_MODULE}:")]
        self.assertEqual(
            stray, [],
            f"{len(stray)} text read(s) outside {SHARED_READER_MODULE}: {stray}. Each one "
            f"is free to guard its own subset of the ways a read fails, which is how five "
            f"call sites came to disagree and how the UnicodeDecodeError class survived "
            f"D61 (D77). Route it through jsonio.read_text_file / read_json_file.",
        )

    def test_the_scan_would_notice_a_stray_read(self) -> None:
        """The premise. A scan that finds nothing proves nothing until it is shown to
        find something — D73's lesson, which was a probe that could not fire."""
        tree = ast.parse("from pathlib import Path\nPath('x').read_text(encoding='utf-8')\n")
        found = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "read_text"]
        self.assertEqual(len(found), 1, "the scan's own pattern must match a real call")

    def test_the_findings_artifact_has_one_loader(self) -> None:
        """`score` and `verify` must parse an artifact through the same function.

        This is the worst place in the project for two copies: verify's entire premise
        is that it reproduces what scoring did, so a rejection added to one and not the
        other would make it compare a scorecard against a recomputation whose inputs it
        had accepted on different terms."""
        callers: list[str] = []
        for path in sorted(PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "parse_findings_artifact"):
                    callers.append(f"{path.name}:{node.lineno}")
        self.assertEqual(
            [c.split(":")[0] for c in callers], ["dataset.py"],
            f"parse_findings_artifact is called from {callers}; it must be reached only "
            f"through dataset.load_findings_artifact, so scoring and verify cannot "
            f"validate the same artifact on different terms (D77).",
        )


class WriteDestinationTests(unittest.TestCase):
    def test_a_ledger_destination_that_cannot_be_written_is_named(self) -> None:
        """`--ledger` takes a path from the caller, so it can name one that cannot be
        created. That is ordinary operator error and gets a named halt, not the bare
        `FileNotFoundError` that stood here."""
        with tempfile.TemporaryDirectory() as t:
            td = Path(t)
            findings = _perfect_findings(td / "findings.json")
            out = td / "out"
            code, _ = _run([
                "score", "--dataset", "dev", "--datasets-root", str(support.DATASETS),
                "--findings", str(findings), "--out", str(out),
            ])
            self.assertEqual(code, 0)
            code, err = _run([
                "rebuild-ledger", "--out", str(out),
                "--ledger", str(td / "no_such_directory" / "run-ledger.jsonl"),
            ])
            self.assertEqual(code, 2)
            self.assertIn("could not be written", err)
            self.assertIn("no_such_directory", err)


if __name__ == "__main__":
    unittest.main()
