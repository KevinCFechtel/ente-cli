#!/usr/bin/env bash
set -euo pipefail

image="${1:?Usage: smoke-test.sh IMAGE VERSION}"
version="${2:?Usage: smoke-test.sh IMAGE VERSION}"

test "$(docker run --rm "$image" --version)" = "ente $version"
docker run --rm "$image" --help > /dev/null
test "$(docker run --rm --entrypoint id "$image" -u)" = "1000"
# Test a real CLI subcommand without credentials, network access or a keyring.
key="$(docker run --rm --network none "$image" vault key generate)"
test -n "$key"
docker run --rm --network none \
    --env "ENTE_CLI_VAULT_KEY=$key" \
    "$image" account list --no-input > /dev/null
