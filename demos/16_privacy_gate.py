"""Scenario 16 - the privacy engine: data sensitivity picks the trust class.

Before capability or price, the scheduler runs a privacy gate: a job's data
sensitivity sets the minimum node trust class allowed to touch it -
confidential -> Class A only; private -> A/B; public -> any. This demo runs the
same job at all three sensitivities over one heterogeneous swarm and shows the
eligible set shrink. Offline.
"""
from _common import fixture_nodes, rule

from edgemesh.protocol import (DATA_CONFIDENTIAL, DATA_PRIVATE, DATA_PUBLIC, Job)
from edgemesh.scheduler import allowed_classes, eligible


def main() -> None:
    rule("PRIVACY GATE  -  data sensitivity decides who may compute on it")

    nodes = fixture_nodes()
    print("\nSwarm (class -> node):")
    for n in nodes:
        print(f"   class {n.node_class}  {n.name}")

    for data_class in (DATA_PUBLIC, DATA_PRIVATE, DATA_CONFIDENTIAL):
        job = Job.new("llama3.1-8b", data_class=data_class, min_vram_mb=1000)
        allowed = sorted(allowed_classes(data_class))
        elig = eligible(job, nodes)
        print(f"\n{data_class.upper():<13} allows classes {allowed}")
        print(f"   eligible nodes: {[n.name + ' (' + n.node_class + ')' for n in elig]}")

    print("\nA confidential job can NEVER land on a public community node - the gate")
    print("runs first, before fit and price. Privacy is a hard constraint, not a preference.")


if __name__ == "__main__":
    main()
