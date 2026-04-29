from typing import Any, Dict, List, Literal, Optional

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

class GHGCalculatorRequest(BaseModel):
    fuel_liters: float = Field(default=0, ge=0)
    electricity_kwh: float = Field(default=0, ge=0)
    diesel_liters: float = Field(default=0, ge=0)
    natural_gas_therms: float = Field(default=0, ge=0)
    vehicle_km: float = Field(default=0, ge=0)
    flight_km: float = Field(default=0, ge=0)
    fuel_emission_factor: float = Field(default=0.00268, ge=0)
    electricity_emission_factor: float = Field(default=0.0005, ge=0)
    diesel_emission_factor: float = Field(default=0.00268, ge=0)
    natural_gas_emission_factor: float = Field(default=0.0053, ge=0)
    vehicle_emission_factor: float = Field(default=0.00018, ge=0)
    flight_emission_factor: float = Field(default=0.00015, ge=0)

class GHGCalculatorResponse(BaseModel):
    scope_1_tco2e: float
    scope_2_tco2e: float
    scope_3_tco2e: float = 0.0
    total_tco2e: float
    scope_1_equivalent: Optional[str] = None
    scope_2_equivalent: Optional[str] = None
    scope_3_equivalent: Optional[str] = None
    total_equivalent: Optional[str] = None
    summary: Optional[str] = None
    fuel_emission_factor: Optional[float] = None
    electricity_emission_factor: Optional[float] = None
    diesel_emission_factor: Optional[float] = None
    natural_gas_emission_factor: Optional[float] = None
    vehicle_emission_factor: Optional[float] = None
    flight_emission_factor: Optional[float] = None
    activity_breakdown: List[Dict[str, Any]] = Field(default_factory=list)
    scope_breakdown: Dict[str, Any] = Field(default_factory=dict)
    recommendation: Optional[str] = None

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

class CompanyDetail(BaseModel):
    id: int
    name: str
    sector: str
    geography: Optional[str] = None
    current_status: Optional[str] = None
    reporting_status: Optional[str] = None
    reporting_completion_percent: Optional[int] = None
    reporting_deadline: Optional[str] = None
    reporting_esg_score: Optional[float] = None
    reporting_risk_level: Optional[str] = None
    reporting_cycle_year: Optional[int] = None
    latest_submission_id: Optional[int] = None
    previous_submission_id: Optional[int] = None
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
    impact_story: Dict[str, Any]


class ManagerAnalyticsResponse(BaseModel):
    summary_cards: List[Dict[str, Any]]
    status_distribution: List[Dict[str, Any]]
    emissions_trend: List[Dict[str, Any]]
    sector_performance: List[Dict[str, Any]]
    policy_adoption: List[Dict[str, Any]]
    top_performers: List[Dict[str, Any]]
    bottom_performers: List[Dict[str, Any]]
    data_quality: Dict[str, float]
    cycle_snapshot: Dict[str, Any]
    impact_story: Dict[str, Any]


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
    cycle_year: int = Field(ge=2000, le=2100)
    submission_open_date: str
    submission_deadline: str
    extension_date: Optional[str] = None
    reminder_days_before_deadline: List[int]
    private_equity_template: str
    real_estate_template: str
    debt_template: str
    activate_on_create: bool = True
    carry_forward_prefill: bool = True


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


class ActivityEventResponse(BaseModel):
    id: int
    event_type: str
    title: str
    message: str
    severity: str = 'info'
    actor_role: Optional[str] = None
    actor_email: Optional[str] = None
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    submission_id: Optional[int] = None
    cycle_id: Optional[int] = None
    entity_status: Optional[str] = None
    is_toast: bool = True
    visible_to_investors: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ActivityFeedResponse(BaseModel):
    items: List[ActivityEventResponse] = Field(default_factory=list)


class ExternalContextItemResponse(BaseModel):
    id: str
    item_type: Literal['sector-news', 'regulation']
    title: str
    summary: str
    sector: Optional[str] = None
    geography: Optional[str] = None
    priority: Literal['high', 'medium', 'low'] = 'medium'
    source_label: str = 'Curated ESG signal'
    source_type: Literal['curated', 'portfolio-derived'] = 'curated'
    published_at: str
    related_topics: List[str] = Field(default_factory=list)
    impact_hint: Optional[str] = None
    action_prompt: Optional[str] = None
    company_id: Optional[int] = None
    company_name: Optional[str] = None


