import gc
import inspect
import importlib
import os
import shutil
import stat
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Optional

import torch

try:
    import folder_paths
except Exception:
    folder_paths = None

try:
    from .model_urls import CONTROLFOLEY_WEIGHT_FILES, CONTROLFOLEY_WEIGHTS_REPOS, dependency_repos
except Exception:
    from model_urls import CONTROLFOLEY_WEIGHT_FILES, CONTROLFOLEY_WEIGHTS_REPOS, dependency_repos

CATEGORY = "ControlFoley"
AUDIO_TYPE = "AUDIO"
CONTROLFOLEY_MODEL_TYPE = "CONTROLFOLEY_MODEL"
CONTROLFOLEY_DEPENDENCIES_TYPE = "CONTROLFOLEY_DEPENDENCIES"
CONTROLFOLEY_VIDEO_TYPE = "CONTROLFOLEY_VIDEO"
CONTROLFOLEY_AUDIO_FILE_TYPE = "CONTROLFOLEY_AUDIO_FILE"
CONTROLFOLEY_VIDEO_FILE_TYPE = "CONTROLFOLEY_VIDEO_FILE"
MIN_VIDEO_DURATION = 0.7
DEFAULT_TEXT_ONLY_DURATION = 10.0
DEFAULT_VIDEO_DURATION = 8.0
MAX_GENERATION_DURATION = 30.0
FIXED_STEP_SENTINEL = "fixed"
DEFAULT_INFERENCE_STEPS = 25
VIDEO_CACHE_MAX_ITEMS = 2
DEFAULT_CONTROLFOLEY_SOURCE_DIR = "controlfoley"
CONTROLFOLEY_SOURCE_DEFAULT_URL = "https://github.com/xiaomi-research/controlfoley"
# The public inference API is not versioned; an unpinned clone would silently pick up
# upstream API changes and break this integration, so always fetch a known-good revision.
CONTROLFOLEY_SOURCE_PIN = "6858cd12a48d141201e3266e7abe1f38357a133e"
CONTROLFOLEY_FETCH_TIMEOUT_SEC = 300
DEFAULT_MODEL_WEIGHTS_DIR = "path/to/model_weights"
DEFAULT_DEMO_VIDEO_PATH = "examples/generated/01_v2a_basic/v2a_video.mp4"
DEFAULT_TEXT_PROMPT = "A bird sings melodically in a forest"


def _register_model_folder() -> None:
    if folder_paths is None or not hasattr(folder_paths, "folder_names_and_paths"):
        return
    model_dir = Path(folder_paths.models_dir) / "controlfoley"
    extensions = getattr(folder_paths, "supported_pt_extensions", {".ckpt", ".pt", ".pth", ".safetensors"})
    current = folder_paths.folder_names_and_paths.get("controlfoley")
    if current is None:
        folder_paths.folder_names_and_paths["controlfoley"] = ([str(model_dir)], extensions)
        return
    paths, existing_extensions = current
    paths = list(paths)
    if str(model_dir) not in paths:
        paths.append(str(model_dir))
    folder_paths.folder_names_and_paths["controlfoley"] = (paths, existing_extensions)


_register_model_folder()


def _output_dir() -> Path:
    if folder_paths is not None:
        return Path(folder_paths.get_output_directory())
    return Path.cwd() / "output"


def _input_dir() -> Path:
    if folder_paths is not None:
        return Path(folder_paths.get_input_directory())
    return Path.cwd() / "input"


def _temp_dir() -> Path:
    path = _output_dir() / "controlfoley" / "temp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _temp_video_path(prefix: str) -> Path:
    return _temp_dir() / f"{prefix}_{time.time_ns()}.mp4"


_TEMP_MAX_AGE_SEC = 48 * 3600


def _cleanup_stale_temp_files() -> None:
    # Intermediate MP4s written for VIDEO/IMAGE inputs must outlive the run that
    # created them (the muxer re-reads the same path), so they are reaped by age
    # at startup instead of being deleted right after generation.
    temp_dir = _output_dir() / "controlfoley" / "temp"
    if not temp_dir.is_dir():
        return
    cutoff = time.time() - _TEMP_MAX_AGE_SEC
    removed = 0
    for item in temp_dir.iterdir():
        try:
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink()
                removed += 1
        except Exception as exc:
            print(f"[ControlFoley] Could not remove stale temp file {item.name}: {exc}")
    if removed:
        print(f"[ControlFoley] Removed {removed} stale temp file(s) from {temp_dir}")


try:
    _cleanup_stale_temp_files()
except Exception as _cleanup_exc:
    print(f"[ControlFoley] Temp cleanup skipped: {_cleanup_exc}")


def _node_dir() -> Path:
    return Path(__file__).resolve().parent


def _comfy_root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_weights_dir() -> Path:
    env_dir = os.environ.get("CONTROLFOLEY_WEIGHTS_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    comfy_dir = _comfy_root_dir()
    packaged_dir = comfy_dir.parent / "controlfoley_workspace" / "model_weights"
    if packaged_dir.exists():
        return packaged_dir.resolve()
    if folder_paths is not None and hasattr(folder_paths, "models_dir"):
        return (Path(folder_paths.models_dir) / "controlfoley").resolve()
    return (comfy_dir / "models" / "controlfoley").resolve()


def _resolve_path(path_text: str, base: Optional[Path] = None) -> Optional[Path]:
    text = (path_text or "").strip().strip('"')
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        roots = []
        if base is not None:
            roots.append(base)
        roots.extend([_input_dir(), _node_dir(), _comfy_root_dir(), Path.cwd()])
        for root in roots:
            candidate = root / path
            if candidate.exists():
                return candidate.resolve()
    return path.resolve()


def _looks_like_controlfoley_source(path: Path) -> bool:
    return (path / "demo.py").exists() and (path / "controlfoley" / "inference_utils.py").exists()


def _candidate_controlfoley_source_dirs(text: str) -> list[Path]:
    candidates: list[Path] = []
    env_dir = os.environ.get("CONTROLFOLEY_SOURCE_DIR")
    if env_dir:
        candidates.append(Path(env_dir).expanduser())
    if text and text not in {"path/to/controlfoley", "controlfoley"}:
        resolved = _resolve_path(text)
        if resolved is not None:
            candidates.append(resolved)
    candidates.extend([
        _node_dir() / "controlfoley",
        _node_dir().parent / "controlfoley",
        _comfy_root_dir() / "controlfoley",
        _comfy_root_dir() / "custom_nodes" / "controlfoley",
        Path.cwd() / "controlfoley",
    ])
    return candidates


def _resolve_controlfoley_source_dir(path_text: str) -> Optional[Path]:
    text = (path_text or "").strip().strip('"')
    for candidate in _candidate_controlfoley_source_dirs(text):
        candidate = candidate.expanduser().resolve()
        if _looks_like_controlfoley_source(candidate):
            return candidate
    if text:
        resolved = _resolve_path(text)
        if resolved is not None:
            return resolved
    return None


def _resolve_source_dir_with_auto_fetch(path_text: str, auto_fetch_source: bool) -> Optional[Path]:
    source_dir = _resolve_controlfoley_source_dir(path_text)
    if auto_fetch_source and (source_dir is None or not _looks_like_controlfoley_source(source_dir)):
        fetched = _auto_fetch_controlfoley_source()
        if fetched is not None:
            source_dir = fetched
    return source_dir


def _resolve_weights_dir(path_text: str) -> Path:
    text = (path_text or "").strip().strip('"')
    if not text or text == "path/to/model_weights":
        return _default_weights_dir()
    resolved = _resolve_path(text)
    if resolved is None:
        return _default_weights_dir()
    return resolved


def _download_hf_file(repo_id: str, filename: str, destination: Path) -> None:
    try:
        from huggingface_hub import hf_hub_download
    except Exception as exc:
        raise RuntimeError("Install huggingface-hub to auto-download ControlFoley weights.") from exc

    source = Path(hf_hub_download(repo_id=repo_id, filename=filename))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _ensure_controlfoley_weights(weights_dir: Path) -> None:
    missing = [filename for filename in CONTROLFOLEY_WEIGHT_FILES if not (weights_dir / filename).exists()]
    if not missing:
        return

    print(f"[ControlFoley] Downloading missing weights to {weights_dir}")
    errors = []
    for filename in missing:
        destination = weights_dir / filename
        for repo_id in CONTROLFOLEY_WEIGHTS_REPOS:
            try:
                _download_hf_file(repo_id, filename, destination)
                print(f"[ControlFoley] Downloaded {repo_id}/{filename}")
                break
            except Exception as exc:
                errors.append(f"{repo_id}/{filename}: {exc}")
        if not destination.exists():
            raise FileNotFoundError(
                "Could not auto-download ControlFoley weight "
                f"{filename}. Tried {', '.join(CONTROLFOLEY_WEIGHTS_REPOS)}. Last errors: "
                + " | ".join(errors[-len(CONTROLFOLEY_WEIGHTS_REPOS):])
            )


def _ensure_hf_dependency_cache(low_vram: bool) -> None:
    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:
        raise RuntimeError("Install huggingface-hub to auto-download ControlFoley dependency weights.") from exc

    for repo_id in dependency_repos(low_vram):
        try:
            snapshot_download(repo_id=repo_id)
            continue
        except Exception as exc:
            network_error = exc
        try:
            # Offline or unreachable network: a complete local cache is fine.
            # (Network-first keeps the original repair semantics for partial caches.)
            snapshot_download(repo_id=repo_id, local_files_only=True)
        except Exception as exc:
            raise RuntimeError(
                f"Could not auto-download ControlFoley dependency weights from {repo_id} "
                f"({network_error}) and no complete local cache was found. "
                "If you are offline, pre-cache this repository once while online. If Hugging Face "
                "is unreachable from your network, set the HF_ENDPOINT environment variable to a mirror "
                "(for example https://hf-mirror.com) and retry."
            ) from exc


def _safe_path(value: str, fallback: str, suffix: str | None = None) -> Path:
    raw = (value or fallback).strip().replace("\\", "/") or fallback
    parts = []
    for part in raw.split("/"):
        clean = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in part).strip("._")
        if clean:
            parts.append(clean[:120])
    if not parts:
        parts = [fallback.replace("/", "_")]
    path = Path(*parts)
    if suffix is not None and path.suffix.lower() != suffix:
        path = path.with_suffix(suffix)
    return path


