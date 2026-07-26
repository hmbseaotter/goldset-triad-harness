"""Generator staleness: does the committed data still match the rules that made it (D58)?

The gap this closes. The generator lives out of tree and agent-denied (D14, D17), so
nothing inside the repository could notice that a domain rule changed and the datasets
were never regenerated. Every mechanical check would stay green: the key is
self-consistent, the index matches, the digests verify — all of it describing data
authored under rules that no longer exist. That is the failure this project fears most,
because it is not an error, it is a confidently wrong score.

Each manifest therefore carries ``generator_sha256``, a digest of the generator's source.
Two independent halves:

* Always — every shipped dataset carries a stamp. Needs no generator, so it runs in CI.
* When the generator is reachable — each stamp still matches its source. Skips cleanly
  when it is not, because D14 requires the whole suite to pass from a fresh clone with
  no out-of-tree path in existence.

The skip is the load-bearing part. A test that fails when the secret side is absent would
make CI red for everyone who clones the harness, and a red suite that is always red is a
suite nobody reads.

On hashing an agent-denied file: this reads the generator's bytes into a hash and emits a
hex digest. It never surfaces a rule. That is the same move D10 already makes on the
held-out key, and it is why the deny guard and this check can coexist — hashing is not
disclosure, so this is not a route around a refusal.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from tests import support
from goldset_triad.dataset import generator_digest

#: Where the generator may be found, in order of authority.
#:
#: The environment variable comes first so a machine with a different layout needs no
#: code change. The conventional sibling is the layout this project actually uses; it is
#: a fallback, not a requirement, and its absence is a skip rather than a failure.
GENERATOR_ENV_VAR = "GOLDSET_TRIAD_GENERATOR_DIR"
CONVENTIONAL_GENERATOR_DIR = support.REPO_ROOT.parents[1] / "goldset-triad-secret" / "_generators"

REGENERATE_HINT = (
    "the datasets were authored by a generator whose source has since changed: "
    "re-run the generator (python generate.py) and commit the result, or if the change "
    "was cosmetic, re-run it anyway — the stamp records the source, not the behaviour, "
    "and a cosmetic edit that leaves the data byte-identical will re-stamp and stop here"
)


def find_generator_dir() -> Path | None:
    """The generator directory, or None when this machine has no access to it."""
    override = os.environ.get(GENERATOR_ENV_VAR)
    if override:
        candidate = Path(override)
        # An explicit override that does not resolve is a misconfiguration, not an
        # absence: staying silent there would report "skipped" to someone who believes
        # the check ran.
        if not candidate.is_dir():
            raise AssertionError(
                f"{GENERATOR_ENV_VAR}={override!r} is not a directory; unset it to skip "
                f"the staleness check, or point it at the generator"
            )
        return candidate
    if CONVENTIONAL_GENERATOR_DIR.is_dir():
        return CONVENTIONAL_GENERATOR_DIR
    return None


def _manifest(name: str) -> dict:
    path = support.DATASETS / name / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


class GeneratorStampTests(unittest.TestCase):
    """The half that needs no generator, so it runs everywhere."""

    def test_every_shipped_dataset_records_its_generator(self) -> None:
        for name in support.DEV_DATASETS:
            stamp = _manifest(name).get("generator_sha256")
            self.assertIsNotNone(
                stamp, f"{name}/manifest.json has no generator_sha256; it cannot be "
                f"checked for staleness (D58)"
            )
            assert stamp is not None  # narrowing for the type gate
            self.assertRegex(
                stamp, r"^[0-9a-f]{64}$",
                f"{name}: generator_sha256 is not a sha256 hex digest",
            )

    def test_all_datasets_share_one_stamp(self) -> None:
        """One generator run emits all splits, so disagreement means a partial
        regeneration — some splits current, some stale, and no single check would
        otherwise notice the mixture."""
        stamps = {name: _manifest(name).get("generator_sha256") for name in support.DEV_DATASETS}
        self.assertEqual(
            len(set(stamps.values())), 1,
            f"datasets disagree about their generator: {stamps}; regenerate all splits "
            f"together",
        )


class GeneratorFreshnessTests(unittest.TestCase):
    """The half that needs the generator, and skips without it."""

    def setUp(self) -> None:
        self.generator_dir = find_generator_dir()
        if self.generator_dir is None:
            self.skipTest(
                f"generator not reachable from this checkout (looked at "
                f"${GENERATOR_ENV_VAR} and {CONVENTIONAL_GENERATOR_DIR}); staleness "
                f"cannot be checked here, by design (D14)"
            )

    def test_stamp_matches_the_current_generator(self) -> None:
        assert self.generator_dir is not None
        actual = generator_digest(self.generator_dir)
        for name in support.DEV_DATASETS:
            self.assertEqual(
                _manifest(name).get("generator_sha256"), actual,
                f"{name} is STALE — {REGENERATE_HINT}",
            )

    def test_digest_notices_a_source_change(self) -> None:
        """A stamp that never changes detects nothing. Proven on a copy: mutating one
        generator source must move the digest, and adding bytecode must not."""
        import shutil
        import tempfile

        assert self.generator_dir is not None
        with tempfile.TemporaryDirectory() as td:
            copy = Path(td) / "_generators"
            shutil.copytree(self.generator_dir, copy)
            baseline = generator_digest(copy)
            self.assertEqual(
                baseline, generator_digest(self.generator_dir),
                "the digest depends on the directory's location, so it can never be "
                "compared across machines",
            )

            cache = copy / "__pycache__"
            cache.mkdir(exist_ok=True)
            (cache / "gen_rules.cpython-999.pyc").write_bytes(b"\x00bytecode")
            self.assertEqual(
                generator_digest(copy), baseline,
                "bytecode moved the digest; its name carries an interpreter version, so "
                "the stamp would differ per machine and every dataset would read stale",
            )

            target = copy / "gen_rules.py"
            target.write_text(
                target.read_text(encoding="utf-8") + "\n# a rule changed\n",
                encoding="utf-8", newline="\n",
            )
            self.assertNotEqual(
                generator_digest(copy), baseline,
                "editing a generator source did not move the digest, so the staleness "
                "check cannot detect the thing it exists to detect",
            )


if __name__ == "__main__":
    unittest.main()
