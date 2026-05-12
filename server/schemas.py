from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ForgotPasswordResponse(BaseModel):
    message: str


class SSOLoginRequest(BaseModel):
    email_hint: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str

    class Config:
        from_attributes = True


class SubmissionCreateRequest(BaseModel):
    scope_1_emissions: float = Field(ge=0)
    scope_1_emissions_confidence: str
    scope_2_location_based: float = Field(ge=0)
    scope_2_location_based_confidence: str
    scope_2_market_based: float = Field(ge=0)
    scope_2_market_based_confidence: str
    scope_3_emissions: float = Field(ge=0)
    scope_3_emissions_confidence: str
    total_ghg_emissions: float = Field(ge=0)
    total_ghg_emissions_confidence: str
    reduction_target_percent: float = Field(ge=0, le=100)
    reduction_target_percent_confidence: str
    reduction_target_year: int = Field(ge=2026)
    reduction_target_year_confidence: str
    reduction_strategy_description: Optional[str] = None
    total_energy_consumption: float = Field(ge=0)
    total_energy_consumption_confidence: str
    renewable_energy_consumption: float = Field(ge=0)
    renewable_energy_consumption_confidence: str
    total_water_withdrawal: float = Field(ge=0)
    total_water_withdrawal_confidence: str
    water_recycled_reused: float = Field(ge=0)
    water_recycled_reused_confidence: str
    total_waste_generated: float = Field(ge=0)
    total_waste_generated_confidence: str
    waste_diverted_from_landfill: float = Field(ge=0)
    waste_diverted_from_landfill_confidence: str
    hazardous_waste_generated: float = Field(ge=0)
    hazardous_waste_generated_confidence: str
    air_quality_control_measures: str
    air_quality_control_measures_confidence: str
    nox_sox_emissions: float = Field(ge=0)
    nox_sox_emissions_confidence: str

    whs_policy_in_place: str
    whs_policy_in_place_confidence: str
    whs_policy_document_reference: Optional[str] = None
    trifr: float = Field(ge=0)
    trifr_confidence: str
    total_fatalities: int = Field(ge=0)
    total_fatalities_confidence: str
    total_lost_time_injuries: int = Field(ge=0)
    total_lost_time_injuries_confidence: str
    total_incidents_reported: int = Field(ge=0)
    total_incidents_reported_confidence: str
    total_employees_fte: int = Field(gt=0)
    total_employees_fte_confidence: str
    employee_turnover_rate: float = Field(ge=0, le=100)
    employee_turnover_rate_confidence: str
    female_representation_percent: float = Field(ge=0, le=100)
    female_representation_percent_confidence: str
    female_leadership_representation_percent: float = Field(ge=0, le=100)
    female_leadership_representation_percent_confidence: str
    community_investment_spend: float = Field(ge=0)
    community_investment_spend_confidence: str

    esg_policy_in_place: str
    esg_policy_in_place_confidence: str
    esg_policy_document_reference: Optional[str] = None
    board_level_esg_oversight: str
    board_level_esg_oversight_confidence: str
    esg_kpis_linked_to_remuneration: str
    esg_kpis_linked_to_remuneration_confidence: str
    cybersecurity_policy_in_place: str
    cybersecurity_policy_in_place_confidence: str
    cybersecurity_policy_document_reference: Optional[str] = None
    cyber_incidents_in_reporting_period: int = Field(ge=0)
    cyber_incidents_in_reporting_period_confidence: str
    anti_bribery_corruption_policy: str
    anti_bribery_corruption_policy_confidence: str
    confirmed_cases_of_corruption: int = Field(ge=0)
    confirmed_cases_of_corruption_confidence: str
    total_board_members: int = Field(gt=0)
    total_board_members_confidence: str
    independent_board_members_percent: float = Field(ge=0, le=100)
    independent_board_members_percent_confidence: str
    female_board_members_percent: float = Field(ge=0, le=100)
    female_board_members_percent_confidence: str

    submission_notes: Optional[str] = None
    section_comment_environmental: Optional[str] = None
    section_comment_social: Optional[str] = None
    section_comment_governance: Optional[str] = None

    @model_validator(mode='after')
    def validate_submission(self):
        allowed_yes_no = {'Yes', 'No'}
        confidence_values = {'Measured', 'Estimated', 'Not Available'}

        yes_no_fields = [
            'air_quality_control_measures',
            'whs_policy_in_place',
            'esg_policy_in_place',
            'board_level_esg_oversight',
            'esg_kpis_linked_to_remuneration',
            'cybersecurity_policy_in_place',
            'anti_bribery_corruption_policy',
        ]
        for field_name in yes_no_fields:
            if getattr(self, field_name) not in allowed_yes_no:
                raise ValueError(f'{field_name} must be Yes or No')

        for field_name, value in self.__dict__.items():
            if field_name.endswith('_confidence') and value not in confidence_values:
                raise ValueError(f'{field_name} must be one of Measured, Estimated, or Not Available')

        if abs(self.total_ghg_emissions - (self.scope_1_emissions + self.scope_2_location_based + self.scope_3_emissions)) > 0.01:
            raise ValueError('Total GHG emissions must equal Scope 1 + Scope 2 (location-based) + Scope 3 emissions')

        if self.renewable_energy_consumption > self.total_energy_consumption:
            raise ValueError('Renewable energy consumption cannot exceed total energy consumption')

        if self.water_recycled_reused > self.total_water_withdrawal:
            raise ValueError('Water recycled or reused cannot exceed total water withdrawal')

        if self.waste_diverted_from_landfill > self.total_waste_generated:
            raise ValueError('Waste diverted from landfill cannot exceed total waste generated')

        if self.reduction_target_percent > 0:
            if not (self.reduction_strategy_description or '').strip():
                raise ValueError('Reduction strategy description is required when a reduction target is set')
            if self.reduction_target_year < 2026:
                raise ValueError('Reduction target year must be 2026 or later')

        if self.whs_policy_in_place == 'Yes' and not (self.whs_policy_document_reference or '').strip():
            raise ValueError('WHS policy document reference is required when a WHS policy is in place')

        if self.esg_policy_in_place == 'Yes' and not (self.esg_policy_document_reference or '').strip():
            raise ValueError('ESG policy document reference is required when an ESG policy is in place')

        if self.cybersecurity_policy_in_place == 'Yes' and not (self.cybersecurity_policy_document_reference or '').strip():
            raise ValueError('Cybersecurity policy document reference is required when a cybersecurity policy is in place')

        return self