class ExternalContextFeedResponse(BaseModel):
    available: bool = True
    role: str
    scope: Literal['portfolio', 'company'] = 'portfolio'
    generated_at: str
    sectors_in_view: List[str] = Field(default_factory=list)
    items: List[ExternalContextItemResponse] = Field(default_factory=list)
    message: Optional[str] = None


class AnomalyItemResponse(BaseModel):
    id: str
    anomaly_type: str
    severity: Literal['high', 'medium', 'low'] = 'medium'
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    sector: Optional[str] = None
    reporting_year: Optional[int] = None
    metric_name: str
    current_value: str
    previous_value: Optional[str] = None
    delta_percent: Optional[float] = None
    rationale: str
    recommendation: str
    source_submission_id: Optional[int] = None


class AnomalySummaryResponse(BaseModel):
    available: bool = True
    scope: Literal['portfolio', 'company'] = 'portfolio'
    generated_at: str
    headline: str
    summary: str
    severity_counts: Dict[str, int] = Field(default_factory=dict)
    watchlist_companies: List[Dict[str, Any]] = Field(default_factory=list)
    items: List[AnomalyItemResponse] = Field(default_factory=list)
    fallback_used: bool = False
    model: Optional[str] = None
    message: Optional[str] = None


class CollaborationClaimRequest(BaseModel):
    section: str


class CollaborationReleaseRequest(BaseModel):
    section: str
    force: bool = False


class CollaborationSessionResponse(BaseModel):
    id: int
    submission_id: int
    company_id: int
    cycle_id: int
    section: str
    owner_role: str
    owner_email: str
    owner_name: Optional[str] = None
    status: str = 'active'
    lock_mode: str = 'soft'
    is_you: bool = False
    expires_at: str
    last_seen_at: str
    created_at: str
    updated_at: str


class SubmissionCollaborationResponse(BaseModel):
    submission_id: int
    company_id: int
    cycle_id: int
    lock_mode: str = 'soft'
    active_sections: List[CollaborationSessionResponse] = Field(default_factory=list)
    current_user_sections: List[str] = Field(default_factory=list)
    viewer_role: str
    viewer_email: Optional[str] = None


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
    context_summary: List[str] = []
    impact_headline: Optional[str] = None
    narrative_headline: Optional[str] = None
    narrative_included: bool = False
    narrative_status: str = 'missing'
    narrative_status_label: str = 'No approved narrative'
    narrative_status_reason: Optional[str] = None
    benchmark_callouts: List[str] = []
    comparison_rows: List[Dict[str, Any]] = []
    trend_summary: Optional[str] = None
    impact_story: Dict[str, Any] = {}
    external_context_items: List[ExternalContextItemResponse] = Field(default_factory=list)
    anomaly_summary: Optional[AnomalySummaryResponse] = None


class ReportPreviewResponse(BaseModel):
    report_type: str
    period: str
    portfolio: str
    rows_in_scope: int
    context_summary: List[str] = []
    impact_headline: Optional[str] = None
    benchmark_callouts: List[str] = []
    comparison_rows: List[Dict[str, Any]] = []
    trend_summary: Optional[str] = None
    impact_story: Dict[str, Any] = {}
    external_context_items: List[ExternalContextItemResponse] = Field(default_factory=list)
    anomaly_summary: Optional[AnomalySummaryResponse] = None
    narrative_id: Optional[int] = None
    narrative_headline: Optional[str] = None
    narrative_status: str = 'missing'
    narrative_status_label: str = 'No approved narrative'
    narrative_status_reason: Optional[str] = None
    narrative_included: bool = False


class NewsletterGenerateRequest(BaseModel):
    audience: Literal['manager', 'investor'] = 'manager'
    tone: Literal['board-ready', 'lp-letter', 'exec-summary'] = 'board-ready'
    force_refresh: bool = False
    dry_run: bool = False
    recipient_emails: List[str] = Field(default_factory=list)


