"""Dataset loading and validation — resolution, timestamps, D29, digests, halts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests import support
from goldset_triad.dataset import (
    DatasetError,
    aggregate_inputs_digest,
    load_dataset,
    load_invoice_index,
    per_file_digests,
    resolve_manifest,
)


class DatasetLoadingTests(unittest.TestCase):
    def test_resolves_by_identifier_and_by_path(self) -> None:
        by_id = load_dataset("dev", support.DATASETS)
        by_path = load_dataset(str(support.DATASETS / "dev" / "manifest.json"), support.DATASETS)
        self.assertEqual(by_id.manifest.identifier, "dev")
        self.assertEqual(by_path.manifest.identifier, "dev")
        self.assertEqual(by_id.inputs_aggregate_sha256, by_path.inputs_aggregate_sha256)

    def test_manifest_names_three_artifacts_separately(self) -> None:
        m = resolve_manifest("dev", support.DATASETS)
        self.assertTrue(m.inputs_dir.is_dir())
        self.assertTrue(m.key_path.is_file())
        self.assertTrue(m.invoice_index_path.is_file())
        self.assertNotEqual(m.key_path, m.invoice_index_path)

    def test_missing_dataset_halts_naming_it(self) -> None:
        with self.assertRaises(DatasetError) as ctx:
            load_dataset("no-such-dataset", support.DATASETS)
        self.assertIn("no-such-dataset", str(ctx.exception))

    def test_unreadable_answer_key_halts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "d")
            (manifest.parent / "dev_answer_key.json").unlink()
            with self.assertRaises(DatasetError):
                load_dataset(str(manifest), support.DATASETS)

    def test_timestamp_without_z_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "d")
            po = manifest.parent / "inputs" / "purchase_orders" / "PO-3001.json"
            data = json.loads(po.read_text())
            data["timestamp"] = "2026-06-01"  # bare date, no Z
            po.write_text(json.dumps(data))
            with self.assertRaises(DatasetError) as ctx:
                load_dataset(str(manifest), support.DATASETS)
            self.assertIn("Z-suffixed", str(ctx.exception))

    def test_zero_taxable_subtotal_with_nonzero_tax_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "d")
            po = manifest.parent / "inputs" / "purchase_orders" / "PO-3001.json"
            data = json.loads(po.read_text())
            for ln in data["lines"]:
                ln["taxable"] = False  # now taxable subtotal is 0 but tax > 0
            po.write_text(json.dumps(data))
            with self.assertRaises(DatasetError) as ctx:
                load_dataset(str(manifest), support.DATASETS)
            self.assertIn("PO-3001", str(ctx.exception))

    def test_absent_tax_field_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "d")
            po = manifest.parent / "inputs" / "purchase_orders" / "PO-3001.json"
            data = json.loads(po.read_text())
            del data["tax"]
            po.write_text(json.dumps(data))
            with self.assertRaises(DatasetError):
                load_dataset(str(manifest), support.DATASETS)

    def test_inputs_digest_changes_when_one_byte_edited(self) -> None:
        before = load_dataset("dev", support.DATASETS).inputs_aggregate_sha256
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "d")
            po = manifest.parent / "inputs" / "purchase_orders" / "PO-3001.json"
            po.write_bytes(po.read_bytes() + b" ")  # one-byte change
            after = load_dataset(str(manifest), support.DATASETS).inputs_aggregate_sha256
        self.assertNotEqual(before, after)

    def test_inputs_digest_stable_on_recompute(self) -> None:
        m = resolve_manifest("dev", support.DATASETS)
        self.assertEqual(aggregate_inputs_digest(m.inputs_dir),
                         aggregate_inputs_digest(m.inputs_dir))

    def test_per_file_digest_locates_the_changed_file(self) -> None:
        m = resolve_manifest("dev", support.DATASETS)
        base = dict(per_file_digests(m.inputs_dir))
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "d")
            po = manifest.parent / "inputs" / "purchase_orders" / "PO-3001.json"
            po.write_bytes(po.read_bytes() + b" ")
            m2 = resolve_manifest(str(manifest), support.DATASETS)
            changed = dict(per_file_digests(m2.inputs_dir))
        diffs = [p for p in base if base[p] != changed.get(p)]
        self.assertTrue(any("PO-3001.json" in d for d in diffs))

    def test_reordering_invoice_index_lines_changes_no_target(self) -> None:
        m = resolve_manifest("dev", support.DATASETS)
        idx = load_invoice_index(m.invoice_index_path)
        with tempfile.TemporaryDirectory() as td:
            manifest = support.copy_dataset("dev", Path(td) / "d")
            ipath = manifest.parent / "dev_invoice_index.json"
            data = json.loads(ipath.read_text())
            for inv in data["invoices"]:
                inv["lines"].reverse()  # reorder lines
            ipath.write_text(json.dumps(data))
            idx2 = load_invoice_index(ipath)
        self.assertEqual(idx.inventory.line_targets, idx2.inventory.line_targets)

    def test_no_input_file_modified_by_a_load(self) -> None:
        m = resolve_manifest("dev", support.DATASETS)
        before = dict(per_file_digests(m.inputs_dir))
        load_dataset("dev", support.DATASETS)
        after = dict(per_file_digests(m.inputs_dir))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
