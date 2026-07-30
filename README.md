# comfyui-controlfoley

<p>
  <a href="https://registry.comfy.org/publishers/yjx-research/nodes/ComfyUI-ControlFoley"><img alt="Comfy Registry" src="https://img.shields.io/badge/Comfy%20Registry-ControlFoley%20Official-blue"></a>
  <a href="https://github.com/YJX-Research/comfyui-controlfoley-official"><img alt="GitHub source" src="https://img.shields.io/badge/GitHub-source-111111"></a>
  <a href="https://github.com/xiaomi-research/controlfoley"><img alt="ControlFoley" src="https://img.shields.io/badge/ControlFoley-official%20integration-2f80ed"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776ab">
  <img alt="License" src="https://img.shields.io/badge/code%20license-Apache--2.0-green">
  <img alt="Weights license" src="https://img.shields.io/badge/weights-CC%20BY--NC%204.0-orange">
</p>

Official ComfyUI custom nodes and full-task workflows for [ControlFoley](https://github.com/xiaomi-research/controlfoley), Xiaomi Research's controllable video-to-audio generation project.

- Generate sound effects / Foley audio that follows the visual content of a video, with optional control from text prompts or reference audio.
- Run video-to-audio (V2A), text-to-audio (T2A), text-guided video-to-audio (TV2A/TC-V2A), and reference-audio-guided video-to-audio (AC-V2A) workflows directly in ComfyUI.
- Auto-fetch the public ControlFoley source tree (pinned revision) and download missing Hugging Face weights on demand.
- Save generated audio as WAV/FLAC and mux generated audio back into video.
- Use bundled workflow templates and release-reviewed demo media for quick inspection.

> ⭐ If this ComfyUI node is useful for your workflow, please consider starring both this repository and the original [ControlFoley](https://github.com/xiaomi-research/controlfoley) repository.


## Demo Video

<video src="docs/assets/controlfoley_comfyui_demo.mp4" controls width="100%"></video>

[Watch the ComfyUI demo video](docs/assets/controlfoley_comfyui_demo.mp4): install from Comfy Registry, open bundled workflow templates, run V2A / TC-V2A / AC-V2A / TV2A / T2A workflows, and preview generated audio/video outputs in ComfyUI.

This repository is a ComfyUI integration layer. It does not modify the ControlFoley model architecture, retrain models, or include ControlFoley model weights.

## ✨ Features

- Load the public ControlFoley source tree and Hugging Face weights from local paths, with missing weights downloaded on demand.
- Generate audio from video content, guide the generated sound with text prompts, or condition it on a reference audio clip.
- Support video-to-audio, text-to-audio, text-guided video-to-audio, and reference-audio-guided video-to-audio workflows, with task abbreviations shown in the bundled examples.
- Use either a simple one-node generator or an advanced reusable chain for preloading, dependency download, Torch compile, and generation.
- Save generated audio as WAV or FLAC.
- Mux generated audio back into the source video as MP4 using replace-original-audio mode.
- Support `fp16`, `bf16`, and `fp32` model loading options.
- Support fixed seeds, custom duration, inference steps, CFG scale, CLIP masking, staged encoder offload, encoder frame-batch multipliers, and video feature caching.
- Expose optional encoder compilation, a `low_vram` T2A/TTA path, and an unload node for memory-constrained runs.

## 🚀 Installation

Install `ControlFoley Official` from [Comfy Registry](https://registry.comfy.org/publishers/yjx-research/nodes/ComfyUI-ControlFoley) / ComfyUI Manager. This installs the custom node package and bundled workflow templates.

After installing the node, the public ControlFoley source tree is fetched automatically on first use: when `auto_fetch_source` is enabled (the default) and no local copy is found, the node shallow-clones a pinned revision of the upstream repository into `<ComfyUI root>/controlfoley` using `git`. If GitHub is unreachable from your network, set the `CONTROLFOLEY_SOURCE_URL` environment variable to a reachable mirror of the repository, or clone it manually as described below. The node auto-detects a folder named `controlfoley` next to this custom node, under the ComfyUI root, or from `CONTROLFOLEY_SOURCE_DIR`; otherwise set `controlfoley_source_dir` manually in the workflow.

For source installation, clone this custom node into `ComfyUI/custom_nodes`:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/YJX-Research/comfyui-controlfoley-official.git comfyui-controlfoley
cd comfyui-controlfoley
pip install -r requirements.txt
```

This repository is published at `YJX-Research/comfyui-controlfoley-official`; the local custom-node folder can still be named `comfyui-controlfoley`.

`requirements.txt` does not install `torch`, `torchaudio`, or `torchvision`; use the versions from your ComfyUI/PyTorch CUDA environment.

> **Note:** `requirements.txt` uses minimum-version ranges, so running `pip install -r requirements.txt` may upgrade shared packages (for example `numpy` or `transformers`) that your existing ComfyUI environment depends on. On an already-working ComfyUI install, prefer installing only the packages that are actually missing, one at a time.

Manual source setup (optional, for offline or custom layouts — otherwise `auto_fetch_source` handles this):

```bash
git clone https://github.com/xiaomi-research/controlfoley controlfoley
```

Start ComfyUI after installing the node:

```bash
cd ComfyUI
python main.py
```

## ⚡ Quick Start

1. Install ComfyUI.
2. Clone this custom node into `ComfyUI/custom_nodes`.
3. Install requirements with `pip install -r requirements.txt` (see the note above about version ranges on existing environments); keep the existing ComfyUI PyTorch stack.
4. The public ControlFoley source is fetched automatically on first run (`auto_fetch_source`, enabled by default). To manage it yourself, clone it as `controlfoley` next to this custom node or under the ComfyUI root, or set `CONTROLFOLEY_SOURCE_DIR`.
5. Start ComfyUI.
6. Open the bundled templates from ComfyUI Browse Templates or load a workflow from `example_workflows`.
7. Leave `model_weights_dir` as `path/to/model_weights` to use the default download directory, or set a custom local path.
8. The bundled workflow templates point to demo media under this node's `examples/generated` folder. You can also copy inputs into `ComfyUI/input/assets` or edit the workflow paths.
9. Run the workflow. Output nodes show audio/video previews and save files under `ComfyUI/output/controlfoley`.

## 📦 ControlFoley Weights

This repository does not include ControlFoley model weights. During `ControlFoley Model Loader` or `ControlFoley Dependencies Loader`, missing weights are downloaded from Hugging Face into the configured `model_weights_dir`.

The five ControlFoley weight files total roughly **16 GB** (about 11 GB core weights plus 5 GB external encoder weights), and the third-party dependency models cached by Hugging Face add several more GB. The first model load therefore takes a while even on a fast connection.

> **If huggingface.co is unreachable or very slow from your network**, set the `HF_ENDPOINT` environment variable to a mirror **before starting ComfyUI**, otherwise the first download can appear to hang with no error:
>
> ```bash
> export HF_ENDPOINT=https://hf-mirror.com
> ```
>
> On Windows PowerShell: `$env:HF_ENDPOINT = "https://hf-mirror.com"`.

If `model_weights_dir` is empty or left as `path/to/model_weights`, the node uses `CONTROLFOLEY_WEIGHTS_DIR` when set, then an existing packaged `controlfoley_workspace/model_weights`, then `ComfyUI/models/controlfoley`. The node registers `ComfyUI/models/controlfoley` with ComfyUI's model folder system under the `controlfoley` key.

You can still pre-download the public model release manually:

```bash
pip install "huggingface-hub[hf_xet]"
huggingface-cli download YJX-Xiaomi/ControlFoley \
  --resume-download \
  --local-dir model_weights \
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

The node also prefetches third-party Hugging Face model dependencies used by the public ControlFoley runtime, including CLIP, BigVGAN, and the reference-audio models used outside `low_vram` mode. These dependency models are fetched from their own upstream repositories instead of being treated as part of the ControlFoley weight package, so users should ensure network access or pre-cache them separately and review each upstream model's license and terms. Download repository IDs are centralized in `model_urls.py` so mirrors or future model releases can be updated without changing node logic.

`controlfoley_source_dir` should point to the cloned ControlFoley repository. `model_weights_dir` can point to an existing local weight directory or to a writable directory for automatic downloads.

## 🗂️ Folder Structure

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
  example_workflows/
    01_v2a_basic.json
    02_tcv2a_text_controlled.json
    03_acv2a_audio_controlled.json
    04_tv2a_text_video.json
    05_t2a_basic.json
    06_advanced_chain.json
    07_simple_generate.json
  examples/
    inputs/README.md
    generated/
```

Do not commit ControlFoley weights, Hugging Face caches, ComfyUI outputs, or local runtime files.

## 🧩 Available Nodes

- **ControlFoley Simple Generate**: one-node path for loading the model and generating audio in the same node.
- **ControlFoley Dependencies Loader**: validates the public ControlFoley source tree (auto-fetching it when `auto_fetch_source` is enabled), downloads missing ControlFoley weights, and prefetches known Hugging Face dependencies.
- **ControlFoley Model Loader**: loads ControlFoley and related encoders from local source and weight directories, optionally using the dependency-loader output.
- **ControlFoley Torch Compile**: optional advanced node for compiling feature encoders and, if requested, the generator module.
- **ControlFoley Video Loader**: resolves a video path from ComfyUI `input` or an absolute path, shows an inline preview of the loaded video, and exposes a native ComfyUI `VIDEO` output for chaining into core video nodes.
- **ControlFoley Generate**: runs V2A, TV2A, TC-V2A, AC-V2A, or T2A/TTA depending on connected inputs and parameters. It accepts the `ControlFoley Video Loader` output, native ComfyUI `VIDEO`, or native ComfyUI `IMAGE` batches.
- **ControlFoley Advanced Generate**: same generation path with `enabled`, `silent_audio_on_error`, and a status output for complex workflows.
- **ControlFoley Save Audio**: writes generated audio to `ComfyUI/output` as WAV or FLAC and shows an inline audio player.
- **ControlFoley Video-Audio Muxer**: writes an MP4 with generated audio replacing the original audio track and shows an inline video preview.
- **ControlFoley Model Unloader**: releases cached model objects and clears CUDA cache.

## 🧪 Demo Workflows

Workflow templates are in `example_workflows` (also available in ComfyUI Browse Templates):

| File | Task | Outputs |
| --- | --- | --- |
| `01_v2a_basic.json` | Video-to-audio | WAV + MP4 |
| `02_tcv2a_text_controlled.json` | TC-V2A text-controlled video-to-audio | WAV + MP4 |
| `03_acv2a_audio_controlled.json` | AC-V2A audio-controlled video-to-audio | WAV + MP4 |
| `04_tv2a_text_video.json` | TV2A text + video to audio | WAV + MP4 |
| `05_t2a_basic.json` | Text-to-audio | WAV |
| `06_advanced_chain.json` | Advanced generation chain | WAV |
| `07_simple_generate.json` | Simple one-node T2A generation | WAV |

Before running any workflow, review the source and weight directory settings (the source tree is fetched automatically by default; prepare it manually only for offline or custom layouts):

- `controlfoley`: default source-tree value. The node auto-detects a local clone named `controlfoley` next to this custom node, under the ComfyUI root, or from `CONTROLFOLEY_SOURCE_DIR`; replace it with an absolute path if needed.
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
- The seed `control_after_generate` option is set to `fixed` in all bundled workflows; `num_inference_steps` is set to `25`.

Bundled workflow defaults use a medium/low-VRAM preset intended to run on more GPUs before users tune for speed:

- `precision=bf16`
- `low_vram=false`
- `compile_encoders=false`
- `staged_offload=true`
- `clip_batch_size_multiplier=8`
- `sync_batch_size_multiplier=8`
- `num_inference_steps=25`
- `guidance_scale=4.5`

Native ComfyUI inputs:

- `video`: existing `CONTROLFOLEY_VIDEO` output from `ControlFoley Video Loader`.
- `video_input`: native ComfyUI `VIDEO` object from video loader / video creation nodes.
- `images`: native ComfyUI `IMAGE` batch. When connected, `image_fps` is used to encode a temporary MP4 before ControlFoley preprocessing.
- Connect only one of `video`, `video_input`, or `images` for each generation. Temporary IMAGE/VIDEO files are written under `ComfyUI/output/controlfoley/temp`.

For workflows with video input, keep both output nodes enabled: standalone `.wav` and muxed `.mp4`.

## 🎬 Generated Examples

Selected generated samples are stored in `examples/generated`. Each workflow has one representative output folder with the original input files needed for comparison and the generated result files.

Actual demo media durations are listed in each `examples/generated/*/README.txt` file.

Only publish example media that has passed the repository owner's release review. Keep source attribution, usage permissions, and any required media notices with the example files. Runtime media outside `examples/generated` should remain uncommitted.

See `examples/generated/README.md` for demo media credits.

## 📥 Input Media

The workflow templates bundled with the node point directly to approved demo inputs under `examples/generated`, and relative paths are resolved against the custom-node folder. You may also copy the approved demo inputs into `ComfyUI/input/assets` using the names below, or edit the workflow paths.

Suggested demo input mapping:

```text
examples/generated/01_v2a_basic/v2a_video.mp4 -> ComfyUI/input/assets/v2a_video.mp4
examples/generated/02_tcv2a_text_controlled/tcv2a_video.mp4 -> ComfyUI/input/assets/tcv2a_video.mp4
examples/generated/02_tcv2a_text_controlled/prompt.txt -> prompt "thunder strike"
examples/generated/03_acv2a_audio_controlled/acv2a_video.mp4 -> ComfyUI/input/assets/acv2a_video.mp4
examples/generated/03_acv2a_audio_controlled/acv2a_reference.wav -> ComfyUI/input/assets/acv2a_reference.wav
examples/generated/04_tv2a_text_video/tv2a_video.mp4 -> ComfyUI/input/assets/tv2a_video.mp4
examples/generated/04_tv2a_text_video/prompt.txt -> prompt "skateboarding"
examples/generated/05_t2a_basic/prompt.txt -> prompt "A bird sings melodically in a forest"
examples/generated/06_advanced_chain/prompt.txt -> prompt "A bird sings melodically in a forest"
examples/generated/07_simple_generate/prompt.txt -> prompt "A bird sings melodically in a forest"
```

Reference audio for AC-V2A should be 2-4 seconds. Longer audio is truncated and shorter audio is padded by the node.

## 📤 Outputs

ComfyUI writes outputs under `ComfyUI/output`. With the default prefixes, files are written to:

```text
ComfyUI/output/controlfoley/
```

Default workflow outputs:

- `v2a_video_output_00001_.wav` and `v2a_video_output_00001_.mp4`
- `tcv2a_video_output_00001_.wav` and `tcv2a_video_output_00001_.mp4`
- `acv2a_video_output_00001_.wav` and `acv2a_video_output_00001_.mp4`
- `tv2a_video_output_00001_.wav` and `tv2a_video_output_00001_.mp4`
- `t2a_basic_prompt_output_00001_.wav`
- `advanced_chain_prompt_output_00001_.wav`
- `simple_generate_prompt_output_00001_.wav`

ComfyUI increments the numeric suffix on repeated runs, so the second run writes `_00002_` files instead of overwriting earlier outputs. For video workflows, the `.wav` and muxed `.mp4` from the same run share the same numeric suffix because the mux node consumes the audio output from `ControlFoley Save Audio`.

## 🧠 Low VRAM Mode

The alpha release only applies engineering-side memory options. It does not change model structure.

Implemented options:

- `torch.inference_mode()` during generation.
- `fp16`, `bf16`, and `fp32` precision selection.
- Fixed batch size 1.
- Optional video feature caching.
- Optional CLIP masking through `mask_away_clip`.
- `clip_batch_size_multiplier` and `sync_batch_size_multiplier` tune feature-extractor frame batches for VRAM/performance tradeoffs.
- `staged_offload` moves encoders to CPU during DiT sampling and restores them for decode/vocode **when the selected ControlFoley source implements it**. The pinned public upstream source does not accept this parameter; the option is then ignored and a console note is printed.
- Optional `compile_encoders` for users who want to pay one-time `torch.compile` cost.
- `low_vram` path for text-only T2A/TTA runs.
- `ControlFoley Model Unloader` node.
- CUDA cache cleanup after low-VRAM generation.
- Medium/low-VRAM bundled workflow defaults: `bf16`, `low_vram=false`, `staged_offload=true`, `clip_batch_size_multiplier=8`, `sync_batch_size_multiplier=8`, and 25-step generation.

For V2A, TV2A, TC-V2A, and AC-V2A memory reduction, keep `low_vram=false`; `staged_offload=true` helps when the source supports it (it is ignored with a console note on the public upstream source). `low_vram=true` remains a text-only T2A/TTA path.

## 📊 VRAM and Speed Benchmark

See `docs/vram_speed_log.md` for recorded runs.

Cold-start behavior:

- First load can take several minutes because ControlFoley weights and Hugging Face dependencies are downloaded and cached.
- Later loads reuse local weights and the HF cache; startup time is then dominated by model construction and GPU transfer.
- `compile_encoders=true` adds extra one-time compile latency and should be left off for first-run smoke tests.

Memory guidance:

- Use a CUDA GPU; CPU/MPS execution is not supported by this node's integrated public inference path.
- Use `staged_offload=true` to reduce memory pressure in V2A, TV2A, TC-V2A, and AC-V2A workflows on sources that implement it (ignored with a console note on the public upstream source).
- Lower `clip_batch_size_multiplier` and `sync_batch_size_multiplier` only when feature extraction peaks too high; this trades speed for memory during encoder feature extraction.
- `low_vram=true` is intended for text-only T2A/TTA; keep it `false` for V2A, TV2A, TC-V2A, and AC-V2A.
- Keep `num_inference_steps=25` for normal output quality. Lower step counts mainly reduce runtime, not peak VRAM, and are only useful for quick internal smoke checks.

## ⚠️ Known Issues

See `docs/known_issues.md`.

Important alpha limitations:

- Use `staged_offload=true` for video/reference-audio workflows on smaller GPUs when the selected source implements it (the public upstream source ignores it with a console note).
- Missing weights and known Hugging Face dependency models are downloaded during model loading.
- `ControlFoley Video-Audio Muxer` currently supports replace-original-audio mode only; mix mode is planned.
- The public ControlFoley inference path is CUDA-only in this node.

## 📄 License and Third-Party Assets

- **ComfyUI custom node code**: Apache 2.0; see `LICENSE`.
- **Original ControlFoley source code**: Apache 2.0. This repository loads a separate local clone of `xiaomi-research/controlfoley`; it does not vendor the upstream source tree.
- **ControlFoley model weights**: CC BY-NC 4.0, non-commercial use only. The weights are not included in this repository and are downloaded or supplied separately by the user.
- **Third-party dependency models**: downloaded or cached separately from their own upstream Hugging Face repositories. Their licenses and usage terms are not controlled by this repository.
- **Bundled demo media**: not covered by this repository's Apache 2.0 code license. Demo media provenance and source/license notes are documented in `examples/generated/README.md` and each example folder.
- **Generated demo outputs**: produced with ControlFoley from the bundled demo inputs and prompts. Treat them as demonstration assets subject to the model-weight license and the underlying input-media permissions.

Review the upstream [ControlFoley repository](https://github.com/xiaomi-research/controlfoley), the [Hugging Face model card](https://huggingface.co/YJX-Xiaomi/ControlFoley), and the source licenses/terms for any bundled media before public or commercial use.