class NewsletterSummaryResponse(BaseModel):
    available: bool
    audience: Literal['manager', 'investor']
    tone: str = 'board-ready'
    generated_at: str
    subject_line: str = ''
    preheader: str = ''
    headline: str = ''
    summary: str = ''
    highlights: List[str] = []
    watchouts: List[str] = []
    recommendations: List[str] = []
    call_to_action: str = ''
    source_years: List[int] = []
    source_company_count: int = 0
    source_submission_count: int = 0
    impact_headline: Optional[str] = None
    trend_summary: Optional[str] = None
    benchmark_callouts: List[str] = []
    external_context_items: List[ExternalContextItemResponse] = Field(default_factory=list)
    anomaly_summary: Optional[AnomalySummaryResponse] = None
    cached: bool = False
    fallback_used: bool = False
    message: Optional[str] = None


class NewsletterExportResponse(BaseModel):
    available: bool
    audience: Literal['manager', 'investor']
    tone: str = 'board-ready'
    generated_at: str
    file_name: str = ''
    file_path: str = ''
    download_url: str = ''
    content_type: str = 'text/plain'
    subject_line: str = ''
    preheader: str = ''
    headline: str = ''
    impact_headline: Optional[str] = None
    trend_summary: Optional[str] = None
    benchmark_callouts: List[str] = []
    external_context_items: List[ExternalContextItemResponse] = Field(default_factory=list)
    anomaly_summary: Optional[AnomalySummaryResponse] = None
    message: Optional[str] = None


class NewsletterSendResponse(BaseModel):
    available: bool
    audience: Literal['manager', 'investor']
    tone: str = 'board-ready'
    generated_at: str
    delivery_status: Literal['sent', 'dry_run', 'queued', 'failed', 'skipped']
    provider: str = 'smtp'
    recipient_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    subject_line: str = ''
    preheader: str = ''
    headline: str = ''
    dry_run: bool = False
    message: Optional[str] = None


class NarrativeSummaryResponse(BaseModel):
    available: bool
    audience: Literal['company', 'lp', 'board']
    scope: Literal['company', 'portfolio']
    tone: str = 'board-ready'
    status: str = 'generated'
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    source_years: List[int] = []
    source_company_count: int = 0
    source_submission_count: int = 0
    latest_source_years: List[int] = []
    latest_source_company_count: int = 0
    latest_source_submission_count: int = 0
    provider: str = 'openai'
    model: Optional[str] = None
    cached: bool = False
    fallback_used: bool = False
    freshness_status: str = 'missing'
    freshness_label: str = 'No approved narrative'
    freshness_reason: Optional[str] = None
    generated_at: str
    headline: str = ''
    summary: str = ''
    highlights: List[str] = []
    watchouts: List[str] = []
    recommendations: List[str] = []
    message: Optional[str] = None


class NarrativeHistoryItem(BaseModel):
    narrative_id: int
    audience: Literal['company', 'lp', 'board']
    scope: Literal['company', 'portfolio']
    tone: str = 'board-ready'
    status: str = 'generated'
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    generated_at: str
    updated_at: str
    headline: str = ''
    source_years: List[int] = []
    source_company_count: int = 0
    source_submission_count: int = 0
    freshness_status: str = 'missing'
    freshness_label: str = 'No approved narrative'
    approved_by_role: Optional[str] = None
    approved_at: Optional[str] = None


class NarrativeHistoryResponse(BaseModel):
    available: bool = True
    audience: Literal['company', 'lp', 'board']
    scope: Literal['company', 'portfolio']
    items: List[NarrativeHistoryItem] = Field(default_factory=list)
    message: Optional[str] = None


class NarrativeGenerateRequest(BaseModel):
    audience: Literal['company', 'lp', 'board'] = 'company'
    company_id: Optional[int] = None
    tone: Literal['board-ready', 'lp-letter', 'exec-summary'] = 'board-ready'
    force_refresh: bool = False


