# Known Issues

This alpha release focuses on ComfyUI integration and reproducible inference. It does not modify the ControlFoley model architecture and does not retrain any model.

## TTA Status

- TTA has passed a short alpha smoke test and generated a valid WAV file.
- Longer TTA clips and full 25-step quality-oriented settings still need more validation.
- Treat TTA as alpha-supported, not production-stable.

## Memory Status

- `staged_offload=true` is the supported memory-saving path for V2A, TV2A, TC-V2A, and AC-V2A.
- `low_vram=true` is text-only T2A/TTA mode; video and reference-audio workflows should keep `low_vram=false`.

## Weights and Downloads

- Missing ControlFoley weights are downloaded from Hugging Face during user-triggered `ControlFoley Model Loader` execution, or by `ControlFoley Dependencies Loader` when `auto_download=true`.
- The node does not download weights during import or startup.
- The expected weight layout and default download directory order are documented in `README.md`.

## Video Muxing

- `ControlFoley Video-Audio Muxer` currently supports replacing the source video's original audio track.
- Mixing generated audio with original audio is planned for a later release.

## Standard Fixed-Step Validation

- The alpha release includes verified smoke and short validation runs, but not a full consumer-GPU support matrix.
- Bundled workflows use fixed 25-step generation.
- A full V2A / TC-V2A / AC-V2A 25-step benchmark matrix is planned.
- Do not infer full benchmark performance or quality from the smoke-test records.

## Runtime Constraints

- CUDA is currently required by the integrated public ControlFoley inference path.
- CPU/MPS inference is not supported by this node's integrated public inference path in this alpha release.
- ComfyUI output media, local caches, and model weights should not be committed to this repository.
