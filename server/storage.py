from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

from env import load_local_env

load_local_env()

try:
    from vercel.blob import BlobClient, list_objects
except ImportError:  # pragma: no cover - optional dependency for local dev
    BlobClient = None
    list_objects = None


BASE_DIR = Path(__file__).resolve().parent
LOCAL_EXPORT_DIR = BASE_DIR / 'exports'
EXPORT_PREFIX = 'exports'


def is_blob_storage_enabled() -> bool:
    return bool(os.getenv('BLOB_READ_WRITE_TOKEN')) and BlobClient is not None and list_objects is not None


def ensure_local_export_dir() -> Path:
    if os.getenv('VERCEL') == '1':
        raise RuntimeError('BLOB_READ_WRITE_TOKEN is required when running on Vercel.')
    LOCAL_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return LOCAL_EXPORT_DIR


def _local_export_url(file_name: str) -> str:
    return f'/{EXPORT_PREFIX}/{file_name}'


def save_export_artifact(file_name: str, content: bytes, content_type: str) -> Dict[str, Any]:
    if is_blob_storage_enabled():
        client = BlobClient()
        blob = client.put(
            f'{EXPORT_PREFIX}/{file_name}',
            content,
            access='public',
            content_type=content_type,
            add_random_suffix=False,
        )
        return {
            'file_name': file_name,
            'file_path': blob.download_url,
            'download_url': blob.download_url,
            'content_type': content_type,
            'storage_mode': 'blob',
            'storage_url': blob.url,
            'pathname': blob.pathname,
        }

    export_dir = ensure_local_export_dir()
    file_path = export_dir / file_name
    file_path.write_bytes(content)
    return {
        'file_name': file_name,
        'file_path': str(file_path),
        'download_url': _local_export_url(file_name),
        'content_type': content_type,
        'storage_mode': 'filesystem',
        'storage_url': str(file_path),
        'pathname': f'{EXPORT_PREFIX}/{file_name}',
    }


def list_export_artifacts() -> List[Dict[str, Any]]:
    if is_blob_storage_enabled():
        page = list_objects(prefix=f'{EXPORT_PREFIX}/')
        blobs = getattr(page, 'blobs', page)
        artifacts: List[Dict[str, Any]] = []
        for blob in blobs:
            pathname = getattr(blob, 'pathname', '') or ''
            file_name = Path(pathname).name or pathname
            artifacts.append(
                {
                    'file_name': file_name,
                    'download_url': getattr(blob, 'download_url', None) or getattr(blob, 'url', None) or '',
                    'file_path': getattr(blob, 'download_url', None) or getattr(blob, 'url', None) or '',
                    'content_type': getattr(blob, 'content_type', None) or '',
                    'storage_mode': 'blob',
                    'storage_url': getattr(blob, 'url', None) or getattr(blob, 'download_url', None) or '',
                    'pathname': pathname,
                    'uploaded_at': getattr(blob, 'uploaded_at', None),
                }
            )
        return artifacts

    export_dir = ensure_local_export_dir()
    artifacts = []
    for file_path in sorted(export_dir.glob('*.*'), reverse=True):
        artifacts.append(
            {
                'file_name': file_path.name,
                'download_url': _local_export_url(file_path.name),
                'file_path': str(file_path),
                'content_type': '',
                'storage_mode': 'filesystem',
                'storage_url': str(file_path),
                'pathname': f'{EXPORT_PREFIX}/{file_path.name}',
                'uploaded_at': None,
            }
        )
    return artifacts