class NarrativeUpdateRequest(BaseModel):
    headline: Optional[str] = None
    summary: Optional[str] = None
    highlights: Optional[List[str]] = None
    watchouts: Optional[List[str]] = None
    recommendations: Optional[List[str]] = None
    tone: Optional[Literal['board-ready', 'lp-letter', 'exec-summary']] = None


class NarrativeApproveRequest(BaseModel):
    approved: bool = True


class NarrativeDetailResponse(NarrativeSummaryResponse):
    narrative_id: int
    framework_tags: List[str] = []
    generated_payload: Dict[str, Any] = {}
    edited_payload: Dict[str, Any] = {}
    published_payload: Dict[str, Any] = {}
    approved_by_role: Optional[str] = None
    approved_at: Optional[str] = None
    edited_by_role: Optional[str] = None
    edited_at: Optional[str] = None
    generated_at: str
    updated_at: str
    can_edit: bool = False
    can_approve: bool = False
    can_export: bool = False


class NarrativeExportResponse(BaseModel):
    narrative_id: int
    file_name: str
    file_path: str
    download_url: str
    content_type: str


class ManagerCycleBanner(BaseModel):
    active_cycle_year: Optional[int] = None
    submission_open_date: Optional[str] = None
    submission_deadline: Optional[str] = None
    days_remaining: Optional[int] = None
    cycle_status: str = 'closed'


class ManagerDeadlineRow(BaseModel):
    company_id: int
    submission_id: Optional[int] = None
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
    impact_story: Dict[str, Any]


class GlobalSearchResult(BaseModel):
    type: str
    title: str
    subtitle: str
    path: str
    score: float = 0.0
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    sector: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GlobalSearchResponse(BaseModel):
    query: str
    role: str
    results: List[GlobalSearchResult] = Field(default_factory=list)


# ==========================================
# LP (LIMITED PARTNER / INVESTOR) SCHEMAS
# ==========================================

class LPCompanyMetrics(BaseModel):
    id: int
    name: str
    sector: str
    asset_class: Optional[str] = None
    geography: Optional[str] = None
    approval_status: str
    esg_score: float
    e_score: float
    s_score: float
    g_score: float


class LPESGPillar(BaseModel):
    name: str  # "E", "S", or "G"
    current_score: float
    previous_score: float
    yoy_change: float  # percentage
    trend_sparkline: List[float]  # Last 5 years


class LPPortfolioScorecard(BaseModel):
    overall_esg_score: float
    overall_esg_score_previous: float
    yoy_change_percent: float
    three_year_trend: List[float]
    pillars: List[LPESGPillar]


class LPPortfolioCompletion(BaseModel):
    total_companies: int
    companies_with_approved_submission: int
    completion_percent: float
    last_updated: str


class LPKeyMetricTile(BaseModel):
    metric_name: str
    current_value: str  # Can be number or percentage
    unit: str
    trend_percent: Optional[float] = None
    trend_direction: Optional[str] = None  # "up", "down", "neutral"
    last_updated: str


class LPEmissionsPoint(BaseModel):
    period: str
    scope_1: float
    scope_2: float
    scope_3: float


class LPDiversityMetric(BaseModel):
    metric_name: str
    percentage: float
    previous_year: float
    trend: str  # "up", "down", "stable"


class LPPolicyAdoption(BaseModel):
    policy_name: str
    adoption_percentage: float
    companies_with_policy: int
    total_companies: int


class LPActionPlanStatus(BaseModel):
    in_progress: int
    completed: int


class LPDashboardResponse(BaseModel):
    portfolio_scorecard: LPPortfolioScorecard
    completion_status: LPPortfolioCompletion
    key_metrics: List[LPKeyMetricTile]
    emissions_trend: List[LPEmissionsPoint]
    diversity_metrics: List[LPDiversityMetric]
    policy_adoption: List[LPPolicyAdoption]
    action_plan_status: LPActionPlanStatus
    portfolio_companies: List[LPCompanyMetrics]  # For authorised LPs only
    impact_story: Dict[str, Any]


