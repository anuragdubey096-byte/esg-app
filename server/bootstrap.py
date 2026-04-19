import json

from database import IS_SQLITE, SQLITE_DB_PATH, SessionLocal, engine
from models import Base, CollectionCycle, Company, Submission, User, ReviewAction, ValidationFlag
from login_users import seed_login_users_from_csv


def build_sample_submission(
    *,
    scope_1=10.0,
    scope_2_location=20.0,
    scope_2_market=18.0,
    scope_3=30.0,
    total_energy=100.0,
    renewable_energy=40.0,
    total_water=200.0,
    recycled_water=50.0,
    total_waste=80.0,
    diverted_waste=20.0,
    hazardous_waste=5.0,
    trifr=0.5,
    employee_turnover=8.0,
    female_representation=45.0,
    female_leadership=40.0,
    community_spend=10000.0,
    independent_board=50.0,
    female_board=33.0,
    notes='Sample seeded ESG submission',
):
    total_ghg = scope_1 + scope_2_location + scope_3
    return {
        'scope_1_emissions': scope_1,
        'scope_1_emissions_confidence': 'Measured',
        'scope_2_location_based': scope_2_location,
        'scope_2_location_based_confidence': 'Measured',
        'scope_2_market_based': scope_2_market,
        'scope_2_market_based_confidence': 'Estimated',
        'scope_3_emissions': scope_3,
        'scope_3_emissions_confidence': 'Measured',
        'total_ghg_emissions': total_ghg,
        'total_ghg_emissions_confidence': 'Measured',
        'reduction_target_percent': 15.0,
        'reduction_target_percent_confidence': 'Measured',
        'reduction_target_year': 2028,
        'reduction_target_year_confidence': 'Measured',
        'reduction_strategy_description': 'Operational efficiency and renewable transition plan',
        'total_energy_consumption': total_energy,
        'total_energy_consumption_confidence': 'Measured',
        'renewable_energy_consumption': renewable_energy,
        'renewable_energy_consumption_confidence': 'Measured',
        'total_water_withdrawal': total_water,
        'total_water_withdrawal_confidence': 'Measured',
        'water_recycled_reused': recycled_water,
        'water_recycled_reused_confidence': 'Measured',
        'total_waste_generated': total_waste,
        'total_waste_generated_confidence': 'Measured',
        'waste_diverted_from_landfill': diverted_waste,
        'waste_diverted_from_landfill_confidence': 'Measured',
        'hazardous_waste_generated': hazardous_waste,
        'hazardous_waste_generated_confidence': 'Measured',
        'air_quality_control_measures': 'Yes',
        'air_quality_control_measures_confidence': 'Measured',
        'nox_sox_emissions': 1.0,
        'nox_sox_emissions_confidence': 'Estimated',
        'whs_policy_in_place': 'Yes',
        'whs_policy_in_place_confidence': 'Measured',
        'whs_policy_document_reference': 'whs-policy.pdf',
        'trifr': trifr,
        'trifr_confidence': 'Measured',
        'total_fatalities': 0,
        'total_fatalities_confidence': 'Measured',
        'total_lost_time_injuries': 1,
        'total_lost_time_injuries_confidence': 'Measured',
        'total_incidents_reported': 3,
        'total_incidents_reported_confidence': 'Measured',
        'total_employees_fte': 120,
        'total_employees_fte_confidence': 'Measured',
        'employee_turnover_rate': employee_turnover,
        'employee_turnover_rate_confidence': 'Measured',
        'female_representation_percent': female_representation,
        'female_representation_percent_confidence': 'Measured',
        'female_leadership_representation_percent': female_leadership,
        'female_leadership_representation_percent_confidence': 'Measured',
        'community_investment_spend': community_spend,
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
        'independent_board_members_percent': independent_board,
        'independent_board_members_percent_confidence': 'Measured',
        'female_board_members_percent': female_board,
        'female_board_members_percent_confidence': 'Measured',
        'submission_notes': notes,
}


