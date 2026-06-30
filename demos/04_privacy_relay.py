"""Scenario 4 - privacy-conscious users: onion-style relaying, honestly framed.

A request can travel through a circuit of volunteer relays so no single relay
learns both who asked and which node answered. Each relay peels exactly one
encryption layer (X25519 sealed box + AES-GCM) and sees only the next hop. This
demo builds a 3-hop onion locally and peels it layer by layer, proving each hop
learns only what it must.

The relay needs the optional `cryptography` package (`pip install edgemesh[relay]`).
It FAILS CLOSED when missing - it never falls back to a fake/insecure scheme - so
this demo reports that honestly and still exits 0.
"""
import json

from _common import rule

from edgemesh import relay


def main() -> None:
    rule("PRIVACY RELAY  -  onion circuit: each hop sees only the next hop")

    if not relay.HAVE_CRYPTO:
        print("\nThe 'cryptography' package is not installed, so the relay is")
        print("UNAVAILABLE. It fails closed by design - no fake encryption fallback.")
        print("Install it with:  pip install edgemesh[relay]")
        print("\n(Skipping the live circuit; this is the honest, safe behavior.)")
        return

    # Three volunteer relays, each with its own identity keypair.
    relays = []
    for i in range(3):
        priv, pub = relay.gen_keypair()
        relays.append({"endpoint": f"http://relay{i + 1}.example:9{i}00",
                       "priv": priv, "pub": pub})
    circuit = [(r["endpoint"], r["pub"]) for r in relays]
    deliver_to = "http://compute-node.example:8000"

    print("\nGuard selection (stable, deterministic by key - the Tor lesson):")
    guards = relay.select_guards(circuit, n=2)
    print(f"   pinned guards: {[e for e, _ in guards]}")

    payload = {"model": "llama3.1-8b",
               "messages": [{"role": "user", "content": "(secret prompt)"}]}
    onion = relay.build_onion(circuit, deliver_to, payload)
    print(f"\nBuilt a 3-layer onion ({len(onion)} b64 chars). Entry relay receives this blob.")
    print("Padded to fixed buckets, so a relay can't infer its position from size.\n")

    # Peel it hop by hop, the way each relay would.
    blob = onion
    for i, r in enumerate(relays):
        layer = json.loads(relay.unpad(relay.unseal(r["priv"], blob)))
        if "next" in layer:
            print(f"   relay {i + 1} ({r['endpoint']}) peels -> next hop is {layer['next']}")
            print("              (learns ONLY the next hop; not the origin, not the payload)")
            blob = layer["blob"]
        else:
            print(f"   relay {i + 1} (EXIT) peels -> deliver to {layer['deliver']}")
            print(f"              payload model: {layer['payload']['model']}")
            print("              (learns the destination + request, but not who originated it)")

    print("\nNo single relay sees both endpoints. This raises the bar; it is NOT")
    print("Tor-grade anonymity (no mixing / global-adversary resistance) - and we say so.")


if __name__ == "__main__":
    main()
