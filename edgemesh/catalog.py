"""A curated catalog of popular open-weight models, with the metadata edgemesh
needs to *fit a model to the cluster* and to *toggle censorship*.

This is a reference list (not an endorsement). VRAM figures are rough estimates
for a ~4-bit quant (Q4_K_M-ish) plus KV-cache/runtime headroom; treat them as
"will this plausibly run", not exact. `uncensored=True` flags abliterated /
uncensored community fine-tunes so the menu can filter them in or out.

`pull` is how a backend obtains the model:
  - "ollama:<tag>"  -> `ollama pull <tag>`
  - "hf:<repo>"     -> Hugging Face repo id (download via huggingface-cli / hf)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCard:
    id: str                  # short handle used in the menu/catalog
    family: str
    params_b: float          # billions of parameters
    modality: str            # text | code | vision | embedding | audio
    approx_vram_mb: int      # rough ~4-bit footprint incl. runtime headroom
    pull: str                # "ollama:<tag>" or "hf:<repo>"
    uncensored: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "family": self.family, "params_b": self.params_b,
            "modality": self.modality, "approx_vram_mb": self.approx_vram_mb,
            "pull": self.pull, "uncensored": self.uncensored, "note": self.note,
        }


# Curated, intentionally broad across sizes so fit-to-hardware always has options.
CATALOG: list[ModelCard] = [
    # --- small / edge (runs on CPU or small GPUs) ---
    ModelCard("qwen2.5-0.5b", "Qwen2.5", 0.5, "text", 900, "ollama:qwen2.5:0.5b", note="tiny, edge devices"),
    ModelCard("llama3.2-1b", "Llama 3.2", 1.0, "text", 1500, "ollama:llama3.2:1b"),
    ModelCard("gemma2-2b", "Gemma 2", 2.0, "text", 2600, "ollama:gemma2:2b"),
    ModelCard("phi3.5-mini", "Phi-3.5", 3.8, "text", 3200, "ollama:phi3.5"),
    ModelCard("qwen2.5-3b", "Qwen2.5", 3.0, "text", 3000, "ollama:qwen2.5:3b"),
    # --- mid (8-16 GB GPUs) ---
    ModelCard("llama3.1-8b", "Llama 3.1", 8.0, "text", 6500, "ollama:llama3.1:8b"),
    ModelCard("qwen2.5-7b", "Qwen2.5", 7.0, "text", 5800, "ollama:qwen2.5:7b"),
    ModelCard("mistral-7b", "Mistral", 7.0, "text", 5800, "ollama:mistral"),
    ModelCard("gemma2-9b", "Gemma 2", 9.0, "text", 7200, "ollama:gemma2:9b"),
    ModelCard("qwen2.5-coder-7b", "Qwen2.5-Coder", 7.0, "code", 5800, "ollama:qwen2.5-coder:7b"),
    ModelCard("deepseek-r1-8b", "DeepSeek-R1-Distill", 8.0, "text", 6500, "ollama:deepseek-r1:8b", note="reasoning"),
    ModelCard("llava-7b", "LLaVA", 7.0, "vision", 6200, "ollama:llava:7b"),
    ModelCard("qwen2.5-vl-7b", "Qwen2.5-VL", 7.0, "vision", 6800, "hf:Qwen/Qwen2.5-VL-7B-Instruct"),
    ModelCard("nomic-embed", "Nomic Embed", 0.1, "embedding", 600, "ollama:nomic-embed-text"),
    # --- large (24 GB+) ---
    ModelCard("qwen2.5-32b", "Qwen2.5", 32.0, "text", 22000, "ollama:qwen2.5:32b"),
    ModelCard("qwen2.5-coder-32b", "Qwen2.5-Coder", 32.0, "code", 22000, "ollama:qwen2.5-coder:32b"),
    ModelCard("llama3.3-70b", "Llama 3.3", 70.0, "text", 43000, "ollama:llama3.3:70b"),
    ModelCard("deepseek-r1-32b", "DeepSeek-R1-Distill", 32.0, "text", 22000, "ollama:deepseek-r1:32b", note="reasoning"),
    # --- uncensored / abliterated community fine-tunes (censorship toggle) ---
    ModelCard("dolphin3-8b", "Dolphin 3.0 (Llama 3.1)", 8.0, "text", 6500,
              "ollama:dolphin3", uncensored=True, note="uncensored community fine-tune"),
    ModelCard("qwen3-8b-ablit", "Qwen3-8B-abliterated", 8.0, "text", 6500,
              "hf:huihui-ai/Qwen3-8B-abliterated", uncensored=True, note="abliterated; matches Cognis uncensored slot"),
    ModelCard("llama3.1-8b-ablit", "Llama-3.1-8B-abliterated", 8.0, "text", 6500,
              "hf:mlabonne/Meta-Llama-3.1-8B-Instruct-abliterated", uncensored=True),
    ModelCard("dolphin-mixtral", "Dolphin 2.7 Mixtral", 47.0, "text", 28000,
              "ollama:dolphin-mixtral:8x7b", uncensored=True, note="MoE, needs lots of VRAM/RAM"),
]


def fit(vram_mb: int | None, *, modality: str | None = None,
        include_uncensored: bool = True, headroom: float = 0.90) -> list[ModelCard]:
    """Models that plausibly fit a VRAM budget, largest-first.

    `vram_mb=None` means "unknown" -> return everything (let the user choose).
    `headroom` reserves a fraction of VRAM for the OS / other processes.
    """
    out = []
    budget = int(vram_mb * headroom) if vram_mb else None
    for card in CATALOG:
        if modality and card.modality != modality:
            continue
        if not include_uncensored and card.uncensored:
            continue
        if budget is None or card.approx_vram_mb <= budget:
            out.append(card)
    return sorted(out, key=lambda c: c.approx_vram_mb, reverse=True)


def by_id(model_id: str) -> ModelCard | None:
    return next((c for c in CATALOG if c.id == model_id), None)


def modalities() -> list[str]:
    return sorted({c.modality for c in CATALOG})
