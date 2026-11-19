# syntax=docker/dockerfile:1

# Build natively for each target. Do not reuse the upstream amd64 binary:
# 0.4.5 executes AVX even during ring's CPU detection (SIGILL on e.g. J4125).
FROM rust:1-alpine3.23 AS build
ARG TARGETARCH
ARG ENTE_CLI_VERSION

RUN apk add --no-cache build-base ca-certificates git linux-headers perl pkgconf
RUN set -eu; \
    echo "$ENTE_CLI_VERSION" | grep -Eq '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'; \
    case "$TARGETARCH" in amd64|arm64) ;; *) exit 1 ;; esac; \
    tag="ente-cli-v${ENTE_CLI_VERSION}"; \
    git clone --depth 1 --filter=blob:none --sparse --branch "$tag" \
      https://github.com/ente/ente.git /src; \
    git -C /src sparse-checkout set rust

WORKDIR /src/rust
RUN set -eu; \
    case "$TARGETARCH" in \
      amd64) \
        export RUSTFLAGS="-C target-cpu=x86-64 -C target-feature=-avx,-avx2,-fma"; \
        export CFLAGS="-march=x86-64 -mtune=generic -mno-avx -mno-avx2 -mno-fma" ;; \
      arm64) \
        export RUSTFLAGS="-C target-cpu=generic --cfg chacha20_force_neon"; \
        export CFLAGS="-march=armv8-a -mno-outline-atomics" ;; \
      *) exit 1 ;; \
    esac; \
    export CXXFLAGS="$CFLAGS"; \
    cargo build --locked --release --jobs 2 -p ente-cli --bin ente \
      --features rusqlite/bundled-sqlcipher-vendored-openssl,keyring/vendored; \
    mkdir -p /out/licenses; \
    cp target/release/ente /out/ente; \
    test "$(/out/ente --version)" = "ente $ENTE_CLI_VERSION"; \
    cp /src/LICENSE /out/licenses/ente-AGPL-3.0.txt; \
    revision="$(git -C /src rev-parse HEAD)"; \
    printf 'Ente Rust CLI %s, built from unmodified source with generic CPU flags\nLicense: AGPL-3.0\nSource: https://github.com/ente/ente/tree/%s\nSource archive: https://github.com/ente/ente/archive/%s.tar.gz\nBuild instructions: Dockerfile in the container source repository (org.opencontainers.image.source label)\n' \
      "$ENTE_CLI_VERSION" "$revision" "$revision" > /out/licenses/NOTICE

FROM alpine:3.23
ARG ENTE_CLI_VERSION
LABEL org.opencontainers.image.title="Ente CLI (Rust)" \
      org.opencontainers.image.description="Unofficial Ente Rust CLI built from source for generic CPUs" \
      org.opencontainers.image.version="${ENTE_CLI_VERSION}" \
      org.opencontainers.image.licenses="AGPL-3.0 AND BSD-3-Clause" \
      io.ente.cli.source="https://github.com/ente/ente/tree/ente-cli-v${ENTE_CLI_VERSION}" \
      io.ente.cli.build="source-generic"

RUN apk add --no-cache ca-certificates \
    && addgroup -g 1000 ente \
    && adduser -D -u 1000 -G ente -h /home/ente ente \
    && mkdir -p /config /export \
    && chown ente:ente /config /export \
    && chmod 0700 /config
COPY --from=build /out/ente /usr/local/bin/ente
COPY --from=build /out/licenses/ /usr/share/licenses/ente-cli/
COPY LICENSE /usr/share/licenses/ente-cli/container-BSD-3-Clause.txt

ENV HOME=/home/ente \
    ENTE_CLI_HOME=/config
USER 1000:1000
WORKDIR /export
ENTRYPOINT ["/usr/local/bin/ente"]
CMD ["--help"]
