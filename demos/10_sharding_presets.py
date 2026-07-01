"""Scenario 10 - the too-big-for-one-box model: sharding presets + routing.

edgemesh doesn't split a model across machines itself; it registers a
sharding-capable runtime (exo, vLLM+Ray, Petals, llama.cpp RPC, ...) as a
`--sharding` node and routes oversized jobs to it. This demo lists the presets,
then shows the scheduler exempting a sharding node from the single-node VRAM
filter so a 70B job that fits nowhere still lands. Offline.
"""
from _common import rule

from edgemesh import presets
from edgemesh.protocol import CLASS_C, HardwareProfile, Job, NodeInfo
from edgemesh.scheduler import eligible


def _node(nid, vram, sharding=False):
    return NodeInfo(nid, nid, CLASS_C, f"http://{nid}",
                    HardwareProfile(os="L", arch="x", accelerator="cuda",
                                    ram_mb=32000, vram_mb=vram, gpu_name="G"),
                    sharding=sharding)


def main() -> None:
    rule("SHARDING PRESETS  -  route a model too big for any single node")

    print("\nOne-command sharding-backend presets (`edgemesh node --preset <key>`):")
    for key in presets.keys():
        p = presets.get(key)
        span = "multi-machine" if p.multi_machine else "single-node multi-GPU"
        print(f"   {key:<14} {span:<22} {p.default_url}")

    print("\nScheduling a 70B job (needs ~43000 MB) across a mixed swarm:")
    nodes = [_node("gpu-8gb", 8000), _node("gpu-24gb", 24000),
             _node("exo-cluster", None, sharding=True)]
    job = Job.new("llama3.3-70b", min_vram_mb=43000)
    elig = eligible(job, nodes)
    print(f"   eligible nodes: {[n.node_id for n in elig]}")
    print("   (both single GPUs are filtered out; the exo sharding node is EXEMPT")
    print("    from the per-node VRAM check because it spans machines)")

    print(f"\nStart hint for 'exo':\n   {presets.get('exo').start_hint}")
    print("\nedgemesh routes; the sharding runtime does the tensor split. Clear division of labor.")


if __name__ == "__main__":
    main()