class LPEnvironmentalMetrics(BaseModel):
    scope_1_emissions: List[Dict[str, Any]]  # {period: str, value: float, trend: float}
    scope_2_emissions: List[Dict[str, Any]]
    scope_3_emissions: List[Dict[str, Any]]
    energy_total: List[Dict[str, Any]]
    energy_renewable: List[Dict[str, Any]]
    water_usage: List[Dict[str, Any]]
    water_recycled: List[Dict[str, Any]]
    waste_generated: List[Dict[str, Any]]
    waste_diverted: List[Dict[str, Any]]


class LPSocialMetrics(BaseModel):
    trifr: List[Dict[str, Any]]  # {period: str, value: float, trend: float}
    fatalities: List[Dict[str, Any]]
    total_employees: List[Dict[str, Any]]
    female_workforce_percent: List[Dict[str, Any]]
    female_leadership_percent: List[Dict[str, Any]]
    community_investment: List[Dict[str, Any]]


class LPGovernanceMetrics(BaseModel):
    esg_policy_compliance: float
    whs_policy_compliance: float
    cybersecurity_policy_compliance: float
    antibribery_policy_compliance: float
    board_esg_oversight: float
    cyber_incidents: List[Dict[str, Any]]  # {period: str, value: int}


class LPAssetClassBreakdown(BaseModel):
    asset_class: str
    company_count: int
    avg_esg_score: float
    avg_emission_intensity: float
    avg_female_representation: float


class LPBenchmarkComparison(BaseModel):
    metric_name: str
    portfolio_value: float
    benchmark_value: float
    status: str  # "above", "at", "below"
    industry: str
    tooltip: Optional[str] = None
    real_world_equivalent: Optional[str] = None
    direction: Literal['higher', 'lower'] = 'higher'


class LPMetricsPageResponse(BaseModel):
    environmental: LPEnvironmentalMetrics
    social: LPSocialMetrics
    governance: LPGovernanceMetrics
    asset_class_breakdown: List[LPAssetClassBreakdown]
    benchmark_comparisons: List[LPBenchmarkComparison]
    metric_insights: List[Dict[str, Any]] = []
    impact_story: Dict[str, Any] = {}


class LPReportMetadata(BaseModel):
    report_type: Optional[str] = None  # edci | sfdr (when export-enabled)
    report_name: str
    year: int
    generated_date: str
    format: str  # "PDF", "Excel"
    download_url: str
    generated: bool = True
    status_label: Optional[str] = None
    status_note: Optional[str] = None


class LPReportsResponse(BaseModel):
    available_reports: List[LPReportMetadata]
    historical_archive: Dict[int, List[LPReportMetadata]]  # Grouped by year
    export_available: bool


# ==========================================
# COMPANY PORTAL / PORTFOLIO COMPANY SCHEMAS
# ==========================================

class ValidationErrorResponse(BaseModel):
    id: int
    section: str
    field_key: str
    field_label: str
    error_type: str  # "required", "range", "variance", "format"
    error_message: str
    severity: str  # "error", "warning"
    resolved: bool


class MetricReviewDecisionRequest(BaseModel):
    field_key: str
    decision: Literal['pass', 'fail']
    comment: Optional[str] = None


class MetricReviewDecisionResponse(BaseModel):
    submission_id: int
    field_key: str
    decision: Literal['pass', 'fail']
    updated_errors: int
    message: str


class SubmissionDataFieldResponse(BaseModel):
    field_key: str
    field_label: str
    value: Optional[str] = None
    prior_year_value: Optional[str] = None
    unit: Optional[str] = None
    confidence_level: str  # High, Medium, Low, Estimated, Not Available, Measured(legacy)
    yoy_variance_percent: Optional[float] = None
    requires_explanation: bool
    explanation: Optional[str] = None
    subsection: Optional[str] = None
    input_type: Optional[str] = None
    helper_text: Optional[str] = None
    required: bool = False
    read_only: bool = False
    supports_reporting: bool = True
    confidence_field: Optional[str] = None
    confidence_options: List[str] = Field(default_factory=list)
    policy_options: List[str] = Field(default_factory=list)
    conditional_visibility: Optional[str] = None
    last_updated_at: Optional[str] = None
    validation_errors: List[ValidationErrorResponse] = []


