CONTROLFOLEY_WEIGHTS_REPOS = ("YJX-Xiaomi/ControlFoley", "controlfoley/controlfoley")

CONTROLFOLEY_WEIGHT_FILES = (
    "weights/controlfoley.pth",
    "ext_weights/v1-44.pth",
    "ext_weights/synchformer_state_dict.pth",
    "ext_weights/cav_mae_st.pth",
    "ext_weights/music_speech_audioset_epoch_15_esc_89.98.pt",
)

CONTROLFOLEY_BASE_DEPENDENCY_REPOS = (
    "apple/DFN5B-CLIP-ViT-H-14-384",
    "nvidia/bigvgan_v2_44khz_128band_512x",
)

CONTROLFOLEY_AUDIO_DEPENDENCY_REPOS = (
    "facebook/musicgen-style",
    "roberta-base",
    "facebook/bart-base",
    "bert-base-uncased",
    "m-a-p/MERT-v1-95M",
)


def dependency_repos(low_vram: bool) -> tuple[str, ...]:
    if low_vram:
        return CONTROLFOLEY_BASE_DEPENDENCY_REPOS
    return CONTROLFOLEY_BASE_DEPENDENCY_REPOS + CONTROLFOLEY_AUDIO_DEPENDENCY_REPOS
