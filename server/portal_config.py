from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

CONFIG_PATH = Path(__file__).resolve().parent.parent / 'client' / 'src' / 'lib' / 'portalConfig.json'


@lru_cache(maxsize=1)
def _load_portal_config() -> Dict[str, Any]:
    with CONFIG_PATH.open('r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError('portalConfig.json must contain an object at the top level')
    return payload


PORTAL_CONFIG: Dict[str, Any] = _load_portal_config()
FOUNDATION_CONFIG: Dict[str, Any] = PORTAL_CONFIG.get('foundation') or {}
EXPERIENCE_CONFIG: Dict[str, Any] = PORTAL_CONFIG.get('experience') or {}
SEARCH_CONFIG: Dict[str, Any] = PORTAL_CONFIG.get('search') or {}

PORTAL_BRAND_PROFILES = EXPERIENCE_CONFIG.get('brandProfiles') or []
DEFAULT_BRAND_ID = EXPERIENCE_CONFIG.get('defaultBrandId') or 'greenledger'
DEFAULT_APPEARANCE = EXPERIENCE_CONFIG.get('defaultAppearance') or 'light'

PORTAL_SEARCH_PAGE_CATALOG: Dict[str, List[Dict[str, Any]]] = SEARCH_CONFIG.get('pageCatalog') or {}
SEARCH_RANKING: Dict[str, Any] = SEARCH_CONFIG.get('ranking') or {}