class CompanySubmissionSectionResponse(BaseModel):
    submission_id: Optional[int] = None
    company_id: Optional[int] = None
    cycle_id: Optional[int] = None
    section: str  # Environmental, Social, Governance
    completion_percent: int
    total_fields: int
    completed_fields: int
    validation_status: str  # "pass", "warning", "error"
    error_count: int
    warning_count: int
    fields: List[SubmissionDataFieldResponse] = []
    collaboration: Optional[SubmissionCollaborationResponse] = None


class CompanyDashboardResponse(BaseModel):
    company_id: int
    company_name: str
    current_cycle_id: Optional[int] = None
    current_cycle_year: int
    submission_status: str  # NOT STARTED, IN PROGRESS, SUBMITTED, APPROVED, REJECTED, RESUBMISSION REQUIRED
    status_color: str  # grey, blue, yellow, green, red, amber
    deadline: str
    days_remaining: int
    deadline_urgency: str  # green (>14 days), amber (7–14 days), red (<7 days)
    overall_completion_percent: int
    total_data_points: int
    completed_data_points: int
    section_breakdown: Dict[str, int]  # {"Environmental": 45, "Social": 32, "Governance": 28}
    outstanding_validation_errors: int
    feedback_from_admin: Optional[str] = None
    sections_requiring_correction: List[str] = []
    prior_year_summary: Optional[Dict[str, str]] = None  # Last year's key metrics for reference
    action_items_in_progress: int
    impact_story: Dict[str, Any] = {}


class CompanySubmissionReviewResponse(BaseModel):
    submission_id: int
    company_id: int
    company_name: str
    cycle_year: int
    total_data_points: int
    mandatory_fields_incomplete: int  # Must be 0 to submit
    optional_fields_incomplete: int
    outstanding_validation_errors: List[ValidationErrorResponse]
    all_entered_data: List[CompanySubmissionSectionResponse]
    can_submit: bool  # True if all mandatory fields complete, all mandatory errors resolved
    collaboration: Optional[SubmissionCollaborationResponse] = None


class CompanyActionPlanResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    linked_metric: Optional[str] = None
    owner: str
    target_date: str
    status: str  # "Not Started", "In Progress", "Completed", "Overdue"
    created_at: str
    updated_at: str


class CompanyActionPlansPageResponse(BaseModel):
    active_actions: List[CompanyActionPlanResponse]
    completed_actions: List[CompanyActionPlanResponse]
    overdue_actions: List[CompanyActionPlanResponse]


class CompanyActionPlanCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    linked_metric: Optional[str] = None
    owner: str
    target_date: str


class CompanyActionPlanUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    linked_metric: Optional[str] = None
    owner: Optional[str] = None
    target_date: Optional[str] = None
    status: Optional[str] = None


class CompanySubmissionDataUpdateRequest(BaseModel):
    field_key: str
    value: str
    confidence_level: str  # High, Medium, Low, Estimated, Not Available, Measured(legacy)
    explanation: Optional[str] = None  # For YoY variance


class CompanyBulkImportResponse(BaseModel):
    success: bool
    imported_fields: int
    skipped_fields: int
    errors: List[str] = []


class SupportingDocumentResponse(BaseModel):
    id: int
    field_key: str
    file_name: str
    file_size: int
    file_type: str
    uploaded_at: str
    uploaded_by_email: Optional[str] = None


class DocumentExtractionSuggestion(BaseModel):
    field_key: str
    suggested_value: Optional[str] = None
    confidence_level: str
    explanation: Optional[str] = None
    source_excerpt: Optional[str] = None
    needs_confirmation: bool = True
    document_type: Optional[str] = None
    document_topics: List[str] = Field(default_factory=list)


class SupportingDocumentUploadResponse(BaseModel):
    message: str
    document: SupportingDocumentResponse
    document_type: str = 'document'
    document_topics: List[str] = Field(default_factory=list)
    matched_keywords: List[str] = Field(default_factory=list)
    extraction_summary: str = ''
    suggestion_count: int = 0
    extraction_suggestions: List[DocumentExtractionSuggestion] = Field(default_factory=list)
