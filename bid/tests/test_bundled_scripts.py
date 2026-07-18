import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import BID_ROOT, run


SKILLS_ROOT = BID_ROOT / "skills"
CHROME_PATH = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

EXPECTED_SCRIPTS = {
    "adversarial-review/scripts/check-residuals.sh",
    "bid-costing/scripts/discount-check.cjs",
    "bid-research/scripts/extract-frames.sh",
    "bid-scheduling/scripts/level.cjs",
    "deai-writing/scripts/aiflavor-scan.cjs",
    "diagram-pdf-pipeline/scripts/add-outline.cjs",
    "prototype-handoff/scripts/extract-frames.sh",
    "single-source-sync/scripts/xlsx-dump.cjs",
}

CJS_SCRIPTS = tuple(
    SKILLS_ROOT / relative
    for relative in sorted(EXPECTED_SCRIPTS)
    if relative.endswith(".cjs")
)
FRAME_SCRIPTS = (
    SKILLS_ROOT / "bid-research/scripts/extract-frames.sh",
    SKILLS_ROOT / "prototype-handoff/scripts/extract-frames.sh",
)


def combined_output(result):
    return result.stdout + result.stderr


def require_resolves(module, script):
    result = run(
        "node",
        "-e",
        "require.resolve(process.argv[1], {paths: [process.argv[2]]})",
        module,
        str(script.parent),
    )
    return result.returncode == 0