class SubmissionInfo(BaseModel):
    id: int
    esg_data: str
    status: str
    cycle_id: Optional[int] = None

    class Config:
        from_attributes = True


class ActionPlanInfo(BaseModel):
    id: int
    initiative_name: str
    target_completion_date: str
    assigned_owner: str
    status: str

    class Config:
        from_attributes = True


class ActionPlanCreateRequest(BaseModel):
    initiative_name: str
    target_completion_date: str
    assigned_owner: str

class CarbonBreakdownItem(BaseModel):
    scope: str
    category: str
    activity: str
    amount: float
    unit: str
    emission_factor_kg_per_unit: float
    emissions_tco2e: float

class GHGCalculatorRequest(BaseModel):
    # Legacy fields kept for compatibility.
    fuel_liters: float = Field(default=0, ge=0)
    electricity_kwh: float = Field(default=0, ge=0)
    # Enhanced carbon calculator inputs.
    natural_gas_kwh: float = Field(default=0, ge=0)
    lpg_liters: float = Field(default=0, ge=0)
    refrigerant_kg: float = Field(default=0, ge=0)
    renewable_electricity_kwh: float = Field(default=0, ge=0)
    grid_emission_factor_kg_per_kwh: Optional[float] = Field(default=None, ge=0)
    business_travel_car_km: float = Field(default=0, ge=0)
    business_travel_rail_km: float = Field(default=0, ge=0)
    business_travel_flight_km: float = Field(default=0, ge=0)
    waste_tonnes: float = Field(default=0, ge=0)
    wastewater_m3: float = Field(default=0, ge=0)

class GHGCalculatorResponse(BaseModel):
    scope_1_tco2e: float
    scope_2_tco2e: float
    scope_2_market_tco2e: float
    scope_3_tco2e: float
    total_tco2e: float
    methodology_version: str
    assumptions: List[str] = []
    breakdown: List[CarbonBreakdownItem] = []

class ReviewSubmissionRequest(BaseModel):
    reviewer_role: str
    review_status: str
    review_comment: str

class ReviewActionInfo(BaseModel):
    id: int
    reporting_year: int
    review_status: str
    reviewer_role: str
    review_comment: Optional[str] = None

    class Config:
        from_attributes = True

class ValidationFlagInfo(BaseModel):
    id: int
    reporting_year: int
    flag_type: str
    field_name: str
    issue_description: str
    severity: str

    class Config:
        from_attributes = True


class ValidationDecisionRequest(BaseModel):
    field_name: str
    decision: str
    comment: Optional[str] = None

class CompanyDetail(BaseModel):
    id: int
    name: str
    sector: str
    geography: Optional[str] = None
    current_status: Optional[str] = None
    submissions: List[SubmissionInfo]
    action_plans: List[ActionPlanInfo] = []
    review_actions: List[ReviewActionInfo] = []
    validation_flags: List[ValidationFlagInfo] = []

    class Config:
        from_attributes = True


class CompanySummary(BaseModel):
    id: int
    name: str
    sector: str
    status: str

    class Config:
        from_attributes = True


class InvestorSummary(BaseModel):
    total_companies: int
    total_submissions: int
    status_counts: Dict[str, int]
    portfolio_esg_score: float
    average_ghg_emissions: float
    average_female_representation: float
    underperforming_sectors: List[str]


class InvestorTrendPoint(BaseModel):
    period: str
    total_emissions: float


class InvestorPerformer(BaseModel):
    company_name: str
    sector: str
    esg_score: float


