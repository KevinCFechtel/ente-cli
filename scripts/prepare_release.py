#!/usr/bin/env python3
"""Find the latest stable Rust CLI release and prepare container release notes."""

import argparse
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

UPSTREAM = "ente/ente"
TAG_PATTERN = re.compile(r"ente-cli-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


def github_api(path, missing_ok=False):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ente-cli-container-release",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com/{path}", headers=headers)
    try:
        with urlopen(request, timeout=60) as response:
            return json.load(response)
    except HTTPError as error:
        # Authentication, rate-limit and server errors must NOT mean "no release".
        if missing_ok and error.code == 404:
            return None
        raise


def releases(repository):
    # Ente is a monorepo: /releases/latest may refer to a completely different app.
    page = 1
    while True:
        batch = github_api(f"repos/{repository}/releases?per_page=100&page={page}")
        yield from batch
        if len(batch) < 100:
            return
        page += 1


def latest_rust_release(items):
    candidates = []
    for release in items:
        match = TAG_PATTERN.fullmatch(release["tag_name"])
        if match and not release["draft"] and not release["prerelease"]:
            candidates.append((tuple(map(int, match.groups())), release))
    if not candidates:
        raise ValueError("No stable Ente Rust CLI release found")
    return max(candidates, key=lambda candidate: candidate[0])[1]


def validate_assets(release):
    tag = release["tag_name"]
    expected = {
        f"{tag}-linux-amd64.tar.gz",
        f"{tag}-linux-arm64.tar.gz",
        "SHA256SUMS",
    }
    available = {
        asset["name"] for asset in release["assets"]
        if asset.get("state") == "uploaded"
    }
    missing = expected - available
    if missing:
        raise ValueError(f"{tag}: missing release assets: {', '.join(sorted(missing))}")


def release_notes(release, image, revision):
    version = release["tag_name"].removeprefix("ente-cli-v")
    tag = release["tag_name"]
    # Keep upstream notes verbatim, including contributor credits and links.
    body = release.get("body") or "_Upstream hat keine Release Notes veröffentlicht._"
    return (
        f"# Ente CLI Container {version}\n\n"
        f"Unveränderte **Rust-CLI {version}** aus "
        f"[{UPSTREAM} / {tag}]({release['html_url']}).\n\n"
        f"## Container\n\n"
        f"- Image: `{image}:{version}` (auch `:latest`)\n"
        f"- Plattformen: `linux/amd64`, `linux/arm64`\n"
        f"- Container-Quellstand: [{revision}]"
        f"(https://github.com/{image.removeprefix('ghcr.io/')}/commit/{revision})\n"
        f"- [CLI-Quellcode](https://github.com/{UPSTREAM}/tree/{tag}) · "
        f"[Quellcode-Archiv](https://github.com/{UPSTREAM}/archive/refs/tags/{tag}.tar.gz)\n"
        f"- CLI: AGPL-3.0; Container-Builddateien: BSD-3-Clause.\n\n"
        f"## Änderungen der Ente Rust CLI (Upstream)\n\n{body}\n"
    )


def prepare(repository, output_dir, force=False):
    release = latest_rust_release(releases(UPSTREAM))
    validate_assets(release)
    version = release["tag_name"].removeprefix("ente-cli-v")
    tag = f"v{version}"
    existing = None if force else github_api(
        f"repos/{repository}/releases/tags/{tag}", missing_ok=True
    )
    should_build = force or existing is None or existing["draft"]
    image = f"ghcr.io/{repository.lower()}"
    metadata = {
        "should_build": str(should_build).lower(),
        "version": version,
        "tag": tag,
        "upstream_tag": release["tag_name"],
        "image": image,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "release.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "release-notes.md").write_text(
        release_notes(release, image, os.environ.get("GITHUB_SHA", "HEAD")),
        encoding="utf-8",
    )
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as handle:
            for key, value in metadata.items():
                handle.write(f"{key}={value}\n")
    print(json.dumps(metadata, indent=2))
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--output-dir", type=Path, default=Path(".release"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not args.repository or not re.fullmatch(
        r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository
    ):
        parser.error("--repository owner/repo (or GITHUB_REPOSITORY) is required")
    prepare(args.repository, args.output_dir, args.force)


if __name__ == "__main__":
    main()
