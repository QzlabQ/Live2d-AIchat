from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = BACKEND_ROOT.parent
PUBLIC_ROOT = APP_ROOT / "frontend" / "public"
LIVE2D_ROOT = PUBLIC_ROOT / "live2d"
PREFERRED_LIVE2D_MODEL_PATH = "/live2d/haru/haru_greeter_t03.model3.json"


@dataclass(frozen=True, slots=True)
class Live2DModelEntry:
    web_path: str
    label: str


def discover_live2d_model_entries(live2d_root: Path = LIVE2D_ROOT) -> list[Live2DModelEntry]:
    if not live2d_root.exists():
        return []

    entries: list[Live2DModelEntry] = []
    public_root = live2d_root.parent
    for model_path in sorted(live2d_root.rglob("*.model3.json")):
        web_path = "/" + str(model_path.relative_to(public_root)).replace("\\", "/")
        entries.append(Live2DModelEntry(web_path=web_path, label=model_path.parent.name))
    return entries


def discover_live2d_model_paths(live2d_root: Path = LIVE2D_ROOT) -> list[str]:
    return [entry.web_path for entry in discover_live2d_model_entries(live2d_root)]


def pick_default_live2d_model_path(
    available_paths: Iterable[str],
    *,
    preferred_path: str = PREFERRED_LIVE2D_MODEL_PATH,
) -> str:
    paths = list(available_paths)
    if preferred_path in paths:
        return preferred_path
    if paths:
        return paths[0]
    return preferred_path


def normalize_live2d_model_path(
    model_path: str,
    available_paths: Iterable[str],
    *,
    preferred_path: str = PREFERRED_LIVE2D_MODEL_PATH,
) -> str:
    paths = list(available_paths)
    if model_path in paths:
        return model_path
    return pick_default_live2d_model_path(paths, preferred_path=preferred_path)
