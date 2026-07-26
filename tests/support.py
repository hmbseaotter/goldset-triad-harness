"""Shared test support: paths, dataset helpers, and Finding builders.

Everything here works against the in-repo dev splits only, so the whole suite
passes with no out-of-tree path configured (the CI constraint, D14).
"""

from __future__ import annotations

import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
DATASETS = REPO_ROOT / "datasets"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from goldset_triad.schema import (  # noqa: E402
    Category,
    Finding,
    Scope,
    Status,
    Target,
    parse_finding,
    parse_findings_artifact,
)
from goldset_triad.scoring import LineInventory  # noqa: E402


def line(category: Category, document_id: str, line_id: str,
         status: Status = Status.DISCREPANCY,
         confidence: Decimal | None = None) -> Finding:
    return Finding(status, category, Scope.LINE, Target(document_id, line_id), confidence)


def document(category: Category, document_id: str,
             status: Status = Status.DISCREPANCY,
             confidence: Decimal | None = None) -> Finding:
    return Finding(status, category, Scope.DOCUMENT, Target(document_id, "__DOCUMENT__"), confidence)


def inventory(line_targets: set[tuple[str, str]], documents: set[str],
              invoice_count: int) -> LineInventory:
    return LineInventory(frozenset(line_targets), frozenset(documents), invoice_count)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


def key_path(dataset: str) -> Path:
    return DATASETS / dataset / "dev_answer_key.json"


def expected_findings(dataset: str) -> tuple[Finding, ...]:
    key = read_json(key_path(dataset))
    return tuple(parse_finding(e, i) for i, e in enumerate(key["expected_findings"]))


def perfect_artifact(dataset: str) -> tuple[Finding, ...]:
    """A findings artifact that reproduces exactly the dataset's expected findings."""
    key = read_json(key_path(dataset))
    findings = [
        {k: e[k] for k in ("status", "category", "scope", "target")}
        for e in key["expected_findings"]
    ]
    return parse_findings_artifact({"schema_version": "1", "findings": findings})


def has_finding(dataset: str, category: str, scope: str, document_id: str,
                line_id: str) -> bool:
    """Whether the dataset's key declares a given expected finding — the way the
    boundary/arithmetic criteria are checked, since the key encodes each decision."""
    key = read_json(key_path(dataset))
    for e in key["expected_findings"]:
        if (e["category"] == category and e["scope"] == scope
                and e["target"]["document_id"] == document_id
                and e["target"]["line_id"] == line_id):
            return True
    return False


def copy_dataset(dataset: str, dest: Path) -> Path:
    """Copy an in-repo dataset to a temp location so a test can mutate it. Returns
    the copied manifest path."""
    src = DATASETS / dataset
    shutil.copytree(src, dest)
    return dest / "manifest.json"
