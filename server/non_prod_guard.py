from __future__ import annotations

from sqlalchemy import func, or_

from models import Company, User

NON_PROD_NAME_PREFIXES = (
    'qa company',
    'test company',
    'dummy company',
    'sample company',
)
NON_PROD_NAME_TOKENS = (
    '[qa]',
    '(qa)',
    ' qa ',
    'integration test',
    'autotest',
)
NON_PROD_SECTOR_VALUES = (
    'testing',
    'quality assurance',
    'qa',
)
NON_PROD_OWNER_NAME_PREFIXES = (
    'qa ',
    'test ',
    'dummy ',
)
NON_PROD_EMAIL_LOCAL_PREFIXES = (
    'qa_',
    'test_',
    'dummy_',
    'sample_',
    'autotest_',
)
NON_PROD_EMAIL_DOMAINS = (
    'example.com',
    'example.org',
    'example.net',
)


def _normalize(value: str | None) -> str:
    return str(value or '').strip().lower()


def is_non_prod_email(value: str | None) -> bool:
    normalized = _normalize(value)
    if not normalized or '@' not in normalized:
        return False

    local_part, domain = normalized.split('@', 1)
    if domain in NON_PROD_EMAIL_DOMAINS:
        return True
    if any(local_part.startswith(prefix) for prefix in NON_PROD_EMAIL_LOCAL_PREFIXES):
        return True
    return False


def is_non_prod_company_record(
    *,
    company_name: str | None,
    sector: str | None = None,
    owner_email: str | None = None,
    owner_name: str | None = None,
    company_code: str | None = None,
) -> bool:
    normalized_name = _normalize(company_name)
    normalized_sector = _normalize(sector)
    normalized_owner_name = _normalize(owner_name)
    normalized_code = _normalize(company_code)

    if any(normalized_name.startswith(prefix) for prefix in NON_PROD_NAME_PREFIXES):
        return True
    if any(token in normalized_name for token in NON_PROD_NAME_TOKENS):
        return True
    if normalized_sector in NON_PROD_SECTOR_VALUES:
        return True
    if any(normalized_owner_name.startswith(prefix) for prefix in NON_PROD_OWNER_NAME_PREFIXES):
        return True
    if normalized_code.startswith('qa'):
        return True
    if is_non_prod_email(owner_email):
        return True
    return False


def build_non_prod_company_clause():
    lower_name = func.lower(func.coalesce(Company.name, ''))
    lower_sector = func.lower(func.coalesce(Company.sector, ''))
    lower_owner_name = func.lower(func.coalesce(User.name, ''))
    lower_owner_email = func.lower(func.coalesce(User.email, ''))
    lower_code = func.lower(func.coalesce(Company.code, ''))

    clauses = [lower_code.like('qa%')]
    clauses.extend(lower_name.like(f'{prefix}%') for prefix in NON_PROD_NAME_PREFIXES)
    clauses.extend(lower_name.like(f'%{token}%') for token in NON_PROD_NAME_TOKENS)
    clauses.extend(lower_owner_name.like(f'{prefix}%') for prefix in NON_PROD_OWNER_NAME_PREFIXES)
    clauses.extend(lower_owner_email.like(f'{prefix}%') for prefix in NON_PROD_EMAIL_LOCAL_PREFIXES)
    clauses.extend(lower_owner_email.like(f'%@{domain}') for domain in NON_PROD_EMAIL_DOMAINS)
    if NON_PROD_SECTOR_VALUES:
        clauses.append(lower_sector.in_(NON_PROD_SECTOR_VALUES))
    return or_(*clauses)
