"""Mutual TLS: a client cert signed by the CA is required to reach the gateway."""

from __future__ import annotations

import json
import shutil
import ssl
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from edgemesh.gateway import make_handler
from edgemesh.registry import BackendRegistry
from edgemesh.security import client_context, gen_dev_pki, server_context

pytestmark = pytest.mark.skipif(not shutil.which("openssl"), reason="openssl not installed")


def test_mtls_requires_a_client_cert(tmp_path):
    paths = gen_dev_pki(str(tmp_path))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(BackendRegistry()))
    srv.socket = server_context(paths["server_cert"], paths["server_key"],
                                paths["ca"]).wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "https://127.0.0.1:%d/healthz" % srv.server_address[1]
    try:
        # with a CA-signed client cert -> allowed
        cctx = client_context(paths["client_cert"], paths["client_key"], paths["ca"])
        with urllib.request.urlopen(url, timeout=5, context=cctx) as r:
            assert json.loads(r.read())["status"] == "ok"
        # trusting the CA but presenting NO client cert -> mutual-auth handshake fails
        nocert = ssl.create_default_context(cafile=paths["ca"])
        nocert.check_hostname = False
        with pytest.raises(Exception):
            urllib.request.urlopen(url, timeout=5, context=nocert)
    finally:
        srv.shutdown()
