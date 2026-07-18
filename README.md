# comfyui-controlfoley

<p>
  <a href="https://github.com/YJX-Research/comfyui-controlfoley-official"><img alt="ComfyUI custom node" src="https://img.shields.io/badge/ComfyUI-custom%20node-111111"></a>
  <a href="https://github.com/xiaomi-research/controlfoley"><img alt="ControlFoley" src="https://img.shields.io/badge/ControlFoley-official%20integration-2f80ed"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776ab">
  <img alt="License" src="https://img.shields.io/badge/code%20license-Apache--2.0-green">
  <img alt="Weights license" src="https://img.shields.io/badge/weights-CC%20BY--NC%204.0-orange">
</p>

Official ComfyUI custom nodes and full-task workflows for [ControlFoley](https://github.com/xiaomi-research/controlfoley), Xiaomi Research's video-to-audio and controllable Foley generation project.

- Run V2A, TV2A, TC-V2A, AC-V2A, and T2A workflows directly in ComfyUI.
- Load the public ControlFoley source tree and download missing Hugging Face weights on demand.
- Save generated audio as WAV/FLAC and mux generated audio back into video.
- Use bundled workflow templates and release-reviewed demo media for quick inspection.

This repository is a ComfyUI integration layer. It does not modify the ControlFoley model architecture, retrain models, or include ControlFoley model weights.

If this node helps your workflow, please consider giving a star &#11088; to this repository and the original [ControlFoley](https://github.com/xiaomi-research/controlfoley) repository.

## Features

- Load the public ControlFoley source tree and Hugging Face weights from local paths, with missing weights downloaded on demand.
- Generate Foley audio from video input, text prompts, or reference audio conditioning.
- Use either a simple one-node generator or an advanced reusable chain for preloading, dependency download, Torch compile, and generation.
- Save generated audio as WAV or FLAC.
- Mux generated audio back into the source video as MP4 using replace-original-audio mode.
- Support `fp16`, `bf16`, and `fp32` model loading options.
- Support fixed seeds, custom duration, inference steps, CFG scale, CLIP masking, staged encoder offload, encoder frame-batch multipliers, and video feature caching.
- Expose optional encoder compilation, a `low_vram` T2A/TTA path, and an unload node for memory-constrained runs.

## Installation

Clone this custom node into `ComfyUI/custom_nodes`:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/YJX-Research/comfyui-controlfoley-official.git comfyui-controlfoley
cd comfyui-controlfoley
pip install -r requirements.txt
```

This repository is published at `YJX-Research/comfyui-controlfoley-official`; the local custom-node folder can still be named `comfyui-controlfoley`.

`requirements.txt` does not install `torch`, `torchaudio`, or `torchvision`; use the versions from your ComfyUI/PyTorch CUDA environment.

Clone the public ControlFoley repository separately:

```bash
git clone https://github.com/xiaomi-research/controlfoley /path/to/controlfoley
```

Start ComfyUI after installing the node:

```bash
cd /path/to/ComfyUI
python main.py --listen 0.0.0.0 --port 8188
```

## Quick Start

1. Install ComfyUI.
2. Clone this custom node into `ComfyUI/custom_nodes`.
3. Install requirements with `pip install -r requirements.txt`; keep the existing ComfyUI PyTorch stack.
4. Clone the public ControlFoley repository.
5. Start ComfyUI.
6. Load a workflow from `examples/workflows`.
7. Set `controlfoley_source_dir`; leave `model_weights_dir` as `path/to/model_weights` to use the default download directory, or set a custom local path.
8. Place input videos and reference audio in `ComfyUI/input`, or edit the workflow paths.
9. Run the workflow and check `ComfyUI/output/controlfoley`.

## ControlFoley Weights

This repository does not include ControlFoley model weights. During `ControlFoley Model Loader` or `ControlFoley Dependencies Loader`, missing weights are downloaded from Hugging Face into the configured `model_weights_dir`.

If `model_weights_dir` is empty or left as `path/to/model_weights`, the node uses `CONTROLFOLEY_WEIGHTS_DIR` when set, then an existing packaged `controlfoley_workspace/model_weights`, then `ComfyUI/models/controlfoley`. The node registers `ComfyUI/models/controlfoley` with ComfyUI's model folder system under the `controlfoley` key.

You can still pre-download the public model release manually:

```bash
pip install huggingface-hub
huggingface-cli download YJX-Xiaomi/ControlFoley \
  --resume-download \
  --local-dir /path/to/model_weights \
  --local-dir-use-symlinks False
```

Expected layout:

```text
model_weights/
  weights/controlfoley.pth
  ext_weights/v1-44.pth
  ext_weights/synchformer_state_dict.pth
  ext_weights/cav_mae_st.pth
  ext_weights/music_speech_audioset_epoch_15_esc_89.98.pt
```

The node also prefetches Hugging Face model dependencies used by the public ControlFoley runtime, including CLIP, BigVGAN, and the reference-audio models used outside `low_vram` mode. Download repository IDs are centralized in `model_urls.py` so mirrors or future model releases can be updated without changing node logic.

`controlfoley_source_dir` should point to the cloned ControlFoley repository. `model_weights_dir` can point to an existing local weight directory or to a writable directory for automatic downloads.

## Folder Structure

```text
comfyui-controlfoley/
  __init__.py
  model_urls.py
  nodes.py
  requirements.txt
  pyproject.toml
  README.md
  LICENSE
  docs/
    known_issues.md
    vram_speed_log.md
  examples/
    inputs/README.md
    generated/README.md
    workflows/
      01_v2a_basic.json
      02_tcv2a_text_controlled.json
      03_acv2a_audio_controlled.json
      04_tv2a_text_video.json
      05_t2a_basic.json
      06_advanced_chain.json
      07_simple_generate.json
```

Do not commit ControlFoley weights, Hugging Face caches, ComfyUI outputs, or local runtime files.

## Available Nodes

- **ControlFoley Simple Generate**: one-node path for loading the model and generating audio in the same node.
- **ControlFoley Dependencies Loader**: validates the public ControlFoley source tree, downloads missing ControlFoley weights, and prefetches known Hugging Face dependencies.
- **ControlFoley Model Loader**: loads ControlFoley and related encoders from local source and weight directories, optionally using the dependency-loader output.
- **ControlFoley Torch Compile**: optional advanced node for compiling feature encoders and, if requested, the generator module.
- **ControlFoley Video Loader**: resolves a video path from ComfyUI `input` or an absolute path.
- **ControlFoley Generate**: runs V2A, TV2A, TC-V2A, AC-V2A, or T2A/TTA depending on connected inputs and parameters. It accepts the `ControlFoley Video Loader` output, native ComfyUI `VIDEO`, or native ComfyUI `IMAGE` batches.
- **ControlFoley Advanced Generate**: same generation path with `enabled`, `silent_audio_on_error`, and a status output for complex workflows.
- **ControlFoley Save Audio**: writes generated audio to `ComfyUI/output` as WAV or FLAC.
- **ControlFoley Video-Audio Muxer**: writes an MP4 with generated audio replacing the original audio track.
- **ControlFoley Model Unloader**: releases cached model objects and clears CUDA cache.

## Demo Workflows

Workflow templates are in `examples/workflows`:

| File | Task | Outputs |
| --- | --- | --- |
| `01_v2a_basic.json` | Video-to-audio | WAV + MP4 |
| `02_tcv2a_text_controlled.json` | TC-V2A text-controlled video-to-audio | WAV + MP4 |
| `03_acv2a_audio_controlled.json` | AC-V2A audio-controlled video-to-audio | WAV + MP4 |
| `04_tv2a_text_video.json` | TV2A text + video to audio | WAV + MP4 |
| `05_t2a_basic.json` | Text-to-audio | WAV |
| `06_advanced_chain.json` | Advanced generation chain | WAV |
| `07_simple_generate.json` | Simple one-node T2A generation | WAV |

Before running any workflow, edit these placeholders:

- `path/to/controlfoley`: local clone of the public ControlFoley repository.
- `path/to/model_weights`: keep this placeholder to use the default automatic download directory, or replace it with a custom writable local weight directory.

Mode mapping:

- **V2A**: connect video, leave prompt and reference audio empty.
- **TV2A / TC-V2A**: connect video and provide a text prompt. `TV2A` and `TC-V2A` use the same node path; the examples keep both names for clarity.
- **AC-V2A**: connect video and provide `reference_audio_path`.
- **T2A / TTA**: no video input, text prompt only. `TTA` is the legacy naming used in earlier docs.

Duration behavior:

- Text-only workflows use `10s` by default.
- Video workflows follow the input video duration and cap generation at `30s` for long videos.
- The `duration` field is treated as an upper limit for video workflows, not a forced output length when the input video is shorter.

Native ComfyUI inputs:

- `video`: existing `CONTROLFOLEY_VIDEO` output from `ControlFoley Video Loader`.
- `video_input`: native ComfyUI `VIDEO` object from video loader / video creation nodes.
- `images`: native ComfyUI `IMAGE` batch. When connected, `image_fps` is used to encode a temporary MP4 before ControlFoley preprocessing.
- Connect only one of `video`, `video_input`, or `images` for each generation. Temporary IMAGE/VIDEO files are written under `ComfyUI/output/controlfoley/temp`.

For workflows with video input, keep both output nodes enabled: standalone `.wav` and muxed `.mp4`.

## Generated Examples

Selected generated samples are stored in `examples/generated`. Each workflow has one representative output folder with the original input files needed for comparison and the generated result files.

Actual demo media durations are listed in each `examples/generated/*/README.txt` file.

Only publish example media that has passed the repository owner's release review. Keep source attribution, usage permissions, and any required media notices with the example files.

See `examples/generated/README.md` for demo media credits.

## Input Media

The workflow templates expect demo input media under `ComfyUI/input/assets`. To run the bundled examples, copy the approved demo inputs from `examples/generated` into `ComfyUI/input/assets` using the names below, or edit the workflow paths.

Suggested demo input mapping:

```text
examples/generated/01_v2a_basic/original_video.mp4 -> ComfyUI/input/assets/v2a_video.mp4
examples/generated/02_tcv2a_text_controlled/original_video.mp4 -> ComfyUI/input/assets/tcv2a_video.mp4
examples/generated/03_acv2a_audio_controlled/original_video.mp4 -> ComfyUI/input/assets/acv2a_video.mp4
examples/generated/03_acv2a_audio_controlled/original_reference_audio.wav -> ComfyUI/input/assets/acv2a_reference.wav
examples/generated/04_tv2a_text_video/original_video.mp4 -> ComfyUI/input/assets/tv2a_video.mp4
```

Reference audio for AC-V2A should be 2-4 seconds. Longer audio is truncated and shorter audio is padded by the node.

## Outputs

ComfyUI writes outputs under `ComfyUI/output`. With the default prefixes, files are written to:

```text
ComfyUI/output/controlfoley/
```

Default workflow outputs:

- `01_v2a_basic.wav` and `01_v2a_basic.mp4`
- `02_tcv2a_text_controlled.wav` and `02_tcv2a_text_controlled.mp4`
- `03_acv2a_audio_controlled.wav` and `03_acv2a_audio_controlled.mp4`
- `04_tv2a_text_video.wav` and `04_tv2a_text_video.mp4`
- `05_t2a_basic.wav`
- `06_advanced_chain.wav`
- `07_simple_generate.wav`

## Low VRAM Mode

The alpha release only applies engineering-side memory options. It does not change model structure.

Implemented options:

- `torch.inference_mode()` during generation.
- `fp16`, `bf16`, and `fp32` precision selection.
- Fixed batch size 1.
- Optional video feature caching.
- Optional CLIP masking through `mask_away_clip`.
- `clip_batch_size_multiplier` and `sync_batch_size_multiplier` tune feature-extractor frame batches for VRAM/performance tradeoffs.
- `staged_offload` moves encoders to CPU during DiT sampling and restores them for decode/vocode.
- Optional `compile_encoders` for users who want to pay one-time `torch.compile` cost.
- `low_vram` path for text-only T2A/TTA runs.
- `ControlFoley Model Unloader` node.
- CUDA cache cleanup after low-VRAM generation.
- Fixed 25-step generation in the bundled workflows.

For V2A, TV2A, TC-V2A, and AC-V2A memory reduction, keep `low_vram=false` and use `staged_offload=true`. `low_vram=true` remains a text-only T2A/TTA path.

## VRAM and Speed Benchmark

See `docs/vram_speed_log.md` for recorded runs.

Cold-start behavior:

- First load can take several minutes because ControlFoley weights and Hugging Face dependencies are downloaded and cached.
- Later loads reuse local weights and the HF cache; startup time is then dominated by model construction and GPU transfer.
- `compile_encoders=true` adds extra one-time compile latency and should be left off for first-run smoke tests.

Memory guidance:

- Use a CUDA GPU; CPU/MPS execution is not supported by this node's integrated public inference path.
- Use `staged_offload=true` to reduce memory pressure in V2A, TV2A, TC-V2A, and AC-V2A workflows.
- Lower `clip_batch_size_multiplier` and `sync_batch_size_multiplier` only when feature extraction peaks too high; this trades speed for memory during encoder feature extraction.
- `low_vram=true` is intended for text-only T2A/TTA; keep it `false` for V2A, TV2A, TC-V2A, and AC-V2A.
- Keep `num_inference_steps=25` for normal output quality. Lower step counts mainly reduce runtime, not peak VRAM, and are only useful for quick internal smoke checks.

## Known Issues

See `docs/known_issues.md`.

Important alpha limitations:

- Use `staged_offload=true` for video/reference-audio workflows on smaller GPUs.
- Missing weights and known Hugging Face dependency models are downloaded during model loading.
- `ControlFoley Video-Audio Muxer` currently supports replace-original-audio mode only; mix mode is planned.
- The public ControlFoley inference path is CUDA-only in this node.

## License

- ComfyUI custom node code: Apache 2.0.
- Original ControlFoley code: Apache 2.0.
- ControlFoley model weights: CC BY-NC 4.0.
- ControlFoley model weights are for non-commercial use only.

The custom node code is Apache 2.0, but the model weights are CC BY-NC 4.0 and are restricted to non-commercial use.

Review the ControlFoley repository and Hugging Face model card before use.
