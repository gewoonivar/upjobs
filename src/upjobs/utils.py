from __future__ import annotations

from pathlib import Path
from typing import List

import yaml


def get_dynamic_webscrapbook_dir(base_dir: Path) -> Path:
    """Return the most recent YYYY-MM-DD subfolder under base_dir. If none, return base_dir."""
    base = Path(base_dir).expanduser()
    if not base.exists():
        return base
    dated = [p for p in base.iterdir() if p.is_dir() and p.name[:4].isdigit()]
    if not dated:
        return base
    return sorted(dated)[-1]


def cleanup_dir(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for p in target.glob("*.json"):
        p.unlink(missing_ok=True)


def load_search_urls(file_path: Path) -> List[str]:
    if not Path(file_path).exists():
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    urls = data.get("urls")
    return urls if isinstance(urls, list) else []
