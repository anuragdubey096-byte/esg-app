import json
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from main import app


def run_self_test():
    results = []

    def check(name, condition, detail=''):
        results.append((name, bool(condition), detail))

    with TestClient(app) as client:
        role_headers = {}

        for email, expected_role in [
            ('manager@example.com', 'manager'),
            ('investor@example.com', 'investor'),
            ('company@example.com', 'company'),
        ]:
            response = client.post('/login', json={'email': email, 'password': 'password123'})
            ok = response.status_code == 200 and response.json().get('role') == expected_role
            check(f'login:{email}', ok, response.text)
            token = response.cookies.get('esg_session')
            role_headers[expected_role] = {'Authorization': f'Bearer {token}'} if token else {}

        manager_headers = role_headers['manager']
        investor_headers = role_headers['investor']

        forged_rbac = client.get('/dashboard/manager', headers={'x-user-role': 'manager', 'x-user-email': 'manager@example.com'})
        check('forged role headers cannot authenticate as manager', forged_rbac.status_code in {401, 403}, forged_rbac.text)

        manager_dashboard = client.get('/dashboard/manager', headers=manager_headers)
        check('GET /dashboard/manager', manager_dashboard.status_code == 200 and 'summary' in manager_dashboard.json(), manager_dashboard.text)
        check('manager dashboard includes timing telemetry', 'app;dur=' in manager_dashboard.headers.get('server-timing', ''), dict(manager_dashboard.headers))
        check('manager dashboard exposes app duration', float(manager_dashboard.headers.get('x-app-duration-ms', -1)) >= 0, dict(manager_dashboard.headers))

        disposable_login = client.post('/login', json={'email': 'manager@example.com', 'password': 'password123'})
        disposable_token = disposable_login.cookies.get('esg_session')
        disposable_headers = {'Authorization': f'Bearer {disposable_token}'}
        session_me = client.get('/auth/me', headers=disposable_headers)
        session_logout = client.post('/auth/logout', headers=disposable_headers)
        session_after_logout = client.get('/auth/me', headers=disposable_headers)
        check(
            'session supports restore, logout, and revocation',
            session_me.status_code == 200 and session_logout.status_code == 200 and session_after_logout.status_code == 401,
            session_after_logout.text,
        )

        rbac_fail = client.get('/dashboard/manager', headers=investor_headers)
        check('GET /dashboard/manager blocked for investor', rbac_fail.status_code == 403, rbac_fail.text)

        cycles_for_investor = client.get('/cycles', headers=investor_headers)
        check('GET /cycles available to authenticated investor', cycles_for_investor.status_code == 200, cycles_for_investor.text)

        response = client.get('/dashboard/investor', headers=investor_headers)
        check('GET /dashboard/investor', response.status_code == 200 and 'portfolio_esg_score' in response.json(), response.text)
        check('investor dashboard includes timing telemetry', 'app;dur=' in response.headers.get('server-timing', ''), dict(response.headers))
        check('investor dashboard exposes app duration', float(response.headers.get('x-app-duration-ms', -1)) >= 0, dict(response.headers))

        response = client.get('/analytics/portfolio')
        check('GET /analytics/portfolio', response.status_code == 200 and 'portfolio_esg_score' in response.json(), response.text)

        data_quality = client.get('/analytics/data-quality', headers=manager_headers)
        data_quality_payload = data_quality.json() if data_quality.status_code == 200 else {}
        check(
            'GET /analytics/data-quality manager dashboard',
            data_quality.status_code == 200
            and isinstance(data_quality_payload.get('rows'), list)
            and 'quality_index' in data_quality_payload
            and 'evidence_coverage' in data_quality_payload,
            data_quality.text,
        )
        data_quality_forbidden = client.get('/analytics/data-quality', headers=role_headers['company'])
        check(
            'GET /analytics/data-quality blocks company role',
            data_quality_forbidden.status_code == 403,
            data_quality_forbidden.text,
        )

        framework_mapping = client.get('/analytics/framework-mapping', headers=manager_headers)
        framework_payload = framework_mapping.json() if framework_mapping.status_code == 200 else {}
        check(
            'GET /analytics/framework-mapping returns auditable disclosure coverage',
            framework_mapping.status_code == 200
            and {item.get('framework') for item in framework_payload.get('frameworks', [])} == {'EDCI', 'GRI', 'ISSB', 'SFDR'}
            and len(framework_payload.get('disclosures', [])) == 20,
            framework_mapping.text,
        )
        framework_forbidden = client.get('/analytics/framework-mapping', headers=role_headers['company'])
        check('framework mapping blocks company role', framework_forbidden.status_code == 403, framework_forbidden.text)

        stamp = int(time.time())
        existing_cycles_response = client.get('/cycles', headers=manager_headers)
        existing_cycle_years = {
            int(item.get('cycle_year')) for item in existing_cycles_response.json()
            if item.get('cycle_year') is not None
        }
        current_year = datetime.now(timezone.utc).year
        cycle_year = next(
            year for year in range(current_year + 5, 1999, -1)
            if year not in existing_cycle_years
        )
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

        invalid_cycle_response = client.post('/cycles', json={
            'cycle_year': 2595,
            'submission_open_date': '2026-04-10',
            'submission_deadline': '2026-05-10',
            'extension_date': '2026-05-20',
            'reminder_days_before_deadline': [30, 14, 7, 1],
            'private_equity_template': 'PE Standard',
            'real_estate_template': 'RE Standard',
            'debt_template': 'Debt Standard',
            'activate_on_create': False,
            'carry_forward_prefill': False,
        }, headers=manager_headers)
        check('POST /cycles rejects irrelevant year', invalid_cycle_response.status_code == 422, invalid_cycle_response.text)

        list_cycles = client.get('/cycles', headers=manager_headers)
        cycles = list_cycles.json() if list_cycles.status_code == 200 else []
        check('GET /cycles manager', list_cycles.status_code == 200 and any(item.get('cycle_year') == cycle_year for item in cycles), list_cycles.text)
        check(
            'GET /cycles excludes irrelevant future years',
            all(2000 <= int(item.get('cycle_year')) <= current_year + 5 for item in cycles),
            list_cycles.text,
        )

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

        response = client.post('/login', json={'email': company_email, 'password': 'password123'})
        new_company_user = response.json() if response.status_code == 200 else {}
        company_token = response.cookies.get('esg_session')
        company_headers = {'Authorization': f'Bearer {company_token}'} if company_token else {}
        check('login:new company', response.status_code == 200 and new_company_user.get('role') == 'company', response.text)

        response = client.get(f"/dashboard/company/{new_company_user['id']}", headers=company_headers)
        company_dashboard = response.json() if response.status_code == 200 else []
        company_id = company_dashboard[0]['id'] if company_dashboard else None
        check(
            'dashboard/company shows created company',
            response.status_code == 200 and company_id is not None and company_dashboard[0]['name'] == company_name,
            response.text,
        )
        check('company dashboard includes timing telemetry', 'app;dur=' in response.headers.get('server-timing', ''), dict(response.headers))
        check('company dashboard exposes app duration', float(response.headers.get('x-app-duration-ms', -1)) >= 0, dict(response.headers))

        target_response = client.post(f'/company/{company_id}/targets', json={
            'pillar': 'Environmental',
            'metric_key': 'total_ghg_emissions',
            'target_name': 'Reduce operational emissions',
            'baseline_value': 100,
            'target_value': 70,
            'current_value': 85,
            'unit': 'tCO2e',
            'target_date': '2030-12-31',
            'owner': 'Sustainability Lead',
            'status': 'on track',
            'notes': 'QA target',
        }, headers=manager_headers)
        target_payload = target_response.json() if target_response.status_code == 200 else {}
        check(
            'POST /company/{id}/targets creates measurable target',
            target_response.status_code == 200 and target_payload.get('progress_percent') == 50.0,
            target_response.text,
        )
        target_update = client.patch(
            f"/targets/{target_payload.get('id')}",
            json={'current_value': 75, 'status': 'on track'},
            headers=company_headers,
        )
        check(
            'PATCH /targets/{id} updates company target progress',
            target_update.status_code == 200 and target_update.json().get('progress_percent') == 83.3,
            target_update.text,
        )
        target_list = client.get('/targets', headers=investor_headers)
        check(
            'GET /targets exposes read-only target register',
            target_list.status_code == 200 and any(item.get('id') == target_payload.get('id') for item in target_list.json()),
            target_list.text,
        )
        target_forbidden = client.patch(
            f"/targets/{target_payload.get('id')}",
            json={'status': 'achieved'},
            headers=investor_headers,
        )
        check('PATCH /targets blocks investor writes', target_forbidden.status_code == 403, target_forbidden.text)

        malformed_preview = client.post(
            '/admin/import/submissions',
            data={'mode': 'preview', 'cycle_id': str(cycle.get('id') or '')},
            files={'file': ('malformed.csv', f'company_name,reporting_year,female_representation_percent\n{company_name},{cycle_year},11442,shifted\n', 'text/csv')},
            headers=manager_headers,
        )
        malformed_payload = malformed_preview.json() if malformed_preview.status_code == 200 else {}
        check(
            'CSV preview rejects shifted rows without importing',
            malformed_preview.status_code == 200
            and malformed_payload.get('summary', {}).get('accepted') == 0
            and malformed_payload.get('summary', {}).get('rejected') == 1
            and any('shifted or malformed' in message for message in malformed_payload.get('rows', [{}])[0].get('errors', [])),
            malformed_preview.text,
        )

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
            'section_comment_environmental': 'QA variance explanation for environmental metrics.',
            'section_comment_social': 'QA variance explanation for social metrics.',
            'section_comment_governance': 'QA variance explanation for governance metrics.',
        }

        invalid_percentage_payload = {**submission_payload, 'female_representation_percent': 11442}
        invalid_percentage = client.post(f'/company/{company_id}/submissions', json=invalid_percentage_payload, headers=manager_headers)
        check('percentage values outside 0-100 are rejected', invalid_percentage.status_code == 422, invalid_percentage.text)

        first_draft = client.put(
            f'/company/{company_id}/draft',
            json={'payload': {'scope_1_emissions': 8, 'submission_notes': 'First synced draft'}},
            headers=company_headers,
        )
        first_draft_payload = first_draft.json() if first_draft.status_code == 200 else {}
        second_draft = client.put(
            f'/company/{company_id}/draft',
            json={'payload': {'scope_1_emissions': 10, 'submission_notes': 'Updated synced draft'}},
            headers=company_headers,
        )
        second_draft_payload = second_draft.json() if second_draft.status_code == 200 else {}
        check(
            'draft upserts one row per company/cycle',
            first_draft.status_code == 200
            and second_draft.status_code == 200
            and first_draft_payload.get('id') == second_draft_payload.get('id'),
            second_draft.text,
        )

        evidence_upload = client.post(
            f'/company/{company_id}/upload-evidence',
            data={'metric_key': 'scope_1_emissions'},
            files={'file': ('scope-1-proof.pdf', b'qa-evidence', 'application/pdf')},
            headers=company_headers,
        )
        evidence_payload = evidence_upload.json() if evidence_upload.status_code == 200 else {}
        evidence_download = client.get(
            f"/company/{company_id}/evidence/{evidence_payload.get('id')}",
            headers=company_headers,
        )
        draft_read = client.get(f'/company/{company_id}/draft', headers=company_headers)
        draft_read_payload = draft_read.json() if draft_read.status_code == 200 else {}
        check(
            'evidence is connected to metric and returned with draft',
            evidence_upload.status_code == 200
            and evidence_payload.get('metric_key') == 'scope_1_emissions'
            and evidence_download.status_code == 200
            and evidence_download.content == b'qa-evidence'
            and any(item.get('id') == evidence_payload.get('id') for item in draft_read_payload.get('evidence', [])),
            evidence_upload.text,
        )

        investor_write_attempt = client.post(f'/company/{company_id}/submissions', json=submission_payload, headers=investor_headers)
        check('investor blocked from submission writes', investor_write_attempt.status_code == 403, investor_write_attempt.text)

        initial_submit = client.post(f'/company/{company_id}/submissions', json=submission_payload, headers=manager_headers)
        submission = initial_submit.json() if initial_submit.status_code == 200 else {}
        submission_id = submission.get('id')
        check('active cycle accepts submission', initial_submit.status_code == 200 and submission.get('status') == 'submitted', initial_submit.text)

        assurance_before = client.get(f'/submissions/{submission_id}/assurance', headers=manager_headers)
        assurance_before_payload = assurance_before.json() if assurance_before.status_code == 200 else {}
        assurance_update = client.put(
            f'/submissions/{submission_id}/assurance/scope_1_emissions',
            json={
                'evidence_id': evidence_payload.get('id'),
                'status': 'assured',
                'assurance_level': 'limited',
                'conclusion': 'Meter evidence reconciled to the reported value.',
            },
            headers=manager_headers,
        )
        assurance_payload = assurance_update.json() if assurance_update.status_code == 200 else {}
        check(
            'assurance workflow records metric evidence decisions',
            assurance_before.status_code == 200
            and assurance_before_payload.get('total_metrics') == 1
            and assurance_update.status_code == 200
            and assurance_payload.get('assured') == 1
            and assurance_payload.get('completion_percent') == 100.0,
            assurance_update.text,
        )
        assurance_investor = client.get(f'/submissions/{submission_id}/assurance', headers=investor_headers)
        assurance_investor_write = client.put(
            f'/submissions/{submission_id}/assurance/scope_1_emissions',
            json={'status': 'exception', 'assurance_level': 'limited', 'conclusion': 'Blocked'},
            headers=investor_headers,
        )
        check(
            'investors can read but cannot change assurance decisions',
            assurance_investor.status_code == 200 and assurance_investor_write.status_code == 403,
            assurance_investor_write.text,
        )

        duplicate_submit = client.post(f'/company/{company_id}/submissions', json=submission_payload, headers=manager_headers)
        check('submitted form is locked and duplicate row blocked', duplicate_submit.status_code == 423, duplicate_submit.text)

        to_under_review = client.patch(f'/submissions/{submission_id}/status', json={'status': 'under review'}, headers=manager_headers)
        check('submitted -> under review', to_under_review.status_code == 200 and to_under_review.json().get('status') == 'under review', to_under_review.text)

        metric_comment = client.put(
            f'/submissions/{submission_id}/metric-comments',
            json={'metric_key': 'scope_1_emissions', 'comment': 'Attach the meter reconciliation.'},
            headers=manager_headers,
        )
        metric_comments = client.get(f'/submissions/{submission_id}/metric-comments', headers=manager_headers)
        check(
            'reviewer comments persist against individual metrics',
            metric_comment.status_code == 200
            and metric_comments.status_code == 200
            and any(item.get('metric_key') == 'scope_1_emissions' for item in metric_comments.json()),
            metric_comment.text,
        )

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
        company_notifications = client.get('/notifications', headers=company_headers)
        check(
            'resubmission request creates company notification',
            company_notifications.status_code == 200
            and any(item.get('type') == 'resubmission' for item in company_notifications.json().get('items', [])),
            company_notifications.text,
        )

        editable_resubmission = client.get(f'/company/{company_id}/draft', headers=company_headers)
        check(
            'manager resubmission request unlocks synced draft',
            editable_resubmission.status_code == 200 and editable_resubmission.json().get('can_edit') is True,
            editable_resubmission.text,
        )

        resubmit = client.post(f'/company/{company_id}/submissions', json=submission_payload, headers=manager_headers)
        resubmitted = resubmit.json() if resubmit.status_code == 200 else {}
        check(
            'resubmission requested -> submitted',
            resubmit.status_code == 200 and resubmitted.get('id') == submission_id and resubmitted.get('status') == 'submitted',
            resubmit.text,
        )

        close_cycle = client.patch(f"/cycles/{cycle['id']}/status", json={'status': 'closed'}, headers=manager_headers)
        check('PATCH /cycles/{id}/status close', close_cycle.status_code == 200 and close_cycle.json().get('status') == 'closed', close_cycle.text)

        blocked_submit = client.post(f'/company/{company_id}/submissions', json=submission_payload, headers=manager_headers)
        check('closed cycle blocks write', blocked_submit.status_code == 423, blocked_submit.text)

        unlock_response = client.post(
            f'/submissions/{submission_id}/unlock',
            json={'reason': 'Allow corrections after close', 'expiry_hours': 2},
            headers=manager_headers,
        )
        unlock_payload = unlock_response.json() if unlock_response.status_code == 200 else {}
        check('POST /submissions/{id}/unlock', unlock_response.status_code == 200 and unlock_payload.get('active') is True, unlock_response.text)

        submission_history = client.get(f'/submissions/{submission_id}/history', headers=manager_headers)
        history_payload = submission_history.json() if submission_history.status_code == 200 else []
        check(
            'GET /submissions/{id}/history returns review and unlock audit events',
            submission_history.status_code == 200
            and any(item.get('event_type') == 'review' and item.get('created_at') for item in history_payload)
            and any(item.get('event_type') == 'unlock' and item.get('expires_at') for item in history_payload),
            submission_history.text,
        )

        company_history_attempt = client.get(f'/submissions/{submission_id}/history', headers=company_headers)
        check('submission audit history restricted to managers', company_history_attempt.status_code == 403, company_history_attempt.text)

        unlocked_submit = client.post(f'/company/{company_id}/submissions', json=submission_payload, headers=manager_headers)
        unlocked_submission = unlocked_submit.json() if unlocked_submit.status_code == 200 else {}
        check(
            'unlock allows temporary write without duplicate submission',
            unlocked_submit.status_code == 200 and unlocked_submission.get('id') == submission_id,
            unlocked_submit.text,
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

        validate_response = client.post(f'/submissions/{submission_id}/validate', headers=manager_headers)
        check('POST /submissions/{id}/validate', validate_response.status_code == 200 and 'flagged' in validate_response.json(), validate_response.text)

        metadata = client.get('/reports/edci')
        check('GET /reports/edci metadata', metadata.status_code == 200 and metadata.json().get('report_type') == 'EDCI', metadata.text)

        csv_export = client.get(f'/reports/edci/export?format=csv&period=FY{cycle_year}&portfolio=All%20Portfolio%20Companies', headers=manager_headers)
        csv_payload = csv_export.json() if csv_export.status_code == 200 else {}
        csv_ok = False
        if csv_payload.get('file_path'):
            csv_file = Path(csv_payload['file_path'])
            csv_ok = csv_file.exists() and csv_file.stat().st_size > 0 and csv_payload.get('content_type') == 'text/csv'
        check('GET /reports/{type}/export csv', csv_export.status_code == 200 and csv_ok, csv_export.text)

        pdf_export = client.get(f'/reports/sfdr/export?format=pdf&period=FY{cycle_year}&portfolio=All%20Portfolio%20Companies', headers=manager_headers)
        pdf_payload = pdf_export.json() if pdf_export.status_code == 200 else {}
        pdf_ok = False
        if pdf_payload.get('file_path'):
            pdf_file = Path(pdf_payload['file_path'])
            pdf_ok = (
                pdf_file.exists()
                and pdf_file.stat().st_size > 5_000
                and pdf_file.read_bytes()[:4] == b'%PDF'
                and pdf_payload.get('content_type') == 'application/pdf'
            )
        check('GET /reports/{type}/export pdf', pdf_export.status_code == 200 and pdf_ok, pdf_export.text)

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
