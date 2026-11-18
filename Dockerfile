# syntax=docker/dockerfile:1

# Download on the builder's architecture; the binary is selected for the target.
FROM --platform=$BUILDPLATFORM alpine:3.23 AS download
ARG TARGETARCH
ARG ENTE_CLI_VERSION

RUN apk add --no-cache ca-certificates curl
WORKDIR /download
RUN set -eu; \
    echo "$ENTE_CLI_VERSION" | grep -Eq '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'; \
    case "$TARGETARCH" in amd64|arm64) ;; *) exit 1 ;; esac; \
    tag="ente-cli-v${ENTE_CLI_VERSION}"; \
    archive="${tag}-linux-${TARGETARCH}.tar.gz"; \
    url="https://github.com/ente/ente/releases/download/${tag}"; \
    curl --fail --location --retry 3 --output "$archive" "${url}/${archive}"; \
    curl --fail --location --retry 3 --output SHA256SUMS "${url}/SHA256SUMS"; \
    awk -v name="$archive" '$2 == name || $2 == "*" name { print }' SHA256SUMS > selected.sha256; \
    test "$(wc -l < selected.sha256)" -eq 1; \
    sha256sum --check selected.sha256; \
    mkdir -p /out/licenses; \
    tar -xzf "$archive" -C /out ente; \
    chmod 0755 /out/ente; \
    curl --fail --location --retry 3 --output /out/licenses/ente-AGPL-3.0.txt \
      "https://raw.githubusercontent.com/ente/ente/${tag}/LICENSE"; \
    printf 'Unmodified Ente Rust CLI %s\nLicense: AGPL-3.0\nSource: https://github.com/ente/ente/tree/%s\nSource archive: https://github.com/ente/ente/archive/refs/tags/%s.tar.gz\nBuild instructions: .github/workflows/ente-cli-release.yml in the source archive\n' \
      "$ENTE_CLI_VERSION" "$tag" "$tag" > /out/licenses/NOTICE

FROM alpine:3.23
ARG ENTE_CLI_VERSION
LABEL org.opencontainers.image.title="Ente CLI (Rust)" \
      org.opencontainers.image.description="Unofficial container for the unmodified Ente Rust CLI" \
      org.opencontainers.image.version="${ENTE_CLI_VERSION}" \
      org.opencontainers.image.licenses="AGPL-3.0 AND BSD-3-Clause" \
      io.ente.cli.source="https://github.com/ente/ente/tree/ente-cli-v${ENTE_CLI_VERSION}"

RUN apk add --no-cache ca-certificates \
    && addgroup -g 1000 ente \
    && adduser -D -u 1000 -G ente -h /home/ente ente \
    && mkdir -p /config /export \
    && chown ente:ente /config /export \
    && chmod 0700 /config
COPY --from=download /out/ente /usr/local/bin/ente
COPY --from=download /out/licenses/ /usr/share/licenses/ente-cli/
COPY LICENSE /usr/share/licenses/ente-cli/container-BSD-3-Clause.txt

ENV HOME=/home/ente \
    ENTE_CLI_HOME=/config
USER 1000:1000
WORKDIR /export
ENTRYPOINT ["/usr/local/bin/ente"]
CMD ["--help"]