class BundledScriptTests(unittest.TestCase):
    def test_script_inventory_is_exact(self):
        actual = {
            str(path.relative_to(SKILLS_ROOT))
            for path in SKILLS_ROOT.glob("*/scripts/*")
            if path.is_file()
        }
        self.assertEqual(actual, EXPECTED_SCRIPTS)

    def test_shell_and_node_syntax(self):
        for script in FRAME_SCRIPTS:
            with self.subTest(script=script.relative_to(BID_ROOT)):
                result = run("bash", "-n", str(script))
                self.assertEqual(result.returncode, 0, combined_output(result))

        self.assertEqual(len(CJS_SCRIPTS), 5)
        for script in CJS_SCRIPTS:
            with self.subTest(script=script.relative_to(BID_ROOT)):
                result = run("node", "--check", str(script))
                self.assertEqual(result.returncode, 0, combined_output(result))

    def test_check_residuals_selftest(self):
        script = SKILLS_ROOT / "adversarial-review/scripts/check-residuals.sh"
        result = run("bash", str(script), "selftest")
        self.assertEqual(result.returncode, 0, combined_output(result))
        self.assertIn("SELFTEST OK", result.stdout)

    def test_level_selftest(self):
        script = SKILLS_ROOT / "bid-scheduling/scripts/level.cjs"
        result = run("node", str(script), "--selftest")
        self.assertEqual(result.returncode, 0, combined_output(result))
        self.assertIn("selftest: PASS", result.stdout)

    def test_discount_check_accepts_consistent_prices(self):
        script = SKILLS_ROOT / "bid-costing/scripts/discount-check.cjs"
        result = run("node", str(script), "1000", "500:0.5", "400:0.4")
        self.assertEqual(result.returncode, 0, combined_output(result))
        self.assertIn("PASS", result.stdout)

    def test_aiflavor_scan_writes_nonempty_json(self):
        script = SKILLS_ROOT / "deai-writing/scripts/aiflavor-scan.cjs"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "中文样稿.md"
            output = tmp_path / "scan.json"
            source.write_text(
                "# 项目说明：交付口径\n\n"
                "值得注意的是，这不是临时拼接，而是可复核的单一真源。\n",
                encoding="utf-8",
            )

            result = run("node", str(script), str(source), "--json", str(output))
            self.assertEqual(result.returncode, 0, combined_output(result))
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertIsInstance(payload, list)
            self.assertTrue(payload)
            self.assertGreater(payload[0]["chars"], 0)

    def test_frame_scripts_are_executable_and_show_usage_without_arguments(self):
        for script in FRAME_SCRIPTS:
            with self.subTest(script=script.relative_to(BID_ROOT)):
                self.assertTrue(os.access(script, os.X_OK), f"not executable: {script}")
                result = run(str(script))
                self.assertNotEqual(result.returncode, 0, combined_output(result))
                self.assertIn("用法", combined_output(result))

    def test_frame_script_integrations_when_tools_are_installed(self):
        commands = ("ffmpeg", "magick", "montage")
        missing = [command for command in commands if shutil.which(command) is None]
        if missing:
            self.skipTest("missing optional command(s): " + ", ".join(missing))

        research = SKILLS_ROOT / "bid-research/scripts/extract-frames.sh"
        prototype = SKILLS_ROOT / "prototype-handoff/scripts/extract-frames.sh"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video = tmp_path / "color.mp4"
            generated = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=red:s=64x64:r=2:d=2",
                    "-pix_fmt",
                    "yuv420p",
                    "-y",
                    str(video),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(generated.returncode, 0, combined_output(generated))
            self.assertGreater(video.stat().st_size, 0)

            research_out = tmp_path / "research-out"
            result = run(str(research), str(video), str(research_out), "1", "2")
            self.assertEqual(result.returncode, 0, combined_output(result))
            self.assertTrue(list((research_out / "frames").glob("f*.png")))
            self.assertTrue(list((research_out / "sheets").glob("sheet_*.png")))

            prototype_frames = tmp_path / "prototype-frames"
            result = run(
                str(prototype), "frames", str(video), str(prototype_frames), "1"
            )
            self.assertEqual(result.returncode, 0, combined_output(result))
            frames = sorted(prototype_frames.glob("f*.jpg"))
            self.assertTrue(frames)

            prototype_sheets = tmp_path / "prototype-sheets"
            result = run(
                str(prototype), "sheet", str(prototype_frames), str(prototype_sheets), "2"
            )
            self.assertEqual(result.returncode, 0, combined_output(result))
            self.assertTrue(list(prototype_sheets.glob("sheet-*.png")))

            result = run(str(prototype), "pixel", str(frames[0]), "0", "0")
            self.assertEqual(result.returncode, 0, combined_output(result))
            self.assertRegex(result.stdout.strip(), r"^#[0-9A-Fa-f]{6,16}$")

    def test_add_outline_usage_and_pdf_when_dependency_is_installed(self):
        script = SKILLS_ROOT / "diagram-pdf-pipeline/scripts/add-outline.cjs"
        if not require_resolves("playwright-core", script):
            self.skipTest("optional Node module not resolvable: playwright-core")

        usage = run("node", str(script))
        self.assertNotEqual(usage.returncode, 0, combined_output(usage))
        self.assertIn("用法", combined_output(usage))
        if not CHROME_PATH.is_file():
            self.skipTest(f"optional macOS Chrome executable missing: {CHROME_PATH}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            html = tmp_path / "input.html"
            pdf = tmp_path / "output.pdf"
            html.write_text(
                "<!doctype html><meta charset='utf-8'>"
                "<style>@page { size: A4; }</style>"
                "<h1>投标方案</h1><p>中文 PDF 集成测试。</p>",
                encoding="utf-8",
            )
            result = run("node", str(script), str(html), str(pdf))
            self.assertEqual(result.returncode, 0, combined_output(result))
            self.assertGreater(pdf.stat().st_size, 4)
            self.assertEqual(pdf.read_bytes()[:4], b"%PDF")

    def test_xlsx_dump_usage_and_workbook_when_dependency_is_installed(self):
        script = SKILLS_ROOT / "single-source-sync/scripts/xlsx-dump.cjs"
        if not require_resolves("exceljs", script):
            self.skipTest("optional Node module not resolvable: exceljs")

        usage = run("node", str(script))
        self.assertNotEqual(usage.returncode, 0, combined_output(usage))
        self.assertIn("用法", combined_output(usage))

        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "input.xlsx"
            fixture = run(
                "node",
                "-e",
                """
const ExcelJS = require('exceljs');
(async () => {
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet('报价');
  sheet.getCell('A1').value = 100;
  await workbook.xlsx.writeFile(process.argv[1]);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
""",
                str(workbook),
                cwd=script.parent,
            )
            self.assertEqual(fixture.returncode, 0, combined_output(fixture))

            result = run("node", str(script), str(workbook), "报价")
            self.assertEqual(result.returncode, 0, combined_output(result))
            self.assertIn("报价!A1\t100", result.stdout)


if __name__ == "__main__":
    unittest.main()
