"""Validate release metadata and deployment configuration without external services."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMVER_PATTERN = re.compile(r'^\d+\.\d+\.\d+$')


def load_json(relative_path: str) -> dict:
    with (ROOT / relative_path).open(encoding='utf-8') as source:
        return json.load(source)


def read_server_version() -> str:
    module = ast.parse((ROOT / 'server' / 'version.py').read_text(encoding='utf-8'))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'APP_VERSION':
                    value = ast.literal_eval(node.value)
                    if isinstance(value, str):
                        return value
    raise AssertionError('server/version.py must define a string APP_VERSION')


def validate() -> str:
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    assert SEMVER_PATTERN.fullmatch(version), f'Invalid semantic version: {version!r}'

    package = load_json('client/package.json')
    package_lock = load_json('client/package-lock.json')
    server_version = read_server_version()
    versions = {
        'VERSION': version,
        'client/package.json': package.get('version'),
        'client/package-lock.json': package_lock.get('version'),
        'client lock root package': package_lock.get('packages', {}).get('', {}).get('version'),
        'server/version.py': server_version,
    }
    mismatches = {name: value for name, value in versions.items() if value != version}
    assert not mismatches, f'Version mismatch: expected {version}; found {mismatches}'

    vercel = load_json('vercel.json')
    assert vercel.get('buildCommand') == 'cd client && npm ci && npm run build'
    assert vercel.get('outputDirectory') == 'client/dist'
    rewrites = {row.get('source'): row.get('destination') for row in vercel.get('rewrites', [])}
    assert rewrites.get('/api/(.*)') == '/api/index'
    assert rewrites.get('/(.*)') == '/index.html'

    required_docs = [
        'README.md',
        'CHANGELOG.md',
        'docs/PRODUCT_AND_USER_GUIDE.md',
        'docs/TECHNICAL_AND_OPERATIONS_GUIDE.md',
        'docs/IMPLEMENTATION_PLAN.md',
        'VERCEL_PRODUCTION_CHECKLIST.md',
    ]
    missing_docs = [path for path in required_docs if not (ROOT / path).is_file()]
    assert not missing_docs, f'Missing required documentation: {missing_docs}'
    return version


if __name__ == '__main__':
    validated_version = validate()
    print(f'Release metadata and Vercel configuration valid for v{validated_version}')