def _save_comfy_video_to_path(video_input: Any, fallback_prefix: str = "comfy_video") -> Path:
    if video_input is None:
        raise ValueError("video_input is required")
    if isinstance(video_input, (str, Path)):
        path = _resolve_path(str(video_input))
        if path is None or not path.exists():
            raise FileNotFoundError(f"VIDEO input path not found: {video_input}")
        return path
    if isinstance(video_input, dict):
        for key in ("path", "video_path", "filename", "file"):
            value = video_input.get(key)
            if value:
                path = _resolve_path(str(value))
                if path is not None and path.exists():
                    return path

    get_stream_source = getattr(video_input, "get_stream_source", None)
    if callable(get_stream_source):
        source = get_stream_source()
        if isinstance(source, (str, Path)):
            path = Path(source).expanduser().resolve()
            if path.exists():
                return path

    save_to = getattr(video_input, "save_to", None)
    if callable(save_to):
        path = _temp_video_path(fallback_prefix)
        save_to(str(path))
        return path

    raise TypeError("Unsupported VIDEO input. Connect a ComfyUI VIDEO object, path-like value, or path dictionary.")


def _comfy_video_duration(video_input: Any) -> Optional[float]:
    get_duration = getattr(video_input, "get_duration", None)
    if callable(get_duration):
        try:
            duration = float(get_duration())
            if duration > 0:
                return duration
        except Exception:
            return None
    if isinstance(video_input, dict):
        for key in ("duration", "total_duration"):
            value = video_input.get(key)
            if value:
                return float(value)
    return None


def _media_duration(path: Path) -> Optional[float]:
    try:
        import av
        with av.open(str(path)) as container:
            # Prefer the video stream's decodable span (last frame timestamp).
            # Container/stream metadata routinely overstates it by up to one frame
            # duration, and requesting that overstated length upstream makes
            # frame extraction warn "... video is too short" on every run.
            for stream in container.streams.video:
                frames = stream.frames or 0
                rate = stream.average_rate
                if frames > 1 and rate:
                    duration = float((frames - 1) / rate)
                    # average_rate is approximate for variable-frame-rate files;
                    # never report more than the container itself claims.
                    if container.duration is not None:
                        duration = min(duration, float(container.duration) / 1_000_000.0)
                    if duration > 0:
                        return duration
            if container.duration is not None:
                duration = float(container.duration) / 1_000_000.0
                if duration > 0:
                    return duration
            for stream in container.streams:
                if stream.duration is not None and stream.time_base is not None:
                    duration = float(stream.duration * stream.time_base)
                    if duration > 0:
                        return duration
    except Exception as exc:
        print(f"[ControlFoley] Could not probe media duration of {path.name}: {exc}")
        return None
    return None


def _save_images_to_video(images: torch.Tensor, fps: float) -> tuple[Path, float]:
    if images is None:
        raise ValueError("images is required")
    if not torch.is_tensor(images):
        raise TypeError("IMAGE input must be a torch.Tensor")
    if images.ndim == 3:
        images = images.unsqueeze(0)
    if images.ndim != 4:
        raise ValueError("IMAGE input must have shape [N, H, W, C] or [H, W, C]")
    if images.shape[0] < 1:
        raise ValueError("IMAGE input is empty")
    if float(fps) <= 0:
        raise ValueError("image_fps must be greater than 0")

    duration = float(images.shape[0]) / float(fps)

    if images.shape[-1] == 1:
        images = images.expand(*images.shape[:-1], 3)
    elif images.shape[-1] >= 3:
        images = images[..., :3]
    else:
        raise ValueError("IMAGE input must have at least one channel")
    height, width = int(images.shape[1]), int(images.shape[2])
    pad_h = height % 2
    pad_w = width % 2
    if pad_h or pad_w:
        images = torch.nn.functional.pad(
            images.permute(0, 3, 1, 2),
            (0, pad_w, 0, pad_h),
            mode="replicate",
        ).permute(0, 2, 3, 1)
        height, width = int(images.shape[1]), int(images.shape[2])

    import av

    path = _temp_video_path("image_input")
    with av.open(str(path), mode="w", options={"movflags": "use_metadata_tags"}) as container:
        stream = container.add_stream("h264", rate=Fraction(round(float(fps) * 1000), 1000))
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        for image in images:
            array = torch.clamp(image * 255, 0, 255).to(device="cpu", dtype=torch.uint8).contiguous().numpy()
            frame = av.VideoFrame.from_ndarray(array, format="rgb24").reformat(format="yuv420p")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return path, duration


def _select_generation_video(video, video_input, images, duration: float, image_fps: float):
    sources = [value is not None for value in (video, video_input, images)]
    if sum(sources) > 1:
        raise ValueError("Connect only one video source: video, video_input, or images.")
    if video is not None:
        return video
    if video_input is not None:
        path = _save_comfy_video_to_path(video_input)
        source_duration = _media_duration(path) or _comfy_video_duration(video_input)
        return {"path": path, "duration": float(source_duration or duration)}
    if images is not None:
        path, source_duration = _save_images_to_video(images, float(image_fps))
        return {"path": path, "duration": float(_media_duration(path) or source_duration)}
    return None


def _bounded_duration(duration: float, maximum: float = MAX_GENERATION_DURATION) -> float:
    return max(MIN_VIDEO_DURATION, min(float(duration), float(maximum)))


def _resolve_generation_duration(duration: float, video: Optional[dict]) -> float:
    if video is None:
        return _bounded_duration(duration)
    source_duration = float(video.get("duration") or duration)
    return _bounded_duration(source_duration)


def _dtype_from_precision(precision: str) -> torch.dtype:
    if precision == "fp16":
        return torch.float16
    if precision == "bf16":
        return torch.bfloat16
    return torch.float32


def _device_from_choice(device: str) -> str:
    if device == "auto":
        try:
            import comfy.model_management as model_management

            torch_device = model_management.get_torch_device()
            if torch_device is not None:
                return str(torch_device).split(":", 1)[0]
        except Exception as exc:
            print(f"[ControlFoley] Could not query ComfyUI torch device, probing manually: {exc}")
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    return device


def _free_vram_for_low_vram_load() -> None:
    try:
        import comfy.model_management as model_management

        model_management.unload_all_models()
    except Exception as exc:
        print(f"[ControlFoley] Could not unload other ComfyUI models before low-VRAM load: {exc}")
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


_SOURCE_FETCH_LOCK = threading.Lock()


def _rmtree_force(path: Path) -> None:
    def _onerror(func, item, exc_info):
        try:
            os.chmod(item, stat.S_IWRITE)
            func(item)
        except Exception:
            pass

    shutil.rmtree(str(path), onerror=_onerror)


def _controlfoley_source_url() -> str:
    return os.environ.get("CONTROLFOLEY_SOURCE_URL", "").strip() or CONTROLFOLEY_SOURCE_DEFAULT_URL


