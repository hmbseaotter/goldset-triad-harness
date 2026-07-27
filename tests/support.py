"""Shared test support: paths, dataset helpers, and Finding builders.

Everything here works against the in-repo dev splits only, so the whole suite
passes with no out-of-tree path configured (the CI constraint, D14).
"""

from __future__ import annotations

import json
import os
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


def _discover_dev_datasets() -> tuple[str, ...]:
    """The in-repo splits, read off disk rather than hand-listed.

    Several suites iterate "every shipped dataset". A hand-kept literal makes adding a
    split silently narrow every one of those loops — the same positional/index drift that
    has bitten this project before. Derived from the filesystem, a new split is covered
    the moment it exists.

    The floor below is what keeps the derivation honest: an empty or shrunken directory
    would otherwise turn every such loop into a vacuous pass, green because it checked
    nothing."""
    found = tuple(sorted(
        p.name for p in DATASETS.iterdir() if (p / "manifest.json").is_file()
    ))
    missing = {"dev", "dev-synthetic", "dev-zero-defect"} - set(found)
    if missing:
        raise AssertionError(
            f"expected dev splits are missing from {DATASETS}: {sorted(missing)}; "
            f"loops over 'every shipped dataset' would silently check less"
        )
    return found


#: Every in-repo dataset. Never includes the held-out split, which lives out of tree.
DEV_DATASETS: tuple[str, ...] = _discover_dev_datasets()


#: The secret tier, when this machine has it. Absence is a skip, never a failure: D14
#: requires the whole suite to pass from a clone, which by construction has no secret
#: tier. An explicit override that does not resolve IS a failure, because reporting
#: "skipped" to someone who believes the check ran is the misdiagnosis D50 warns about.
SECRET_ENV_VAR = "GOLDSET_TRIAD_SECRET_DIR"
CONVENTIONAL_SECRET_DIR = REPO_ROOT.parents[1] / "goldset-triad-secret"


def find_secret_dir() -> Path | None:
    """The secret tier's root, or None when unavailable on this machine.

    Reading from it here is consistent with the generator-staleness check and leaks
    nothing: the artifacts these checks read are a digest and a set of deny rules, never
    answer-key content."""
    override = os.environ.get(SECRET_ENV_VAR)
    if override:
        candidate = Path(override)
        if not candidate.is_dir():
            raise AssertionError(
                f"{SECRET_ENV_VAR}={override!r} is not a directory; unset it to skip the "
                f"secret-tier checks, or point it at the secret tier"
            )
        return candidate
    if CONVENTIONAL_SECRET_DIR.is_dir():
        return CONVENTIONAL_SECRET_DIR
    return None


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


def key_path(dataset: str) -> Path:
    return DATASETS / dataset / "dev_answer_key.json"


def index_path(dataset: str) -> Path:
    """The dev-side invoice index. Prefixed `dev_` so the public name is not a
    substring of `holdout_invoice_index.json` (D51)."""
    return DATASETS / dataset / "dev_invoice_index.json"


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
