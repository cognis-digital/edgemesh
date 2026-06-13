"""Mutual TLS for the swarm — every node and the control plane prove identity.

Uses only the standard-library `ssl` module for the contexts. Certificate
generation uses the system `openssl` (a dev/self-signed PKI helper) — generating
X.509 certs is out of stdlib scope, so we shell out when openssl is present and
otherwise tell you exactly what to run.

  gen_dev_pki(dir)         -> create ca.crt/ca.key, server.crt/key, client.crt/key
  server_context(...)      -> SSLContext requiring a client cert signed by the CA
  client_context(...)      -> SSLContext presenting a client cert, trusting the CA
"""

from __future__ import annotations

import os
import shutil
import ssl
import subprocess


def server_context(certfile: str, keyfile: str, cafile: str) -> ssl.SSLContext:
    """Server side: present server cert, REQUIRE a client cert signed by `cafile`."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
    ctx.load_verify_locations(cafile=cafile)
    ctx.verify_mode = ssl.CERT_REQUIRED          # mutual auth
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def client_context(certfile: str, keyfile: str, cafile: str,
                   check_hostname: bool = False) -> ssl.SSLContext:
    """Client side: present client cert, trust the CA. (`check_hostname=False`
    is convenient for IP-addressed dev nodes; turn it on with real hostnames.)"""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
    ctx.load_verify_locations(cafile=cafile)
    ctx.check_hostname = check_hostname
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def gen_dev_pki(directory: str, cn: str = "edgemesh", days: int = 825) -> dict:
    """Generate a self-signed dev CA + a server and a client cert via openssl.

    Returns a dict of file paths. Raises RuntimeError with guidance if openssl
    is unavailable. This is for development / a private swarm you control — for
    production, issue certs from your real CA.
    """
    if not shutil.which("openssl"):
        raise RuntimeError(
            "openssl not found. Install it, or issue certs from your own CA. Need: "
            "ca.crt/ca.key, server.crt/server.key (CN/SAN = coordinator host), "
            "client.crt/client.key — all leaf certs signed by ca.crt.")
    os.makedirs(directory, exist_ok=True)
    p = lambda f: os.path.join(directory, f)  # noqa: E731

    # CA
    _run(["openssl", "genrsa", "-out", p("ca.key"), "2048"])
    _run(["openssl", "req", "-x509", "-new", "-nodes", "-key", p("ca.key"),
          "-sha256", "-days", str(days), "-out", p("ca.crt"), "-subj", f"/CN={cn}-ca"])

    # leaf certs (server + client), each signed by the CA
    for role in ("server", "client"):
        _run(["openssl", "genrsa", "-out", p(f"{role}.key"), "2048"])
        _run(["openssl", "req", "-new", "-key", p(f"{role}.key"),
              "-out", p(f"{role}.csr"), "-subj", f"/CN={cn}-{role}"])
        _run(["openssl", "x509", "-req", "-in", p(f"{role}.csr"),
              "-CA", p("ca.crt"), "-CAkey", p("ca.key"), "-CAcreateserial",
              "-out", p(f"{role}.crt"), "-days", str(days), "-sha256"])
        if os.path.exists(p(f"{role}.csr")):
            os.remove(p(f"{role}.csr"))

    return {"ca": p("ca.crt"), "server_cert": p("server.crt"), "server_key": p("server.key"),
            "client_cert": p("client.crt"), "client_key": p("client.key")}
