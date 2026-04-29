import json
import os
import sys
import time
import io
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import urlopen

from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
from import_csv import (
    EXPECTED_FILES,
    get_default_data_dir,
    load_csv_rows,
    validate_fixture_consistency,
    validate_fixture_schema,
)
from platform_config import (
    IMPACT_DEFAULT_DIVERSITY_BENCHMARK,
    IMPACT_DIVERSITY_BENCHMARKS,
    IMPACT_PORTFOLIO_EMISSIONS_INTENSITY_BENCHMARK,
    IMPACT_PORTFOLIO_ESG_BENCHMARK,
    IMPACT_PORTFOLIO_POLICY_BENCHMARK,
    IMPACT_PORTFOLIO_TRIFR_BENCHMARK,
)
from portal_config import (
    DEFAULT_APPEARANCE,
    DEFAULT_BRAND_ID,
    PORTAL_BRAND_PROFILES,
    PORTAL_SEARCH_PAGE_CATALOG,
    SEARCH_RANKING,
)
from models import SubmissionUnlock


def run_self_test():
    results = []
    full_mode = str(os.getenv('SELF_TEST_FULL', '')).strip().lower() in {'1', 'true', 'yes', 'full'}
    if full_mode:
        os.environ.pop('SELF_TEST_FAST', None)
    else:
        os.environ['SELF_TEST_FAST'] = '1'
    fixture_dir = get_default_data_dir()

    def check(name, condition, detail=''):
        results.append((name, bool(condition), detail))

    def artifact_is_available(payload, expected_content_type):
        file_ref = payload.get('file_path') or payload.get('download_url') or ''
        if not file_ref:
            return False
        if payload.get('content_type') != expected_content_type:
            return False
        if file_ref.startswith('http://') or file_ref.startswith('https://'):
            try:
                with urlopen(file_ref, timeout=10) as response:
                    return len(response.read()) > 0
            except Exception:
                return False
        try:
            file_path = Path(file_ref)
        except Exception:
            return False
        return file_path.exists() and file_path.stat().st_size > 0

    try:
        validate_fixture_schema(fixture_dir)
        validate_fixture_consistency(fixture_dir)
        companies = load_csv_rows(fixture_dir / EXPECTED_FILES['companies'])
        previous_submissions = load_csv_rows(fixture_dir / EXPECTED_FILES['submissions_previous'])
        current_submissions = load_csv_rows(fixture_dir / EXPECTED_FILES['submissions_current'])
        company_ids = {row['company_id'].strip() for row in companies if row.get('company_id')}
        previous_ids = {row['company_id'].strip() for row in previous_submissions if row.get('company_id')}
        current_ids = {row['company_id'].strip() for row in current_submissions if row.get('company_id')}
        check(
            'synthetic fixture coverage',
            bool(company_ids)
            and previous_ids.issubset(company_ids)
            and current_ids.issubset(company_ids)
            and len(previous_ids) >= len(current_ids),
            json.dumps(
                {
                    'companies': len(company_ids),
                    'previous_submissions': len(previous_ids),
                    'current_submissions': len(current_ids),
                }
            ),
        )
    except Exception as exc:
        check('synthetic fixture coverage', False, str(exc))

    if not full_mode:
        route_paths = {
            getattr(route, 'path', None)
            for route in app.routes
            if getattr(route, 'path', None)
        }

        for label, expected, actual in [
            ('technology', 38.0, IMPACT_DIVERSITY_BENCHMARKS.get('technology')),
            ('default diversity benchmark', 38.0, IMPACT_DEFAULT_DIVERSITY_BENCHMARK),
            ('portfolio ESG benchmark', 72.0, IMPACT_PORTFOLIO_ESG_BENCHMARK),
            ('portfolio emissions intensity benchmark', 5.1, IMPACT_PORTFOLIO_EMISSIONS_INTENSITY_BENCHMARK),
            ('portfolio TRIFR benchmark', 1.45, IMPACT_PORTFOLIO_TRIFR_BENCHMARK),
            ('portfolio policy benchmark', 83.1, IMPACT_PORTFOLIO_POLICY_BENCHMARK),
        ]:
            check(f'platform config {label}', actual == expected, str(actual))

        for path in ['/login', '/dashboard/manager', '/dashboard/investor', '/lp/dashboard', '/search/global']:
            check(f'route present {path}', path in route_paths, json.dumps(sorted(route_paths)[:12]))

        catalog_sections = set(PORTAL_SEARCH_PAGE_CATALOG.keys())
        check(
            'portal catalog sections',
            {'manager', 'investor', 'company'}.issubset(catalog_sections),
            json.dumps(sorted(catalog_sections)),
        )

        check(
            'portal catalog manager pages',
            any(item.get('path') == '/analytics' for item in PORTAL_SEARCH_PAGE_CATALOG.get('manager', [])),
            json.dumps(PORTAL_SEARCH_PAGE_CATALOG.get('manager', [])[:3]),
        )

        check(
            'portal theme config',
            DEFAULT_BRAND_ID == 'greenledger'
            and DEFAULT_APPEARANCE == 'light'
            and len(PORTAL_BRAND_PROFILES) >= 3
            and any(profile.get('id') == 'summit' for profile in PORTAL_BRAND_PROFILES),
            json.dumps({'default_brand_id': DEFAULT_BRAND_ID, 'default_appearance': DEFAULT_APPEARANCE}),
        )
        check(
            'portal search ranking config',
            float((SEARCH_RANKING.get('weights') or {}).get('ratio', 0)) > 0
            and float(SEARCH_RANKING.get('minimumScore', 0)) >= 0,
            json.dumps(SEARCH_RANKING),
        )

        return results

    with TestClient(app) as client:
        manager_headers = {'x-user-role': 'manager', 'x-user-email': 'manager@example.com'}
        admin_alias_headers = {'x-user-role': 'admin', 'x-user-email': 'manager@example.com'}
        investor_headers = {'x-user-role': 'investor', 'x-user-email': 'investor@example.com'}
        company_headers = {'x-user-role': 'company', 'x-user-email': 'company@example.com'}

        def call(method: str, path: str, headers=None, payload=None):
            kwargs = {'headers': headers or {}}
            if payload is not None:
                kwargs['json'] = payload
            if method == 'GET':
                return client.get(path, **kwargs)
            if method == 'POST':
                return client.post(path, **kwargs)
            if method == 'PATCH':
                return client.patch(path, **kwargs)
            raise ValueError(f'Unsupported method: {method}')

        health = client.get('/health')
        health_payload = health.json() if health.status_code == 200 else {}
        check(
            'GET /health',
            health.status_code == 200
            and health_payload.get('status') in {'ok', 'degraded'}
            and isinstance(health_payload.get('checks'), dict)
            and bool(health_payload.get('checks', {}).get('database', {}).get('ok')),
            health.text,
        )

        ready = client.get('/health/ready')
        ready_payload = ready.json() if ready.status_code == 200 else {}
        check(
            'GET /health/ready',
            ready.status_code == 200
            and ready_payload.get('ready') is True
            and ready_payload.get('checks', {}).get('startup', {}).get('ok') is True,
            ready.text,
        )

        for email, expected_role in [
            ('manager@example.com', 'manager'),
            ('investor@example.com', 'investor'),
            ('company@example.com', 'company'),
        ]:
            response = client.post('/login', json={'email': email, 'password': 'password123'})
            ok = response.status_code == 200 and response.json().get('role') == expected_role
            check(f'login:{email}', ok, response.text)

        # Admin alias should normalize to manager privileges.
        alias_rbac = client.get('/dashboard/manager', headers=admin_alias_headers)
        check('RBAC admin alias behaves as manager', alias_rbac.status_code == 200, alias_rbac.text)

        manager_dashboard = client.get('/dashboard/manager', headers=manager_headers)
        manager_dashboard_payload = manager_dashboard.json() if manager_dashboard.status_code == 200 else {}
        check(
            'GET /dashboard/manager',
            manager_dashboard.status_code == 200
            and 'summary' in manager_dashboard_payload
            and isinstance(manager_dashboard_payload.get('impact_story'), dict)
            and manager_dashboard_payload.get('impact_story', {}).get('headline') == 'Portfolio impact story',
            manager_dashboard.text,
        )
        check(
            'manager impact story comparison rows',
            manager_dashboard.status_code == 200
            and isinstance(manager_dashboard_payload.get('impact_story', {}).get('comparison_rows'), list)
            and len(manager_dashboard_payload.get('impact_story', {}).get('comparison_rows', [])) >= 4,
            manager_dashboard.text,
        )

        rbac_fail = client.get('/dashboard/manager', headers=investor_headers)
        check('GET /dashboard/manager blocked for investor', rbac_fail.status_code == 403, rbac_fail.text)

        cycles_for_investor = client.get('/cycles', headers=investor_headers)
        check('GET /cycles blocked for investor', cycles_for_investor.status_code == 403, cycles_for_investor.text)

        response = client.get('/dashboard/investor', headers=investor_headers)
        investor_dashboard_payload = response.json() if response.status_code == 200 else {}
        check(
            'GET /dashboard/investor',
            response.status_code == 200
            and 'portfolio_esg_score' in investor_dashboard_payload
            and isinstance(investor_dashboard_payload.get('impact_story'), dict)
            and 'summary' in investor_dashboard_payload.get('impact_story', {})
            and 'equivalents' in investor_dashboard_payload.get('impact_story', {}),
            response.text,
        )

        response = client.get('/analytics/portfolio', headers=investor_headers)
        check('GET /analytics/portfolio', response.status_code == 200 and 'portfolio_esg_score' in response.json(), response.text)

        manager_analytics = client.get('/analytics/manager', headers=manager_headers)
        manager_analytics_payload = manager_analytics.json() if manager_analytics.status_code == 200 else {}
        check(
            'GET /analytics/manager',
            manager_analytics.status_code == 200 and 'impact_story' in manager_analytics_payload,
            manager_analytics.text,
        )

        lp_dashboard = client.get('/lp/dashboard', headers=investor_headers)
        lp_dashboard_payload = lp_dashboard.json() if lp_dashboard.status_code == 200 else {}
        check(
            'GET /lp/dashboard',
            lp_dashboard.status_code == 200
            and 'portfolio_scorecard' in lp_dashboard_payload
            and isinstance(lp_dashboard_payload.get('impact_story'), dict)
            and len(lp_dashboard_payload.get('impact_story', {}).get('benchmark_comparisons', [])) >= 5,
            lp_dashboard.text,
        )
        check(
            'lp impact story comparison rows',
            lp_dashboard.status_code == 200
            and isinstance(lp_dashboard_payload.get('impact_story', {}).get('comparison_rows'), list)
            and len(lp_dashboard_payload.get('impact_story', {}).get('comparison_rows', [])) >= 4,
            lp_dashboard.text,
        )
        lp_metrics = client.get('/lp/metrics', headers=investor_headers)
        lp_metrics_payload = lp_metrics.json() if lp_metrics.status_code == 200 else {}
        check(
            'GET /lp/metrics',
            lp_metrics.status_code == 200
            and 'benchmark_comparisons' in lp_metrics_payload
            and 'metric_insights' in lp_metrics_payload
            and any(item.get('tooltip') for item in lp_metrics_payload.get('benchmark_comparisons', [])),
            lp_metrics.text,
        )
        lp_reports = client.get('/lp/reports', headers=investor_headers)
        check('GET /lp/reports', lp_reports.status_code == 200 and 'available_reports' in lp_reports.json(), lp_reports.text)
        lp_dashboard_manager_blocked = client.get('/lp/dashboard', headers=manager_headers)
        check('GET /lp/dashboard blocked for manager', lp_dashboard_manager_blocked.status_code == 403, lp_dashboard_manager_blocked.text)

        config_checks = [
            ('technology', 38.0, IMPACT_DIVERSITY_BENCHMARKS.get('technology')),
            ('default diversity benchmark', 38.0, IMPACT_DEFAULT_DIVERSITY_BENCHMARK),
            ('portfolio ESG benchmark', 72.0, IMPACT_PORTFOLIO_ESG_BENCHMARK),
            ('portfolio emissions intensity benchmark', 5.1, IMPACT_PORTFOLIO_EMISSIONS_INTENSITY_BENCHMARK),
            ('portfolio TRIFR benchmark', 1.45, IMPACT_PORTFOLIO_TRIFR_BENCHMARK),
            ('portfolio policy benchmark', 83.1, IMPACT_PORTFOLIO_POLICY_BENCHMARK),
        ]
        for label, expected, actual in config_checks:
            check(f'platform config {label}', actual == expected, str(actual))

        search_denied = client.get('/search/global?q=Green&limit=3')
        check('GET /search/global blocked without role', search_denied.status_code == 403, search_denied.text)

        manager_search = client.get('/search/global?q=Green&limit=6', headers=manager_headers)
        manager_search_payload = manager_search.json() if manager_search.status_code == 200 else {}
        manager_search_results = manager_search_payload.get('results', [])
        check(
            'GET /search/global manager',
            manager_search.status_code == 200 and manager_search_payload.get('role') == 'manager' and len(manager_search_results) > 0,
            manager_search.text,
        )
        check(
            'manager search returns action plan and company results',
            manager_search.status_code == 200
            and any(item.get('type') == 'Action Plan' for item in manager_search_results)
            and any(item.get('type') == 'Company' for item in manager_search_results)
            and all(item.get('type') in {'Action Plan', 'Company'} for item in manager_search_results),
            manager_search.text,
        )

        manager_dashboard_search = client.get('/search/global', params={'q': 'dashboard', 'limit': 6}, headers=manager_headers)
        manager_dashboard_search_payload = manager_dashboard_search.json() if manager_dashboard_search.status_code == 200 else {}
        manager_dashboard_search_results = manager_dashboard_search_payload.get('results', [])
        check(
            'manager dashboard search',
            manager_dashboard_search.status_code == 200
            and manager_dashboard_search_payload.get('role') == 'manager'
            and any(item.get('type') == 'Page' for item in manager_dashboard_search_results)
            and any(item.get('metadata', {}).get('section') == 'manager' for item in manager_dashboard_search_results),
            manager_dashboard_search.text,
        )

        investor_search = client.get('/search/global?q=Portfolio&limit=4', headers=investor_headers)
        investor_search_payload = investor_search.json() if investor_search.status_code == 200 else {}
        investor_search_results = investor_search_payload.get('results', [])
        check(
            'GET /search/global investor',
            investor_search.status_code == 200 and investor_search_payload.get('role') == 'investor' and len(investor_search_results) > 0,
            investor_search.text,
        )
        check(
            'investor search stays in investor scope',
            investor_search.status_code == 200
            and all(
                item.get('type') != 'Page' or item.get('metadata', {}).get('section') == 'investor'
                for item in investor_search_results
            ),
            investor_search.text,
        )

        investor_dashboard_search = client.get('/search/global', params={'q': 'dashboard', 'limit': 6}, headers=investor_headers)
        investor_dashboard_search_payload = investor_dashboard_search.json() if investor_dashboard_search.status_code == 200 else {}
        investor_dashboard_search_results = investor_dashboard_search_payload.get('results', [])
        check(
            'investor dashboard search',
            investor_dashboard_search.status_code == 200
            and investor_dashboard_search_payload.get('role') == 'investor'
            and any(item.get('type') == 'Page' for item in investor_dashboard_search_results)
            and any(item.get('metadata', {}).get('section') == 'investor' for item in investor_dashboard_search_results),
            investor_dashboard_search.text,
        )

        if not full_mode:
            return results

        seeded_company_login = client.post('/login', json={'email': 'company@example.com', 'password': 'password123'})
        seeded_company_user = seeded_company_login.json() if seeded_company_login.status_code == 200 else {}
        seeded_company_dashboard = client.get(
            f"/dashboard/company/{seeded_company_user.get('id')}",
            headers=company_headers,
        )
        seeded_company_rows = seeded_company_dashboard.json() if seeded_company_dashboard.status_code == 200 else []
        seeded_company_name = seeded_company_rows[0]['name'] if seeded_company_rows else 'company'

        company_search = client.get('/search/global', params={'q': seeded_company_name, 'limit': 6}, headers=company_headers)
        company_search_payload = company_search.json() if company_search.status_code == 200 else {}
        company_search_results = company_search_payload.get('results', [])
        check(
            'GET /search/global company',
            company_search.status_code == 200 and company_search_payload.get('role') == 'company' and len(company_search_results) > 0,
            company_search.text,
        )
        check(
            'company search stays on owned company',
            company_search.status_code == 200
            and all(
                item.get('type') != 'Company' or item.get('company_name') == seeded_company_name
                for item in company_search_results
            )
            and all(
                item.get('type') != 'Page' or item.get('metadata', {}).get('section') == 'company'
                for item in company_search_results
            ),
            company_search.text,
        )

        company_dashboard_search = client.get('/search/global', params={'q': 'dashboard', 'limit': 6}, headers=company_headers)
        company_dashboard_search_payload = company_dashboard_search.json() if company_dashboard_search.status_code == 200 else {}
        company_dashboard_search_results = company_dashboard_search_payload.get('results', [])
        check(
            'company dashboard search',
            company_dashboard_search.status_code == 200
            and company_dashboard_search_payload.get('role') == 'company'
            and any(item.get('type') == 'Page' for item in company_dashboard_search_results)
            and any(item.get('metadata', {}).get('section') == 'company' for item in company_dashboard_search_results),
            company_dashboard_search.text,
        )

        if not full_mode:
            return results

        stamp = int(time.time())
        existing_cycle_years = set()
        existing_cycles_response = client.get('/cycles', headers=manager_headers)
        if existing_cycles_response.status_code == 200:
            existing_cycle_years = {
                int(item.get('cycle_year'))
                for item in existing_cycles_response.json()
                if str(item.get('cycle_year')).isdigit()
            }
        cycle_year = datetime.utcnow().year + 1
        while cycle_year in existing_cycle_years:
            cycle_year += 1
        cycle_response = client.post('/cycles', json={
            'cycle_year': cycle_year,
            'submission_open_date': '2026-04-10',
            'submission_deadline': '2026-05-10',
            'extension_date': '2026-05-20',
            'reminder_days_before_deadline': [30, 14, 7, 1],
            'private_equity_template': 'PE Standard',
            'real_estate_template': 'RE Standard',
            'debt_template': 'Debt Standard',
            'activate_on_create': True,
            'carry_forward_prefill': True,
        }, headers=manager_headers)
        cycle = cycle_response.json() if cycle_response.status_code == 200 else {}
        check('POST /cycles', cycle_response.status_code == 200 and cycle.get('cycle_year') == cycle_year, cycle_response.text)

        denied_cycle_payload = {
            'cycle_year': cycle_year + 1,
            'submission_open_date': '2026-06-01',
            'submission_deadline': '2026-07-01',
            'extension_date': '2026-07-10',
            'reminder_days_before_deadline': [14, 7, 1],
            'private_equity_template': 'PE Standard',
            'real_estate_template': 'RE Standard',
            'debt_template': 'Debt Standard',
            'activate_on_create': False,
            'carry_forward_prefill': False,
        }
        denied_cycles_investor = call('POST', '/cycles', headers=investor_headers, payload=denied_cycle_payload)
        check('POST /cycles blocked for investor', denied_cycles_investor.status_code == 403, denied_cycles_investor.text)
        denied_cycles_company = call('POST', '/cycles', headers=company_headers, payload=denied_cycle_payload)
        check('POST /cycles blocked for company', denied_cycles_company.status_code == 403, denied_cycles_company.text)

        list_cycles = client.get('/cycles', headers=manager_headers)
        cycles = list_cycles.json() if list_cycles.status_code == 200 else []
        check('GET /cycles manager', list_cycles.status_code == 200 and any(item.get('cycle_year') == cycle_year for item in cycles), list_cycles.text)

        company_email = f'qa_{stamp}@example.com'
        company_name = f'QA Company {stamp}'
        create_company = client.post('/companies', json={
            'name': company_name,
            'sector': 'Testing',
            'contact_name': 'QA User',
            'contact_email': company_email,
        }, headers=manager_headers)
        created_company = create_company.json() if create_company.status_code == 200 else {}
        check('POST /companies manager', create_company.status_code == 200 and created_company.get('portfolio_user_email') == company_email, create_company.text)

        denied_company_payload = {
            'name': f'Blocked Co {stamp}',
            'sector': 'Testing',
            'contact_name': 'Blocked User',
            'contact_email': f'blocked_{stamp}@example.com',
        }
        denied_company_investor = call('POST', '/companies', headers=investor_headers, payload=denied_company_payload)
        check('POST /companies blocked for investor', denied_company_investor.status_code == 403, denied_company_investor.text)
        denied_company_company = call('POST', '/companies', headers=company_headers, payload=denied_company_payload)
        check('POST /companies blocked for company', denied_company_company.status_code == 403, denied_company_company.text)

        response = client.post('/login', json={'email': company_email, 'password': 'password123'})
        new_company_user = response.json() if response.status_code == 200 else {}
        check('login:new company', response.status_code == 200 and new_company_user.get('role') == 'company', response.text)
        created_company_headers = {'x-user-role': 'company', 'x-user-email': company_email}

        company_search = client.get('/search/global', params={'q': company_name, 'limit': 6}, headers=created_company_headers)
        company_search_payload = company_search.json() if company_search.status_code == 200 else {}
        company_search_results = company_search_payload.get('results', [])
        check(
            'GET /search/global company',
            company_search.status_code == 200 and company_search_payload.get('role') == 'company' and len(company_search_results) > 0,
            company_search.text,
        )
        check(
            'company search stays on owned company',
            company_search.status_code == 200
            and all(
                item.get('type') != 'Company' or item.get('company_name') == company_name
                for item in company_search_results
            )
            and all(
                item.get('type') != 'Page' or item.get('metadata', {}).get('section') == 'company'
                for item in company_search_results
            ),
            company_search.text,
        )

        company_dashboard_search = client.get('/search/global', params={'q': 'dashboard', 'limit': 6}, headers=created_company_headers)
        company_dashboard_search_payload = company_dashboard_search.json() if company_dashboard_search.status_code == 200 else {}
        company_dashboard_search_results = company_dashboard_search_payload.get('results', [])
        check(
            'company dashboard search',
            company_dashboard_search.status_code == 200
            and company_dashboard_search_payload.get('role') == 'company'
            and any(item.get('type') == 'Page' for item in company_dashboard_search_results)
            and any(item.get('metadata', {}).get('section') == 'company' for item in company_dashboard_search_results),
            company_dashboard_search.text,
        )

        response = client.get(f"/dashboard/company/{new_company_user['id']}", headers=created_company_headers)
        company_dashboard = response.json() if response.status_code == 200 else []
        company_id = company_dashboard[0]['id'] if company_dashboard else None
        check(
            'dashboard/company shows created company',
            response.status_code == 200 and company_id is not None and company_dashboard[0]['name'] == company_name,
            response.text,
        )
        company_scope_block = client.get(f"/dashboard/company/{new_company_user['id']}", headers=company_headers)
        check('dashboard/company blocks other company user', company_scope_block.status_code == 403, company_scope_block.text)

        submission_payload = {
            'scope_1_emissions': 10,
            'scope_1_emissions_confidence': 'Measured',
            'scope_2_location_based': 20,
            'scope_2_location_based_confidence': 'Measured',
            'scope_2_market_based': 18,
            'scope_2_market_based_confidence': 'Estimated',
            'scope_3_emissions': 30,
            'scope_3_emissions_confidence': 'Measured',
            'total_ghg_emissions': 60,
            'total_ghg_emissions_confidence': 'Measured',
            'reduction_target_percent': 15,
            'reduction_target_percent_confidence': 'Measured',
            'reduction_target_year': 2028,
            'reduction_target_year_confidence': 'Measured',
            'reduction_strategy_description': 'Energy efficiency program',
            'total_energy_consumption': 100,
            'total_energy_consumption_confidence': 'Measured',
            'renewable_energy_consumption': 40,
            'renewable_energy_consumption_confidence': 'Measured',
            'total_water_withdrawal': 200,
            'total_water_withdrawal_confidence': 'Measured',
            'water_recycled_reused': 50,
            'water_recycled_reused_confidence': 'Measured',
            'total_waste_generated': 80,
            'total_waste_generated_confidence': 'Measured',
            'waste_diverted_from_landfill': 20,
            'waste_diverted_from_landfill_confidence': 'Measured',
            'hazardous_waste_generated': 5,
            'hazardous_waste_generated_confidence': 'Measured',
            'air_quality_control_measures': 'Yes',
            'air_quality_control_measures_confidence': 'Measured',
            'nox_sox_emissions': 1,
            'nox_sox_emissions_confidence': 'Estimated',
            'whs_policy_in_place': 'Yes',
            'whs_policy_in_place_confidence': 'Measured',
            'whs_policy_document_reference': 'whs-policy.pdf',
            'trifr': 0.5,
            'trifr_confidence': 'Measured',
            'total_fatalities': 0,
            'total_fatalities_confidence': 'Measured',
            'total_lost_time_injuries': 1,
            'total_lost_time_injuries_confidence': 'Measured',
            'total_incidents_reported': 3,
            'total_incidents_reported_confidence': 'Measured',
            'total_employees_fte': 120,
            'total_employees_fte_confidence': 'Measured',
            'employee_turnover_rate': 8,
            'employee_turnover_rate_confidence': 'Measured',
            'female_representation_percent': 45,
            'female_representation_percent_confidence': 'Measured',
            'female_leadership_representation_percent': 40,
            'female_leadership_representation_percent_confidence': 'Measured',
            'community_investment_spend': 10000,
            'community_investment_spend_confidence': 'Measured',
            'esg_policy_in_place': 'Yes',
            'esg_policy_in_place_confidence': 'Measured',
            'esg_policy_document_reference': 'esg-policy.pdf',
            'board_level_esg_oversight': 'Yes',
            'board_level_esg_oversight_confidence': 'Measured',
            'esg_kpis_linked_to_remuneration': 'No',
            'esg_kpis_linked_to_remuneration_confidence': 'Measured',
            'cybersecurity_policy_in_place': 'Yes',
            'cybersecurity_policy_in_place_confidence': 'Measured',
            'cybersecurity_policy_document_reference': 'cyber-policy.pdf',
            'cyber_incidents_in_reporting_period': 0,
            'cyber_incidents_in_reporting_period_confidence': 'Measured',
            'anti_bribery_corruption_policy': 'Yes',
            'anti_bribery_corruption_policy_confidence': 'Measured',
            'confirmed_cases_of_corruption': 0,
            'confirmed_cases_of_corruption_confidence': 'Measured',
            'total_board_members': 6,
            'total_board_members_confidence': 'Measured',
            'independent_board_members_percent': 50,
            'independent_board_members_percent_confidence': 'Measured',
            'female_board_members_percent': 33,
            'female_board_members_percent_confidence': 'Measured',
            'submission_notes': 'QA submission',
        }

        initial_submit = client.post(f'/company/{company_id}/submissions', json=submission_payload, headers=created_company_headers)
        submission = initial_submit.json() if initial_submit.status_code == 200 else {}
        submission_id = submission.get('id')
        check('active cycle accepts submission', initial_submit.status_code == 200 and submission.get('status') == 'submitted', initial_submit.text)

        company_section = client.get(
            f'/company/submission/{cycle["id"]}?section=Environmental',
            headers=created_company_headers,
        )
        company_section_payload = company_section.json() if company_section.status_code == 200 else {}
        check(
            'GET /company/submission/{cycle_id} collaboration payload',
            company_section.status_code == 200
            and company_section_payload.get('submission_id')
            and isinstance(company_section_payload.get('collaboration'), dict),
            company_section.text,
        )

        collaboration_claim = client.post(
            f'/company/submission/{cycle["id"]}/collaboration/claim',
            json={'section': 'Environmental'},
            headers=created_company_headers,
        )
        collaboration_claim_payload = collaboration_claim.json() if collaboration_claim.status_code == 200 else {}
        check(
            'POST /company/submission/{cycle_id}/collaboration/claim',
            collaboration_claim.status_code == 200
            and 'Environmental' in collaboration_claim_payload.get('current_user_sections', []),
            collaboration_claim.text,
        )

        collaboration_view = client.get(f'/submissions/{submission_id}/collaboration', headers=manager_headers)
        collaboration_view_payload = collaboration_view.json() if collaboration_view.status_code == 200 else {}
        check(
            'GET /submissions/{id}/collaboration manager',
            collaboration_view.status_code == 200
            and any(item.get('section') == 'Environmental' for item in collaboration_view_payload.get('active_sections', [])),
            collaboration_view.text,
        )

        collaboration_unlock = client.post(
            f'/companies/{company_id}/unlock',
            json={'reason': 'Allow collaboration smoke-test edit', 'expiry_hours': 1},
            headers=manager_headers,
        )
        check(
            'POST /companies/{id}/unlock collaboration smoke test',
            collaboration_unlock.status_code == 200 and collaboration_unlock.json().get('active') is True,
            collaboration_unlock.text,
        )

        company_field_update = client.post(
            f'/company/submission/{cycle["id"]}',
            json={'field_key': 'scope_1_emissions', 'value': '123', 'confidence_level': 'Measured', 'explanation': ''},
            headers=created_company_headers,
        )
        company_field_update_payload = company_field_update.json() if company_field_update.status_code == 200 else {}
        check(
            'POST /company/submission/{cycle_id} field update',
            company_field_update.status_code == 200
            and company_field_update_payload.get('status') == 'success',
            company_field_update.text,
        )

        live_activity = client.get(
            f'/live/activity?company_id={company_id}&submission_id={submission_id}&limit=5',
            headers=manager_headers,
        )
        live_activity_payload = live_activity.json() if live_activity.status_code == 200 else {}
        check(
            'GET /live/activity company submission',
            live_activity.status_code == 200
            and any(item.get('event_type') == 'submission_field_saved' for item in live_activity_payload.get('items', []))
            and any(item.get('event_type') == 'submission_section_claimed' for item in live_activity_payload.get('items', [])),
            live_activity.text,
        )

        with SessionLocal() as db:
            db.query(SubmissionUnlock).filter(
                SubmissionUnlock.company_id == company_id,
                SubmissionUnlock.cycle_id == cycle['id'],
                SubmissionUnlock.active.is_(True),
            ).update({'active': False}, synchronize_session=False)
            db.commit()

        with client.websocket_connect('/ws/live?role=manager&email=manager@example.com') as websocket:
            hello = websocket.receive_json()
            reminder_from_ws = client.post(
                f'/companies/{company_id}/reminders',
                json={'channel': 'email', 'message': 'Live reminder smoke test', 'cycle_id': cycle['id']},
                headers=manager_headers,
            )
            websocket_event = websocket.receive_json()
        check(
            'GET /ws/live manager reminder event',
            hello.get('type') == 'hello'
            and reminder_from_ws.status_code == 200
            and websocket_event.get('type') == 'event'
            and websocket_event.get('event', {}).get('event_type') == 'reminder_sent',
            json.dumps(websocket_event),
        )

        investor_submit = client.post(f'/company/{company_id}/submissions', json=submission_payload, headers=investor_headers)
        check('POST /company/{id}/submissions blocked for investor', investor_submit.status_code == 403, investor_submit.text)

        action_plan_payload = {
            'initiative_name': 'Decarbonization sprint',
            'target_completion_date': '2026-08-15',
            'assigned_owner': 'Ops Lead',
        }
        manager_action_plan = client.post(f'/company/{company_id}/action-plans', json=action_plan_payload, headers=manager_headers)
        check('POST /company/{id}/action-plans manager', manager_action_plan.status_code == 200, manager_action_plan.text)
        investor_action_plan = client.post(f'/company/{company_id}/action-plans', json=action_plan_payload, headers=investor_headers)
        check('POST /company/{id}/action-plans blocked for investor', investor_action_plan.status_code == 403, investor_action_plan.text)
        investor_live_activity = client.get('/live/activity?limit=12', headers=investor_headers)
        investor_live_activity_payload = investor_live_activity.json() if investor_live_activity.status_code == 200 else {}
        check(
            'GET /live/activity investor visible events',
            investor_live_activity.status_code == 200
            and any(
                item.get('event_type') in {'submission_submitted', 'action_plan_created'}
                for item in investor_live_activity_payload.get('items', [])
            ),
            investor_live_activity.text,
        )

        carbon_calculator = client.post(
            '/calculator/ghg',
            json={
                'fuel_liters': 1000,
                'electricity_kwh': 2000,
                'diesel_liters': 300,
                'natural_gas_therms': 120,
                'vehicle_km': 4500,
                'flight_km': 2200,
            },
        )
        carbon_payload = carbon_calculator.json() if carbon_calculator.status_code == 200 else {}
        check(
            'POST /calculator/ghg rich payload',
            carbon_calculator.status_code == 200
            and carbon_payload.get('scope_1_tco2e', 0) > 0
            and carbon_payload.get('scope_2_tco2e', 0) > 0
            and carbon_payload.get('scope_3_tco2e', 0) > 0
            and carbon_payload.get('total_tco2e', 0) >= carbon_payload.get('scope_1_tco2e', 0)
            and isinstance(carbon_payload.get('activity_breakdown'), list)
            and len(carbon_payload.get('activity_breakdown', [])) >= 4
            and isinstance(carbon_payload.get('scope_breakdown'), dict)
            and bool(carbon_payload.get('recommendation')),
            carbon_calculator.text,
        )

        def build_docx_bytes(text: str) -> bytes:
            xml_text = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body><w:p><w:r><w:t>'
                + text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                +
                '</w:t></w:r></w:p></w:body></w:document>'
            )
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('word/document.xml', xml_text)
            return buffer.getvalue()

        manager_upload = client.post(
            f'/company/{company_id}/upload-evidence',
            files={
                'file': (
                    'evidence-pack.docx',
                    build_docx_bytes(
                        'WHS policy reference WHS-POL-PTL-2024. '
                        'ESG policy reference ESG-POL-PTL-2024. '
                        'Cybersecurity policy reference CYBER-POL-PTL-2024. '
                        'Scope 1 emissions 36800. Scope 2 location based emissions 6400. '
                        'TRIFR 0.5. Board oversight yes.'
                    ),
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                )
            },
            headers=manager_headers,
        )
        manager_upload_payload = manager_upload.json() if manager_upload.status_code == 200 else {}
        check(
            'POST /company/{id}/upload-evidence manager',
            manager_upload.status_code == 200
            and manager_upload_payload.get('document', {}).get('file_name') == 'evidence-pack.docx'
            and manager_upload_payload.get('document_type') == 'mixed'
            and manager_upload_payload.get('suggestion_count', 0) == len(manager_upload_payload.get('extraction_suggestions', []))
            and 'policy' in manager_upload_payload.get('document_topics', [])
            and 'emissions' in manager_upload_payload.get('document_topics', [])
            and 'governance' in manager_upload_payload.get('document_topics', [])
            and manager_upload_payload.get('extraction_summary', '').startswith('Detected mixed')
            and len(manager_upload_payload.get('extraction_suggestions', [])) >= 5
            and any(item.get('field_key') == 'whs_policy_document_reference' for item in manager_upload_payload.get('extraction_suggestions', []))
            and any(item.get('field_key') == 'scope_1_emissions' for item in manager_upload_payload.get('extraction_suggestions', []))
            and any(item.get('field_key') == 'trifr' for item in manager_upload_payload.get('extraction_suggestions', [])),
            manager_upload.text,
        )
        report_upload = client.post(
            f'/company/{company_id}/upload-evidence',
            files={
                'file': (
                    'sustainability-report-2025.txt',
                    (
                        'Sustainability report 2025. '
                        'Scope 1 emissions 1024. Scope 2 location based emissions 240. Scope 3 emissions 3200. '
                        'Total energy consumption 18000. Renewable energy consumption 5400. '
                        'Total water withdrawal 800. Water recycled 120. '
                        'Total waste generated 300. Waste diverted from landfill 90. '
                        'Female representation 44. Female leadership representation 38. '
                        'Community investment spend 120000. Reduction target 30. Target year 2030.'
                    ).encode('utf-8'),
                    'text/plain',
                )
            },
            headers=manager_headers,
        )
        report_upload_payload = report_upload.json() if report_upload.status_code == 200 else {}
        check(
            'POST /company/{id}/upload-evidence report',
            report_upload.status_code == 200
            and report_upload_payload.get('document', {}).get('file_name') == 'sustainability-report-2025.txt'
            and report_upload_payload.get('document_type') == 'report'
            and report_upload_payload.get('suggestion_count', 0) == len(report_upload_payload.get('extraction_suggestions', []))
            and 'report' in report_upload_payload.get('document_topics', [])
            and 'emissions' in report_upload_payload.get('document_topics', [])
            and any(item.get('field_key') == 'scope_2_location_based' for item in report_upload_payload.get('extraction_suggestions', []))
            and any(item.get('field_key') == 'total_water_withdrawal' for item in report_upload_payload.get('extraction_suggestions', []))
            and any(item.get('field_key') == 'female_leadership_representation_percent' for item in report_upload_payload.get('extraction_suggestions', [])),
            report_upload.text,
        )
        investor_upload = client.post(
            f'/company/{company_id}/upload-evidence',
            files={'file': ('evidence.txt', b'test evidence', 'text/plain')},
            headers=investor_headers,
        )
        check('POST /company/{id}/upload-evidence blocked for investor', investor_upload.status_code == 403, investor_upload.text)

        to_under_review = client.patch(f'/submissions/{submission_id}/status', json={'status': 'under review'}, headers=manager_headers)
        check('submitted -> under review', to_under_review.status_code == 200 and to_under_review.json().get('status') == 'under review', to_under_review.text)

        invalid_transition = client.patch(f'/submissions/{submission_id}/status', json={'status': 'submitted'}, headers=manager_headers)
        check('invalid transition blocked', invalid_transition.status_code == 422, invalid_transition.text)

        resub_requested = client.post(
            f'/submissions/{submission_id}/review',
            json={'reviewer_role': 'Manager', 'review_status': 'resubmission requested', 'review_comment': 'Please revise and resubmit.'},
            headers=manager_headers,
        )
        check(
            'under review -> resubmission requested',
            resub_requested.status_code == 200 and resub_requested.json().get('status') == 'resubmission requested',
            resub_requested.text,
        )

        resubmit = client.post(f'/company/{company_id}/submissions', json=submission_payload, headers=created_company_headers)
        resubmitted = resubmit.json() if resubmit.status_code == 200 else {}
        check(
            'resubmission requested -> submitted',
            resubmit.status_code == 200 and resubmitted.get('id') == submission_id and resubmitted.get('status') == 'submitted',
            resubmit.text,
        )

        approved_submission = client.post(
            f'/submissions/{submission_id}/review',
            json={'reviewer_role': 'Manager', 'review_status': 'approved', 'review_comment': 'Approved for narrative summary.'},
            headers=manager_headers,
        )
        check(
            'submitted -> approved for narrative',
            approved_submission.status_code == 200 and approved_submission.json().get('status') == 'approved',
            approved_submission.text,
        )

        narrative_summary = client.get(
            f'/narrative/summary?audience=company&company_id={company_id}&tone=board-ready',
            headers=manager_headers,
        )
        narrative_payload = narrative_summary.json() if narrative_summary.status_code == 200 else {}
        narrative_id = narrative_payload.get('narrative_id')
        check(
            'GET /narrative/summary company approved',
            narrative_summary.status_code == 200 and narrative_payload.get('available') is True and narrative_id,
            narrative_summary.text,
        )

        narrative_patch = client.patch(
            f'/narrative/{narrative_id}',
            json={
                'headline': 'Edited narrative headline',
                'summary': narrative_payload.get('summary', ''),
                'highlights': narrative_payload.get('highlights', []),
                'watchouts': narrative_payload.get('watchouts', []),
                'recommendations': narrative_payload.get('recommendations', []),
            },
            headers=manager_headers,
        )
        check(
            'PATCH /narrative/{id}',
            narrative_patch.status_code == 200 and narrative_patch.json().get('headline') == 'Edited narrative headline',
            narrative_patch.text,
        )

        narrative_approve = client.post(
            f'/narrative/{narrative_id}/approve',
            json={'approved': True},
            headers=manager_headers,
        )
        check(
            'POST /narrative/{id}/approve',
            narrative_approve.status_code == 200 and narrative_approve.json().get('status') == 'approved',
            narrative_approve.text,
        )

        company_dashboard_after_approval = client.get('/company/dashboard', headers=created_company_headers)
        company_dashboard_payload = company_dashboard_after_approval.json() if company_dashboard_after_approval.status_code == 200 else {}
        check(
            'GET /company/dashboard company impact story',
            company_dashboard_after_approval.status_code == 200
            and isinstance(company_dashboard_payload.get('impact_story'), dict)
            and str(company_dashboard_payload.get('impact_story', {}).get('headline') or '').endswith('impact story')
            and len(company_dashboard_payload.get('impact_story', {}).get('comparison_rows', [])) >= 4,
            company_dashboard_after_approval.text,
        )

        portfolio_narrative = client.post(
            '/narrative/generate',
            json={'audience': 'board', 'tone': 'board-ready', 'force_refresh': True},
            headers=manager_headers,
        )
        portfolio_narrative_payload = portfolio_narrative.json() if portfolio_narrative.status_code == 200 else {}
        portfolio_narrative_id = portfolio_narrative_payload.get('narrative_id')
        check(
            'POST /narrative/generate board refresh',
            portfolio_narrative.status_code == 200
            and portfolio_narrative_payload.get('available') is True
            and portfolio_narrative_payload.get('freshness_status') == 'current'
            and portfolio_narrative_id,
            portfolio_narrative.text,
        )

        portfolio_narrative_approve = client.post(
            f'/narrative/{portfolio_narrative_id}/approve',
            json={'approved': True},
            headers=manager_headers,
        )
        check(
            'POST /narrative/{id}/approve portfolio',
            portfolio_narrative_approve.status_code == 200 and portfolio_narrative_approve.json().get('status') == 'approved',
            portfolio_narrative_approve.text,
        )

        report_preview = client.get(
            f'/reports/sfdr/preview?period=FY2026&portfolio=All%20Portfolio%20Companies&narrative_id={portfolio_narrative_id}',
            headers=manager_headers,
        )
        report_preview_payload = report_preview.json() if report_preview.status_code == 200 else {}
        check(
            'GET /reports/{type}/preview narrative current',
            report_preview.status_code == 200
            and report_preview_payload.get('narrative_status') == 'current'
            and isinstance(report_preview_payload.get('impact_story'), dict)
            and bool(report_preview_payload.get('trend_summary'))
            and len(report_preview_payload.get('comparison_rows', [])) >= 4
            and isinstance(report_preview_payload.get('anomaly_summary'), dict)
            and bool(report_preview_payload.get('anomaly_summary', {}).get('headline'))
            and isinstance(report_preview_payload.get('external_context_items'), list)
            and len(report_preview_payload.get('external_context_items', [])) >= 2,
            report_preview.text,
        )

        company_preview = client.get(
            f'/reports/edci/preview?period=FY{cycle_year}&portfolio={quote_plus(company_name)}&narrative_id={narrative_id}',
            headers=manager_headers,
        )
        company_preview_payload = company_preview.json() if company_preview.status_code == 200 else {}
        check(
            'GET /reports/{type}/preview company impact story',
            company_preview.status_code == 200
            and company_preview_payload.get('narrative_status') == 'current'
            and isinstance(company_preview_payload.get('impact_story'), dict)
            and str(company_preview_payload.get('impact_story', {}).get('headline') or '').startswith(company_name)
            and company_preview_payload.get('anomaly_summary', {}).get('scope') == 'company'
            and all(item.get('company_id') == company_id for item in company_preview_payload.get('external_context_items', [])),
            company_preview.text,
        )

        close_cycle = client.patch(f"/cycles/{cycle['id']}/status", json={'status': 'closed'}, headers=manager_headers)
        check('PATCH /cycles/{id}/status close', close_cycle.status_code == 200 and close_cycle.json().get('status') == 'closed', close_cycle.text)
        invalid_cycle_reopen = client.patch(f"/cycles/{cycle['id']}/status", json={'status': 'active'}, headers=manager_headers)
        check('invalid cycle transition blocked', invalid_cycle_reopen.status_code == 422, invalid_cycle_reopen.text)

        blocked_submit = client.post(f'/company/{company_id}/submissions', json=submission_payload, headers=created_company_headers)
        check('closed cycle blocks write', blocked_submit.status_code == 423, blocked_submit.text)

        unlock_response = client.post(
            f'/companies/{company_id}/unlock',
            json={'reason': 'Allow corrections after close', 'expiry_hours': 2},
            headers=manager_headers,
        )
        unlock_payload = unlock_response.json() if unlock_response.status_code == 200 else {}
        check('POST /companies/{id}/unlock', unlock_response.status_code == 200 and unlock_payload.get('active') is True, unlock_response.text)

        updated_submission_payload = dict(submission_payload)
        updated_submission_payload['scope_1_emissions'] = 12
        updated_submission_payload['scope_2_location_based'] = 22
        updated_submission_payload['scope_3_emissions'] = 32
        updated_submission_payload['total_ghg_emissions'] = 66
        updated_submission_payload['female_representation_percent'] = 41
        updated_submission_payload['trifr'] = 1.1
        unlocked_submit = client.post(f'/company/{company_id}/submissions', json=updated_submission_payload, headers=created_company_headers)
        updated_submission = unlocked_submit.json() if unlocked_submit.status_code == 200 else {}
        updated_submission_id = updated_submission.get('id')
        check('unlock allows temporary write', unlocked_submit.status_code == 200 and updated_submission_id, unlocked_submit.text)

        reapproved_submission = client.post(
            f'/submissions/{updated_submission_id}/review',
            json={'reviewer_role': 'Manager', 'review_status': 'approved', 'review_comment': 'Approved updated submission for stale narrative test.'},
            headers=manager_headers,
        )
        check(
            'resubmitted data approved for stale narrative test',
            reapproved_submission.status_code == 200 and reapproved_submission.json().get('status') == 'approved',
            reapproved_submission.text,
        )

        stale_narrative = client.get(f'/narrative/{narrative_id}', headers=manager_headers)
        stale_narrative_payload = stale_narrative.json() if stale_narrative.status_code == 200 else {}
        check(
            'GET /narrative/{id} stale after approved data change',
            stale_narrative.status_code == 200 and stale_narrative_payload.get('freshness_status') == 'stale',
            stale_narrative.text,
        )

        stale_preview = client.get(
            f'/reports/edci/preview?period=FY{cycle_year}&portfolio={quote_plus(company_name)}&narrative_id={narrative_id}',
            headers=manager_headers,
        )
        stale_preview_payload = stale_preview.json() if stale_preview.status_code == 200 else {}
        check(
            'GET /reports/{type}/preview narrative stale',
            stale_preview.status_code == 200
            and stale_preview_payload.get('narrative_status') == 'stale'
            and stale_preview_payload.get('narrative_included') is False,
            stale_preview.text,
        )

        refreshed_company_narrative = client.post(
            '/narrative/generate',
            json={'audience': 'company', 'company_id': company_id, 'tone': 'board-ready', 'force_refresh': True},
            headers=manager_headers,
        )
        refreshed_company_narrative_payload = refreshed_company_narrative.json() if refreshed_company_narrative.status_code == 200 else {}
        refreshed_company_narrative_id = refreshed_company_narrative_payload.get('narrative_id')
        check(
            'POST /narrative/generate company refresh',
            refreshed_company_narrative.status_code == 200
            and refreshed_company_narrative_payload.get('freshness_status') == 'current'
            and refreshed_company_narrative_id
            and refreshed_company_narrative_id != narrative_id,
            refreshed_company_narrative.text,
        )

        refreshed_company_approve = client.post(
            f'/narrative/{refreshed_company_narrative_id}/approve',
            json={'approved': True},
            headers=manager_headers,
        )
        check(
            'POST /narrative/{id}/approve refreshed company narrative',
            refreshed_company_approve.status_code == 200 and refreshed_company_approve.json().get('status') == 'approved',
            refreshed_company_approve.text,
        )

        reminder_response = client.post(
            f'/companies/{company_id}/reminders',
            json={'channel': 'email', 'message': 'Please complete outstanding corrections.', 'cycle_id': cycle['id']},
            headers=manager_headers,
        )
        check('POST /companies/{id}/reminders', reminder_response.status_code == 200 and reminder_response.json().get('delivery_status') == 'logged', reminder_response.text)

        reminder_forbidden = client.post(
            f'/companies/{company_id}/reminders',
            json={'channel': 'email', 'message': 'Investor should be blocked', 'cycle_id': cycle['id']},
            headers=investor_headers,
        )
        check('reminder blocked for investor', reminder_forbidden.status_code == 403, reminder_forbidden.text)

        protected_endpoints = [
            ('GET', '/users', None),
            ('PATCH', f"/cycles/{cycle['id']}/status", {'status': 'closed'}),
            ('PATCH', f"/submissions/{submission_id}/status", {'status': 'under review'}),
            ('POST', f"/submissions/{submission_id}/review", {'reviewer_role': 'Manager', 'review_status': 'approved', 'review_comment': 'RBAC check'}),
            ('POST', f"/submissions/{submission_id}/validate", None),
            ('GET', f"/submissions/{submission_id}/validation-errors", None),
            ('POST', f"/submissions/{submission_id}/validation-errors/decision", {'field_key': 'scope_1_emissions', 'decision': 'pass'}),
            ('POST', f"/companies/{company_id}/unlock", {'reason': 'RBAC check', 'expiry_hours': 1}),
            ('POST', f"/companies/{company_id}/reminders", {'channel': 'email', 'message': 'RBAC check', 'cycle_id': cycle['id']}),
        ]

        for method, path, payload in protected_endpoints:
            manager_response = call(method, path, headers=manager_headers, payload=payload)
            check(f'RBAC manager allowed {method} {path}', manager_response.status_code != 403, manager_response.text)
            investor_response = call(method, path, headers=investor_headers, payload=payload)
            check(f'RBAC investor denied {method} {path}', investor_response.status_code == 403, investor_response.text)
            company_response = call(method, path, headers=company_headers, payload=payload)
            check(f'RBAC company denied {method} {path}', company_response.status_code == 403, company_response.text)

        validate_response = client.post(f'/submissions/{submission_id}/validate', headers=manager_headers)
        check('POST /submissions/{id}/validate', validate_response.status_code == 200 and 'flagged' in validate_response.json(), validate_response.text)

        validation_errors_response = client.get(f'/submissions/{submission_id}/validation-errors', headers=manager_headers)
        check(
            'GET /submissions/{id}/validation-errors',
            validation_errors_response.status_code == 200 and isinstance(validation_errors_response.json(), list),
            validation_errors_response.text,
        )

        fail_decision_response = client.post(
            f'/submissions/{submission_id}/validation-errors/decision',
            json={'field_key': 'scope_1_emissions', 'decision': 'fail', 'comment': 'Reviewer forced fail'},
            headers=manager_headers,
        )
        check(
            'POST /submissions/{id}/validation-errors/decision fail',
            fail_decision_response.status_code == 200 and fail_decision_response.json().get('decision') == 'fail',
            fail_decision_response.text,
        )

        pass_decision_response = client.post(
            f'/submissions/{submission_id}/validation-errors/decision',
            json={'field_key': 'scope_1_emissions', 'decision': 'pass'},
            headers=manager_headers,
        )
        check(
            'POST /submissions/{id}/validation-errors/decision pass',
            pass_decision_response.status_code == 200 and pass_decision_response.json().get('decision') == 'pass',
            pass_decision_response.text,
        )

        metadata = client.get('/reports/edci')
        check('GET /reports/edci metadata blocked without role', metadata.status_code == 403, metadata.text)

        metadata_investor = client.get('/reports/edci', headers=investor_headers)
        check(
            'GET /reports/edci metadata investor',
            metadata_investor.status_code == 200 and metadata_investor.json().get('report_type') == 'EDCI',
            metadata_investor.text,
        )

        csv_export = client.get('/reports/edci/export?format=csv&period=FY2026&portfolio=All%20Portfolio%20Companies', headers=manager_headers)
        csv_payload = csv_export.json() if csv_export.status_code == 200 else {}
        check('GET /reports/{type}/export csv', csv_export.status_code == 200 and artifact_is_available(csv_payload, 'text/csv'), csv_export.text)

        csv_export_investor = client.get('/reports/edci/export?format=csv&period=FY2026&portfolio=All%20Portfolio%20Companies', headers=investor_headers)
        csv_investor_payload = csv_export_investor.json() if csv_export_investor.status_code == 200 else {}
        check(
            'GET /reports/{type}/export csv investor',
            csv_export_investor.status_code == 200 and artifact_is_available(csv_investor_payload, 'text/csv'),
            csv_export_investor.text,
        )

        csv_export_company = client.get('/reports/edci/export?format=csv&period=FY2026&portfolio=All%20Portfolio%20Companies', headers=company_headers)
        check('GET /reports/{type}/export csv company blocked', csv_export_company.status_code == 403, csv_export_company.text)

        refreshed_portfolio_narrative = client.post(
            '/narrative/generate',
            json={'audience': 'board', 'tone': 'board-ready', 'force_refresh': True},
            headers=manager_headers,
        )
        refreshed_portfolio_narrative_payload = refreshed_portfolio_narrative.json() if refreshed_portfolio_narrative.status_code == 200 else {}
        refreshed_portfolio_narrative_id = refreshed_portfolio_narrative_payload.get('narrative_id')
        check(
            'POST /narrative/generate board refresh before export',
            refreshed_portfolio_narrative.status_code == 200
            and refreshed_portfolio_narrative_payload.get('freshness_status') == 'current'
            and refreshed_portfolio_narrative_id,
            refreshed_portfolio_narrative.text,
        )

        refreshed_portfolio_narrative_approve = client.post(
            f'/narrative/{refreshed_portfolio_narrative_id}/approve',
            json={'approved': True},
            headers=manager_headers,
        )
        check(
            'POST /narrative/{id}/approve refreshed portfolio narrative',
            refreshed_portfolio_narrative_approve.status_code == 200 and refreshed_portfolio_narrative_approve.json().get('status') == 'approved',
            refreshed_portfolio_narrative_approve.text,
        )

        pdf_export = client.get(
            f'/reports/sfdr/export?format=pdf&period=FY2026&portfolio=All%20Portfolio%20Companies&narrative_id={refreshed_portfolio_narrative_id}',
            headers=manager_headers,
        )
        pdf_payload = pdf_export.json() if pdf_export.status_code == 200 else {}
        check(
            'GET /reports/{type}/export pdf with narrative',
            pdf_export.status_code == 200
            and artifact_is_available(pdf_payload, 'application/pdf')
            and pdf_payload.get('narrative_included') is True
            and pdf_payload.get('narrative_status') == 'current'
            and isinstance(pdf_payload.get('context_summary'), list)
            and len(pdf_payload.get('context_summary', [])) > 0
            and pdf_payload.get('impact_headline') == 'Portfolio impact story'
            and isinstance(pdf_payload.get('anomaly_summary'), dict)
            and bool(pdf_payload.get('anomaly_summary', {}).get('headline'))
            and isinstance(pdf_payload.get('external_context_items'), list)
            and len(pdf_payload.get('external_context_items', [])) >= 2,
            pdf_export.text,
        )
        check(
            'GET /reports/{type}/export pdf comparison rows',
            pdf_export.status_code == 200
            and isinstance(pdf_payload.get('comparison_rows'), list)
            and len(pdf_payload.get('comparison_rows', [])) >= 4
            and isinstance(pdf_payload.get('impact_story'), dict)
            and bool(pdf_payload.get('trend_summary')),
            pdf_export.text,
        )

        newsletter_summary = client.post(
            '/newsletter/generate',
            json={'audience': 'manager', 'tone': 'board-ready', 'force_refresh': False},
            headers=manager_headers,
        )
        newsletter_payload = newsletter_summary.json() if newsletter_summary.status_code == 200 else {}
        check(
            'POST /newsletter/generate manager',
            newsletter_summary.status_code == 200
            and newsletter_payload.get('available') is True
            and bool(newsletter_payload.get('subject_line'))
            and isinstance(newsletter_payload.get('anomaly_summary'), dict)
            and bool(newsletter_payload.get('anomaly_summary', {}).get('headline'))
            and isinstance(newsletter_payload.get('external_context_items'), list)
            and len(newsletter_payload.get('external_context_items', [])) >= 2,
            newsletter_summary.text,
        )

        newsletter_export = client.post(
            '/newsletter/export',
            json={'audience': 'manager', 'tone': 'board-ready', 'force_refresh': False},
            headers=manager_headers,
        )
        newsletter_export_payload = newsletter_export.json() if newsletter_export.status_code == 200 else {}
        check(
            'POST /newsletter/export manager',
            newsletter_export.status_code == 200
            and artifact_is_available(newsletter_export_payload, 'text/plain')
            and newsletter_export_payload.get('available') is True
            and bool(newsletter_export_payload.get('subject_line'))
            and isinstance(newsletter_export_payload.get('anomaly_summary'), dict)
            and isinstance(newsletter_export_payload.get('external_context_items'), list)
            and len(newsletter_export_payload.get('external_context_items', [])) >= 2,
            newsletter_export.text,
        )

        newsletter_export_company = client.post(
            '/newsletter/export',
            json={'audience': 'manager', 'tone': 'board-ready', 'force_refresh': False},
            headers=company_headers,
        )
        check(
            'POST /newsletter/export company blocked',
            newsletter_export_company.status_code == 403,
            newsletter_export_company.text,
        )

        newsletter_send_preview = client.post(
            '/newsletter/send',
            json={'audience': 'manager', 'tone': 'board-ready', 'force_refresh': False, 'dry_run': True},
            headers=manager_headers,
        )
        newsletter_send_preview_payload = newsletter_send_preview.json() if newsletter_send_preview.status_code == 200 else {}
        check(
            'POST /newsletter/send manager dry run',
            newsletter_send_preview.status_code == 200
            and newsletter_send_preview_payload.get('delivery_status') == 'dry_run'
            and newsletter_send_preview_payload.get('available') is True,
            newsletter_send_preview.text,
        )

        newsletter_send_company = client.post(
            '/newsletter/send',
            json={'audience': 'manager', 'tone': 'board-ready', 'force_refresh': False, 'dry_run': True},
            headers=company_headers,
        )
        check(
            'POST /newsletter/send company blocked',
            newsletter_send_company.status_code == 403,
            newsletter_send_company.text,
        )

        manager_external_context = client.get('/external-context/feed?limit=4', headers=manager_headers)
        manager_external_context_payload = manager_external_context.json() if manager_external_context.status_code == 200 else {}
        check(
            'GET /external-context/feed manager',
            manager_external_context.status_code == 200
            and manager_external_context_payload.get('available') is True
            and isinstance(manager_external_context_payload.get('items'), list)
            and len(manager_external_context_payload.get('items', [])) >= 3,
            manager_external_context.text,
        )

        investor_external_context_blocked = client.get(f'/external-context/feed?company_id={company_id}', headers=investor_headers)
        check(
            'GET /external-context/feed investor company blocked',
            investor_external_context_blocked.status_code == 403,
            investor_external_context_blocked.text,
        )

        company_external_context = client.get('/external-context/feed?limit=3', headers=created_company_headers)
        company_external_context_payload = company_external_context.json() if company_external_context.status_code == 200 else {}
        check(
            'GET /external-context/feed company',
            company_external_context.status_code == 200
            and company_external_context_payload.get('scope') == 'company'
            and isinstance(company_external_context_payload.get('items'), list),
            company_external_context.text,
        )

        investor_anomaly_summary = client.get('/anomalies/summary', headers=investor_headers)
        investor_anomaly_summary_payload = investor_anomaly_summary.json() if investor_anomaly_summary.status_code == 200 else {}
        check(
            'GET /anomalies/summary investor',
            investor_anomaly_summary.status_code == 200
            and investor_anomaly_summary_payload.get('scope') == 'portfolio'
            and isinstance(investor_anomaly_summary_payload.get('severity_counts'), dict),
            investor_anomaly_summary.text,
        )

        investor_anomaly_blocked = client.get(f'/anomalies/summary?company_id={company_id}', headers=investor_headers)
        check(
            'GET /anomalies/summary investor company blocked',
            investor_anomaly_blocked.status_code == 403,
            investor_anomaly_blocked.text,
        )

        company_anomaly_summary = client.get('/company/anomalies', headers=created_company_headers)
        company_anomaly_summary_payload = company_anomaly_summary.json() if company_anomaly_summary.status_code == 200 else {}
        check(
            'GET /company/anomalies company',
            company_anomaly_summary.status_code == 200
            and company_anomaly_summary_payload.get('scope') == 'company'
            and isinstance(company_anomaly_summary_payload.get('items'), list),
            company_anomaly_summary.text,
        )

        cron_newsletter_blocked = client.get('/cron/newsletter/manager')
        check(
            'GET /cron/newsletter/manager blocked without secret',
            cron_newsletter_blocked.status_code in {401, 503},
            cron_newsletter_blocked.text,
        )

        manager_after = client.get('/dashboard/manager', headers=manager_headers)
        manager_json = manager_after.json() if manager_after.status_code == 200 else {}
        summary = manager_json.get('summary', {})
        buckets = summary.get('status_breakdown', {})
        required_buckets = {'Not Started', 'In Progress', 'Submitted', 'Under Review', 'Approved', 'Resubmission Requested'}
        check(
            'manager dashboard six buckets',
            manager_after.status_code == 200 and required_buckets.issubset(set(buckets.keys())),
            manager_after.text,
        )
        check(
            'manager dashboard cycle banner/upcoming deadlines',
            manager_after.status_code == 200 and isinstance(summary.get('cycle_banner'), dict) and isinstance(summary.get('upcoming_deadlines'), list),
            json.dumps(summary),
        )

    return results


if __name__ == '__main__':
    results = run_self_test()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f'SUMMARY: {passed}/{len(results)} passed')
    sys.stdout.flush()
    os._exit(0 if passed == len(results) else 1)
