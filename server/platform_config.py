from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict

DEFAULT_PLATFORM_CONFIG: Dict[str, Any] = {
    'impact': {
        'diversity_benchmarks': {
            'agriculture': 30.0,
            'aviation': 29.0,
            'consumer goods': 40.0,
            'education': 54.0,
            'energy': 24.0,
            'energy & utilities': 26.0,
            'financial services': 39.0,
            'food & beverage': 37.0,
            'forestry & land use': 34.0,
            'healthcare': 48.0,
            'infrastructure': 33.0,
            'logistics & transport': 28.0,
            'manufacturing': 31.0,
            'mining & resources': 22.0,
            'real estate': 41.0,
            'technology': 38.0,
            'telecommunications': 35.0,
            'waste management': 30.0,
        },
        'default_diversity_benchmark': 38.0,
        'portfolio_esg_benchmark': 72.0,
        'portfolio_emissions_intensity_benchmark': 5.1,
        'portfolio_trifr_benchmark': 1.45,
        'portfolio_policy_benchmark': 83.1,
        'tco2e_per_passenger_vehicle_year': 4.6,
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _load_json_env(name: str) -> Dict[str, Any]:
    raw = os.getenv(name, '').strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


PLATFORM_CONFIG = _deep_merge(DEFAULT_PLATFORM_CONFIG, _load_json_env('PLATFORM_CONFIG_JSON'))
IMPACT_CONFIG = PLATFORM_CONFIG['impact']
IMPACT_DIVERSITY_BENCHMARKS = IMPACT_CONFIG['diversity_benchmarks']
IMPACT_DEFAULT_DIVERSITY_BENCHMARK = float(IMPACT_CONFIG['default_diversity_benchmark'])
IMPACT_PORTFOLIO_ESG_BENCHMARK = float(IMPACT_CONFIG['portfolio_esg_benchmark'])
IMPACT_PORTFOLIO_EMISSIONS_INTENSITY_BENCHMARK = float(IMPACT_CONFIG['portfolio_emissions_intensity_benchmark'])
IMPACT_PORTFOLIO_TRIFR_BENCHMARK = float(IMPACT_CONFIG['portfolio_trifr_benchmark'])
IMPACT_PORTFOLIO_POLICY_BENCHMARK = float(IMPACT_CONFIG['portfolio_policy_benchmark'])
IMPACT_TCO2E_PER_PASSENGER_VEHICLE_YEAR = float(IMPACT_CONFIG['tco2e_per_passenger_vehicle_year'])

