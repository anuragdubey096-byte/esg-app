import json
import time
from pathlib import Path
from urllib.request import urlopen

from fastapi.testclient import TestClient

from main import app


def run_self_test():
    results = []

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
        check('GET /dashboard/manager', manager_dashboard.status_code == 200 and 'summary' in manager_dashboard.json(), manager_dashboard.text)

        rbac_fail = client.get('/dashboard/manager', headers=investor_headers)
        check('GET /dashboard/manager blocked for investor', rbac_fail.status_code == 403, rbac_fail.text)

        cycles_for_investor = client.get('/cycles', headers=investor_headers)
        check('GET /cycles blocked for investor', cycles_for_investor.status_code == 403, cycles_for_investor.text)

        response = client.get('/dashboard/investor', headers=investor_headers)
        check('GET /dashboard/investor', response.status_code == 200 and 'portfolio_esg_score' in response.json(), response.text)

        response = client.get('/analytics/portfolio', headers=investor_headers)
        check('GET /analytics/portfolio', response.status_code == 200 and 'portfolio_esg_score' in response.json(), response.text)

        lp_dashboard = client.get('/lp/dashboard', headers=investor_headers)
        check('GET /lp/dashboard', lp_dashboard.status_code == 200 and 'portfolio_scorecard' in lp_dashboard.json(), lp_dashboard.text)
        lp_reports = client.get('/lp/reports', headers=investor_headers)
        check('GET /lp/reports', lp_reports.status_code == 200 and 'available_reports' in lp_reports.json(), lp_reports.text)
        lp_dashboard_manager_blocked = client.get('/lp/dashboard', headers=manager_headers)
        check('GET /lp/dashboard blocked for manager', lp_dashboard_manager_blocked.status_code == 403, lp_dashboard_manager_blocked.text)

        stamp = int(time.time())
        existing_cycle_years = set()
        existing_cycles_response = client.get('/cycles', headers=manager_headers)
        if existing_cycles_response.status_code == 200:
            existing_cycle_years = {
                int(item.get('cycle_year'))
                for item in existing_cycles_response.json()
                if str(item.get('cycle_year')).isdigit()
            }
        cycle_year = 2500 + (stamp % 1000)
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

        manager_upload = client.post(
            f'/company/{company_id}/upload-evidence',
            files={'file': ('evidence.txt', b'test evidence', 'text/plain')},
            headers=manager_headers,
        )
        check('POST /company/{id}/upload-evidence manager', manager_upload.status_code == 200, manager_upload.text)
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

        unlocked_submit = client.post(f'/company/{company_id}/submissions', json=submission_payload, headers=created_company_headers)
        check('unlock allows temporary write', unlocked_submit.status_code == 200, unlocked_submit.text)

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

        pdf_export = client.get(
            f'/reports/sfdr/export?format=pdf&period=FY2026&portfolio=All%20Portfolio%20Companies&narrative_id={narrative_id}',
            headers=manager_headers,
        )
        pdf_payload = pdf_export.json() if pdf_export.status_code == 200 else {}
        check(
            'GET /reports/{type}/export pdf with narrative',
            pdf_export.status_code == 200 and artifact_is_available(pdf_payload, 'application/pdf'),
            pdf_export.text,
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
