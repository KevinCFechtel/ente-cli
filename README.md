# Ente CLI Container (Rust)

Unofficial multi-architecture container image for the new Rust-based
[Ente CLI](https://ente.com/help/cli/). The old Go CLI is not used.

## Automated builds and changelogs

The [GitHub Actions workflow](.github/workflows/container.yml):

1. checks releases from `ente/ente` daily at **05:23 UTC**;
2. selects the highest stable semantic version tagged `ente-cli-vX.Y.Z`
   (excluding Go releases, drafts, and prereleases);
3. skips container versions that have already been published;
4. builds the unmodified release-tag sources with `Cargo.lock` natively for
   **linux/amd64** and **linux/arm64**, using generic Rust and C/C++ CPU flags;
5. tests both images as a non-root user and additionally tests HTTPS/TLS on amd64
   under QEMU with a **Nehalem CPU without AVX**;
6. scans both final images with Trivy and blocks publication on **HIGH/CRITICAL**
   vulnerabilities, including those without an available fix;
7. publishes those exact tested and scanned images as a multi-architecture image
   on **GHCR**, with signed provenance and per-architecture SBOM attestations;
8. creates a GitHub release `vX.Y.Z` with the **unmodified upstream release notes**,
   source code links, the image digest, and SPDX JSON SBOMs for both architectures.

Image: `ghcr.io/kevincfechtel/ente-cli`

Tags: `:X.Y.Z` and `:latest`, plus `:X.Y.Z-amd64` and `:X.Y.Z-arm64`.
GitHub releases serve as the container changelog;
no automated commits to `main` are needed.
The first run builds only the latest stable version, not a historical archive.
After a pause, the latest version is picked up; intermediate releases are not
built retroactively.

Pushes to `main` rebuild the current CLI version so that container changes can be
published immediately. Pull requests test both architectures but do not publish
anything. A manual run under **Actions → Ente CLI container → Run workflow** also
checks for updates; enabling `force` rebuilds the current version, for example
to pick up base image security updates.
A rebuild updates the image tags and release notes; for an immutable image,
use the digest provided in the release.
The Git tag of an existing release stays at its original commit;
the container source revision actually used is recorded in the release notes
and the OCI label `org.opencontainers.image.revision`.

Failed builds or pushes do not create a new successful GitHub release;
for unpublished versions, the next daily run retries publication.
If a rebuild of an already published version fails, rerun it with `force`
or retry after another push to `main`.
Missing upstream assets and API errors abort the run rather than accidentally
publishing a different CLI version.

### Image security

Security checks inspect the **final container images**, not the upstream Ente
source repository. No Ente CodeQL analysis or separate Cargo audit is performed.
Both architectures must pass before either is published; the scanned image
archives are reused for publication without rebuilding.

The [published-image security workflow](.github/workflows/image-security.yml)
also checks the current `:latest` image daily at **07:23 UTC**, and can be started
manually under **Actions → Published image security → Run workflow**.
It resolves the multi-architecture digest once and scans both platforms from
that immutable reference, even when no new Ente release or container build exists.
It does not scan every historical version or automatically rebuild or remove images.

Trivy uses a version- and digest-pinned scanner image, maintained by Dependabot,
and downloads current vulnerability data for each run. Scanner, database, and
report-generation errors fail the check rather than being treated as clean scans.
All detected vulnerability severities are retained in SARIF/JSON reports;
**HIGH/CRITICAL**, including unfixed findings, fail the workflow. There are no
automatic vulnerability exceptions. Review findings before updating the base
image or waiting for an upstream release; use `force` to rebuild when appropriate.

Results appear under **Security → Code scanning** and as 30-day workflow artifacts
(`image-security-amd64` / `image-security-arm64`), including SPDX JSON SBOMs.
Fork and Dependabot PRs run the same checks and retain artifacts but skip SARIF
upload because their tokens may be read-only. The use of `codeql-action/upload-sarif`
only uploads Trivy reports; it does not run CodeQL.

Published releases include downloadable per-architecture SBOMs. Signed provenance
for the multi-platform digest and SBOM attestations for each architecture's digest
are stored in GitHub and GHCR, without changing the tested image layers.
For example, verify provenance using the digest from a release:

```sh
gh attestation verify 'oci://ghcr.io/kevincfechtel/ente-cli@sha256:<digest>' \
  --repo KevinCFechtel/ente-cli
```

Coverage depends on metadata present in the final image. Alpine packages are
inventoried, but statically linked Rust/native dependencies may not be fully
discoverable. A clean scan and its SBOM are not proof that every component is
free of vulnerabilities. The GitHub Dependency Graph continues to cover Actions;
these image SBOMs are not automatically submitted to it.

### Synology and CPUs without AVX

The official Ente CLI 0.4.5 amd64 binary executes an AVX instruction in the
`ring` cryptography library. On CPUs such as the Intel Celeron J4125,
this causes `SIGILL` / exit code **132** during login or HTTPS requests.
This image therefore builds the CLI and its native dependencies from source
without requiring AVX. The CLI source code remains unmodified.
The additional test exercises TLS certificate verification against a local
test server, not just `--version`. It requires neither an Ente account nor
credentials and does not contact a real Ente server.

Pushing the container change to `main` rebuilds the CLI version even if it has
already been published. Its image tag and `latest` are updated only after all
checks pass. Afterwards, run the following on the Docker host from the
Compose directory:

```sh
sudo docker compose pull
sudo docker compose up -d
```

Keep the Compose configuration, vault key, and config and export volumes;
do not use `down -v`. If you pin the image by digest, explicitly update it
to the new digest. Simply restarting the container does not pull a new image.

## Initial setup

1. Commit the changes and push to `main`. GitHub Actions must be enabled
   in the repository; the push starts the first build.
2. The workflow uses the existing `GITHUB_TOKEN` with `contents: write`,
   `packages: write`, and `attestations: write` for publication,
   `security-events: write` for scan uploads, and `id-token: write` for signing.
   These permissions are restricted to the jobs that need them.
   No separate PAT or registry secret is required.
   Repository and organization policies must allow these permissions.
3. After the first push, make the GHCR package public if needed under
   **Package settings → Change visibility → Public**. New packages may initially
   be private, in which case pulling them requires authentication.
4. When the workflow runs in a fork, it automatically uses
   `ghcr.io/<owner>/<repo>` in lowercase.

GitHub may delay scheduled runs and disables them in public repositories after
60 days of inactivity. If this happens, re-enable the schedule under Actions.
Scheduled runs execute only on the default branch.

## Usage

```sh
docker run --rm ghcr.io/kevincfechtel/ente-cli:latest --version
docker run --rm ghcr.io/kevincfechtel/ente-cli:latest --help
```

The CLI is the entrypoint; arguments go directly after the image name.
It runs as **UID/GID 1000:1000**. The CLI home is `/config`;
export destinations can be mounted at `/export`.

### Log in and export photos

A container has no system credential store. The Rust CLI therefore needs
its own vault key, which must remain the same across invocations.

```sh
umask 077
mkdir -p "$HOME/.config/ente-cli-container"
# Run only once; never overwrite an existing file.
(set -C; docker run --rm ghcr.io/kevincfechtel/ente-cli:latest \
  vault key generate > "$HOME/.config/ente-cli-container/vault-key")
export ENTE_CLI_VAULT_KEY="$(cat "$HOME/.config/ente-cli-container/vault-key")"

docker volume create ente-cli-config
docker volume create ente-cli-export

docker run --rm -it \
  --env ENTE_CLI_VAULT_KEY \
  --mount source=ente-cli-config,target=/config \
  ghcr.io/kevincfechtel/ente-cli:latest account login --app photos

docker run --rm \
  --env ENTE_CLI_VAULT_KEY \
  --mount source=ente-cli-config,target=/config \
  --mount source=ente-cli-export,target=/export \
  ghcr.io/kevincfechtel/ente-cli:latest photos export /export --no-input
```

Store and back up the vault key securely, separately from the CLI home.
Without this key, the vault cannot be opened. Users with Docker access
can inspect environment variables.
For bind mounts, the directories must be writable by UID/GID 1000:1000
(alternatively, use `--user UID:GID` and set permissions accordingly).
This image does not include a schedule for recurring photo exports.

More commands: [Accounts](https://ente.com/help/cli/accounts),
[Automation](https://ente.com/help/cli/automation),
[Migration from the Go CLI](https://ente.com/help/cli/migration).

## Build and test locally

The version is intentionally passed explicitly; the Dockerfile does not
resolve `latest`.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/prepare_release.py --repository KevinCFechtel/ente-cli --force
# The detected version is recorded in .release/release.json.
docker build --build-arg ENTE_CLI_VERSION=0.4.5 -t ente-cli:local .
bash scripts/smoke-test.sh ente-cli:local 0.4.5
docker save ente-cli:local -o .release/ente-cli-local.tar
python3 scripts/scan_image.py .release/ente-cli-local.tar security-reports/local
# Additionally, on a Linux amd64 host with Docker, OpenSSL, and qemu-user-static:
python3 scripts/test_no_avx.py ente-cli:local 0.4.5
```

The scripts require Python **3.9+** with no additional Python packages.
Optionally set `GH_TOKEN` for API requests to use GitHub's higher
authenticated rate limit.
Source builds take longer than binary downloads, especially on the first run.
Dependabot checks GitHub Actions versions and Docker base images weekly.

## Licenses and source code

This repository's build files are licensed under [BSD-3-Clause](LICENSE).
The Ente CLI built from unmodified sources is licensed under **AGPL-3.0**;
building it does not change its license. License texts and version-specific
source code links are included in the image at `/usr/share/licenses/ente-cli/`.
Each container release also links to the corresponding
[upstream source code and build workflow](https://github.com/ente/ente).
