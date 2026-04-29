from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query


SERVER_DIR = Path(__file__).resolve().parents[1] / 'server'
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


def _fallback_narrative(audience: str, tone: str) -> dict:
    normalized_audience = str(audience or 'lp').strip().lower()
    if normalized_audience in {'investor', 'portfolio'}:
        normalized_audience = 'lp'
    if normalized_audience not in {'lp', 'company'}:
        normalized_audience = 'lp'

    if normalized_audience == 'company':
        headline = 'Company ESG Narrative'
        summary = (
            'Data is being refreshed. Key ESG signals remain available and '
            'the latest validated records are being prepared for review.'
        )
    else:
        headline = 'Portfolio ESG Narrative'
        summary = (
            'Portfolio ESG narrative is available in fallback mode while AI services initialize. '
            'Submission quality, trend signals, and governance indicators remain accessible.'
        )

    return {
        'narrative_id': 0,
        'scope': 'portfolio' if normalized_audience == 'lp' else 'company',
        'audience': normalized_audience,
        'tone': tone,
        'company_id': None,
        'company_name': None,
        'provider': 'fallback',
        'fallback_used': True,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'headline': headline,
        'summary': summary,
        'highlights': [],
        'watchouts': [],
        'recommendations': [],
    }


try:
    from main import app as app  # type: ignore[assignment]  # noqa: F401,E402
except Exception:
    # Keep API alive with critical fallback endpoints even if full app bootstrap fails.
    app = FastAPI(title='ESG API Fallback')

    @app.get('/api/healthz')
    @app.get('/healthz')
    def healthz():
        return {
            'status': 'degraded',
            'mode': 'fallback',
            'vercel': bool(os.getenv('VERCEL')),
        }

    @app.get('/api/narrative/summary')
    @app.get('/narrative/summary')
    def narrative_summary(
        audience: str = Query(default='lp'),
        tone: str = Query(default='board-ready'),
    ):
        return _fallback_narrative(audience, tone)
