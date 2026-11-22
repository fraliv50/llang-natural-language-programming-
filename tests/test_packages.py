"""Package manifests, version specs, and the local package registry."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang.packages import (  # noqa: E402
    MANIFEST_FILENAME,
    Manifest,
    PackageNotFound,
    PackageRegistry,
    compare_versions,
    load_manifest,
    parse_version,
    version_matches,
)


def write_manifest(directory, name, version="1.0.0", entry=None,
                   exports=None, dependencies=None, filename=MANIFEST_FILENAME,
                   raw=None):
    """Create a manifest JSON file and return its path."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": name,
        "version": version,
        "entry": entry or f"{name}.ll",
        "exports": exports if exports is not None else [],
        "dependencies": dependencies if dependencies is not None else {},
    }
    path = directory / filename
    path.write_text(
        json.dumps(raw if raw is not None else payload),
        encoding="utf-8",
    )
    return path


class VersionTests(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(parse_version("1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version(" 0.10.0 "), (0, 10, 0))
        with self.assertRaises(ValueError):
            parse_version("1.2")
        with self.assertRaises(ValueError):
            parse_version("v1.2.3")
        with self.assertRaises(ValueError):
            parse_version("1.2.x")

    def test_compare_versions_is_numeric(self):
        self.assertEqual(compare_versions("1.10.0", "1.9.9"), 1)
        self.assertEqual(compare_versions("1.2.3", "1.2.3"), 0)
        self.assertEqual(compare_versions("0.9.9", "1.0.0"), -1)

    def test_exact_and_wildcard_specs(self):
        cases = [
            ("1.2.3", "1.2.3", True),
            ("1.2.3", "==1.2.3", True),
            ("1.2.4", "1.2.3", False),
            ("9.9.9", "*", True),
            ("9.9.9", "", True),
        ]
        for version, spec, expected in cases:
            with self.subTest(version=version, spec=spec):
                self.assertEqual(version_matches(version, spec), expected)

    def test_ordering_specs(self):
        cases = [
            ("1.5.0", ">=1.2.3", True),
            ("1.2.3", ">=1.2.3", True),
            ("1.2.2", ">=1.2.3", False),
            ("2.0.0", ">1.2.3", True),
            ("1.2.3", ">1.2.3", False),
            ("1.0.0", "<=1.2.3", True),
            ("1.2.4", "<=1.2.3", False),
            ("1.0.0", "<1.2.3", True),
            ("1.2.3", "<1.2.3", False),
        ]
        for version, spec, expected in cases:
            with self.subTest(version=version, spec=spec):
                self.assertEqual(version_matches(version, spec), expected)

    def test_caret_and_tilde_specs(self):
        cases = [
            ("1.9.9", "^1.2.3", True),
            ("2.0.0", "^1.2.3", False),
            ("1.2.2", "^1.2.3", False),
            ("1.2.9", "~1.2.3", True),
            ("1.3.0", "~1.2.3", False),
            ("1.4.0", "~1.2.3", False),
        ]
        for version, spec, expected in cases:
            with self.subTest(version=version, spec=spec):
                self.assertEqual(version_matches(version, spec), expected)

    def test_unsupported_spec_raises(self):
        with self.assertRaises(ValueError) as ctx:
            version_matches("1.0.0", "latest")
        self.assertIn("unsupported version spec", str(ctx.exception))


class LoadManifestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_valid_manifest(self):
        path = write_manifest(
            self.root / "text", "text", version="1.2.0", entry="text.ll",
            exports=["uppercase", "lowercase"],
            dependencies={"lists": "^1.0.0"})
        manifest = load_manifest(path)
        self.assertEqual(manifest.name, "text")
        self.assertEqual(manifest.version, "1.2.0")
        self.assertEqual(manifest.entry, "text.ll")
        self.assertEqual(manifest.exports, ["uppercase", "lowercase"])
        self.assertEqual(manifest.dependencies, {"lists": "^1.0.0"})
        self.assertEqual(manifest.path, path)

    def test_optional_fields_default_to_empty(self):
        path = self.root / MANIFEST_FILENAME
        path.write_text(
            json.dumps({"name": "tiny", "version": "0.1.0", "entry": "tiny.ll"}),
            encoding="utf-8")
        manifest = load_manifest(path)
        self.assertEqual(manifest.exports, [])
        self.assertEqual(manifest.dependencies, {})

    def test_manifest_dataclass_equality_ignores_path(self):
        a = load_manifest(write_manifest(self.root / "a", "mod"))
        b = load_manifest(write_manifest(self.root / "b", "mod"))
        self.assertEqual(a, b)

    def test_invalid_manifests_name_the_field(self):
        bad_manifests = [
            ({"version": "1.0.0", "entry": "x.ll"}, "name"),
            ({"name": "", "version": "1.0.0", "entry": "x.ll"}, "name"),
            ({"name": 7, "version": "1.0.0", "entry": "x.ll"}, "name"),
            ({"name": "x", "entry": "x.ll"}, "version"),
            ({"name": "x", "version": "1.0", "entry": "x.ll"}, "version"),
            ({"name": "x", "version": "1.0.0"}, "entry"),
            ({"name": "x", "version": "1.0.0", "entry": "x.ll",
              "exports": "uppercase"}, "exports"),
            ({"name": "x", "version": "1.0.0", "entry": "x.ll",
              "exports": [1, 2]}, "exports"),
            ({"name": "x", "version": "1.0.0", "entry": "x.ll",
              "dependencies": ["lists"]}, "dependencies"),
            ({"name": "x", "version": "1.0.0", "entry": "x.ll",
              "dependencies": {"lists": 1}}, "dependencies"),
            ([], None),
        ]
        for index, (payload, field) in enumerate(bad_manifests):
            with self.subTest(index=index):
                path = self.root / f"bad_{index}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError) as ctx:
                    load_manifest(path)
                if field is not None:
                    self.assertIn(field, str(ctx.exception))

    def test_invalid_json_and_missing_file(self):
        bad = self.root / "broken.json"
        bad.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            load_manifest(bad)
        self.assertIn("not valid JSON", str(ctx.exception))
        with self.assertRaises(ValueError):
            load_manifest(self.root / "does-not-exist.json")


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.lib = self.root / "lib"
        self.packages = self.root / "packages"
        self.lib.mkdir()
        self.packages.mkdir()

        write_manifest(self.lib / "math", "math", version="1.0.0",
                       exports=["sqrt"])
        write_manifest(self.lib / "text", "text", version="1.4.0",
                       exports=["uppercase"],
                       dependencies={"math": ">=1.0.0"})
        write_manifest(self.packages / "nested" / "extra", "extra",
                       version="2.1.0", exports=["frobnicate"],
                       dependencies={"text": "^1.0.0", "ghost": "*"})
        write_manifest(self.lib / "multi", "multi", version="1.9.0",
                       filename="old.json")  # not a llang.json -> ignored
        (self.lib / "readme.md").write_text("not a manifest", encoding="utf-8")
        self.registry = PackageRegistry([self.lib, self.packages])

    def test_discover(self):
        manifests = self.registry.discover()
        self.assertEqual(
            {item.name for item in manifests}, {"math", "text", "extra"})
        self.assertTrue(all(item.path is not None for item in manifests))

    def test_discover_skips_missing_roots(self):
        registry = PackageRegistry([self.root / "nope", self.lib])
        self.assertEqual({item.name for item in registry.discover()},
                         {"math", "text"})

    def test_resolve_latest_and_by_spec(self):
        # Auto-discovery on first resolve.
        self.assertEqual(self.registry.resolve("text").version, "1.4.0")
        self.assertEqual(self.registry.resolve("math", ">=1.0.0").version,
                         "1.0.0")
        with self.assertRaises(PackageNotFound):
            self.registry.resolve("ghost")
        with self.assertRaises(PackageNotFound):
            self.registry.resolve("math", ">=2.0.0")

    def test_resolve_picks_highest_matching_version(self):
        write_manifest(self.packages / "math2", "math", version="2.0.0")
        registry = PackageRegistry([self.lib, self.packages])
        self.assertEqual(registry.resolve("math").version, "2.0.0")
        self.assertEqual(registry.resolve("math", "^1.0.0").version, "1.0.0")

    def test_check_dependencies(self):
        text = self.registry.resolve("text")
        self.assertEqual(self.registry.check_dependencies(text), [])

        extra = self.registry.resolve("extra")
        problems = self.registry.check_dependencies(extra)
        self.assertEqual(len(problems), 1)
        self.assertIn("ghost", problems[0])
        self.assertIn("missing", problems[0])

    def test_check_dependencies_reports_incompatible(self):
        write_manifest(self.lib / "picky", "picky",
                       dependencies={"math": ">=2.0.0"})
        problems = self.registry.check_dependencies(self.registry.resolve("picky"))
        self.assertEqual(len(problems), 1)
        self.assertIn("math", problems[0])
        self.assertIn("1.0.0", problems[0])

    def test_check_dependencies_with_manually_built_manifest(self):
        manifest = Manifest(
            name="manual", version="1.0.0", entry="manual.ll",
            dependencies={"math": "^9.0.0"})
        problems = self.registry.check_dependencies(manifest)
        self.assertEqual(len(problems), 1)
        self.assertIn("math", problems[0])

    def test_describe(self):
        text = self.registry.resolve("text")
        summary = PackageRegistry.describe(text)
        self.assertIn("text 1.4.0", summary)
        self.assertIn("text.ll", summary)
        self.assertIn("uppercase", summary)
        self.assertIn("math >=1.0.0", summary)
        self.assertEqual(summary, self.registry.describe(text))

    def test_describe_empty_dependencies(self):
        summary = self.registry.describe(Manifest("solo", "0.1.0", "solo.ll"))
        self.assertIn("(none)", summary)


if __name__ == "__main__":
    unittest.main()
