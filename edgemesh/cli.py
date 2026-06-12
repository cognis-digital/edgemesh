"""edgemesh CLI.

    edgemesh discover [--host H] [--save]   probe local ports, show/register backends
    edgemesh add <name> <base_url> [--save] register a backend manually
    edgemesh models                         show the aggregated model catalog
    edgemesh backends                       list registered backends
    edgemesh serve [--host H] [--port P]    run the OpenAI-compatible gateway

Config defaults to ~/.edgemesh/config.json (home-resolved, so it works from any
directory and on any OS); override with --config.
"""

from __future__ import annotations

import argparse
import sys

from edgemesh.backends import Backend, probe
from edgemesh.gateway import serve
from edgemesh.registry import DEFAULT_CONFIG, BackendRegistry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edgemesh", description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"config path (default: {DEFAULT_CONFIG})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser("discover", help="probe local ports for backends")
    p_disc.add_argument("--host", default="127.0.0.1")
    p_disc.add_argument("--save", action="store_true", help="persist discovered backends to config")

    p_add = sub.add_parser("add", help="register a backend manually")
    p_add.add_argument("name")
    p_add.add_argument("base_url")
    p_add.add_argument("--save", action="store_true")

    sub.add_parser("models", help="show aggregated model catalog")
    sub.add_parser("backends", help="list registered backends")

    p_serve = sub.add_parser("serve", help="run the gateway")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8780)

    args = parser.parse_args(argv)
    registry = BackendRegistry.load(args.config)

    if args.command == "discover":
        registry_local = BackendRegistry()
        added = registry_local.discover_local(host=args.host)
        if not added:
            print(f"no backends found on {args.host}", file=sys.stderr)
        for backend in registry_local.backends():
            print(f"{backend.name}\t{backend.base_url}\t{len(backend.models)} model(s)")
        if args.save:
            for backend in registry_local.backends():
                registry.add(backend)
            registry.save(args.config)
            print(f"saved {len(added)} backend(s) to {args.config}")
        return 0 if added else 1

    if args.command == "add":
        models = probe(args.base_url) or []
        backend = Backend(name=args.name, base_url=args.base_url, models=models)
        registry.add(backend)
        print(f"added {backend.name} ({backend.base_url}) with {len(models)} model(s)")
        if args.save:
            registry.save(args.config)
            print(f"saved to {args.config}")
        return 0

    if args.command == "models":
        catalog = registry.model_catalog()
        if not catalog:
            print("(no models; run 'edgemesh discover --save' or 'edgemesh add')")
        for model in sorted(catalog):
            print(f"{model}\t{', '.join(catalog[model])}")
        return 0

    if args.command == "backends":
        for backend in registry.backends():
            print(f"{backend.name}\t{backend.base_url}\t{len(backend.models)} model(s)")
        return 0

    if args.command == "serve":  # pragma: no cover
        serve(registry, host=args.host, port=args.port)
        return 0

    return 0  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