def _auto_fetch_controlfoley_source() -> Optional[Path]:
    """Clone the pinned public ControlFoley source into <ComfyUI root>/controlfoley.

    The clone lands in a temporary sibling directory first and is renamed into place
    only after it passes the completeness check, so a failed or interrupted fetch
    never leaves a half-populated folder for the auto-detection to misjudge as ready.
    Returns the final source directory on success, None on any failure (callers fall
    back to the manual-clone error message).
    """
    target = _comfy_root_dir() / DEFAULT_CONTROLFOLEY_SOURCE_DIR
    with _SOURCE_FETCH_LOCK:
        if _looks_like_controlfoley_source(target):
            return target
        url = _controlfoley_source_url()
        tmp = target.parent / f"{DEFAULT_CONTROLFOLEY_SOURCE_DIR}.fetch-{os.getpid()}-{time.time_ns()}"
        print(
            f"[ControlFoley] Auto-fetching ControlFoley source revision {CONTROLFOLEY_SOURCE_PIN[:7]} "
            f"from {url} into {target}"
        )
        try:
            if target.exists():
                raise RuntimeError(
                    f"{target} already exists but is not a complete ControlFoley source tree; "
                    "remove it or point controlfoley_source_dir at a valid clone."
                )
            tmp.mkdir(parents=True, exist_ok=False)

            def _run_git(*args: str) -> None:
                completed = subprocess.run(
                    ["git", *args],
                    cwd=str(tmp),
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=CONTROLFOLEY_FETCH_TIMEOUT_SEC,
                )
                if completed.returncode != 0:
                    detail = (completed.stderr or completed.stdout or "").strip()[:500]
                    raise RuntimeError(f"git {args[0]} failed: {detail}")

            _run_git("init", "--quiet")
            _run_git("remote", "add", "origin", url)
            _run_git("fetch", "--quiet", "--depth", "1", "origin", CONTROLFOLEY_SOURCE_PIN)
            _run_git("checkout", "--quiet", "FETCH_HEAD")
            if not _looks_like_controlfoley_source(tmp):
                raise RuntimeError(
                    "fetched tree does not look like the public ControlFoley source "
                    "(missing demo.py / controlfoley/inference_utils.py)"
                )
            tmp.rename(target)
            print(f"[ControlFoley] ControlFoley source fetch complete: {target}")
            return target
        except subprocess.TimeoutExpired:
            print(
                "[ControlFoley] ControlFoley source auto-fetch timed out after "
                f"{CONTROLFOLEY_FETCH_TIMEOUT_SEC}s. If GitHub is unreachable from your network, "
                "set the CONTROLFOLEY_SOURCE_URL environment variable to a reachable mirror."
            )
            return None
        except Exception as exc:
            if _looks_like_controlfoley_source(target):
                # Another process (sharing this ComfyUI root) landed the source while we
                # were fetching; use it instead of reporting a failure.
                print(f"[ControlFoley] ControlFoley source already fetched elsewhere: {target}")
                return target
            print(f"[ControlFoley] ControlFoley source auto-fetch failed: {exc}")
            return None
        finally:
            if tmp.exists():
                _rmtree_force(tmp)


