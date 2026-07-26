"""goldset-triad-harness — a held-out golden-dataset harness.

Scores an AP document-matching agent's 3-way (PO / invoice / goods-receipt)
findings against hand-audited ground truth.

The four components are deliberately separated (D35):

- ``scoring engine``     — loads the key and invoice index, matches, counts,
                           emits the scorecard. Holds NO domain rule, ever.
                           Standard library only.
- ``key generator``      — applies the domain rules and authors the key. Lives
                           on the secret side; NOT part of this package.
- ``key-audit command``  — independently re-derives expectations and diffs them
                           against the key. Ships (``audit_key``) but is never
                           imported by any scoring path.
- ``matching policy``    — the published statement of every rule the generator
                           applied. A data file in each dataset.
"""

from typing import Final

__version__: Final = "0.1.0"
