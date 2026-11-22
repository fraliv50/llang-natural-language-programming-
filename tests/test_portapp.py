"""Tests for the universal porting application (scanner to CLI)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang.portapp import cleanup, pipeline, scanner, verifier  # noqa: E402
from llang.portapp.adapters import ADAPTERS, register  # noqa: E402
from llang.portapp.cli import main as cli_main  # noqa: E402
from llang.portapp.models import ConversionResult, Gap  # noqa: E402


class FakeAdapter:
    """Adapter for an extension no real adapter claims."""

    name = "fake"
    extensions = ("zzz",)

    def convert(self, source, path):
        return ConversionResult(
            source='show "from fake"\n',
            gaps=[Gap("MagicConstruct", "no llang equivalent", 1, "DO_MAGIC()")],
            notes=[],
            stats={"nodes": 2},
            source_language="fake",
        )


class PortAppTests(unittest.TestCase):
    TIMEOUT = 20

    @classmethod
    def setUpClass(cls):
        cls.fake = FakeAdapter()
        register(cls.fake)

    @classmethod
    def tearDownClass(cls):
        if cls.fake in ADAPTERS:
            ADAPTERS.remove(cls.fake)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    # --- scanner ---------------------------------------------------------
    def test_scan_detects_adapters_and_skips_excluded_dirs(self):
        expected = {
            "main.py",
            "pkg/util.py",
            "magic.zzz",
        }
        for relative in expected:
            self.write(relative, "print(1)\n")
        for relative in (
            ".git/hooks/pre_commit.py",
            "node_modules/dep/index.py",
            "__pycache__/cached.py",
            ".venv/lib/site.py",
            "vendor/lib.py",
            "third_party/lib.py",
            "rewrites/old.py",
            "out/generated.py",
            "build/generated.py",
            "dist/generated.py",
            "notes.txt",
        ):
            self.write(relative, "print(1)\n")

        found = scanner.scan_repo(self.root, output_dir=self.root / "out")
        self.assertEqual([item[0] for item in found], sorted(expected))
        names = {item[0]: item[2] for item in found}
        self.assertEqual(names["main.py"], "python")
        self.assertEqual(names["pkg/util.py"], "python")
        self.assertEqual(names["magic.zzz"], "fake")
        for _relative, absolute, _adapter in found:
            self.assertTrue(Path(absolute).is_absolute())
            self.assertTrue(Path(absolute).is_file())

    def test_scan_include_filter_and_missing_root(self):
        self.write("a.py", "print(1)\n")
        self.write("b.zzz", "anything\n")
        self.assertEqual(
            [item[0] for item in scanner.scan_repo(self.root, include=["py"])],
            ["a.py"],
        )
        self.assertEqual(
            [item[0] for item in scanner.scan_repo(self.root, include=[".ZZZ"])],
            ["b.zzz"],
        )
        with self.assertRaises(ValueError):
            scanner.scan_repo(self.root / "does-not-exist")

    # --- conversion / pipeline artifacts ---------------------------------
    def test_pipeline_converts_python_and_preserves_structure(self):
        self.write("top.py", "print(1 + 2)\n")
        self.write("pkg/nested.py", "x = 4\nprint(x)\n")
        output = self.root / "out"
        summary = pipeline.run_pipeline(self.root, output, verify=False)

        self.assertEqual(summary.files_scanned, 2)
        self.assertEqual(summary.files_converted, 2)
        self.assertEqual(summary.files_failed, 0)
        self.assertEqual((output / "top.ll").read_text(encoding="utf-8").count("show"), 1)
        nested = (output / "pkg" / "nested.ll").read_text(encoding="utf-8")
        self.assertIn("set x to 4", nested)
        self.assertIn("show x", nested)
        self.assertFalse((output / "top.py").exists())

    def test_pipeline_generates_report_and_cleanup_queue(self):
        self.write("gappy.py", "class Foo:\n    pass\n\nprint(1)\n")
        output = self.root / "out"
        summary = pipeline.run_pipeline(self.root, output, verify=False)

        self.assertGreaterEqual(summary.total_gaps, 1)
        self.assertEqual(summary.files_with_gaps, 1)
        queue_path = output / "cleanup_queue.jsonl"
        self.assertTrue(queue_path.is_file())
        lines = [line for line in queue_path.read_text(encoding="utf-8").splitlines() if line]
        self.assertTrue(lines)
        for line in lines:
            item = json.loads(line)
            for key in ("source_path", "target_path", "source_language",
                        "gap", "source_snippet", "partial_llang", "prompt"):
                self.assertIn(key, item)
            self.assertIn("line", item["gap"])
            self.assertIn("description", item["gap"])
            self.assertIn("class Foo", item["source_snippet"])
            self.assertIn("show", item["partial_llang"])
            self.assertIn("llang", item["prompt"])

        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["total_gaps"], summary.total_gaps)
        self.assertEqual(len(report["files"]), 1)
        self.assertEqual(report["files"][0]["gap_count"], summary.total_gaps)
        markdown = (output / "REPORT.md").read_text(encoding="utf-8")
        self.assertIn("# Porting report", markdown)
        self.assertIn("## Cleanup queue", markdown)
        self.assertIn("gappy.py", markdown)

    def test_fake_adapter_conversion_through_pipeline(self):
        self.write("magic.zzz", "DO_MAGIC()\n")
        output = self.root / "out"
        summary = pipeline.run_pipeline(self.root, output, verify=False)
        self.assertEqual(summary.files_converted, 1)
        self.assertEqual(summary.total_gaps, 1)
        self.assertEqual(
            (output / "magic.ll").read_text(encoding="utf-8"),
            'show "from fake"\n',
        )

    def test_cleanup_renderers(self):
        result = ConversionResult(
            source='show "part"\n',
            gaps=[Gap("Weird", "cannot map", 3, "x = WEIRD")],
            stats={"nodes": 4},
            source_language="python",
        )
        items = cleanup.build_items("src/a.py", "out/a.ll", result,
                                    "one\ntwo\nweird_call()\nfour\n")
        self.assertEqual(len(items), 1)
        self.assertIn("3: weird_call()", items[0].source_snippet)
        self.assertIn("line 3", items[0].gap["description"])
        self.assertEqual(len(cleanup.render_queue(items).splitlines()), 1)
        rendered = cleanup.render_report(items)
        self.assertIn("Weird", rendered)
        self.assertIn("line 3", rendered)
        self.assertIn("AI prompt", rendered)
        self.assertIn("No gaps", cleanup.render_report([]))

    # --- verifier --------------------------------------------------------
    def test_verifier_parse_and_lint_real_llang(self):
        output = self.root / "out"
        good = self.write("out/good.ll", 'show "ok"\n')
        bad = self.write("out/bad.ll", 'if true then\nshow "x"\n')

        results = {Path(item.path).name: item for item in verifier.verify_tree(
            output, project_root=ROOT, timeout=self.TIMEOUT,
        )}
        self.assertEqual(set(results), {"good.ll", "bad.ll"})
        self.assertTrue(results["good.ll"].passed)
        self.assertTrue(results["good.ll"].lint_ok)
        self.assertTrue(results["good.ll"].parse_ok)
        self.assertFalse(results["bad.ll"].passed)
        self.assertFalse(results["bad.ll"].parse_ok)
        self.assertTrue(results["bad.ll"].errors)
        self.assertTrue(good.is_file() and bad.is_file())  # never modified

    def test_verifier_lint_failure_and_timeout(self):
        ll_file = self.write("ported.ll", 'show "ok"\n')

        failing_root = self.root / "fake_project_fail"
        failing_root.mkdir()
        (failing_root / "run.py").write_text(
            'print("error: deliberate")\nraise SystemExit(1)\n', encoding="utf-8")
        result = verifier.verify_file(ll_file, project_root=failing_root,
                                      timeout=self.TIMEOUT)
        self.assertFalse(result.lint_ok)
        self.assertFalse(result.passed)
        self.assertIn("deliberate", result.lint_output)

        slow_root = self.root / "fake_project_slow"
        slow_root.mkdir()
        (slow_root / "run.py").write_text(
            "import time\ntime.sleep(10)\n", encoding="utf-8")
        result = verifier.verify_file(ll_file, project_root=slow_root, timeout=1)
        self.assertFalse(result.lint_ok)
        self.assertTrue(any("timed out" in message for message in result.errors))
        self.assertTrue(result.parse_ok)  # parse check is independent of lint

    # --- pipeline summary + CLI ------------------------------------------
    def test_pipeline_summary_with_verification(self):
        self.write("clean.py", "print(1 + 2)\n")
        self.write("gappy.py", "class Foo:\n    pass\nprint(2)\n")
        self.write("magic.zzz", "DO_MAGIC()\n")
        output = self.root / "out"

        summary = pipeline.run_pipeline(
            self.root, output, verify=True, project_root=ROOT, timeout=self.TIMEOUT,
        )
        self.assertEqual(summary.files_scanned, 3)
        self.assertEqual(summary.files_converted, 3)
        self.assertEqual(summary.files_failed, 0)
        self.assertEqual(summary.files_with_gaps, 2)  # gappy.py + magic.zzz
        self.assertEqual(summary.total_gaps, 2)
        self.assertEqual(summary.files_verified, 3)
        self.assertEqual(summary.verification_passed, 3)
        self.assertEqual(summary.verification_failed, 0)
        self.assertTrue(Path(summary.reports["json"]).is_file())
        self.assertTrue(Path(summary.reports["markdown"]).is_file())
        self.assertTrue(Path(summary.reports["cleanup_queue"]).is_file())

    def test_cli_main_direct_and_module_subprocess(self):
        self.write("hello.py", "print(7)\n")
        output = self.root / "out"

        buffer = StringIO()
        with redirect_stdout(buffer):
            code = cli_main([str(self.root), "-o", str(output), "--no-verify",
                             "--include", "py"])
        self.assertEqual(code, 0)
        self.assertIn("Ported 1/1", buffer.getvalue())
        self.assertIn("verification: skipped", buffer.getvalue())
        self.assertTrue((output / "report.json").is_file())

        subprocess_output = self.root / "out_cli"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [sys.executable, "-m", "llang.portapp.cli", str(self.root),
             "-o", str(subprocess_output), "--no-verify"],
            cwd=str(ROOT), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=self.TIMEOUT,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Ported", completed.stdout)
        self.assertTrue((subprocess_output / "hello.ll").is_file())


if __name__ == "__main__":
    unittest.main()