def _ensure_public_controlfoley_repo(source_dir: Path) -> None:
    required = [
        source_dir / "demo.py",
        source_dir / "controlfoley" / "inference_utils.py",
        source_dir / "controlfoley" / "audio_model.py",
        source_dir / "controlfoley" / "feature_extractor.py",
        source_dir / "lib" / "flow_matching.py",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        hint = (
            "Clone https://github.com/xiaomi-research/controlfoley and set "
            "controlfoley_source_dir to that folder. The node also auto-detects "
            "a sibling or ComfyUI-root folder named 'controlfoley'. "
            "With auto_fetch_source enabled the node clones this automatically; "
            "if GitHub is unreachable from your network, set the CONTROLFOLEY_SOURCE_URL "
            "environment variable to a reachable mirror of the repository and retry."
        )
        raise FileNotFoundError(
            "ControlFoley public source directory is incomplete. "
            f"Checked: {source_dir}. Missing: {', '.join(missing)}. {hint}"
        )


def _patch_timbre_dtype_alignment(net: Any) -> None:
    if getattr(net, "_controlfoley_timbre_dtype_patch", False):
        return
    original = getattr(net, "preprocess_conditions", None)
    projection = getattr(net, "timbre_input_proj", None)
    if original is None or projection is None:
        # Upstream renamed or removed the attributes this patch relies on; a
        # silent no-op here would let the bf16/fp16 timbre crash quietly return.
        print(
            "[ControlFoley] WARNING: timbre dtype patch could not be installed "
            "(preprocess_conditions/timbre_input_proj not found on the upstream model). "
            "Reference-audio runs in bf16/fp16 may fail with a dtype mismatch."
        )
        return

    # Upstream signature: preprocess_conditions(clip_f, visual_f, sync_f, text_f,
    # audio_f, timbre_f). Forward everything verbatim so added upstream parameters
    # keep working; only the timbre tensor is realigned.
    def _patched_preprocess_conditions(*args, **kwargs):
        try:
            param = next(projection.parameters())
        except StopIteration:
            param = None
        if param is not None:
            def _align(value):
                if torch.is_tensor(value) and (value.dtype != param.dtype or value.device != param.device):
                    return value.to(device=param.device, dtype=param.dtype)
                return value

            if "timbre_f" in kwargs:
                kwargs["timbre_f"] = _align(kwargs["timbre_f"])
            elif len(args) >= 6:
                args = list(args)
                args[5] = _align(args[5])
                args = tuple(args)
        return original(*args, **kwargs)

    net.preprocess_conditions = _patched_preprocess_conditions
    net._controlfoley_timbre_dtype_patch = True


@dataclass
class ControlFoleyDependencies:
    source_dir: Path
    weights_dir: Path
    low_vram: bool


@dataclass
class ControlFoleyRuntime:
    source_dir: Path
    weights_dir: Path
    variant: str
    device: str
    dtype: torch.dtype
    precision: str
    low_vram: bool
    model_cfg: Any
    seq_cfg: Any
    net: Any
    feature_utils: Any
    flow_matching_cls: Any
    inference_utils: Any
    torchaudio: Any
    compile_encoders: bool

    def unload(self) -> None:
        self.net = None
        self.feature_utils = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


_MODEL_CACHE: dict[tuple[str, str, str, str, bool, bool], ControlFoleyRuntime] = {}
# Bumped by the Unload node; the loader's IS_CHANGED returns it so a re-load is
# forced after any unload (linked inputs are not available inside IS_CHANGED,
# so a cache-key comparison there would be unreliable).
_UNLOAD_EPOCH = 0
_VIDEO_CACHE: OrderedDict[tuple[str, int, int, float, bool], Any] = OrderedDict()


def _path_signature(path: Path) -> tuple[int, int]:
    st = path.stat()
    return st.st_mtime_ns, st.st_size


def _video_cache_key(video_path: Path, duration: float, load_all_frames: bool) -> tuple[str, int, int, float, bool]:
    mtime_ns, size = _path_signature(video_path)
    return (str(video_path.resolve()), mtime_ns, size, round(float(duration), 3), load_all_frames)


def _get_cached_video(video_path: Path, duration: float, load_all_frames: bool):
    key = _video_cache_key(video_path, duration, load_all_frames)
    video_info = _VIDEO_CACHE.get(key)
    if video_info is not None:
        _VIDEO_CACHE.move_to_end(key)
    return video_info


def _cache_video(video_path: Path, video_info: Any, requested_duration: float, load_all_frames: bool) -> None:
    # Key on the *requested* duration so lookups (which only know the request)
    # hit even when upstream truncated total_duration to the frame grid.
    key = _video_cache_key(video_path, float(requested_duration), load_all_frames)
    _VIDEO_CACHE[key] = video_info
    _VIDEO_CACHE.move_to_end(key)
    while len(_VIDEO_CACHE) > VIDEO_CACHE_MAX_ITEMS:
        _VIDEO_CACHE.popitem(last=False)


def _torch_compile_available() -> bool:
    # torch.compile on CUDA needs a working Triton; without it the failure is
    # deferred until the first compiled call, which poisons the shared cached
    # model for every later workflow. Check up front instead.
    try:
        from torch.utils._triton import has_triton
        return bool(has_triton())
    except Exception:
        try:
            import triton  # noqa: F401
            return True
        except Exception:
            return False


_STAGED_OFFLOAD_WARNED = False


def _warn_staged_offload_unsupported() -> None:
    global _STAGED_OFFLOAD_WARNED
    if _STAGED_OFFLOAD_WARNED:
        return
    _STAGED_OFFLOAD_WARNED = True
    print(
        "[ControlFoley] Note: the selected ControlFoley source does not accept a "
        "staged_offload parameter (the public upstream source does not implement it); "
        "the staged_offload option is ignored for this source."
    )


def _throw_if_interrupted() -> None:
    try:
        import comfy.model_management as model_management
    except Exception:
        return
    model_management.throw_exception_if_processing_interrupted()


def _interruptible_flow_matching_cls(base_cls):
    class _InterruptibleFlowMatching(base_cls):
        # The upstream euler loop has no interrupt checks, so ComfyUI's Cancel
        # only took effect after the whole sampling loop finished. CUDA kernels
        # are enqueued asynchronously — without a sync the Python loop races
        # through all steps in seconds and the checks pass before the user ever
        # cancels — so wait for the GPU to catch up before checking each step.
        def run_t0_to_t1(self, fn, x0, t0, t1):
            def _checked_fn(t, x):
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                _throw_if_interrupted()
                return fn(t, x)
            return super().run_t0_to_t1(_checked_fn, x0, t0, t1)

    return _InterruptibleFlowMatching


def _import_public_controlfoley(source_dir: Path):
    _ensure_public_controlfoley_repo(source_dir)
    source_text = str(source_dir)
    lib_text = str(source_dir / "lib")
    for entry in [source_text, lib_text]:
        if entry not in sys.path:
            sys.path.insert(0, entry)
    inference_utils = importlib.import_module("controlfoley.inference_utils")
    audio_model = importlib.import_module("controlfoley.audio_model")
    feature_extractor = importlib.import_module("controlfoley.feature_extractor")
    flow_matching = importlib.import_module("lib.flow_matching")
    _patch_bigvgan_from_pretrained()
    torchaudio = importlib.import_module("torchaudio")
    return inference_utils, audio_model, feature_extractor, flow_matching, torchaudio


def _patch_bigvgan_from_pretrained() -> None:
    try:
        bigvgan_module = importlib.import_module("lib.bigvgan_v2.bigvgan")
        bigvgan_cls = bigvgan_module.BigVGAN
        original = bigvgan_cls._from_pretrained
    except Exception as exc:
        print(f"[ControlFoley] BigVGAN compatibility patch not installed: {exc}")
        return

    if getattr(original, "_controlfoley_compat", False):
        return

    def _compat_from_pretrained(*args, **kwargs):
        kwargs.setdefault("proxies", None)
        return original(*args, **kwargs)

    _compat_from_pretrained._controlfoley_compat = True
    bigvgan_cls._from_pretrained = _compat_from_pretrained

def _runtime_cache_key(source_dir: Path, weights_dir: Path, variant: str, device: str, precision: str, low_vram: bool, compile_encoders: bool) -> tuple:
    device = _device_from_choice(device)
    return (str(source_dir), str(weights_dir), variant, f"{device}:{precision}", low_vram, compile_encoders)


def _load_runtime(source_dir: Path, weights_dir: Path, variant: str, device: str, precision: str, low_vram: bool, compile_encoders: bool) -> ControlFoleyRuntime:
    device = _device_from_choice(device)
    if device != "cuda":
        raise RuntimeError(
            "The public ControlFoley inference code currently contains CUDA-only tensor moves. "
            "Use device='cuda' until upstream CPU/MPS support is available."
        )

    key = _runtime_cache_key(source_dir, weights_dir, variant, device, precision, low_vram, compile_encoders)
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    if low_vram:
        _free_vram_for_low_vram_load()

    _ensure_controlfoley_weights(weights_dir)
    _ensure_hf_dependency_cache(low_vram)

    inference_utils, audio_model, feature_extractor, flow_matching, torchaudio = _import_public_controlfoley(source_dir)
    if variant not in inference_utils.all_model_cfg:
        raise ValueError(f"Unknown ControlFoley variant '{variant}'. Available: {list(inference_utils.all_model_cfg)}")

    model_cfg = inference_utils.all_model_cfg[variant]
    model_cfg.model_path = weights_dir / "weights" / "controlfoley.pth"
    if not model_cfg.model_path.exists():
        raise FileNotFoundError(f"Missing model weight: {model_cfg.model_path}")

    ext = weights_dir / "ext_weights"
    required_ext = [
        ext / "v1-44.pth",
        ext / "synchformer_state_dict.pth",
        ext / "cav_mae_st.pth",
        ext / "music_speech_audioset_epoch_15_esc_89.98.pt",
    ]
    missing = [str(p) for p in required_ext if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing external weights from Hugging Face: " + ", ".join(missing))

    dtype = _dtype_from_precision(precision)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    net = audio_model.create_audio_generation_model(model_cfg.model_name).to(device, dtype).eval()
    state = torch.load(model_cfg.model_path, map_location="cpu", weights_only=True)
    net.load_weights(state)
    del state

    original_musicgen = getattr(feature_extractor, "MusicGen", None)
    if low_vram and original_musicgen is not None:
        class _LazySkippedMusicGen:
            @staticmethod
            def get_pretrained(*args, **kwargs):
                return None
        feature_extractor.MusicGen = _LazySkippedMusicGen
    try:
        feature_utils = feature_extractor.FeaturesUtils(
            tod_vae_ckpt=str(ext / "v1-44.pth"),
            synchformer_ckpt=str(ext / "synchformer_state_dict.pth"),
            cav_mae_ckpt=str(ext / "cav_mae_st.pth"),
            clap_ckpt=None if low_vram else str(ext / "music_speech_audioset_epoch_15_esc_89.98.pt"),
            mode=model_cfg.mode,
            enable_conditions=True,
            need_vae_encoder=False,
        ).eval()
        if low_vram:
            feature_utils.to("cpu", dtype)
        else:
            feature_utils.to(device, dtype)
        if compile_encoders:
            if _torch_compile_available():
                feature_utils.compile()
            else:
                print("[ControlFoley] compile_encoders skipped: no working Triton on this platform")
    finally:
        if low_vram and original_musicgen is not None:
            feature_extractor.MusicGen = original_musicgen

    _patch_timbre_dtype_alignment(net)

    runtime = ControlFoleyRuntime(
        source_dir=source_dir,
        weights_dir=weights_dir,
        variant=variant,
        device=device,
        dtype=dtype,
        precision=precision,
        low_vram=low_vram,
        model_cfg=model_cfg,
        seq_cfg=model_cfg.seq_cfg,
        net=net,
        feature_utils=feature_utils,
        flow_matching_cls=_interruptible_flow_matching_cls(flow_matching.FlowMatching),
        inference_utils=inference_utils,
        torchaudio=torchaudio,
        compile_encoders=compile_encoders,
    )
    _MODEL_CACHE[key] = runtime
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return runtime


def _load_reference_audio(runtime: ControlFoleyRuntime, audio_path: Optional[Path]):
    if audio_path is None:
        return None, None, 0.0

    try:
        audio_frames, sampling_rate = runtime.torchaudio.load(audio_path)
    except ImportError as exc:
        if "TorchCodec" not in str(exc):
            raise
        import soundfile as sf
        array, sampling_rate = sf.read(str(audio_path), always_2d=True, dtype="float32")
        audio_frames = torch.from_numpy(array).transpose(0, 1).contiguous()
    audio_frames = audio_frames.to(runtime.device, torch.float32)
    timbre_frames = audio_frames.clone()

    if sampling_rate != 16000:
        audio_frames = runtime.torchaudio.functional.resample(audio_frames, sampling_rate, 16000)
    audio_frames = audio_frames.mean(dim=0, keepdim=True).reshape(1, -1).unsqueeze(0).to(runtime.device, runtime.dtype)

    if sampling_rate != 32000:
        timbre_frames = runtime.torchaudio.functional.resample(timbre_frames, sampling_rate, 32000)
    target_sr = 32000
    min_len = 2 * target_sr
    max_len = 4 * target_sr
    num_samples = timbre_frames.shape[-1]
    if num_samples < min_len:
        timbre_frames = torch.nn.functional.pad(timbre_frames, (0, min_len - num_samples), mode="constant", value=0)
    elif num_samples > max_len:
        timbre_frames = timbre_frames[..., :max_len]
    timbre_duration = timbre_frames.shape[-1] / target_sr
    timbre_frames = timbre_frames.mean(dim=0, keepdim=True).reshape(1, -1).unsqueeze(0).to(runtime.device, runtime.dtype)
    return audio_frames, timbre_frames, timbre_duration


def _runtime_sample_rate(runtime: Optional[ControlFoleyRuntime]) -> int:
    if runtime is not None and getattr(runtime, "seq_cfg", None) is not None:
        sample_rate = getattr(runtime.seq_cfg, "audio_sample_rate", None)
        if sample_rate:
            return int(sample_rate)
    return 44100


def _make_silent_audio(duration: float, sample_rate: int = 44100):
    samples = max(1, int(round(float(duration) * int(sample_rate))))
    return {"waveform": torch.zeros((1, 1, samples), dtype=torch.float32), "sample_rate": int(sample_rate)}


def _coerce_int_param(value, default: int, minimum: int, maximum: int, name: str) -> int:
    if value is None:
        return int(default)
    text = str(value).strip().lower()
    if text == "" or text == FIXED_STEP_SENTINEL:
        return int(default)
    try:
        parsed = int(float(text))
    except Exception as exc:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}, or '{FIXED_STEP_SENTINEL}', got {value!r}.") from exc
    return max(int(minimum), min(int(maximum), parsed))


def _resolve_inference_steps(value) -> int:
    if value is None:
        return DEFAULT_INFERENCE_STEPS
    text = str(value).strip().lower()
    if text == "" or text == FIXED_STEP_SENTINEL:
        return DEFAULT_INFERENCE_STEPS
    return _coerce_int_param(value, DEFAULT_INFERENCE_STEPS, 1, 100, "num_inference_steps")


def _resolve_reference_audio_path(value) -> Optional[Path]:
    text = str(value or "").strip().strip('"')
    if not text:
        return None
    if text in {"24", "24.0"}:
        print("[ControlFoley] Ignoring stale reference_audio_path value from an old workflow: 24")
        return None
    resolved = _resolve_path(text)
    if resolved is None or not resolved.exists():
        raise FileNotFoundError(f"Reference audio not found: {text}")
    if not resolved.is_file():
        raise ValueError(f"Reference audio path must be a file, not a directory: {text}")
    return resolved


def _relative_to(path: Path, root: Path) -> Optional[Path]:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return None


def _comfy_temp_dir() -> Path:
    if folder_paths is not None:
        return Path(folder_paths.get_temp_directory())
    return Path.cwd() / "temp"


def _ui_file_entry(path: Path, file_type: str = "output") -> dict[str, str]:
    if file_type == "input":
        base = _input_dir()
    elif file_type == "temp":
        base = _comfy_temp_dir()
    else:
        base = _output_dir()
    rel = _relative_to(path, base)
    subfolder = str(rel.parent).replace("\\", "/") if rel is not None and str(rel.parent) != "." else ""
    return {"filename": path.name, "subfolder": subfolder, "type": file_type}


def _preview_video_path(path: Path) -> Path:
    if _relative_to(path, _output_dir()) is not None or _relative_to(path, _input_dir()) is not None:
        return path
    # Files outside output/input (e.g. the bundled demo media) are copied into the
    # ComfyUI temp directory so /view can serve them; temp is cleared on restart,
    # so preview copies never accumulate in the user's output folder.
    mtime_ns, size = _path_signature(path)
    preview_dir = _comfy_temp_dir() / "controlfoley_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / f"{path.stem}_{size}_{mtime_ns}{path.suffix}"
    if not preview_path.exists():
        shutil.copyfile(path, preview_path)
    return preview_path


def _video_ui(path: Path) -> dict[str, Any]:
    # Mirrors the dict emitted by ComfyUI's own video save/preview nodes
    # (ui.PreviewVideo): the stock frontend only renders video results from the
    # "images" + "animated" keys; the VHS-style "gifs" key is ignored.
    preview_path = _preview_video_path(path)
    if _relative_to(preview_path, _input_dir()) is not None:
        file_type = "input"
    elif _relative_to(preview_path, _output_dir()) is not None:
        file_type = "output"
    else:
        file_type = "temp"
    entry = _ui_file_entry(preview_path, file_type)
    return {"images": [entry], "animated": (True,)}


def _audio_ui(path: Path) -> dict[str, list[dict[str, str]]]:
    return {"audio": [_ui_file_entry(path, "output")]}


class LoadControlFoleyDependencies:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "controlfoley_source_dir": ("STRING", {"default": DEFAULT_CONTROLFOLEY_SOURCE_DIR}),
                "model_weights_dir": ("STRING", {"default": DEFAULT_MODEL_WEIGHTS_DIR}),
                "low_vram": ("BOOLEAN", {"default": False}),
                "auto_download": ("BOOLEAN", {"default": True}),
                "auto_fetch_source": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "When the public ControlFoley source tree is not found locally, run 'git clone' "
                               "(pinned revision) from GitHub into <ComfyUI root>/controlfoley. "
                               "Set the CONTROLFOLEY_SOURCE_URL environment variable to use a mirror.",
                }),
            }
        }

    RETURN_TYPES = (CONTROLFOLEY_DEPENDENCIES_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("controlfoley_dependencies", "weights_dir", "status")
    FUNCTION = "load_dependencies"
    CATEGORY = CATEGORY

    def load_dependencies(self, controlfoley_source_dir, model_weights_dir, low_vram, auto_download, auto_fetch_source=True):
        source_dir = _resolve_source_dir_with_auto_fetch(controlfoley_source_dir, bool(auto_fetch_source))
        weights_dir = _resolve_weights_dir(model_weights_dir)
        if source_dir is None:
            raise ValueError("ControlFoley source directory is required.")
        _ensure_public_controlfoley_repo(source_dir)
        if auto_download:
            _ensure_controlfoley_weights(weights_dir)
            _ensure_hf_dependency_cache(bool(low_vram))
        deps = ControlFoleyDependencies(source_dir=source_dir, weights_dir=weights_dir, low_vram=bool(low_vram))
        status = f"ControlFoley dependencies ready: weights={weights_dir}, low_vram={bool(low_vram)}"
        return (deps, str(weights_dir), status)


class LoadControlFoleyModel:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "controlfoley_source_dir": ("STRING", {"default": DEFAULT_CONTROLFOLEY_SOURCE_DIR}),
                "model_weights_dir": ("STRING", {"default": DEFAULT_MODEL_WEIGHTS_DIR}),
                "variant": (["large_44k"],),
                "device": (["auto", "cuda"], {"default": "auto"}),
                "precision": (["bf16", "fp16", "fp32"], {"default": "bf16"}),
                "low_vram": ("BOOLEAN", {"default": False}),
                "compile_encoders": ("BOOLEAN", {"default": False}),
                "auto_fetch_source": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "When the public ControlFoley source tree is not found locally, run 'git clone' "
                               "(pinned revision) from GitHub into <ComfyUI root>/controlfoley. "
                               "Set the CONTROLFOLEY_SOURCE_URL environment variable to use a mirror.",
                }),
            },
            "optional": {
                "dependencies": (CONTROLFOLEY_DEPENDENCIES_TYPE,),
            },
        }

    RETURN_TYPES = (CONTROLFOLEY_MODEL_TYPE,)
    RETURN_NAMES = ("controlfoley_model",)
    FUNCTION = "load"
    CATEGORY = CATEGORY

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        # Force a re-load after any unload; otherwise the executor could hand
        # downstream nodes a stale, already-unloaded runtime. Widget changes are
        # covered by the executor's normal input comparison.
        return f"unload_epoch:{_UNLOAD_EPOCH}"

    def load(self, controlfoley_source_dir, model_weights_dir, variant, device, precision, low_vram, compile_encoders, auto_fetch_source=True, dependencies=None):
        if dependencies is not None:
            source_dir = dependencies.source_dir
            weights_dir = dependencies.weights_dir
            low_vram = dependencies.low_vram
        else:
            source_dir = _resolve_source_dir_with_auto_fetch(controlfoley_source_dir, bool(auto_fetch_source))
            weights_dir = _resolve_weights_dir(model_weights_dir)
        if source_dir is None:
            raise ValueError("ControlFoley source and weights directories are required.")
        runtime = _load_runtime(source_dir, weights_dir, variant, device, precision, low_vram, compile_encoders)
        return (runtime,)


