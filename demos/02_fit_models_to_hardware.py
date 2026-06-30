"""Scenario 2 - solo devs & hobbyists: which models will actually run here?

"I have an 8 GB card / a 16 GB laptop / a 64 GB Mac - what can I run?" edgemesh
turns a VRAM budget into a shortlist from a curated catalog, biggest-first, and
can filter by modality or hide uncensored fine-tunes. This demo also detects the
machine it runs on (best-effort, no deps) so you see the real budget too.
"""
from _common import rule

from edgemesh import catalog, hardware


def show_fit(label: str, vram_mb: int | None, **kw) -> None:
    cards = catalog.fit(vram_mb, **kw)
    budget = f"{vram_mb} MB" if vram_mb else "unknown (show all)"
    print(f"\n{label}  (budget {budget}) -> {len(cards)} model(s):")
    for c in cards[:6]:
        flag = "  [uncensored]" if c.uncensored else ""
        print(f"   {c.approx_vram_mb:>6} MB  {c.id:<22} {c.modality:<9} {c.family}{flag}")
    if len(cards) > 6:
        print(f"   ... and {len(cards) - 6} more")


def main() -> None:
    rule("FIT MODELS TO HARDWARE  -  what will actually run on this box")

    show_fit("8 GB consumer GPU", 8000)
    show_fit("16 GB laptop", 16000)
    show_fit("64 GB Apple unified (M-series)", int(64000 * 0.70))

    show_fit("16 GB GPU, code models only", 16000, modality="code")
    show_fit("16 GB GPU, hide uncensored fine-tunes", 16000, include_uncensored=False)

    print("\n--- This machine (best-effort detection, no third-party deps) ---")
    hw = hardware.detect()
    print(f"   os={hw.os} arch={hw.arch} cpu={hw.cpu_count} ram_mb={hw.ram_mb} "
          f"gpus={[g.name for g in hw.gpus] or 'none detected'}")
    budget = hardware.usable_vram_mb(hw)
    show_fit("recommended for THIS machine", budget)

    print("\nPick one, then `edgemesh pull <id>` fetches it via Ollama or Hugging Face.")


if __name__ == "__main__":
    main()
