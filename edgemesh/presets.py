"""Sharding-backend presets - one-command setup for "a model too big for one box".

A *sharding backend* is a runtime that splits one model across several machines and
exposes an OpenAI-compatible `/v1`. edgemesh doesn't do the tensor split itself; it
registers such a backend as a `--sharding` node and routes oversized models to it.

Each preset captures: a human title, the default `/v1` URL the runtime listens on,
a start hint (the canonical command to stand it up - verify against upstream docs),
whether it genuinely spans *multiple machines* (vs single-node multi-GPU), and a
docs URL. `edgemesh node --preset <key>` fills in `--serve-url` and `--sharding`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShardingPreset:
    key: str
    title: str
    default_url: str        # OpenAI /v1 base the runtime serves
    multi_machine: bool     # True = shards across machines; False = single-node multi-GPU
    start_hint: str
    docs_url: str

    def to_dict(self) -> dict:
        return {"key": self.key, "title": self.title, "default_url": self.default_url,
                "multi_machine": self.multi_machine, "start_hint": self.start_hint,
                "docs_url": self.docs_url}


PRESETS: dict[str, ShardingPreset] = {p.key: p for p in [
    ShardingPreset(
        "exo", "exo - cluster everyday devices (MLX/CUDA/ROCm)",
        "http://127.0.0.1:52415/v1", True,
        "git clone https://github.com/exo-explore/exo && cd exo && uv run exo",
        "https://github.com/exo-explore/exo"),
    ShardingPreset(
        "vllm-ray", "vLLM + Ray - tensor + pipeline parallel across nodes",
        "http://127.0.0.1:8000/v1", True,
        "ray start --head  # on workers: ray start --address=<head>:6379 ; "
        "then: vllm serve <model> --tensor-parallel-size N --pipeline-parallel-size M",
        "https://docs.vllm.ai/en/stable/serving/distributed_serving.html"),
    ShardingPreset(
        "petals", "Petals - BitTorrent-style swarm for very large models",
        "http://127.0.0.1:8000/v1", True,
        "pip install petals && python -m petals.cli.run_server <model>  "
        "(needs an OpenAI /v1 adapter in front)",
        "https://petals.dev/"),
    ShardingPreset(
        "llamacpp-rpc", "llama.cpp RPC - split a GGUF across machines",
        "http://127.0.0.1:8080/v1", True,
        "on workers: rpc-server -p 50052 ; on host: "
        "llama-server -m model.gguf --rpc worker1:50052,worker2:50052 -ngl 99",
        "https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md"),
    ShardingPreset(
        "gpustack", "GPUStack - manages a heterogeneous GPU cluster",
        "http://127.0.0.1/v1-openai", True,
        "curl -sfL https://get.gpustack.ai | sh -s -  (add workers via the UI/token)",
        "https://docs.gpustack.ai/"),
    ShardingPreset(
        "ray-serve", "Ray Serve LLM - distributed, autoscaling serving",
        "http://127.0.0.1:8000/v1", True,
        "pip install 'ray[serve,llm]' ; serve run <your_llm_app>",
        "https://docs.ray.io/en/latest/serve/llm/index.html"),
    ShardingPreset(
        "sglang-dist", "SGLang - distributed tensor/pipeline parallel",
        "http://127.0.0.1:30000/v1", True,
        "sglang serve --model-path <model> --tp N --pp M --port 30000",
        "https://docs.sglang.ai/"),
    ShardingPreset(
        "tgi", "Hugging Face TGI - multi-GPU sharding (single node)",
        "http://127.0.0.1:8080/v1", False,
        "docker run --gpus all -p 8080:80 ghcr.io/huggingface/text-generation-inference "
        "--model-id <model> --num-shard N",
        "https://github.com/huggingface/text-generation-inference"),
    ShardingPreset(
        "nim", "NVIDIA NIM - multi-GPU per-model microservice (single node)",
        "http://127.0.0.1:8000/v1", False,
        "docker run --gpus all -e NGC_API_KEY=... -p 8000:8000 nvcr.io/nim/<model>:<tag>",
        "https://docs.nvidia.com/nim/"),
]}


def get(key: str) -> ShardingPreset | None:
    return PRESETS.get(key)


def keys() -> list[str]:
    return list(PRESETS)