class ControlFoleyTorchCompile:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "controlfoley_model": (CONTROLFOLEY_MODEL_TYPE,),
                "compile_encoders": ("BOOLEAN", {"default": True}),
                "compile_generator": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = (CONTROLFOLEY_MODEL_TYPE, "STRING")
    RETURN_NAMES = ("controlfoley_model", "status")
    FUNCTION = "compile"
    CATEGORY = CATEGORY

    def compile(self, controlfoley_model, compile_encoders, compile_generator):
        runtime: ControlFoleyRuntime = controlfoley_model
        messages = []
        if (compile_encoders or compile_generator) and not _torch_compile_available():
            # Compiling without Triton would defer a TritonMissing crash into the
            # first generation and poison the shared cached model for later runs.
            message = "torch.compile skipped: no working Triton on this platform"
            print(f"[ControlFoley] {message}")
            return (runtime, message)
        if compile_encoders and hasattr(runtime.feature_utils, "compile"):
            runtime.feature_utils.compile()
            messages.append("feature encoders compiled")
        if compile_generator:
            try:
                runtime.net = torch.compile(runtime.net)
                messages.append("generator compiled")
            except Exception as exc:
                messages.append(f"generator compile skipped: {exc}")
        if not messages:
            messages.append("nothing to compile")
        return (runtime, "; ".join(messages))


