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
6. publishes those exact tested images as a multi-architecture image on **GHCR**;
7. creates a GitHub release `vX.Y.Z` with the **unmodified upstream release notes**,
   source code links, and the image digest.

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
2. The workflow uses the existing `GITHUB_TOKEN` with `contents: write`
   and `packages: write`. No separate PAT or registry secret is required.
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
