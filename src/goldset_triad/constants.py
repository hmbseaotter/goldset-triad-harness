"""Declared constants (D28, D20, D23).

The specification requires several values to be *declared* rather than left to
the ambient environment, so that scorecard bytes are fixed by this file and not
by whichever interpreter happens to run. The values themselves are free choices;
what matters is that they are stated here, in one place, and never read from a
mutable default.
"""

from decimal import ROUND_HALF_UP
from typing import Final

# --- Decimal discipline (D28, D23) ----------------------------------------------
# The decimal context precision is pinned so that any incidental division (e.g. a
# reported ratio) rounds identically on every machine. 28 is Python's own default,
# chosen so pinning it changes nothing observable while making the guarantee
# explicit rather than inherited.
DECIMAL_CONTEXT_PRECISION: Final = 28

# Monetary values display at two decimal places; reported ratios at four. Both use
# ROUND_HALF_UP explicitly, because Python's Decimal defaults to ROUND_HALF_EVEN
# (banker's rounding), which is not what an accountant expects and would silently
# shift a half-cent the wrong way.
MONEY_DISPLAY_PLACES: Final = 2
RATIO_OUTPUT_PLACES: Final = 4
ROUNDING_MODE: Final = ROUND_HALF_UP

# --- Findings payload (D20) ------------------------------------------------------
# A DOCUMENT-scoped finding carries this reserved sentinel in place of a line id.
# It is never empty and never absent: a document-scoped finding whose line id is
# missing is malformed, not inferred to be document-level.
DOCUMENT_LINE_SENTINEL: Final = "__DOCUMENT__"