class ControlFoleyGenerateAdvanced:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "controlfoley_model": (CONTROLFOLEY_MODEL_TYPE,),
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True}),
                "duration": ("FLOAT", {"default": DEFAULT_TEXT_ONLY_DURATION, "min": MIN_VIDEO_DURATION, "max": MAX_GENERATION_DURATION, "step": 0.5, "tooltip": "Text-only generation uses 10s by default. Video generation follows input length up to 30s."}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 0xFFFFFFFF}),
                "num_inference_steps": ("STRING", {"default": FIXED_STEP_SENTINEL, "tooltip": "Use 'fixed' to keep the default step setting, or enter an integer from 1 to 100."}),
                "guidance_scale": ("FLOAT", {"default": 4.5, "min": 0.0, "max": 20.0, "step": 0.1}),
                "mask_away_clip": ("BOOLEAN", {"default": False}),
                "cache_video_features": ("BOOLEAN", {"default": True}),
                "staged_offload": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Move encoders to CPU during sampling when the ControlFoley source supports it. "
                               "The public upstream source does not implement this; the option is then ignored "
                               "and a console note is printed.",
                }),
                "clip_batch_size_multiplier": ("STRING", {
                    "default": "40",
                    "tooltip": "Integer 1-80. Frames per CLIP encoder call = batch size * multiplier. Use 4-8 on low-VRAM GPUs.",
                }),
                "sync_batch_size_multiplier": ("STRING", {
                    "default": "40",
                    "tooltip": "Integer 1-80. Frames per Synchformer encoder call = batch size * multiplier. Use 4-8 on low-VRAM GPUs.",
                }),
                "enabled": ("BOOLEAN", {"default": True}),
                "silent_audio_on_error": ("BOOLEAN", {"default": False}),
                "reference_audio_path": ("STRING", {"default": ""}),
                "image_fps": ("FLOAT", {
                    "default": 24.0,
                    "min": 1.0,
                    "max": 120.0,
                    "step": 1.0,
                    "tooltip": "Frame rate used when the optional IMAGE input is connected.",
                }),
            },
            "optional": {
                "video": (CONTROLFOLEY_VIDEO_TYPE,),
                "video_input": ("VIDEO",),
                "images": ("IMAGE",),
            }
        }

    RETURN_TYPES = (AUDIO_TYPE, "INT", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "sample_rate", "inference_time_sec", "peak_vram_gb", "status")
    FUNCTION = "generate_audio"
    CATEGORY = CATEGORY

    def generate_audio(self, controlfoley_model, prompt, negative_prompt, duration, seed, num_inference_steps,
                       guidance_scale, mask_away_clip, cache_video_features, staged_offload,
                       clip_batch_size_multiplier=40, sync_batch_size_multiplier=40,
                       enabled=True, silent_audio_on_error=False,
                       video=None, video_input=None, images=None, reference_audio_path="", image_fps=24.0):
        runtime: ControlFoleyRuntime = controlfoley_model
        if not enabled:
            silent = _make_silent_audio(float(duration), _runtime_sample_rate(runtime))
            return (silent, int(silent["sample_rate"]), 0.0, 0.0, "Generation disabled; returned silence.")
        try:
            audio, sample_rate, inference_time, peak_vram = ControlFoleyGenerate().generate_audio(
                controlfoley_model, prompt, negative_prompt, duration, seed, num_inference_steps,
                guidance_scale, mask_away_clip, cache_video_features, staged_offload,
                clip_batch_size_multiplier, sync_batch_size_multiplier,
                video, video_input, images, reference_audio_path, image_fps,
            )
            return (audio, sample_rate, inference_time, peak_vram, "Generation completed successfully.")
        except Exception as exc:
            if not silent_audio_on_error:
                raise
            silent = _make_silent_audio(float(duration), _runtime_sample_rate(runtime))
            return (silent, int(silent["sample_rate"]), 0.0, 0.0, f"Generation failed; returned silence: {exc}")


class ControlFoleySimpleGenerate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "controlfoley_source_dir": ("STRING", {"default": DEFAULT_CONTROLFOLEY_SOURCE_DIR}),
                "model_weights_dir": ("STRING", {"default": DEFAULT_MODEL_WEIGHTS_DIR}),
                "variant": (["large_44k"],),
                "device": (["auto", "cuda"], {"default": "auto"}),
                "precision": (["bf16", "fp16", "fp32"], {"default": "bf16"}),
                "low_vram": ("BOOLEAN", {"default": False}),
                "compile_encoders": ("BOOLEAN", {"default": False}),
                "prompt": ("STRING", {"default": DEFAULT_TEXT_PROMPT, "multiline": True}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True}),
                "duration": ("FLOAT", {"default": DEFAULT_TEXT_ONLY_DURATION, "min": MIN_VIDEO_DURATION, "max": MAX_GENERATION_DURATION, "step": 0.5, "tooltip": "Text-only generation uses 10s by default. Video generation follows input length up to 30s."}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 0xFFFFFFFF}),
                "num_inference_steps": ("STRING", {"default": FIXED_STEP_SENTINEL, "tooltip": "Use 'fixed' to keep the default step setting, or enter an integer from 1 to 100."}),
                "guidance_scale": ("FLOAT", {"default": 4.5, "min": 0.0, "max": 20.0, "step": 0.1}),
                "mask_away_clip": ("BOOLEAN", {"default": False}),
                "cache_video_features": ("BOOLEAN", {"default": True}),
                "staged_offload": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Move encoders to CPU during sampling when the ControlFoley source supports it. "
                               "The public upstream source does not implement this; the option is then ignored "
                               "and a console note is printed.",
                }),
                "clip_batch_size_multiplier": ("STRING", {
                    "default": "40",
                    "tooltip": "Integer 1-80. Use 4-8 on low-VRAM GPUs.",
                }),
                "sync_batch_size_multiplier": ("STRING", {
                    "default": "40",
                    "tooltip": "Integer 1-80. Use 4-8 on low-VRAM GPUs.",
                }),
                "reference_audio_path": ("STRING", {"default": ""}),
                "image_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 1.0}),
                "enabled": ("BOOLEAN", {"default": True}),
                "silent_audio_on_error": ("BOOLEAN", {"default": False}),
                "auto_fetch_source": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "When the public ControlFoley source tree is not found locally, run 'git clone' "
                               "(pinned revision) from GitHub into <ComfyUI root>/controlfoley. "
                               "Set the CONTROLFOLEY_SOURCE_URL environment variable to use a mirror.",
                }),
            },
            "optional": {
                "video": (CONTROLFOLEY_VIDEO_TYPE,),
                "video_input": ("VIDEO",),
                "images": ("IMAGE",),
            },
        }

    RETURN_TYPES = (AUDIO_TYPE, "INT", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("audio", "sample_rate", "inference_time_sec", "peak_vram_gb", "status")
    FUNCTION = "generate"
    CATEGORY = CATEGORY

    def generate(self, controlfoley_source_dir, model_weights_dir, variant, device, precision, low_vram, compile_encoders,
                 prompt, negative_prompt, duration, seed, num_inference_steps, guidance_scale, mask_away_clip,
                 cache_video_features, staged_offload, clip_batch_size_multiplier=40, sync_batch_size_multiplier=40,
                 video=None, video_input=None, images=None, reference_audio_path="", image_fps=24.0,
                 enabled=True, silent_audio_on_error=False, auto_fetch_source=True):
        if not enabled:
            silent = _make_silent_audio(float(duration), 44100)
            return (silent, int(silent["sample_rate"]), 0.0, 0.0, "Generation disabled; returned silence.")
        dependencies = ControlFoleyDependencies(
            source_dir=_resolve_source_dir_with_auto_fetch(controlfoley_source_dir, bool(auto_fetch_source)) or Path(controlfoley_source_dir),
            weights_dir=_resolve_weights_dir(model_weights_dir),
            low_vram=bool(low_vram),
        )
        model = _load_runtime(dependencies.source_dir, dependencies.weights_dir, variant, device, precision, low_vram, compile_encoders)
        return ControlFoleyGenerateAdvanced().generate_audio(
            model, prompt, negative_prompt, duration, seed, num_inference_steps, guidance_scale,
            mask_away_clip, cache_video_features, staged_offload,
            clip_batch_size_multiplier, sync_batch_size_multiplier,
            enabled, silent_audio_on_error,
            video, video_input, images, reference_audio_path, image_fps,
        )


class LoadControlFoleyVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {"default": DEFAULT_DEMO_VIDEO_PATH}),
                "duration": ("FLOAT", {"default": DEFAULT_VIDEO_DURATION, "min": MIN_VIDEO_DURATION, "max": MAX_GENERATION_DURATION, "step": 0.5, "tooltip": "Upper limit for video generation. The actual output follows the input video length up to 30s."}),
            }
        }

    RETURN_TYPES = (CONTROLFOLEY_VIDEO_TYPE, "STRING", "VIDEO")
    RETURN_NAMES = ("controlfoley_video", "video_path", "video_output")
    FUNCTION = "load"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY

    @classmethod
    def IS_CHANGED(cls, video_path, duration):
        resolved = _resolve_path(video_path)
        if resolved is None or not resolved.exists():
            return float("nan")
        mtime_ns, size = _path_signature(resolved)
        return f"{resolved}:{mtime_ns}:{size}:{float(duration)}"

    @staticmethod
    def _native_video_output(path: Path):
        try:
            from comfy_api.latest import InputImpl
        except Exception as exc:
            print(f"[ControlFoley] Native VIDEO output unavailable in this ComfyUI version: {exc}")
            return None
        return InputImpl.VideoFromFile(str(path))

    def load(self, video_path, duration):
        resolved = _resolve_path(video_path)
        if resolved is None or not resolved.exists():
            raise FileNotFoundError(f"Input video not found: {video_path}")
        if not resolved.is_file():
            raise ValueError(f"Input video path must be a file, not a directory: {video_path}")
        source_duration = _media_duration(resolved)
        effective_duration = _bounded_duration(source_duration or duration, float(duration))
        result = ({"path": resolved, "duration": effective_duration}, str(resolved), self._native_video_output(resolved))
        return {"ui": _video_ui(resolved), "result": result}


