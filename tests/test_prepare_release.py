import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import prepare_release as subject


def release(version="0.4.4", **overrides):
    tag = f"ente-cli-v{version}"
    result = {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "html_url": f"https://github.com/ente/ente/releases/tag/{tag}",
        "body": "- Fixed exports (@contributor).\n\n[Docs](https://ente.com/help/cli/)\n",
        "assets": [
            {"name": name, "state": "uploaded"}
            for name in (
                f"{tag}-linux-amd64.tar.gz",
                f"{tag}-linux-arm64.tar.gz",
                "SHA256SUMS",
            )
        ],
    }
    result.update(overrides)
    return result


class ReleaseTests(unittest.TestCase):
    def test_only_stable_rust_releases_are_selected_in_semver_order(self):
        items = [
            release("0.4.9"),
            release("0.4.10"),
            release("9.0.0", draft=True),
            release("8.0.0", prerelease=True),
            release("99.0.0", tag_name="cli-v99.0.0"),
            release("99.0.0", tag_name="photos-v99.0.0"),
            release("99.0.0", tag_name="ente-cli-v99.0.0-rc.1"),
            release("99.0.0", tag_name="ente-cli-v99.0.0\n"),
        ]
        self.assertEqual(subject.latest_rust_release(items)["tag_name"], "ente-cli-v0.4.10")

    def test_no_matching_release_fails(self):
        with self.assertRaisesRegex(ValueError, "No stable"):
            subject.latest_rust_release([release(tag_name="cli-v0.3.9")])

    def test_pagination_is_not_limited_to_first_monorepo_page(self):
        with patch.object(subject, "github_api", side_effect=[
            [release(tag_name="photos-v1.0.0")] * 100,
            [release()],
        ]) as api:
            found = subject.latest_rust_release(subject.releases(subject.UPSTREAM))
        self.assertEqual(found["tag_name"], "ente-cli-v0.4.4")
        self.assertIn("page=2", api.call_args.args[0])

    def test_all_linux_assets_and_checksums_are_required(self):
        subject.validate_assets(release())
        for asset_index in range(3):
            item = release()
            item["assets"].pop(asset_index)
            with self.subTest(asset_index=asset_index), self.assertRaises(ValueError):
                subject.validate_assets(item)

    def test_incomplete_upload_is_not_accepted(self):
        item = release()
        item["assets"][0]["state"] = "new"
        with self.assertRaises(ValueError):
            subject.validate_assets(item)

    def test_incomplete_latest_release_never_falls_back_to_older_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            items = [release("0.4.3"), release("0.4.4", assets=[])]
            with patch.object(subject, "releases", return_value=items), \
                 patch.object(subject, "github_api") as api:
                with self.assertRaisesRegex(ValueError, "missing release assets"):
                    subject.prepare("Owner/Repo", Path(tmp))
            api.assert_not_called()
            self.assertFalse((Path(tmp) / "release.json").exists())

    def test_notes_include_verbatim_upstream_changelog_and_source(self):
        item = release()
        notes = subject.release_notes(item, "ghcr.io/owner/repo", "abc123")
        self.assertIn(item["body"], notes)
        self.assertIn("ghcr.io/owner/repo:0.4.4", notes)
        self.assertIn("ente-cli-v0.4.4.tar.gz", notes)
        self.assertIn("https://github.com/owner/repo/commit/abc123", notes)
        self.assertIn("without an AVX requirement", notes)
        self.assertIn("Nehalem", notes)

    def test_empty_notes_have_fallback(self):
        notes = subject.release_notes(release(body=None), "ghcr.io/owner/repo", "HEAD")
        self.assertIn("did not publish any release notes", notes)

    def test_build_decision_and_outputs(self):
        for existing, force, expected in [
            (None, False, "true"),
            ({"draft": False}, False, "false"),
            ({"draft": True}, False, "true"),
            ({"draft": False}, True, "true"),
        ]:
            with self.subTest(existing=existing, force=force), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "output"
                with patch.object(subject, "releases", return_value=[release()]), \
                     patch.object(subject, "github_api", return_value=existing) as api, \
                     patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), \
                     patch("sys.stdout", new_callable=io.StringIO):
                    metadata = subject.prepare("Owner/Repo", Path(tmp), force)
                self.assertEqual(metadata["should_build"], expected)
                self.assertEqual(metadata["image"], "ghcr.io/owner/repo")
                self.assertEqual(metadata["tag"], "v0.4.4")
                self.assertEqual(json.loads((Path(tmp) / "release.json").read_text()), metadata)
                self.assertIn(f"should_build={expected}\n", output.read_text())
                self.assertEqual(api.call_count, 0 if force else 1)

    def test_only_404_is_treated_as_missing(self):
        for status in [401, 403, 404, 429, 500]:
            error = HTTPError("https://api.github.com/test", status, "error", {}, None)
            with self.subTest(status=status), patch.object(subject, "urlopen", side_effect=error):
                if status == 404:
                    self.assertIsNone(subject.github_api("test", missing_ok=True))
                else:
                    with self.assertRaises(HTTPError):
                        subject.github_api("test", missing_ok=True)

    def test_existing_release_api_failure_never_triggers_a_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            error = HTTPError("https://api.github.com/test", 403, "rate limit", {}, None)
            with patch.object(subject, "releases", return_value=[release()]), \
                 patch.object(subject, "github_api", side_effect=error):
                with self.assertRaises(HTTPError):
                    subject.prepare("Owner/Repo", Path(tmp))
            self.assertFalse((Path(tmp) / "release.json").exists())


if __name__ == "__main__":
    unittest.main()
