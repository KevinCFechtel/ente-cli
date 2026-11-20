#!/usr/bin/env python3
"""Scan a final Docker image archive, generate reports, and enforce the CVE gate."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


SCANNER = "ente-cli-security-scanner:local"
SCANNER_CONTEXT = Path(__file__).resolve().parents[1] / ".github" / "trivy"


def scan(archive, output_dir):
    archive = Path(archive).resolve(strict=True)
    if not archive.is_file():
        raise ValueError("Expected an image archive created by docker save")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    # Never upload a stale successful report if a new scan fails.
    for name in ("trivy.json", "trivy.sarif", "sbom.spdx.json"):
        (output_dir / name).unlink(missing_ok=True)

    subprocess.run(
        ["docker", "build", "--pull", "--tag", SCANNER, str(SCANNER_CONTEXT)],
        check=True,
    )
    with tempfile.TemporaryDirectory(prefix="ente-cli-trivy-") as cache:
        # Scan only the archive: no Docker socket, source checkout, or credentials
        # are made available to the scanner. Run as the host user for report access.
        command = [
            "docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
            "--env", "HOME=/cache",
            "--volume", f"{archive}:/image.tar:ro",
            "--volume", f"{output_dir}:/reports",
            "--volume", f"{cache}:/cache",
            SCANNER,
        ]

        def trivy(*args):
            subprocess.run(command + list(args), check=True)

        # Scan once with fresh vulnerability data, retaining all packages and
        # severities for the SBOM and SARIF. Infrastructure/DB errors fail closed.
        trivy(
            "image", "--input", "/image.tar", "--cache-dir", "/cache",
            "--timeout", "10m", "--scanners", "vuln", "--list-all-pkgs",
            "--ignore-unfixed=false", "--ignorefile", "/dev/null",
            "--format", "json", "--output", "/reports/trivy.json",
            "--exit-code", "0",
        )
        for report_format, filename in (
            ("sarif", "trivy.sarif"),
            ("spdx-json", "sbom.spdx.json"),
        ):
            trivy(
                "convert", "--format", report_format,
                "--output", f"/reports/{filename}", "/reports/trivy.json",
            )
        # Generate reports before failing, so findings remain available in CI.
        # Unfixed HIGH/CRITICAL vulnerabilities also block publication.
        trivy(
            "convert", "--format", "table", "--scanners", "vuln",
            "--severity", "HIGH,CRITICAL", "--ignorefile", "/dev/null",
            "--exit-code", "1", "/reports/trivy.json",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    scan(args.archive, args.output_dir)


if __name__ == "__main__":
    main()