class ControlFoleyGenerate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "controlfoley_model": (CONTROLFOLEY_MODEL_TYPE,),
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True}),
                "duration": ("FLOAT", {"default": DEFAULT_TEXT_ONLY_DURATION, "min": MIN_VIDEO_DURATION, "max": MAX_GENERATION_DURATION, "step": 0.5, "tooltip": "Text-only generation uses 10s by default. Video generation follows input length up to 30s."}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 0xFFFFFFFF}),
                "num_inference_steps": ("STRING", {"default": FIXED_STEP_SENTINEL, "tooltip": "Use 'fixed' to keep the default step setting, or enter an integer from 1 to 100."}),
                "guidance_scale": ("FLOAT", {"default": 4.5, "min": 0.0, "max": 20.0, "step": 0.1}),
                "mask_away_clip": ("BOOLEAN", {"default": False}),
                "cache_video_features": ("BOOLEAN", {"default": True}),
                "staged_offload": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Move encoders to CPU during sampling when the ControlFoley source supports it. "
                               "The public upstream source does not implement this; the option is then ignored "
                               "and a console note is printed.",
                }),
                "clip_batch_size_multiplier": ("STRING", {
                    "default": "40",
                    "tooltip": "Integer 1-80. Frames per CLIP encoder call = batch size * multiplier. Use 4-8 on low-VRAM GPUs.",
                }),
                "sync_batch_size_multiplier": ("STRING", {
                    "default": "40",
                    "tooltip": "Integer 1-80. Frames per Synchformer encoder call = batch size * multiplier. Use 4-8 on low-VRAM GPUs.",
                }),
                "reference_audio_path": ("STRING", {"default": ""}),
                "image_fps": ("FLOAT", {
                    "default": 24.0,
                    "min": 1.0,
                    "max": 120.0,
                    "step": 1.0,
                    "tooltip": "Frame rate used when the optional IMAGE input is connected.",
                }),
            },
            "optional": {
                "video": (CONTROLFOLEY_VIDEO_TYPE,),
                "video_input": ("VIDEO",),
                "images": ("IMAGE",),
            }
        }

    RETURN_TYPES = (AUDIO_TYPE, "INT", "FLOAT", "FLOAT")
    RETURN_NAMES = ("audio", "sample_rate", "inference_time_sec", "peak_vram_gb")
    FUNCTION = "generate_audio"
    CATEGORY = CATEGORY

    @classmethod
    def IS_CHANGED(cls, controlfoley_model, prompt, negative_prompt, duration, seed, num_inference_steps,
                   guidance_scale, mask_away_clip, cache_video_features, staged_offload,
                   clip_batch_size_multiplier=40, sync_batch_size_multiplier=40,
                   video=None, video_input=None, images=None, reference_audio_path="", image_fps=24.0):
        if video_input is not None or images is not None:
            return float("nan")
        parts = [prompt or "", negative_prompt or "", str(duration), str(seed), str(num_inference_steps),
                 str(guidance_scale), str(mask_away_clip), str(cache_video_features), str(staged_offload),
                 str(clip_batch_size_multiplier), str(sync_batch_size_multiplier), str(image_fps)]
        if reference_audio_path and str(reference_audio_path).strip() not in {"24", "24.0"}:
            resolved = _resolve_path(reference_audio_path)
            if resolved is None or not resolved.exists():
                return float("nan")
            mtime_ns, size = _path_signature(resolved)
            parts.append(f"{resolved}:{mtime_ns}:{size}")
        return "|".join(parts)

    def generate_audio(self, controlfoley_model, prompt, negative_prompt, duration, seed, num_inference_steps,
                       guidance_scale, mask_away_clip, cache_video_features, staged_offload,
                       clip_batch_size_multiplier=40, sync_batch_size_multiplier=40,
                       video=None, video_input=None, images=None, reference_audio_path="", image_fps=24.0):
        runtime: ControlFoleyRuntime = controlfoley_model
        if runtime.net is None or runtime.feature_utils is None:
            raise RuntimeError(
                "This ControlFoley model was unloaded. Re-run the ControlFoley Model Loader "
                "(or restart ComfyUI) to load it again."
            )
        if runtime.device != "cuda":
            raise RuntimeError("ControlFoley public inference is currently CUDA-only in this node.")
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()

        clip_batch_size_multiplier = _coerce_int_param(
            clip_batch_size_multiplier, 40, 1, 80, "clip_batch_size_multiplier"
        )
        sync_batch_size_multiplier = _coerce_int_param(
            sync_batch_size_multiplier, 40, 1, 80, "sync_batch_size_multiplier"
        )

        ref_path = _resolve_reference_audio_path(reference_audio_path)
        video = _select_generation_video(video, video_input, images, float(duration), float(image_fps))
        duration = _resolve_generation_duration(float(duration), video)
        if duration < MIN_VIDEO_DURATION:
            raise ValueError(f"duration must be at least {MIN_VIDEO_DURATION:.1f}s.")
        if runtime.low_vram and video is not None:
            raise ValueError("low_vram mode keeps video encoders on CPU; use low_vram=False for V2A/TC-V2A.")
        if runtime.low_vram and ref_path is not None:
            raise ValueError("low_vram mode disables CLAP/MusicGen; AC-V2A requires low_vram=False.")

        video_info = None
        clip_frames = visual_frames = sync_frames = None
        audio_frames = timbre_frames = fm = generator = audios = None
        try:
            if runtime.low_vram:
                _free_vram_for_low_vram_load()

            if video is not None:
                video_path = Path(video["path"])
                requested_duration = duration
                if requested_duration < MIN_VIDEO_DURATION:
                    raise ValueError(f"video duration must be at least {MIN_VIDEO_DURATION:.1f}s.")
                if cache_video_features:
                    video_info = _get_cached_video(video_path, requested_duration, False)
                else:
                    video_info = None
                if video_info is None:
                    video_info = runtime.inference_utils.load_video(video_path, requested_duration, load_all_frames=False)
                    if cache_video_features:
                        _cache_video(video_path, video_info, requested_duration, False)
                if video_info.total_duration < duration:
                    duration = video_info.total_duration
                clip_frames = None if mask_away_clip else video_info.clip_embeddings.unsqueeze(0)
                visual_frames = video_info.visual_features.unsqueeze(0)
                sync_frames = video_info.sync_embeddings.unsqueeze(0)

            audio_frames, timbre_frames, timbre_duration = _load_reference_audio(runtime, ref_path)

            runtime.seq_cfg.total_time_seconds = float(duration)
            runtime.net.update_seq_lengths(
                runtime.seq_cfg.latent_sequence_length,
                runtime.seq_cfg.clip_sequence_length,
                runtime.seq_cfg.visual_sequence_length,
                runtime.seq_cfg.sync_sequence_length,
            )
            generator = torch.Generator(device=runtime.feature_utils.device)
            generator.manual_seed(int(seed))
            fm = runtime.flow_matching_cls(min_sigma=0, inference_mode="euler", num_steps=_resolve_inference_steps(num_inference_steps))

            generate_kwargs = {
                "negative_text": [negative_prompt or ""],
                "feature_utils": runtime.feature_utils,
                "net": runtime.net,
                "fm": fm,
                "rng": generator,
                "cfg_strength": float(guidance_scale),
            }
            generate_params = inspect.signature(runtime.inference_utils.generate).parameters
            supports_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in generate_params.values())
            supports_staged_offload = "staged_offload" in generate_params or supports_kwargs
            supports_clip_batch = "clip_batch_size_multiplier" in generate_params or supports_kwargs
            supports_sync_batch = "sync_batch_size_multiplier" in generate_params or supports_kwargs
            if supports_staged_offload:
                generate_kwargs["staged_offload"] = bool(staged_offload or runtime.low_vram)
            elif staged_offload:
                _warn_staged_offload_unsupported()
            if supports_clip_batch:
                generate_kwargs["clip_batch_size_multiplier"] = int(clip_batch_size_multiplier)
            if supports_sync_batch:
                generate_kwargs["sync_batch_size_multiplier"] = int(sync_batch_size_multiplier)
            if (not supports_clip_batch and int(clip_batch_size_multiplier) != 40) or (
                not supports_sync_batch and int(sync_batch_size_multiplier) != 40
            ):
                raise RuntimeError(
                    "The selected ControlFoley source does not support encoder batch-size multipliers. "
                    "Use the optimized ControlFoley source or reset both multipliers to 40."
                )

            start = time.time()
            with torch.inference_mode():
                audios = runtime.inference_utils.generate(
                    clip_frames,
                    visual_frames,
                    sync_frames,
                    audio_frames,
                    timbre_frames,
                    timbre_duration,
                    [prompt or ""],
                    **generate_kwargs,
                )
            elapsed = time.time() - start
            waveform = audios.float().cpu()[0]
            if waveform.ndim == 1:
                waveform = waveform.unsqueeze(0)
            comfy_audio = {"waveform": waveform.unsqueeze(0), "sample_rate": int(runtime.seq_cfg.audio_sample_rate)}
            peak_vram = 0.0
            if torch.cuda.is_available():
                peak_vram = torch.cuda.max_memory_allocated() / (2 ** 30)
            return (comfy_audio, int(runtime.seq_cfg.audio_sample_rate), float(elapsed), float(peak_vram))
        finally:
            del clip_frames, visual_frames, sync_frames, audio_frames, timbre_frames, fm, generator, audios
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()


