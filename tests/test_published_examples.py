"""Every block a published document shows as harness output IS harness output (D102).

D100 bound the scorecard legend to the emitter — and bound **field names**. The legend's
worked example, which is the thing a reader actually holds their own scorecard against, was
bound to nothing, and had drifted three ways at once: two categories were missing from a
per-category table the renderer always prints in full; a `TAX_VARIANCE` row carried
`[not exercised by this dataset]` in the same block as `COVERAGE: … exercises all 5
categories`, a pair the renderer cannot emit; and `Missed findings (6):` was followed by one
bullet where the renderer prints six — which is criterion **H57**, *"the summary names each
miss and each false flag individually"*. The document that exists to explain the output
illustrated the harness breaking one of its own acceptance criteria.

**Why hand-checking cannot work here.** These blocks are long, and the differences that
matter are one row and one bullet. D53's answer to the same problem in `matching_policy.json`
was to derive the published text from the shipped constants; the equivalent here is to
**re-run the run** and compare. So each block is registered with the exact submission that
produces it, and the test scores that submission and diffs.

**A fragment is allowed; an edit is not.** A document may show the tail of a summary — the
runbook does, to make a point about thin coverage without reprinting the header. What it may
not do is show lines the harness did not emit, in an order it did not emit them. So a
registered fragment must appear **contiguously and verbatim** inside the real output.

**Submissions are content-addressed, never positional.** `expected[:3]` would silently mean
something different the day a key gains a record, and the example would still pass while
illustrating a different run — a positional reference breaking quietly, which is the failure
this project inherited as a pattern to reuse carefully.
"""

from __future__ import annotations

import difflib
import re
import unittest
from dataclasses import dataclass
from typing import Callable

from tests import support
from goldset_triad import scorecard as sc
from goldset_triad.dataset import load_dataset
from goldset_triad.schema import Category, Finding
from goldset_triad.scoring import score

#: Substrings that make a fenced block a claim about what the harness prints. Any block
#: containing one must be registered below — that is the completeness half, without which
#: this file would check the three examples someone remembered (D82).
OUTPUT_MARKERS = ("Scorecard - dataset", "Per-category (precision / recall):", "COVERAGE:")

#: The documents this ranges over. Held here rather than imported from the published-document
#: registry because that registry answers "which documents make claims"; this answers "which
#: documents show output", and the day those differ, conflating them would hide it.
EXAMPLE_DOCS = ("README.md", "docs/RUNBOOK.md", "docs/SCORECARD.md", "ISOLATION_ATTESTATION.md")


def _sorted_by_target(findings: tuple[Finding, ...]) -> list[Finding]:
    """Deterministic order that does not depend on the key's record order (H37)."""
    return sorted(findings, key=lambda f: (f.target.document_id, f.target.line_id))


def _all_but_tax_plus_one_false_flag(expected: tuple[Finding, ...]) -> tuple[Finding, ...]:
    """Every expectation except the tax one, plus a flag on a line that is clean.

    The README's example: an agent that is nearly right, so the summary shows one miss and
    one false flag and a reader sees both halves of the verdict."""
    kept = tuple(f for f in expected if f.category is not Category.TAX_VARIANCE)
    return kept + (support.line(Category.PRICE_VARIANCE, "INV-2002", "4"),)


def _price_variance_but_one(expected: tuple[Finding, ...]) -> tuple[Finding, ...]:
    """All but one of the price expectations, and nothing else.

    The legend's example: misses in every category and no false flags at all, which is the
    shape that shows `Missed findings (n)` in full beside `False flags: none`."""
    price = _sorted_by_target(tuple(f for f in expected if f.category is Category.PRICE_VARIANCE))
    return tuple(price[:-1])


def _nothing(_expected: tuple[Finding, ...]) -> tuple[Finding, ...]:
    """An empty findings artifact — valid, and the zero-defect control's own input."""
    return ()


@dataclass(frozen=True)
class Example:
    document: str
    #: A substring identifying which fenced block this is. Unique within its document.
    marker: str
    dataset: str
    submission: Callable[[tuple[Finding, ...]], tuple[Finding, ...]]
    #: True when the document deliberately shows part of the summary rather than all of it.
    fragment: bool = False


EXAMPLES: tuple[Example, ...] = (
    Example("README.md", "Overall precision: 0.8889", "dev", _all_but_tax_plus_one_false_flag),
    Example("docs/SCORECARD.md", "3 finding(s) submitted", "dev", _price_variance_but_one),
    # The runbook shows the tail only, to make a point about thin coverage without
    # reprinting a header the reader has already seen twice by that point.
    Example("docs/RUNBOOK.md", "exercises 1 of 5 categories", "dev-synthetic", _nothing,
            fragment=True),
)


