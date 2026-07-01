"""Scenario 8 - data-parallel inference: fan a batch across the swarm.

scatter_gather distributes many prompts across eligible nodes concurrently and
aggregates the results (all | first | concat | vote). This is genuine data
parallelism over the mesh - not model sharding. This demo runs a batch against a
real in-process backend and shows each aggregation mode. Offline.
"""
from _common import rule, stub_backend

from edgemesh.executor import scatter_gather
from edgemesh.protocol import CLASS_C, HardwareProfile, NodeInfo
from edgemesh.swarm import SwarmController


def _node(nid, endpoint):
    return NodeInfo(nid, nid, CLASS_C, endpoint,
                    HardwareProfile(os="L", arch="x", accelerator="cuda",
                                    ram_mb=32000, vram_mb=12000, gpu_name="G"))


def main() -> None:
    rule("SCATTER / GATHER  -  data-parallel inference across the swarm")

    with stub_backend(["llama3.1-8b"]) as url:
        sc = SwarmController()
        sc.register(_node("worker-1", url))
        prompts = ["summarize A", "summarize B", "summarize C"]
        print(f"\nFanning {len(prompts)} prompts across the swarm concurrently...")

        res = scatter_gather(sc, "llama3.1-8b", prompts, aggregate="all")
        print(f"\n[all]    {res['count']} results from nodes {res['nodes_used']}:")
        for r in res["results"]:
            print(f"           '{r['prompt']}' -> {r.get('content', r.get('error'))}")

        first = scatter_gather(sc, "llama3.1-8b", prompts, aggregate="first")
        print(f"\n[first]  {first['result']}")

        concat = scatter_gather(sc, "llama3.1-8b", prompts, aggregate="concat")
        print(f"\n[concat] {concat['result']!r}")

        # a self-consistency style vote over N replicas of one prompt
        vote = scatter_gather(sc, "llama3.1-8b", ["Q?"] * 5, aggregate="vote")
        print(f"\n[vote]   majority answer over 5 replicas -> {vote['result']!r}")

    print("\nOne call, many nodes, four ways to aggregate - map/reduce for inference.")


if __name__ == "__main__":
    main()
