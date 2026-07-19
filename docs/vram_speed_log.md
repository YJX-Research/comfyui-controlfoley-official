# VRAM and Speed Test Log

This file is a public template for release validation records. Do not commit internal machine names, server paths, private output paths, GPU model names, driver details, or environment-specific identifiers.

Use anonymized hardware classes when publishing benchmark results, for example:

```text
Hardware class: 8GB CUDA GPU / 16GB CUDA GPU / 24GB CUDA GPU
Precision:
Video duration:
Resolution class:
num_inference_steps:
low_vram:
staged_offload:
clip_batch_size_multiplier:
sync_batch_size_multiplier:
Peak VRAM range:
Inference time range:
Result:
Notes:
```

## Planned Test Matrix

Record release-approved, anonymized runs in this file.

## Known Initial Constraints

- CUDA is currently required because the public ControlFoley inference path has CUDA-only tensor moves.
- `mix` mode for muxing is planned; first release supports replacing original audio.
- MP3 saving is not included in the node to keep dependencies predictable; WAV and FLAC are supported through soundfile.
- Bundled demo workflows use fixed 25-step generation. Lower step counts mainly reduce runtime and should not be treated as a VRAM optimization preset.

## Public Benchmark Status

The alpha release includes functional demo workflows, but it does not publish a full consumer-GPU benchmark matrix yet.

Planned benchmark coverage:

- 8GB CUDA GPU class: planned, not yet published.
- 12GB CUDA GPU class: planned, not yet published.
- 16GB CUDA GPU class: planned, not yet published.
- 20GB+ CUDA GPU class: planned, not yet published.
- Standard 25-step V2A / TV2A / TC-V2A / AC-V2A benchmark matrix: planned, not yet published.
- Standard AC-V2A non-fp32 validation after dtype-alignment fix: planned, not yet published.

Do not infer benchmark performance or quality from private smoke tests. Public benchmark rows should be added only after release review and anonymization.