class InvestorDashboardResponse(InvestorSummary):
    reporting_companies: int
    score_breakdown: Dict[str, float]
    emissions_totals: Dict[str, float]
    emissions_trend: List[InvestorTrendPoint]
    resource_totals: Dict[str, float]
    diversity_safety: Dict[str, float]
    governance_adoption_percent: float
    submission_funnel: Dict[str, int]
    top_performers: List[InvestorPerformer] = []
    bottom_performers: List[InvestorPerformer] = []
    data_quality: Dict[str, float]


class SubmissionStatusUpdateRequest(BaseModel):
    status: str


class CompanyCreateRequest(BaseModel):
    name: str
    sector: str
    contact_name: str
    contact_email: str
    temporary_password: str = 'password123'
    current_status: str = 'pre-acquisition'


class CompanyCreateResponse(BaseModel):
    id: int
    name: str
    sector: str
    portfolio_user_email: str
    portfolio_user_password: str


class CycleCreateRequest(BaseModel):
    cycle_year: int
    submission_open_date: str
    submission_deadline: str
    extension_date: Optional[str] = None
    reminder_days_before_deadline: List[int]
    private_equity_template: str
    real_estate_template: str
    debt_template: str
    activate_on_create: bool = True
    carry_forward_prefill: bool = True


class CycleUpdateRequest(BaseModel):
    cycle_year: Optional[int] = None
    submission_open_date: Optional[str] = None
    submission_deadline: Optional[str] = None
    extension_date: Optional[str] = None
    reminder_days_before_deadline: Optional[List[int]] = None
    private_equity_template: Optional[str] = None
    real_estate_template: Optional[str] = None
    debt_template: Optional[str] = None
    status: Optional[Literal['draft', 'active', 'closed']] = None
    carry_forward_prefill: Optional[bool] = None


class CycleInfo(BaseModel):
    id: int
    cycle_year: int
    submission_open_date: str
    submission_deadline: str
    extension_date: Optional[str]
    reminder_days_before_deadline: List[int]
    private_equity_template: str
    real_estate_template: str
    debt_template: str
    status: str
    carry_forward_prefill: bool
    prefill_company_count: int


class CycleStatusUpdateRequest(BaseModel):
    status: Literal['draft', 'active', 'closed']


class SubmissionUnlockRequest(BaseModel):
    reason: str
    expiry_hours: int = Field(default=24, ge=1, le=720)


class SubmissionUnlockInfo(BaseModel):
    id: int
    submission_id: int
    company_id: int
    cycle_id: int
    unlocked_by_user_id: Optional[int] = None
    reason: str
    expires_at: str
    created_at: str
    active: bool


class ReminderRequest(BaseModel):
    message: str
    channel: str = 'email'
    cycle_id: Optional[int] = None


class ReminderInfo(BaseModel):
    id: int
    company_id: int
    cycle_id: int
    sent_by_user_id: Optional[int] = None
    channel: str
    message: str
    created_at: str
    delivery_status: str


class ReportExportResponse(BaseModel):
    report_type: str
    format: Literal['csv', 'pdf']
    period: str
    portfolio: str
    generated_at: str
    file_name: str
    file_path: str
    download_url: str
    content_type: str
    rows_exported: int


class ManagerCycleBanner(BaseModel):
    active_cycle_year: Optional[int] = None
    submission_open_date: Optional[str] = None
    submission_deadline: Optional[str] = None
    days_remaining: Optional[int] = None
    cycle_status: str = 'closed'


class ManagerDeadlineRow(BaseModel):
    company_id: int
    company_name: str
    asset_class: Optional[str] = None
    sector: str
    status: str
    completion_percent: int
    deadline: Optional[str] = None
    days_remaining: Optional[int] = None


class ManagerProgressRow(BaseModel):
    company_id: int
    company_name: str
    asset_class: Optional[str] = None
    sector: str
    status: str
    completion_percent: int
    last_activity: str
    deadline: Optional[str] = None
    actions: List[str]


class ManagerDashboardSummary(BaseModel):
    status_breakdown: Dict[str, int]
    cycle_banner: ManagerCycleBanner
    upcoming_deadlines: List[ManagerDeadlineRow]
    progress_rows: List[ManagerProgressRow]


class ManagerDashboardResponse(BaseModel):
    companies: List[CompanyDetail]
    summary: ManagerDashboardSummary


class CsvParityFileStatus(BaseModel):
    file_key: str
    file_name: str
    present: bool
    rows: int


class CsvParityCompanyMismatch(BaseModel):
    dataset: str
    company_code: str
    company_name: str
    expected: int
    live: int
    delta: int


class CsvParityResponse(BaseModel):
    generated_at: str
    fixtures_dir: str
    files: List[CsvParityFileStatus]
    csv_totals: Dict[str, int]
    live_totals: Dict[str, int]
    delta_totals: Dict[str, int]
    missing_csv_companies_in_live: List[Dict[str, str]]
    extra_live_companies_not_in_csv: List[Dict[str, str]]
    per_company_mismatches: List[CsvParityCompanyMismatch]
    is_full_parity: bool
    notes: List[str]
