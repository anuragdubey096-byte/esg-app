import json
import time

from fastapi.testclient import TestClient

from main import app


def run_self_test():
    results = []

    def check(name, condition, detail=''):
        results.append((name, bool(condition), detail))

    with TestClient(app) as client:
        for email, expected_role in [
            ('manager@example.com', 'manager'),
            ('investor@example.com', 'investor'),
            ('company@example.com', 'company'),
        ]:
            response = client.post('/login', json={'email': email, 'password': 'password123'})
            ok = response.status_code == 200 and response.json().get('role') == expected_role
            check(f'login:{email}', ok, response.text)

        response = client.get('/dashboard/manager')
        check('GET /dashboard/manager', response.status_code == 200 and isinstance(response.json(), list), f'status={response.status_code}')

        # --- Test RBAC Middleware ---
        rbac_fail = client.get('/dashboard/manager', headers={'x-user-role': 'investor'})
        check('GET /dashboard/manager (RBAC Block)', rbac_fail.status_code == 403, rbac_fail.text)

        response = client.get('/dashboard/investor')
        check('GET /dashboard/investor', response.status_code == 200 and 'portfolio_esg_score' in response.json(), f'status={response.status_code}')

        response = client.get('/analytics/portfolio')
        check('GET /analytics/portfolio', response.status_code == 200 and 'portfolio_esg_score' in response.json(), f'status={response.status_code}')

        company_login = client.post('/login', json={'email': 'company@example.com', 'password': 'password123'}).json()
        response = client.get(f"/dashboard/company/{company_login['id']}")
        check(
            'GET /dashboard/company/{id}',
            response.status_code == 200 and isinstance(response.json(), list) and len(response.json()) > 0,
            f'status={response.status_code}, body={response.text}',
        )

        stamp = int(time.time())
        company_email = f'qa_{stamp}@example.com'
        company_name = f'QA Company {stamp}'
        response = client.post('/companies', json={
            'name': company_name,
            'sector': 'Testing',
            'contact_name': 'QA User',
            'contact_email': company_email,
        })
        created_company = response.json() if response.status_code == 200 else {}
        check('POST /companies', response.status_code == 200 and created_company.get('portfolio_user_email') == company_email, response.text)

        cycle_year = 2500 + (stamp % 100)
        response = client.post('/cycles', json={
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
        })
        cycle = response.json() if response.status_code == 200 else {}
        check('POST /cycles', response.status_code == 200 and cycle.get('cycle_year') == cycle_year, response.text)

        response = client.get('/cycles')
        cycles = response.json() if response.status_code == 200 else []
        check('GET /cycles', response.status_code == 200 and any(item.get('cycle_year') == cycle_year for item in cycles), f'status={response.status_code}')

        response = client.post('/login', json={'email': company_email, 'password': 'password123'})
        new_portfolio = response.json() if response.status_code == 200 else {}
        check('login:new portfolio company', response.status_code == 200 and new_portfolio.get('role') == 'company', response.text)

        response = client.get(f"/dashboard/company/{new_portfolio['id']}")
        company_dashboard = response.json() if response.status_code == 200 else []
        company_id = company_dashboard[0]['id'] if company_dashboard else None
        check(
            'new portfolio dashboard has company',
            response.status_code == 200 and company_id is not None and company_dashboard[0]['name'] == company_name,
            response.text,
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
        }

        response = client.post(f'/company/{company_id}/submissions', json=submission_payload)
        submission = response.json() if response.status_code == 200 else {}
        check('POST /company/{id}/submissions', response.status_code == 200 and submission.get('status') == 'submitted', response.text)

        response = client.get(f"/dashboard/company/{new_portfolio['id']}")
        refreshed = response.json() if response.status_code == 200 else []
        stored = refreshed[0]['submissions'][-1] if refreshed and refreshed[0]['submissions'] else None
        stored_ok = False
        if stored:
            esg = json.loads(stored['esg_data'])
            stored_ok = (
                esg.get('scope_1_emissions') == 10 and
                esg.get('whs_policy_document_reference') == 'whs-policy.pdf' and
                esg.get('submission_notes') == 'QA submission'
            )
        check('submitted values stored and returned', stored_ok, stored['esg_data'] if stored else 'missing submission')

        submission_id = stored['id'] if stored else None
        response = client.patch(f'/submissions/{submission_id}/status', json={'status': 'approved'})
        check('PATCH /submissions/{id}/status', response.status_code == 200 and response.json().get('status') == 'approved', response.text)

        response = client.get('/dashboard/manager')
        manager_dashboard = response.json() if response.status_code == 200 else []
        found = next((company for company in manager_dashboard if company['id'] == company_id), None)
        check(
            'manager dashboard reflects updated status',
            bool(found and found['submissions'] and found['submissions'][-1]['status'] == 'approved'),
            str(found),
        )

        response = client.post(f'/company/{company_id}/action-plans', json={
            'initiative_name': 'Reduce Employee Turnover',
            'target_completion_date': '2026-12-31',
            'assigned_owner': 'HR Director'
        })
        check('POST /company/{id}/action-plans', response.status_code == 200 and response.json().get('status') == 'planned', response.text)

        response = client.post('/calculator/ghg', json={'fuel_liters': 1000, 'electricity_kwh': 5000})
        check('POST /calculator/ghg', response.status_code == 200 and response.json().get('total_tco2e') > 0, response.text)

        response = client.post(f'/company/{company_id}/upload-evidence', files={'file': ('policy.pdf', b'dummy content', 'application/pdf')})
        check('POST /company/{id}/upload-evidence', response.status_code == 200, response.text)

        # Test validation on Solar Tech submission (ID=2) which has year-over-year variance from prior baseline
        response = client.post('/submissions/2/validate')
        check('POST /submissions/{id}/validate', response.status_code == 200 and response.json().get('flagged') is True, response.text)

        response = client.post(f'/submissions/{submission_id}/review', json={
            'reviewer_role': 'Manager',
            'review_status': 'resubmission requested',
            'review_comment': 'Please check your Scope 1 emissions, it seems too high.'
        })
        check('POST /submissions/{id}/review', response.status_code == 200 and response.json().get('status') == 'resubmission requested', response.text)

        response = client.get('/reports/edci')
        check('GET /reports/edci', response.status_code == 200, response.text)

        # --- Test v2 Hierarchical JSON Payload ---
        v2_payload = {
            "company_id": company_id,
            "reporting_year": 2026,
            "environmental": {
                "scope_1_emissions": 100.0,
                "scope_1_confidence": "Measured",
                "scope_2_location_based": 50.0,
                "scope_2_confidence": "Measured",
                "scope_3_emissions": 25.0,
                "scope_3_confidence": "Estimated"
            },
            "social": {
                "whs_policy_in_place": True,
                "whs_document_reference": "whs.pdf",
                "trifr": 1.2,
                "female_representation_percent": 45.5
            },
            "governance": {
                "esg_policy_in_place": True,
                "esg_document_reference": "esg.pdf",
                "female_board_members_percent": 33.3
            },
            "prefilled_data": {
                "scope_1_emissions": 50.0  # 100% variance compared to 100.0 above
            }
        }
        
        # 1. Should fail because variance > 30% and no submission_notes are provided
        response = client.post('/api/v2/submissions', json=v2_payload)
        check('POST /api/v2/submissions (validation failure)', response.status_code == 422 and 'submission_notes' in response.text, response.text)

        # 2. Should pass after adding the required submission_notes explanation
        v2_payload["submission_notes"] = "Emissions doubled due to new factory acquisition."
        response = client.post('/api/v2/submissions', json=v2_payload)
        check('POST /api/v2/submissions (success)', response.status_code == 200 and response.json().get('total_ghg_emissions') == 175.0, response.text)

    return results


if __name__ == '__main__':
    results = run_self_test()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f'SUMMARY: {passed}/{len(results)} passed')
