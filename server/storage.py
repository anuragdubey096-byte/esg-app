import os
from pathlib import Path

try:
    from vercel.blob import BlobClient
except ImportError:  # pragma: no cover - local installs may omit the optional SDK
    BlobClient = None


def _blob_token() -> str:
    return str(os.getenv('BLOB_READ_WRITE_TOKEN') or '').strip()


def blob_storage_configured() -> bool:
    return BlobClient is not None and bool(_blob_token())


def storage_health() -> dict[str, object]:
    configured = blob_storage_configured()
    on_vercel = bool(os.getenv('VERCEL'))
    return {
        'ok': configured or not on_vercel,
        'mode': 'vercel-blob' if configured else 'filesystem',
        'configured': configured,
        'error': None if configured or not on_vercel else 'Vercel Blob is not configured',
    }


def persist_export(file_path: Path, content_type: str) -> str:
    """Persist a generated export and return its storage pathname."""
    pathname = f'exports/{file_path.name}'
    if not blob_storage_configured():
        return pathname

    with BlobClient(token=_blob_token()) as client:
        result = client.put(
            pathname,
            file_path.read_bytes(),
            access='private',
            content_type=content_type,
            overwrite=True,
        )
    return result.pathname


def read_export(file_name: str, export_dir: Path) -> tuple[bytes, str | None]:
    """Read an export from Blob in production or the local export directory."""
    if blob_storage_configured():
        with BlobClient(token=_blob_token()) as client:
            result = client.get(f'exports/{file_name}', access='private', use_cache=False)
        return result.content, result.content_type

    local_path = export_dir / file_name
    if not local_path.is_file():
        raise FileNotFoundError(file_name)
    return local_path.read_bytes(), None
