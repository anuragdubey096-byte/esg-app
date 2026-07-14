"""Read-only dashboard smoke test for manager, company, and investor roles."""

import json
import os
import time
from urllib import request
from urllib.error import HTTPError, URLError


BASE_URL = os.getenv('ESG_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
PASSWORD = os.getenv('ESG_TEST_PASSWORD', 'password123')
ROLE_EMAILS = {
    'manager': os.getenv('ESG_MANAGER_EMAIL', 'manager@example.com'),
    'company': os.getenv('ESG_COMPANY_EMAIL', 'company@example.com'),
    'investor': os.getenv('ESG_INVESTOR_EMAIL', 'investor@example.com'),
}


def call(path, *, method='GET', payload=None, headers=None, timeout=20):
    body = json.dumps(payload).encode() if payload is not None else None
    final_headers = {'Accept': 'application/json', **(headers or {})}
    if body is not None:
        final_headers['Content-Type'] = 'application/json'
    req = request.Request(f'{BASE_URL}{path}', data=body, headers=final_headers, method=method)
    started = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw), round((time.perf_counter() - started) * 1000), dict(response.headers)
    except (HTTPError, URLError) as error:
        detail = error.read().decode() if isinstance(error, HTTPError) else str(error)
        raise RuntimeError(f'{method} {path} failed: {getattr(error, "code", "network")} {detail}') from error


def main():
    failures = []
    for role, email in ROLE_EMAILS.items():
        status, user, login_ms, _ = call('/login', method='POST', payload={'email': email, 'password': PASSWORD})
        headers = {'x-user-role': role, 'x-user-email': email}
        if role == 'manager':
            dashboard_path = '/dashboard/manager'
        elif role == 'company':
            dashboard_path = f'/dashboard/company/{user["id"]}'
        else:
            dashboard_path = '/dashboard/investor'

        status, payload, dashboard_ms, response_headers = call(dashboard_path, headers=headers)
        has_data = bool(payload) and status == 200
        has_timing = 'server-timing' in {key.lower(): value for key, value in response_headers.items()}
        passed = has_data and has_timing and dashboard_ms < 15000
        print(json.dumps({
            'role': role,
            'login_ms': login_ms,
            'dashboard_ms': dashboard_ms,
            'status': status,
            'has_data': has_data,
            'server_timing': has_timing,
            'passed': passed,
        }))
        if not passed:
            failures.append(role)

    if failures:
        raise SystemExit(f'Dashboard smoke test failed for: {", ".join(failures)}')


if __name__ == '__main__':
    main()
