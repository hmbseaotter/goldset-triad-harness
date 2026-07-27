"""Reading a file this harness was pointed at, and naming every way that fails (D77).

**One reader, because there were five and they disagreed.** Every module that loaded
JSON had grown its own read-parse-validate sequence, and each guarded a different
subset of the ways a read can fail: `dataset` checked existence and `OSError`,
`cli` dropped the `OSError`, `ledger` dropped the existence check too, and
`audit_key` and `check_isolation` guarded nothing. A caller could not know which
protections applied without reading the callee, and the protections were not the
interesting part of any of those functions — which is exactly the condition under
which copies drift.

**The failure the copies shared: a pinned encoding with no named failure.** D61
required every text read to state its encoding, and every one of them did. Nothing
said what happens when the stated encoding does not apply. `UnicodeDecodeError` is a
`ValueError`, not an `OSError`, so `dataset`'s deliberate `except OSError` — placed
directly around a pinned-encoding read, for exactly this class of problem — caught
the file being unreadable and missed the file not being text. Pointing the harness at
a PDF, a zip, or a UTF-16 export produced a traceback rather than a halt naming its
cause, in a project whose failure policy is that every halt names one.

**Every raise here names the artifact by role, not just by path.** `"answer key is
not valid UTF-8 text"` sends a reader somewhere; `"'utf-8' codec can't decode byte
0xff"` sends them into the standard library. The ``what`` argument is that role, and
it is required rather than defaulted so a new call site cannot omit it quietly.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Final


class DatasetError(Exception):
    """A file is missing, unreadable, or malformed. Every instance names its specific
    cause, so a halt message is never generic (N-observability).

    Defined here rather than in ``dataset`` — where it lived while ``dataset`` was the
    only module that raised it — because it belongs with the reader that raises it, and
    five modules now do. ``dataset`` re-exports it, so every existing
    ``from .dataset import DatasetError`` continues to name this class."""


#: UTF-8, tolerating a leading byte-order mark (D94).
#:
#: `utf-8-sig` strips a BOM when one is present and behaves exactly like `utf-8` when it is
#: not, so this widens what the harness accepts without loosening what it means. It is still
#: an explicitly named encoding, which is what D61 requires — the rule was never "utf-8", it
#: was "never the platform default".
#:
#: Why tolerate it at all: Windows is first-class here by constraint, and Windows tooling
#: adds a BOM freely — Notepad's "UTF-8", `Out-File -Encoding utf8` on PowerShell 5.1, and
#: plenty of editors. An agent under test running there can emit one, and rejecting its
#: findings over three bytes that carry no meaning is refusing to score work for a reason
#: unrelated to the work. Nothing is weakened: every digest in this project hashes RAW BYTES
#: via `read_bytes`, so a BOM'd artifact still fingerprints differently from a clean one, as
#: it should — the two really are different files.
_ENCODING: Final = "utf-8-sig"


def read_text_file(path: Path, what: str) -> str:
    """Read ``path`` as UTF-8, naming existence, permission and encoding failures apart.

    The three are different findings. A file that is absent, a file that cannot be
    opened, and a file that is not text send a reader to three different places, and
    collapsing them into "could not read" is the misdiagnosis D50 ruled worse than
    silence."""
    if not path.is_file():
        raise DatasetError(f"{what} not found or unreadable: {path}")
    try:
        return path.read_text(encoding=_ENCODING)
    except UnicodeDecodeError as exc:
        # Ordered before OSError deliberately: UnicodeDecodeError is a ValueError, so
        # the two are disjoint and this could sit either way -- but reading it first is
        # what states, at the call site, that the encoding failure is handled at all.
        raise DatasetError(
            f"{what} is not UTF-8 text: {path} (byte {exc.start}: {exc.reason}). "
            f"Every file this harness reads is UTF-8 by declaration (D61), so this is a "
            f"file it cannot read, not a file it read and disagreed with"
        ) from exc
    except OSError as exc:
        raise DatasetError(f"{what} not readable: {path} ({exc})") from exc


def read_json_file(path: Path, what: str) -> Any:
    """Read ``path`` as a UTF-8 JSON document.

    ``parse_float=Decimal`` is pinned at every call site this replaces, because no
    monetary value may become a float on any path (D3). Pinning it *here* means a new
    reader cannot forget: the constraint stops depending on each caller remembering
    it, which is the D67/D68 move applied to a parser argument."""
    text = read_text_file(path, what)
    try:
        return json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise DatasetError(f"{what} is not valid JSON: {path} ({exc})") from exc


def read_json_object(path: Path, what: str) -> dict[str, Any]:
    """Read ``path`` as a JSON *object*, rejecting a valid JSON array, string or null.

    Separate from :func:`read_json_file` rather than folded into it: a findings
    artifact's top level is an object, and so is a scorecard's, but a caller reading a
    list-shaped document is not wrong to exist. Making the object requirement explicit
    at the call site keeps the check where the expectation is stated."""
    raw = read_json_file(path, what)
    if not isinstance(raw, dict):
        raise DatasetError(
            f"{what} is not a JSON object: {path} (it parses to {type(raw).__name__})"
        )
    return raw
