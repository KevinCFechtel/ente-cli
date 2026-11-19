#!/usr/bin/env python3
"""Exercise the actual TLS stack under QEMU's AVX-less Nehalem CPU (Linux host)."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ssl
import subprocess
import tempfile
from threading import Thread


def check_tls_result(result):
    # The local self-signed certificate is intentionally untrusted. Reaching
    # certificate verification proves more than --version or a refused TCP port:
    # ring's CPU detection and TLS cryptography have actually run without AVX.
    error = result.stderr.lower()
    certificate_errors = (
        "unknownissuer",
        "unknown issuer",
        "invalid peer certificate",
        "self-signed certificate",
        "self signed certificate",
        "certificate verify failed",
    )
    if result.returncode != 1 or not any(text in error for text in certificate_errors):
        raise RuntimeError(
            f"Expected a TLS certificate error (exit 1), got exit {result.returncode}:\n"
            f"{result.stdout}{result.stderr}"
        )


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # No real Ente endpoint, credentials or OTP delivery is involved.
        self.send_error(503)

    def log_message(self, *_args):
        pass


def test_image(image, version, qemu):
    command = [
        "docker", "run", "--rm", "--network", "host",
        "--mount", f"type=bind,source={qemu},target=/qemu-x86_64,readonly",
        "--entrypoint", "/qemu-x86_64", image,
        "-cpu", "Nehalem", "/usr/local/bin/ente",
    ]
    result = subprocess.run(
        command + ["--version"], check=True, capture_output=True, text=True, timeout=60
    )
    if result.stdout.strip() != f"ente {version}":
        raise RuntimeError(f"Unexpected version under QEMU: {result.stdout}")

    with tempfile.TemporaryDirectory(prefix="ente-no-avx-") as directory:
        cert = str(Path(directory) / "cert.pem")
        key = str(Path(directory) / "key.pem")
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", key, "-out", cert, "-days", "1", "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ], check=True, capture_output=True, timeout=30)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = subprocess.run(command + [
                    "account", "request-otp", "--app", "photos",
                    "--email", "cpu-test@example.invalid", "--purpose", "login",
                    "--host", f"https://127.0.0.1:{server.server_port}", "--no-input",
                ], capture_output=True, text=True, timeout=90)
                check_tls_result(result)
            finally:
                server.shutdown()
                thread.join()
    print("PASS: TLS certificate verification reached on Nehalem without AVX.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("version")
    parser.add_argument("--qemu", type=Path, default=Path("/usr/bin/qemu-x86_64-static"))
    args = parser.parse_args()
    test_image(args.image, args.version, args.qemu.resolve(strict=True))


if __name__ == "__main__":
    main()
