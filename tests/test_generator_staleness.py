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
import tempfile
import unittest
from pathlib import Path

from tests import support
from goldset_triad.dataset import generator_digest, sha256_file

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


class HeldOutStalenessTests(unittest.TestCase):
    """The held-out split needs the same check, and needs it most (D64).

    Every other staleness check iterates the dev splits, so the held-out manifest carried
    a stamp that nothing compared. That is the split whose numbers carry weight — the one
    D60 added coverage reporting for on exactly that ground — and a stale held-out key is
    D58's failure in its most costly form: confidently wrong scores on the evaluation that
    matters, with the key self-consistent and every fingerprint verifying.

    It cannot run in CI, since D14 puts the whole split out of tree. It can run for whoever
    holds the tier, which is who regenerates. Reading the manifest leaks nothing: a stamp
    is a digest, and the paths it names are not the answers."""

    def setUp(self) -> None:
        secret = support.find_secret_dir()
        if secret is None:
            self.skipTest("no secret tier on this machine; the held-out split is out of reach")
        manifest = secret / "held-out" / "manifest.json"
        if not manifest.is_file():
            self.skipTest(f"secret tier present but no held-out manifest at {manifest}")
        self.manifest = json.loads(manifest.read_text(encoding="utf-8"))

    def test_held_out_manifest_records_its_generator(self) -> None:
        stamp = self.manifest.get("generator_sha256")
        self.assertIsNotNone(
            stamp, "the held-out manifest has no generator_sha256, so its staleness "
                   "cannot be detected at all")
        self.assertRegex(str(stamp), r"^[0-9a-f]{64}$")

    def test_held_out_stamp_agrees_with_the_dev_splits(self) -> None:
        """All four splits come from one generator, so one stamp should describe them all.
        A divergence means some split was regenerated and another was not."""
        dev_stamps = {name: _manifest(name).get("generator_sha256") for name in support.DEV_DATASETS}
        held = self.manifest.get("generator_sha256")
        disagreeing = {n: s for n, s in dev_stamps.items() if s != held}
        self.assertEqual(
            disagreeing, {},
            f"the held-out stamp {str(held)[:12]}... disagrees with {disagreeing}: "
            f"{REGENERATE_HINT}",
        )

    def test_held_out_stamp_matches_the_current_generator(self) -> None:
        generator = find_generator_dir()
        if generator is None:
            self.skipTest("no generator on this machine")
        self.assertEqual(
            self.manifest.get("generator_sha256"), generator_digest(generator),
            f"the held-out split is stale: {REGENERATE_HINT}",
        )


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

    def test_a_byte_order_mark_does_not_move_the_digest(self) -> None:
        """Pinned deliberately, having been discovered as a side effect (D107).

        D94 switched the shared reader to `utf-8-sig` so a BOM'd findings artifact from a
        Windows agent would score. `generator_digest` reads through that same function and,
        by D63, digests *normalized text* rather than raw bytes — so the switch also made a
        BOM invisible to the D58 staleness check. D94's justification said the opposite
        (*"every digest hashes RAW BYTES"*), which is true of the fingerprints and not of
        this one.

        The behaviour is kept because D63's own test says to keep it: for source, the
        semantic content is the thing and a line ending is transport. A BOM encodes nothing
        about what the generator *does*, so it should not read as a rule change and send
        someone regenerating four datasets. What was wrong was that nobody had decided
        it — so it is decided here, and asserted, rather than left to be re-derived by the
        next reader who wonders."""
        import shutil
        import tempfile

        assert self.generator_dir is not None
        with tempfile.TemporaryDirectory() as td:
            copy = Path(td) / "_generators"
            shutil.copytree(self.generator_dir, copy)
            baseline = generator_digest(copy)

            source = sorted(p for p in copy.rglob("*.py") if "__pycache__" not in p.parts)[0]
            source.write_bytes(b"\xef\xbb\xbf" + source.read_bytes())
            self.assertEqual(
                generator_digest(copy), baseline,
                f"a byte-order mark on {source.name} moved the generator digest. It must "
                f"not: a BOM is transport, like a line ending (D63), and moving the digest "
                f"would report a stale dataset when no rule changed — a misdiagnosis in "
                f"the alarming direction (D50, D107)",
            )

    def test_a_byte_order_mark_does_move_a_dataset_artifact_fingerprint(self) -> None:
        """The other direction, which must NOT be tolerant (D107).

        Dataset inputs are digested by `read_bytes` (D27), where a BOM is a byte difference
        and has to register as one — the two really are different files, and a scorecard
        fingerprints the bytes an agent read. The BOM tolerance is a *reading* concession,
        never a *hashing* one, and nothing had asserted the boundary between them."""
        with tempfile.TemporaryDirectory() as td:
            source = support.DATASETS / "dev" / "dev_invoice_index.json"
            plain = Path(td) / "plain.json"
            plain.write_bytes(source.read_bytes())
            bommed = Path(td) / "bommed.json"
            bommed.write_bytes(b"\xef\xbb\xbf" + source.read_bytes())
            self.assertNotEqual(
                sha256_file(plain), sha256_file(bommed),
                "a BOM must change an artifact's fingerprint: digests are over raw bytes "
                "so a scorecard records exactly what was scored (D27)",
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
