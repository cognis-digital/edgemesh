"""Scenario 15 - trusting the relay list: an Ed25519-signed relay directory.

A hostile directory server could inject relays it controls. edgemesh defends with
a directory authority that signs each relay descriptor; clients ship the
authority's public key and verify every signature before building a circuit. This
demo signs a directory, tampers one entry, and shows the tampered relay dropped.
Needs the optional `cryptography` dep; fails closed and still exits 0 without it.
"""
from _common import rule

from edgemesh import relay


def main() -> None:
    rule("SIGNED RELAY DIRECTORY  -  verify every relay before trusting it")

    if not relay.HAVE_CRYPTO:
        print("\nThe 'cryptography' package is not installed, so the signed directory")
        print("is UNAVAILABLE. It fails closed by design - no unverified fallback.")
        print("Install it with:  pip install edgemesh[relay]")
        return

    from edgemesh import relay_dir

    apriv, apub = relay_dir.gen_authority()
    print(f"\nDirectory authority public key (clients pin this): {apub[:16]}...")

    directory = relay_dir.RelayDirectory(apub)
    for i in range(3):
        _, onion_pub = relay.gen_keypair()
        directory.add({"relay_id": f"relay-{i}",
                       "endpoint": f"http://relay{i}.example:8780",
                       "public_key": onion_pub}, apriv)
    print(f"Authority signed {len(directory.entries)} relay descriptors.")

    verified = directory.verified_relays()
    print(f"\nClient verifies signatures -> {len(verified)} trusted relays:")
    for endpoint, _ in verified:
        print(f"   {endpoint}")

    print("\nNow a hostile server tampers a relay's endpoint AFTER signing:")
    directory.entries[0]["descriptor"]["endpoint"] = "http://attacker.example:8780"
    verified_after = directory.verified_relays()
    print(f"   verified relays after tampering: {len(verified_after)} "
          f"(the forged entry is dropped - its signature no longer matches)")

    print("\nA directory server can list relays, but it cannot forge the authority's")
    print("signature - so it can't slip you a relay it secretly controls.")


if __name__ == "__main__":
    main()