def seed_sample_data(db):
    seed_login_users_from_csv(db)

    # Create collection cycles
    from datetime import datetime, timedelta
    if db.query(CollectionCycle).count() == 0:
        # Create 2026 active cycle with deadline
        today = datetime.utcnow()
        deadline = today + timedelta(days=30)
        db.add(
            CollectionCycle(
                cycle_year=2026,
                submission_open_date=today.strftime('%Y-%m-%d'),
                submission_deadline=deadline.strftime('%Y-%m-%d'),
                extension_date=None,
                reminder_schedule='["Day 1", "Day 7", "Day 14", "Day 28"]',
                template_config='{}',
                prefill_summary='{}',
                status='active',
            )
        )
        db.commit()

    sample_companies = [
        ('Solar Tech', 'Renewable Energy', 'APAC', 'Senior Secured Debt', 'company@example.com', 'submitted'),
        ('Healthy Foods', 'Consumer Goods', 'North America', 'Direct Lending', 'healthyfoods@example.com', 'approved'),
        ('Acme Target', 'Software', 'EMEA', 'Mezzanine Finance', 'target@example.com', 'pre-acquisition'),
    ]
    for company_name, sector, geography, asset_class, owner_email, current_status in sample_companies:
        existing_company = db.query(Company).filter(Company.name == company_name).first()
        owner = db.query(User).filter(User.email == owner_email).first()
        if not existing_company and owner:
            db.add(
                Company(
                    name=company_name,
                    sector=sector,
                    user_id=owner.id,
                    geography=geography,
                    asset_class=asset_class,
                    current_status=current_status,
                )
            )
    db.commit()

    if db.query(Submission).count() == 0:
        solar_company = db.query(Company).filter(Company.name == 'Solar Tech').first()
        healthy_company = db.query(Company).filter(Company.name == 'Healthy Foods').first()
        active_cycle = db.query(CollectionCycle).filter(CollectionCycle.status == 'active').first()
        
        if solar_company and active_cycle:
            # Baseline submission for year-over-year comparison
            db.add(
                Submission(
                    company_id=solar_company.id,
                    cycle_id=active_cycle.id,
                    esg_data=json.dumps(
                        build_sample_submission(
                            scope_1=8.5,
                            scope_2_location=14.0,
                            scope_2_market=13.0,
                            scope_3=24.0,
                            total_energy=78.0,
                            renewable_energy=31.0,
                            total_water=180.0,
                            recycled_water=45.0,
                            total_waste=72.0,
                            diverted_waste=20.0,
                            hazardous_waste=4.5,
                            trifr=0.5,
                            employee_turnover=8.0,
                            female_representation=42.0,
                            female_leadership=38.0,
                            community_spend=10000.0,
                            independent_board=46.0,
                            female_board=29.0,
                            notes='Solar Tech prior year baseline submission',
                        )
                    ),
                    status='submitted',
                )
            )
            # Current year submission with year-over-year variance
            db.add(
                Submission(
                    company_id=solar_company.id,
                    cycle_id=active_cycle.id,
                    esg_data=json.dumps(
                        build_sample_submission(
                            scope_1=12.0,
                            scope_2_location=21.0,
                            scope_2_market=19.0,
                            scope_3=34.0,
                            total_energy=110.0,
                            renewable_energy=43.0,
                            total_water=220.0,
                            recycled_water=58.0,
                            total_waste=90.0,
                            diverted_waste=24.0,
                            hazardous_waste=5.5,
                            trifr=0.7,
                            employee_turnover=9.1,
                            female_representation=44.0,
                            female_leadership=39.0,
                            community_spend=12000.0,
                            independent_board=48.0,
                            female_board=31.0,
                            notes='Solar Tech seeded baseline submission',
                        )
                    ),
                    status='submitted',
                )
            )
        if healthy_company and active_cycle:
            db.add(
                Submission(
                    company_id=healthy_company.id,
                    cycle_id=active_cycle.id,
                    esg_data=json.dumps(
                        build_sample_submission(
                            scope_1=8.5,
                            scope_2_location=16.0,
                            scope_2_market=14.5,
                            scope_3=27.0,
                            total_energy=87.0,
                            renewable_energy=39.0,
                            total_water=172.0,
                            recycled_water=62.0,
                            total_waste=65.0,
                            diverted_waste=26.0,
                            hazardous_waste=3.2,
                            trifr=0.3,
                            employee_turnover=6.4,
                            female_representation=49.0,
                            female_leadership=43.0,
                            community_spend=15000.0,
                            independent_board=56.0,
                            female_board=38.0,
                            notes='Healthy Foods seeded baseline submission',
                        )
                    ),
                    status='approved',
                )
            )
            db.add(
                ReviewAction(
                    company_id=healthy_company.id,
                    reporting_year=2026,
                    review_status='approved',
                    reviewer_role='Manager',
                    review_comment='Looks good, approved for 2026.'
                )
            )
        if solar_company:
            db.add(
                ValidationFlag(
                    company_id=solar_company.id,
                    reporting_year=2026,
                    flag_type='Variance Alert',
                    field_name='scope_1_emissions',
                    issue_description='Scope 1 emissions increased by 40% year-on-year.',
                    severity='Medium'
                )
            )
        db.commit()


def reset_database():
    engine.dispose()
    if IS_SQLITE and SQLITE_DB_PATH.exists():
        try:
            SQLITE_DB_PATH.unlink()
        except PermissionError:
            pass

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_sample_data(db)
    finally:
        db.close()


def clear_runtime_data():
    db = SessionLocal()
    try:
        db.query(CollectionCycle).delete()
        db.query(Submission).delete()
        db.query(Company).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()
