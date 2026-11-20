from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import scan_image as subject


class ImageScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "tested image.tar"
        self.archive.write_bytes(b"image archive")
        self.reports = self.root / "reports"

    def commands(self, run):
        return [call.args[0] for call in run.call_args_list]

    def test_scans_only_archive_without_source_credentials_or_docker_socket(self):
        with patch.object(subject.subprocess, "run") as run:
            subject.scan(self.archive, self.reports)
        commands = self.commands(run)
        self.assertEqual(commands[0], [
            "docker", "build", "--pull", "--tag", subject.SCANNER,
            str(subject.SCANNER_CONTEXT),
        ])
        self.assertEqual(len(commands), 5)
        scan = commands[1]
        self.assertIn(f"{self.archive.resolve()}:/image.tar:ro", scan)
        self.assertIn(f"{self.reports.resolve()}:/reports", scan)
        self.assertIn("--user", scan)
        self.assertIn("HOME=/cache", scan)
        self.assertEqual(scan[scan.index("--input") + 1], "/image.tar")
        self.assertEqual(scan[scan.index("--scanners") + 1], "vuln")
        self.assertIn("--ignore-unfixed=false", scan)
        self.assertIn("--list-all-pkgs", scan)
        self.assertNotIn("--severity", scan)
        self.assertNotIn("--skip-db-update", scan)
        for command in commands[1:]:
            self.assertNotIn("/var/run/docker.sock", " ".join(command))
            self.assertNotIn("GITHUB_TOKEN", " ".join(command))
            self.assertNotIn(str(subject.SCANNER_CONTEXT), command)
        for call in run.call_args_list:
            self.assertTrue(call.kwargs["check"])

    def test_reports_are_generated_before_high_critical_gate(self):
        with patch.object(subject.subprocess, "run") as run:
            subject.scan(self.archive, self.reports)
        scan, sarif, sbom, gate = self.commands(run)[1:]
        self.assertEqual(scan[scan.index("--exit-code") + 1], "0")
        self.assertEqual(sarif[sarif.index("--format") + 1], "sarif")
        self.assertEqual(sbom[sbom.index("--format") + 1], "spdx-json")
        for command in (sarif, sbom, gate):
            self.assertIn("convert", command)
            self.assertEqual(command[-1], "/reports/trivy.json")
        self.assertEqual(gate[gate.index("--severity") + 1], "HIGH,CRITICAL")
        self.assertEqual(gate[gate.index("--exit-code") + 1], "1")

    def test_missing_archive_fails_before_running_docker(self):
        with patch.object(subject.subprocess, "run") as run:
            with self.assertRaises(FileNotFoundError):
                subject.scan(self.root / "missing.tar", self.reports)
        run.assert_not_called()

    def test_directory_is_not_an_archive(self):
        with patch.object(subject.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                subject.scan(self.root, self.reports)
        run.assert_not_called()

    def test_build_scan_conversion_and_gate_errors_all_fail_closed(self):
        for failed_step in range(5):
            with self.subTest(failed_step=failed_step):
                failure = subprocess.CalledProcessError(1, ["docker"])
                with patch.object(subject.subprocess, "run", side_effect=[
                    *([None] * failed_step), failure,
                ]) as run:
                    with self.assertRaises(subprocess.CalledProcessError):
                        subject.scan(self.archive, self.reports)
                self.assertEqual(run.call_count, failed_step + 1)

    def test_stale_reports_are_removed_even_when_scanner_build_fails(self):
        self.reports.mkdir()
        for name in ("trivy.json", "trivy.sarif", "sbom.spdx.json"):
            (self.reports / name).write_text("stale success")
        with patch.object(subject.subprocess, "run", side_effect=
                          subprocess.CalledProcessError(1, ["docker"])):
            with self.assertRaises(subprocess.CalledProcessError):
                subject.scan(self.archive, self.reports)
        self.assertEqual(list(self.reports.iterdir()), [])

    def test_reports_survive_a_failed_vulnerability_gate(self):
        def run(command, **kwargs):
            if "--output" in command:
                filename = Path(command[command.index("--output") + 1]).name
                (self.reports / filename).write_text("{}")
            if "--severity" in command:
                raise subprocess.CalledProcessError(1, command)

        with patch.object(subject.subprocess, "run", side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError):
                subject.scan(self.archive, self.reports)
        self.assertEqual(
            {path.name for path in self.reports.iterdir()},
            {"trivy.json", "trivy.sarif", "sbom.spdx.json"},
        )


if __name__ == "__main__":
    unittest.main()
