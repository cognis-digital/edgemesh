"""edgemesh CLI.

  Connect
    edgemesh discover [--host H] [--save]   probe local ports, show/register backends
    edgemesh add <name> <base_url> [--save] register a backend manually
    edgemesh fleet [--save]                 register the Cognis fleet (8772-8774, 11434)
  Inspect
    edgemesh models                         aggregated model catalog across the cluster
    edgemesh backends                       list registered backends
    edgemesh hardware                       detect CPU/RAM/GPU and the model-fit budget
    edgemesh catalog [--all] [--uncensored] curated models that fit this machine
  Models
    edgemesh pull <model-id> [--dry-run]    download a catalog model with the right tool
  Cluster & serve
    edgemesh serve [--host H] [--port P]    run the OpenAI-compatible gateway/coordinator
    edgemesh join <coordinator-url>         make THIS device a node of a remote cluster
  Experience
    edgemesh setup                          guided first-run setup wizard
    edgemesh menu                           interactive numbered menu
    edgemesh version                        print version

Config defaults to ~/.edgemesh/config.json (home-resolved; works on any OS).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from edgemesh import (__version__, audit as audit_mod, catalog, hardware, manager, menu,
                      presets, relay, security, wizard)
from edgemesh.auth import KeyStore
from edgemesh.backends import Backend, probe
from edgemesh.cluster import join, local_ip
from edgemesh.gateway import serve
from edgemesh.profile import build_node_info
from edgemesh.protocol import dumps
from edgemesh.registry import DEFAULT_CONFIG, BackendRegistry


def _register_fleet(registry: BackendRegistry) -> list[str]:
    added = []
    for name, url in wizard.COGNIS_FLEET.items():
        models = probe(url, timeout=2.0)
        if models is not None:
            registry.add(Backend(name=name, base_url=url, models=models))
            added.append(name)
    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edgemesh", description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"config path (default: {DEFAULT_CONFIG})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser("discover", help="probe local ports for backends")
    p_disc.add_argument("--host", default="127.0.0.1")
    p_disc.add_argument("--save", action="store_true")

    p_add = sub.add_parser("add", help="register a backend manually")
    p_add.add_argument("name"); p_add.add_argument("base_url")
    p_add.add_argument("--save", action="store_true")

    p_fleet = sub.add_parser("fleet", help="register the Cognis fleet")
    p_fleet.add_argument("--save", action="store_true")

    sub.add_parser("models", help="show aggregated model catalog")
    sub.add_parser("backends", help="list registered backends")
    sub.add_parser("hardware", help="detect hardware + fit budget")
    sub.add_parser("version", help="print version")
    sub.add_parser("setup", help="guided setup wizard")
    sub.add_parser("menu", help="interactive numbered menu")

    p_cat = sub.add_parser("catalog", help="curated models that fit this machine")
    p_cat.add_argument("--all", action="store_true", help="ignore the VRAM fit filter")
    p_cat.add_argument("--no-uncensored", action="store_true", help="hide uncensored models")

    p_pull = sub.add_parser("pull", help="download a catalog model")
    p_pull.add_argument("model_id"); p_pull.add_argument("--dry-run", action="store_true")

    p_serve = sub.add_parser("serve", help="run the gateway / cluster coordinator")
    p_serve.add_argument("--host", default="127.0.0.1"); p_serve.add_argument("--port", type=int, default=8780)
    p_serve.add_argument("--tls", action="store_true", help="require mutual TLS (client certs)")
    p_serve.add_argument("--pki-dir", default=str(Path.home() / ".edgemesh" / "pki"),
                         help="dir holding ca.crt + server.crt/key (see 'edgemesh gen-certs')")
    p_serve.add_argument("--relay-key", default=None,
                         help="run as an onion relay using this private-key file (see 'edgemesh gen-relay-key')")
    p_serve.add_argument("--auth", action="store_true", help="require an API key (see 'edgemesh key add')")
    p_serve.add_argument("--audit", action="store_true", help="write an append-only audit log")

    p_key = sub.add_parser("key", help="manage API keys for --auth")
    p_key.add_argument("action", choices=["add", "list"])
    p_key.add_argument("name", nargs="?", default="default")

    p_rk = sub.add_parser("gen-relay-key", help="generate an onion-relay identity keypair")
    p_rk.add_argument("--out", default=str(Path.home() / ".edgemesh" / "relay.key"))

    p_pki = sub.add_parser("gen-certs", help="generate a self-signed dev PKI (CA + server + client)")
    p_pki.add_argument("--dir", default=str(Path.home() / ".edgemesh" / "pki"))
    p_pki.add_argument("--cn", default="edgemesh")

    p_join = sub.add_parser("join", help="join this device to a remote cluster")
    p_join.add_argument("coordinator_url")
    p_join.add_argument("--name", default=None); p_join.add_argument("--advertise", default=None)

    p_node = sub.add_parser("node", help="join this device to a swarm as a compute node")
    p_node.add_argument("coordinator_url")
    p_node.add_argument("--class", dest="node_class", default="C", choices=["A", "B", "C"])
    p_node.add_argument("--name", default=None)
    p_node.add_argument("--serve-url", default=None,
                        help="this node's reachable OpenAI /v1 base (auto-discovered if omitted)")
    p_node.add_argument("--sharding", action="store_true",
                        help="this node fronts a sharding runtime (exo/Petals/vLLM+Ray) that "
                             "can serve models too big for one machine")
    p_node.add_argument("--preset", choices=presets.keys(), default=None,
                        help="use a sharding-backend preset (implies --sharding; sets --serve-url)")

    sub.add_parser("presets", help="list sharding-backend presets")

    p_swarm = sub.add_parser("swarm", help="show the swarm control plane (nodes + ledger)")
    p_swarm.add_argument("--coordinator", default="http://127.0.0.1:8780")

    p_run = sub.add_parser("run", help="run a distributed job on the swarm")
    p_run.add_argument("prompt")
    p_run.add_argument("--model", required=True)
    p_run.add_argument("--coordinator", default="http://127.0.0.1:8780")
    p_run.add_argument("--consumer", default="cli")

    args = parser.parse_args(argv)
    registry = BackendRegistry.load(args.config)

    if args.command == "discover":
        local = BackendRegistry(); added = local.discover_local(host=args.host)
        for b in local.backends():
            print(f"{b.name}\t{b.base_url}\t{len(b.models)} model(s)")
        if not added:
            print(f"no backends found on {args.host}", file=sys.stderr)
        if args.save and added:
            for b in local.backends():
                registry.add(b)
            registry.save(args.config); print(f"saved {len(added)} backend(s) to {args.config}")
        return 0 if added else 1

    if args.command == "add":
        models = probe(args.base_url) or []
        registry.add(Backend(name=args.name, base_url=args.base_url, models=models))
        print(f"added {args.name} ({args.base_url}) with {len(models)} model(s)")
        if args.save:
            registry.save(args.config); print(f"saved to {args.config}")
        return 0

    if args.command == "fleet":
        added = _register_fleet(registry)
        print(f"registered: {', '.join(added) if added else '(fleet not running)'}")
        if args.save and added:
            registry.save(args.config); print(f"saved to {args.config}")
        return 0 if added else 1

    if args.command == "models":
        cat = registry.model_catalog()
        if not cat:
            print("(no models; run 'edgemesh discover --save', 'edgemesh fleet --save', or 'edgemesh add')")
        for model in sorted(cat):
            print(f"{model}\t{', '.join(cat[model])}")
        return 0

    if args.command == "backends":
        for b in registry.backends():
            print(f"{b.name}\t{b.base_url}\t{len(b.models)} model(s)")
        return 0

    if args.command == "hardware":
        hw = hardware.detect()
        print(json.dumps(hw.to_dict(), indent=2))
        print(f"usable model budget: ~{(hardware.usable_vram_mb(hw) or 0)//1024} GB", file=sys.stderr)
        return 0

    if args.command == "catalog":
        vram = None if args.all else hardware.usable_vram_mb()
        for c in catalog.fit(vram, include_uncensored=not args.no_uncensored):
            u = "[uncensored]" if c.uncensored else ""
            print(f"{c.id}\t~{c.approx_vram_mb//1024}GB\t{c.modality}\t{c.pull}\t{u}")
        return 0

    if args.command == "pull":
        card = catalog.by_id(args.model_id)
        if not card:
            print(f"unknown model id {args.model_id!r}; see 'edgemesh catalog --all'", file=sys.stderr)
            return 1
        ok, msg = manager.pull(card, dry_run=args.dry_run)
        print(msg); return 0 if ok else 1

    if args.command == "version":
        print(__version__); return 0

    if args.command == "setup":  # pragma: no cover - interactive
        return wizard.run(args.config)

    if args.command == "menu":  # pragma: no cover - interactive
        return menu.run(args.config)

    if args.command == "join":
        try:
            resp = join(args.coordinator_url, node_name=args.name, advertise_host=args.advertise)
        except Exception as exc:
            print(f"join failed: {exc}", file=sys.stderr); return 1
        print(f"joined as {resp.get('node')}: added {len(resp.get('added', []))} backend(s); "
              f"cluster catalog now {resp.get('catalog_size')} model(s)")
        return 0

    if args.command == "presets":
        for p in presets.PRESETS.values():
            tag = "multi-machine" if p.multi_machine else "single-node multi-GPU"
            print(f"{p.key:13s} [{tag}]  {p.default_url}")
            print(f"   {p.title}")
            print(f"   start: {p.start_hint}")
            print(f"   docs:  {p.docs_url}")
        print("\nUse:  edgemesh node <coordinator> --preset <key>")
        return 0

    if args.command == "node":
        sharding = args.sharding
        endpoint = args.serve_url
        if args.preset:                       # preset implies sharding + a default /v1
            sharding = True
            endpoint = endpoint or presets.get(args.preset).default_url
        if not endpoint and not sharding:     # auto-discover a local backend to advertise
            local = BackendRegistry(); local.discover_local()
            if local.backends():
                endpoint = (local.backends()[0].base_url
                            .replace("127.0.0.1", local_ip()).replace("localhost", local_ip()))
        info = build_node_info(args.name, args.node_class, endpoint or "", sharding=sharding)
        req = urllib.request.Request(
            args.coordinator_url.rstrip("/") + "/swarm/register",
            data=dumps(info.to_dict()), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                resp = json.loads(r.read())
        except Exception as exc:
            print(f"swarm join failed: {exc}", file=sys.stderr); return 1
        p = info.profile
        kind = (f"sharding node{' (' + args.preset + ')' if args.preset else ''}" if sharding
                else f"{p.accelerator}, {(p.usable_vram_mb() or 0)//1024}GB usable")
        print(f"joined swarm as node {resp.get('node_id')} (class {args.node_class}, {kind}); "
              f"endpoint {endpoint or '(none -> schedule-only)'}; "
              f"swarm size {resp.get('swarm_size')}, reputation {resp.get('reputation')}")
        return 0

    if args.command == "run":
        payload = {"model": args.model, "consumer": args.consumer,
                   "messages": [{"role": "user", "content": args.prompt}]}
        req = urllib.request.Request(args.coordinator.rstrip("/") + "/swarm/run",
                                     data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                res = json.loads(r.read())
        except urllib.error.HTTPError as exc:
            print(f"run failed: {json.loads(exc.read()).get('error')}", file=sys.stderr); return 1
        except Exception as exc:
            print(f"run failed: {exc}", file=sys.stderr); return 1
        if not res.get("ok"):
            print(f"run failed: {res.get('error')}", file=sys.stderr); return 1
        try:
            print(res["result"]["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            print(json.dumps(res.get("result"), indent=2))
        print(f"\n[node {res.get('node_id')} · paid {res.get('paid')} credits]", file=sys.stderr)
        return 0

    if args.command == "swarm":
        base = args.coordinator.rstrip("/")
        try:
            with urllib.request.urlopen(base + "/swarm/nodes", timeout=10) as r:
                nodes = json.loads(r.read()).get("nodes", [])
            with urllib.request.urlopen(base + "/swarm/ledger", timeout=10) as r:
                led = json.loads(r.read())
        except Exception as exc:
            print(f"could not reach coordinator at {base}: {exc}", file=sys.stderr); return 1
        print(f"swarm: {len(nodes)} node(s)")
        for n in nodes:
            p = n.get("profile", {})
            print(f"  {n['node_id']}  class {n['node_class']}  {p.get('accelerator', '?'):4s}  "
                  f"{(p.get('vram_mb') or 0)//1024}GB vram  rep {round(n.get('reputation', 1.0), 2)}")
        if led.get("credits"):
            print(f"credits: {led['credits']}")
        return 0

    if args.command == "gen-certs":
        try:
            paths = security.gen_dev_pki(args.dir, cn=args.cn)
        except Exception as exc:
            print(f"cert generation failed: {exc}", file=sys.stderr); return 1
        print("generated dev PKI:")
        for k, v in paths.items():
            print(f"  {k:12s} {v}")
        print(f"\nserve with mTLS:  edgemesh serve --tls --pki-dir {args.dir}")
        return 0

    if args.command == "gen-relay-key":
        try:
            priv, pub = relay.gen_keypair()
        except relay.RelayUnavailable as exc:
            print(str(exc), file=sys.stderr); return 1
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(priv)
        try:
            os.chmod(args.out, 0o600)
        except OSError:
            pass
        print(f"relay identity written to {args.out}")
        print(f"  relay_id:   {pub[:12]}")
        print(f"  public_key: {pub}")
        print(f"\nrun as a relay:  edgemesh serve --relay-key {args.out}")
        return 0

    if args.command == "key":
        ks = KeyStore.load()
        if args.action == "add":
            plaintext = ks.add(args.name)
            ks.save()
            print(f"created key for '{args.name}':\n  {plaintext}")
            print("  store it now — only the hash is kept, it won't be shown again.")
        else:
            for rec in ks.keys.values():
                print(f"  {rec['name']:20s} scopes={','.join(rec.get('scopes', []))}")
            if not ks.keys:
                print("  (no keys; 'edgemesh key add <name>')")
        return 0

    if args.command == "serve":  # pragma: no cover
        tls = None
        if args.tls:
            d = args.pki_dir
            tls = security.server_context(os.path.join(d, "server.crt"),
                                          os.path.join(d, "server.key"),
                                          os.path.join(d, "ca.crt"))
        relay_priv = None
        if args.relay_key:
            with open(args.relay_key, encoding="utf-8") as fh:
                relay_priv = fh.read().strip()
        keystore = KeyStore.load() if args.auth else None
        audit = audit_mod.AuditLog() if args.audit else None
        serve(registry, host=args.host, port=args.port, tls=tls, relay_priv=relay_priv,
              keystore=keystore, audit=audit); return 0

    return 0  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
