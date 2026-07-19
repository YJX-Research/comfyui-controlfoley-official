# Generated Examples

Selected ControlFoley ComfyUI outputs for quick inspection. Each folder contains one representative generated result for the corresponding workflow.

Generated example files use the same basename as the workflow input/output fields but omit ComfyUI's runtime numeric suffix for easier comparison. Actual ComfyUI runs write numbered files such as `v2a_video_output_00001_.wav`.

| Folder | Workflow | Included outputs |
| --- | --- | --- |
| `01_v2a_basic` | Video-to-audio | Original video, generated WAV, generated MP4 |
| `02_tcv2a_text_controlled` | TC-V2A text-controlled video-to-audio | Original video, prompt, generated WAV, generated MP4 |
| `03_acv2a_audio_controlled` | AC-V2A audio-controlled video-to-audio | Original video, reference audio, generated WAV, generated MP4 |
| `04_tv2a_text_video` | TV2A text + video to audio | Original video, prompt, generated WAV, generated MP4 |
| `05_t2a_basic` | Text-to-audio | Prompt, 10s generated WAV |
| `06_advanced_chain` | Advanced generation chain | Prompt, 10s generated WAV |
| `07_simple_generate` | Simple one-node T2A generation | Prompt, 10s generated WAV |

## Media Provenance and License Notes

Release-reviewed demo media in this directory are supplied only for quick workflow inspection. The repository's Apache 2.0 code license does not apply to these media files.

Source summary supplied by the release owner:

- Audio/reference-audio sources: Pixabay content.
- Video sources: Pexels content and Jimeng AI-generated content.
- Generated outputs: ControlFoley outputs created from the bundled inputs and prompts.

Before publishing a release, keep the release owner's review record for every media file, including source URL or generation record, download/generation date, applicable platform license or terms, and any required attribution or AI-content notices. Do not add unreviewed media to this directory.

License/terms reminders:

- Pexels and Pixabay content is generally free to use under their platform licenses, but those licenses include prohibited-use and third-party-rights restrictions.
- Jimeng AI-generated content must comply with Jimeng AI's user agreement, including user responsibility for inputs/outputs and AI-content labeling requirements where applicable.
- ControlFoley model weights are CC BY-NC 4.0, so generated outputs should be treated as non-commercial demonstration assets unless you have separate permission.

Reference links for release review:

- Pexels License: https://www.pexels.com/license/
- Pixabay Content License Summary: https://pixabay.com/service/license-summary/
- Jimeng AI User Service Agreement: https://lf9-cdn-tos.draftstatic.com/obj/ies-hotsoon-draft/vco/17620dba-f821-4a18-85f9-b8b11f73304a.html
- Jimeng AI Disclaimer: https://lf3-cdn-tos.draftstatic.com/obj/ies-hotsoon-draft/vco/330fd20a-7a83-4931-969d-feca39c914be.html
- ControlFoley model card: https://huggingface.co/YJX-Xiaomi/ControlFoley

Actual demo media durations are listed in each workflow folder's `README.txt`.