def _blocks(document: str) -> list[str]:
    text = (support.REPO_ROOT / document).read_text(encoding="utf-8")
    return re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)


def _real_summary(example: Example) -> str:
    loaded = load_dataset(example.dataset, support.DATASETS)
    expected = loaded.answer_key.expected_findings
    result = score(expected, example.submission(expected), loaded.invoice_index.inventory)
    provenance = sc.Provenance(
        example.dataset, loaded.manifest.version, "f" * 64, loaded.answer_key.sha256,
        loaded.invoice_index.sha256, loaded.inputs_aggregate_sha256,
    )
    # A fixed run stamp: `run_metadata` never reaches the human summary (D18, H56), so this
    # value cannot appear in what is compared. Naming it explicitly beats reading the clock
    # in a test whose whole subject is reproducibility.
    card = sc.build_scorecard(result, provenance, sc.RunMetadata("2026-07-28T00:00:00Z", 1, 2, 3))
    return sc.human_summary(card, result)


class PublishedExampleTests(unittest.TestCase):
    def test_every_registered_example_is_what_the_harness_prints(self) -> None:
        for example in EXAMPLES:
            with self.subTest(document=example.document, marker=example.marker):
                matching = [b for b in _blocks(example.document) if example.marker in b]
                self.assertEqual(
                    len(matching), 1,
                    f"{example.document}: expected exactly one block containing "
                    f"{example.marker!r}, found {len(matching)}",
                )
                documented = matching[0].rstrip("\n").split("\n")
                real = _real_summary(example).rstrip("\n").split("\n")

                if example.fragment:
                    self.assertTrue(
                        _contains_run(real, documented),
                        f"{example.document}: the block containing {example.marker!r} is "
                        f"registered as a FRAGMENT, but those lines do not appear "
                        f"contiguously in what the harness prints:\n"
                        + "\n".join(difflib.unified_diff(
                            documented, real, "documented", "real", lineterm="")),
                    )
                    continue

                self.assertEqual(
                    documented, real,
                    f"{example.document}: the block containing {example.marker!r} is not "
                    f"what the harness prints for the run it is registered against:\n"
                    + "\n".join(difflib.unified_diff(
                        documented, real, "documented", "real", lineterm="")),
                )

    def test_every_output_shaped_block_is_registered(self) -> None:
        """The completeness half. Without it this file checks the examples someone
        remembered to register, which is how the legend's block came to be unchecked while
        its field names were bound (D82, D100)."""
        registered = {(e.document, e.marker) for e in EXAMPLES}
        unregistered: list[str] = []
        for document in EXAMPLE_DOCS:
            for block in _blocks(document):
                if not any(marker in block for marker in OUTPUT_MARKERS):
                    continue
                if not any(doc == document and marker in block
                           for doc, marker in registered):
                    unregistered.append(f"{document}: {block.splitlines()[0][:60]!r}")
        self.assertEqual(
            unregistered, [],
            f"{len(unregistered)} block(s) show harness output and are bound to no run: "
            f"{unregistered}. Register each in EXAMPLES with the submission that produces "
            f"it, or the document is free to drift from the harness (D102).",
        )

    def test_the_registry_is_not_empty_and_every_document_is_read(self) -> None:
        """A scan over documents that do not exist finds nothing and reports success."""
        self.assertTrue(EXAMPLES, "the registry is empty, so the checks above assert nothing")
        for document in EXAMPLE_DOCS:
            with self.subTest(document=document):
                self.assertTrue(
                    (support.REPO_ROOT / document).is_file(),
                    f"{document} is registered for example scanning but does not exist",
                )

    def test_a_doctored_example_is_caught(self) -> None:
        """The premise (D73). A comparison that has only ever seen matching text has not
        been shown to look — and the defect this file exists for was a *deleted row*, which
        is the direction a careless comparison misses."""
        real = _real_summary(EXAMPLES[1]).rstrip("\n").split("\n")
        doctored = [line for line in real if "QTY_OVER_SHIPMENT" not in line]
        self.assertNotEqual(
            doctored, real,
            "the fixture must genuinely differ, or this proves nothing",
        )
        self.assertFalse(
            _contains_run(real, doctored),
            "a block with a row removed must not read as a contiguous fragment either",
        )


def _contains_run(haystack: list[str], needle: list[str]) -> bool:
    """Whether ``needle`` appears as a contiguous run of lines inside ``haystack``."""
    if not needle:
        return False
    for start in range(len(haystack) - len(needle) + 1):
        if haystack[start:start + len(needle)] == needle:
            return True
    return False


if __name__ == "__main__":
    unittest.main()