class SaveControlFoleyAudio:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": (AUDIO_TYPE,),
                "filename_prefix": ("STRING", {"default": "controlfoley/output"}),
                "format": (["wav", "flac"], {"default": "wav"}),
            },
            # The stock frontend only auto-creates an audio player for a hard-coded
            # list of core node classes; custom nodes must declare the AUDIO_UI
            # widget themselves for the ui.audio result to get a player.
            "optional": {
                "audioUI": ("AUDIO_UI",),
            },
        }

    RETURN_TYPES = (AUDIO_TYPE, CONTROLFOLEY_AUDIO_FILE_TYPE, "STRING")
    RETURN_NAMES = ("audio", "audio_file", "audio_path")
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY

    @classmethod
    def IS_CHANGED(cls, audio, filename_prefix, format, audioUI=None):
        return time.time_ns()

    def save(self, audio, filename_prefix, format, audioUI=None):
        import soundfile as sf
        out_dir = _output_dir()
        relative = _safe_path(filename_prefix, "controlfoley/output", f".{format}")
        full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            str(relative.with_suffix("")), str(out_dir)
        )
        path = Path(full_output_folder) / f"{filename}_{counter:05}_.{format}"
        waveform = audio["waveform"]
        if waveform.ndim == 3:
            waveform = waveform[0]
        array = waveform.detach().cpu().transpose(0, 1).numpy()
        sf.write(str(path), array, int(audio["sample_rate"]))
        saved_audio = dict(audio)
        saved_audio["stem"] = str(path.with_suffix(""))
        result = (
            saved_audio,
            {"path": path, "sample_rate": int(audio["sample_rate"]), "stem": str(path.with_suffix(""))},
            str(path),
        )
        return {"ui": _audio_ui(path), "result": result}


class MuxControlFoleyAudioToVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "controlfoley_model": (CONTROLFOLEY_MODEL_TYPE,),
                "video": (CONTROLFOLEY_VIDEO_TYPE,),
                "audio": (AUDIO_TYPE,),
                "output_filename": ("STRING", {"default": "controlfoley/output.mp4"}),
                "mode": (["replace", "mix_planned"], {"default": "replace"}),
            }
        }

    RETURN_TYPES = (CONTROLFOLEY_VIDEO_FILE_TYPE, "STRING")
    RETURN_NAMES = ("video_file", "video_path")
    FUNCTION = "mux"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY

    @classmethod
    def IS_CHANGED(cls, controlfoley_model, video, audio, output_filename, mode):
        return time.time_ns()

    def mux(self, controlfoley_model, video, audio, output_filename, mode):
        if mode != "replace":
            raise NotImplementedError("First release supports replace original audio only. Mix is planned.")
        runtime: ControlFoleyRuntime = controlfoley_model
        video_path = Path(video["path"])
        waveform = audio["waveform"]
        if waveform.ndim == 3:
            waveform = waveform[0]
        if waveform.ndim == 2 and waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        audio_duration = waveform.shape[-1] / int(audio["sample_rate"])
        duration = min(float(video.get("duration", audio_duration)), float(audio_duration))
        video_info = _get_cached_video(video_path, duration, True)
        if video_info is None:
            video_info = runtime.inference_utils.load_video(video_path, duration, load_all_frames=True)
            _cache_video(video_path, video_info, duration, True)
        relative = _safe_path(output_filename, "controlfoley/output.mp4", ".mp4")
        audio_stem = audio.get("stem") if isinstance(audio, dict) else None
        if audio_stem:
            out_path = Path(audio_stem).with_suffix(".mp4")
        else:
            full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
                str(relative.with_suffix("")), str(_output_dir())
            )
            out_path = Path(full_output_folder) / f"{filename}_{counter:05}_.mp4"
        runtime.inference_utils.make_video(video_info, out_path, waveform.cpu(), int(audio["sample_rate"]))
        result = ({"path": out_path}, str(out_path))
        return {"ui": _video_ui(out_path), "result": result}


class UnloadControlFoleyModel:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"controlfoley_model": (CONTROLFOLEY_MODEL_TYPE,)},
            "optional": {"after": (AUDIO_TYPE,)},
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "unload"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY

    def unload(self, controlfoley_model, after=None):
        global _UNLOAD_EPOCH
        if after is None:
            return ("Connect the after input to unload after generation",)
        keys = [k for k, v in _MODEL_CACHE.items() if v is controlfoley_model]
        for key in keys:
            _MODEL_CACHE.pop(key, None)
        _UNLOAD_EPOCH += 1
        # Popping the cache alone does not free VRAM: ComfyUI's execution cache
        # still references the runtime object, so drop its tensors explicitly.
        # (The loader's IS_CHANGED forces a re-load before the gutted runtime
        # could reach a generation node again.)
        controlfoley_model.unload()
        _VIDEO_CACHE.clear()
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return ("ControlFoley model cache cleared",)


NODE_CLASS_MAPPINGS = {
    "LoadControlFoleyDependencies": LoadControlFoleyDependencies,
    "LoadControlFoleyModel": LoadControlFoleyModel,
    "ControlFoleyTorchCompile": ControlFoleyTorchCompile,
    "LoadControlFoleyVideo": LoadControlFoleyVideo,
    "ControlFoleyGenerate": ControlFoleyGenerate,
    "ControlFoleyGenerateAdvanced": ControlFoleyGenerateAdvanced,
    "ControlFoleySimpleGenerate": ControlFoleySimpleGenerate,
    "SaveControlFoleyAudio": SaveControlFoleyAudio,
    "MuxControlFoleyAudioToVideo": MuxControlFoleyAudioToVideo,
    "UnloadControlFoleyModel": UnloadControlFoleyModel,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadControlFoleyDependencies": "ControlFoley Dependencies Loader",
    "LoadControlFoleyModel": "ControlFoley Model Loader",
    "ControlFoleyTorchCompile": "ControlFoley Torch Compile",
    "LoadControlFoleyVideo": "ControlFoley Video Loader",
    "ControlFoleyGenerate": "ControlFoley Generate",
    "ControlFoleyGenerateAdvanced": "ControlFoley Advanced Generate",
    "ControlFoleySimpleGenerate": "ControlFoley Simple Generate",
    "SaveControlFoleyAudio": "ControlFoley Save Audio",
    "MuxControlFoleyAudioToVideo": "ControlFoley Video-Audio Muxer",
    "UnloadControlFoleyModel": "ControlFoley Model Unloader",
}
