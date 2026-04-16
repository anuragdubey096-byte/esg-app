from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_local_env() -> None:
    candidates = [
        PROJECT_ROOT / '.env.local',
        PROJECT_ROOT / '.env',
        BASE_DIR / '.env.local',
        BASE_DIR / '.env',
    ]
    for candidate in candidates:
        for key, value in _parse_env_file(candidate).items():
            os.environ.setdefault(key, value)

