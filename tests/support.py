"""Shared test support: paths, dataset helpers, and Finding builders.

Everything here works against the in-repo dev splits only, so the whole suite
passes with no out-of-tree path configured (the CI constraint, D14).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final

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


#: The held-out INPUTS tier, resolved the same way as the secret tier above. This is the
#: third root, and it had no guard until D123 because D120 enumerated two and stopped.
HOLDOUT_ENV_VAR = "GOLDSET_TRIAD_HOLDOUT_DIR"
CONVENTIONAL_HOLDOUT_DIR = REPO_ROOT.parents[1] / "goldset-triad-holdout"


def find_holdout_dir() -> Path | None:
    """The held-out inputs tier's root, or None when this machine has none."""
    override = os.environ.get(HOLDOUT_ENV_VAR)
    if override:
        candidate = Path(override)
        if not candidate.is_dir():
            raise AssertionError(
                f"{HOLDOUT_ENV_VAR}={override!r} is not a directory; unset it to skip the "
                f"held-out-tier checks, or point it at the held-out inputs tier"
            )
        return candidate
    if CONVENTIONAL_HOLDOUT_DIR.is_dir():
        return CONVENTIONAL_HOLDOUT_DIR
    return None


@dataclass(frozen=True)
class TierRoot:
    """One directory a Claude Code session can be rooted at, and its guard file.

    **Every root, not the roots someone remembered (D123).** Claude Code loads permission
    settings from the session's own root (D91), so a guard binds exactly one root and the
    set of roots IS the universe every guard check must cover. D120 built the secret
    tier's guard after finding the harness's own guards bound nothing there — and
    enumerated two roots, leaving the held-out inputs tier unguarded on the reasoning that
    *its* contents are readable by design. That reasoning is about reads: a session there
    loaded no rules at all, so the answer key next door was reachable, and these inputs are
    private precisely because publishing them burns the split. D82's rule, applied to the
    thing D82's rule is about."""

    name: str
    path: Path
    #: False for the harness itself, which is the published repository — denying writes
    #: into it from a session rooted *at* it would deny all ordinary work.
    is_private: bool

    @property
    def settings(self) -> Path:
        return self.path / ".claude" / "settings.json"


def known_tier_roots() -> tuple[TierRoot, ...]:
    """Every tier root present on this machine. Absence is a skip, never a failure (D14).

    Discovered rather than typed, for D115's reason: a literal list is a second place to
    remember, and the one that gets forgotten. The harness is always present — it is the
    directory this file lives in."""
    roots = [TierRoot("harness", REPO_ROOT, is_private=False)]
    secret = find_secret_dir()
    if secret is not None:
        roots.append(TierRoot("secret", secret, is_private=True))
    holdout = find_holdout_dir()
    if holdout is not None:
        roots.append(TierRoot("held-out inputs", holdout, is_private=True))
    return tuple(roots)


@dataclass(frozen=True)
class Split:
    """One dataset split and where each of its artifacts lives.

    Artifact filenames differ between the public and held-out tiers (D42, D51), so they
    are resolved from the manifest's own `key_path` / `invoice_index_path` rather than
    guessed from the split's name. The manifest describes itself; nothing here restates
    it."""

    name: str
    root: Path
    manifest: Path
    key: Path
    index: Path
    policy: Path
    in_repo: bool
    #: Resolved from the manifest, like `key` and `index` — never assumed to be
    #: `<root>/inputs`. It is not: the held-out split's inputs live in a third tier
    #: entirely. Omitting this field once produced a probe that reported held-out as
    #: having "0 purchase-order lines, 0 without receipts" — which reads as a clean
    #: result and actually meant it had globbed a directory that does not exist. A
    #: helper that resolves three of four artifacts invites exactly that vacuous pass.
    inputs: Path = Path()


def known_splits() -> tuple[Split, ...]:
    """EVERY split this machine can see — in-repo and held-out alike (D67).

    Use this, not ``DEV_DATASETS``, for any check of a *split-level property*. The
    distinction is what D64 was about: every staleness check iterated the dev splits, so
    the held-out manifest carried a stamp nothing compared — not through oversight but
    structurally, because the loop's universe excluded it. The same asymmetry had left the
    published matching policy checked on `dev` alone.

    ``DEV_DATASETS`` remains correct for tests that mutate a copied dataset or assert
    dev-specific content. The rule is: iterate DEV_DATASETS to exercise behaviour,
    iterate known_splits() to assert a property every split must have."""
    splits: list[Split] = []
    roots: list[tuple[str, Path, bool]] = [(n, DATASETS / n, True) for n in DEV_DATASETS]
    secret = find_secret_dir()
    if secret is not None and (secret / "held-out" / "manifest.json").is_file():
        roots.append(("held-out", secret / "held-out", False))
    for name, root, in_repo in roots:
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        splits.append(Split(
            name=name,
            root=root,
            manifest=manifest_path,
            key=(root / str(manifest["key_path"])).resolve(),
            index=(root / str(manifest["invoice_index_path"])).resolve(),
            policy=root / "matching_policy.json",
            in_repo=in_repo,
            inputs=(root / str(manifest["inputs_dir"])).resolve(),
        ))
    return tuple(splits)


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


# ---------------------------------------------------------------------------
# The published documents (D105)
# ---------------------------------------------------------------------------
#: Every document written for a reader outside this project — someone deciding whether to
#: trust the harness, or following it to run something. D30 governs what these may claim;
#: D84, D85, D95 and D102 each bind one aspect of them to what is actually true.
#:
#: **One registry, because there were two.** `test_published_claims` carried `COMMAND_DOCS`
#: and `test_entry_points` carried `INVOCATION_DOCS`: the same three files, in different
#: orders, in different files, with nothing comparing them and nothing checking either
#: against the tree. `COMMAND_DOCS` even cited D82 for why it was named rather than globbed
#: — and then skipped D82's second half, which is that a declared universe must be
#: *asserted covered*. A fourth document could have arrived and been checked by neither.
PUBLISHED_DOCS: Final = (
    "README.md",
    "ISOLATION_ATTESTATION.md",
    "docs/RUNBOOK.md",
    "docs/SCORECARD.md",
)

#: Markdown that exists for this project's own record-keeping rather than for a reader
#: following instructions. Listed rather than pattern-matched so that adding one is a
#: deliberate act, and so `test_every_markdown_document_is_classified` can prove the two
#: lists together cover the tree.
INTERNAL_DOCS: Final = (
    "DECISIONS.md",
)

#: Where `PUBLISHED_DOCS` and `INTERNAL_DOCS` are required to be exhaustive. Specs live
#: outside it on purpose: they address a building agent, are versioned as build inputs, and
#: are bound by their own mechanisms (the criterion checksums, D87's gate count).
CLASSIFIED_DOC_DIRS: Final = (".", "docs")


def markdown_on_disk() -> set[str]:
    """Every markdown file in the directories the classification claims to cover."""
    found: set[str] = set()
    for directory in CLASSIFIED_DOC_DIRS:
        for path in sorted((REPO_ROOT / directory).glob("*.md")):
            found.add(path.relative_to(REPO_ROOT).as_posix())
    return found
