# VRAM and Speed Test Log

Record every run in this format.

```text
GPU:
VRAM:
Precision:
Video duration:
Resolution:
num_inference_steps:
low_vram:
Peak VRAM:
Inference time:
Result:
Notes:
```

## Planned Test Matrix

Record measured runs in this file.

## Known Initial Constraints

- CUDA is currently required because the public ControlFoley inference path has CUDA-only tensor moves.
- `mix` mode for muxing is planned; first release supports replacing original audio.
- MP3 saving is not included in the node to keep dependencies predictable; WAV and FLAC are supported through soundfile.
- Bundled demo workflows use fixed 25-step generation. Lower historical step counts in this log are smoke-test records only; they mainly reduce runtime and should not be treated as a VRAM optimization preset.

## Historical Validation Notes

Historical low-step integration checks are omitted from this public log because they are not representative benchmark results. Current bundled workflows use fixed 25-step generation for normal-quality demos.

Planned benchmark gaps:

- Standard 25-step V2A / TC-V2A / AC-V2A benchmark matrix: planned.
- 12GB GPU: planned, not yet measured.
- 16GB GPU: planned, not yet measured.
- 20GB+ consumer GPU: planned, not yet measured.
- Standard AC-V2A non-fp32 validation after dtype-alignment fix: planned.

Historical 8GB entries below predate the current `staged_offload` implementation and should not be used as recommended settings.

## 2026-07-04 RTX 5060 Laptop 8GB Smoke Test

GPU: NVIDIA GeForce RTX 5060 Laptop GPU
VRAM: 8151 MiB
Precision: fp16 model load path, PyTorch 2.11.0+cu128
Video duration: 2.0 s requested, 2.02 s generated audio
Resolution: source `assets/004.mp4`; ControlFoley public preprocessing defaults
num_inference_steps: 1
low_vram: true; skipped CLAP/MusicGen reference-audio path for V2A; `mask_away_clip=true` (historical, superseded by `staged_offload=true`)
Peak VRAM: 8.72 GiB reported by `torch.cuda.max_memory_allocated()`; nvidia-smi physical VRAM is 8151 MiB, likely includes allocator/accounting differences and shared/WDDM behavior
Inference time: 206.18 s generation; 302.11 s total including load/save
Result: PASS, generated `public-ComfyUI/output/controlfoley/8gb_smoke_v2a_2s_1step.wav`
Notes: The public `demo.py` OOMed on this 8GB GPU because it loads `controlfoley.pth` directly to CUDA in fp32. This historical low_vram V2A path is superseded; current V2A/TC-V2A/AC-V2A workflows should use `low_vram=false` with `staged_offload=true`.

## 2026-07-04 RTX 5060 Laptop 8GB Full Low-VRAM V2A Result

GPU: NVIDIA GeForce RTX 5060 Laptop GPU
VRAM: 8151 MiB
Precision: fp16 model load path, PyTorch 2.11.0+cu128
Video duration: 4.0 s requested, 4.017 s generated audio
Resolution: source `assets/004.mp4`; ControlFoley public preprocessing defaults
num_inference_steps: 4
low_vram: true; V2A-only path; skipped reference-audio modules; `mask_away_clip=true` (historical, superseded by `staged_offload=true`)
Peak VRAM: 9.00 GiB reported by `torch.cuda.max_memory_allocated()`; physical VRAM is 8151 MiB under WDDM/shared-memory accounting
Inference time: 411.48 s generation; 526.94 s total including load/save/mux
Result: PASS, generated:
- `public-ComfyUI/output/controlfoley/8gb_full_v2a_4s_4step_lowvram.wav`
- `public-ComfyUI/output/controlfoley/8gb_full_v2a_4s_4step_lowvram.mp4`
Notes: Historical result. Current V2A/TC-V2A/AC-V2A memory testing should use `low_vram=false` with `staged_offload=true`; 8GB viability still needs fresh benchmark coverage.
