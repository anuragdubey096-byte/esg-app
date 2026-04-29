import csv
import io
import json
import hashlib
import html as html_lib
import asyncio
import os
import re
import smtplib
import time
import threading
import zipfile
from difflib import SequenceMatcher
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus
from email.message import EmailMessage
from xml.etree import ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Header, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, text, inspect
from sqlalchemy.orm import Session, selectinload

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional until dependency is installed
    OpenAI = None

from env import load_local_env
from bootstrap import seed_sample_data
from database import SessionLocal, engine
from platform_config import (
    IMPACT_DEFAULT_DIVERSITY_BENCHMARK,
    IMPACT_DIVERSITY_BENCHMARKS,
    IMPACT_PORTFOLIO_EMISSIONS_INTENSITY_BENCHMARK,
    IMPACT_PORTFOLIO_ESG_BENCHMARK,
    IMPACT_PORTFOLIO_POLICY_BENCHMARK,
    IMPACT_PORTFOLIO_TRIFR_BENCHMARK,
    IMPACT_TCO2E_PER_PASSENGER_VEHICLE_YEAR,
)
from portal_config import PORTAL_SEARCH_PAGE_CATALOG, SEARCH_RANKING
from models import (
    Base,
    User,
    UserRole,
    LPType,
    Company,
    Submission,
    NarrativeSummary,
    CollectionCycle,
    ActionPlan,
    ReviewAction,
    ValidationFlag,
    SubmissionUnlock,
    ReminderLog,
    SubmissionDataField,
    SupportingDocument,
    ValidationError,
    NewsletterDispatchLog,
    ActivityEvent,
    SubmissionCollaborationSession,
)
from schemas import (
    ActionPlanCreateRequest,
    ActionPlanInfo,
    CompanyCreateRequest,
    CompanyCreateResponse,
    CompanyDetail,
    CycleCreateRequest,
    CycleInfo,
    CycleStatusUpdateRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    GHGCalculatorRequest,
    GHGCalculatorResponse,
    ReviewSubmissionRequest,
    InvestorSummary,
    InvestorDashboardResponse,
    LoginRequest,
    SSOLoginRequest,
    SubmissionCreateRequest,
    SubmissionInfo,
    SubmissionStatusUpdateRequest,
    SubmissionUnlockRequest,
    SubmissionUnlockInfo,
    ReminderRequest,
    ReminderInfo,
    ActivityEventResponse,
    ActivityFeedResponse,
    ExternalContextItemResponse,
    ExternalContextFeedResponse,
    AnomalyItemResponse,
    AnomalySummaryResponse,
    CollaborationClaimRequest,
    CollaborationReleaseRequest,
    CollaborationSessionResponse,
    SubmissionCollaborationResponse,
    ReportExportResponse,
    ReportPreviewResponse,
    NewsletterGenerateRequest,
    NewsletterExportResponse,
    NewsletterSendResponse,
    NewsletterSummaryResponse,
    DashboardNarrativeMaterialResponse,
    NarrativeSummaryResponse,
    NarrativeHistoryItem,
    NarrativeHistoryResponse,
    NarrativeGenerateRequest,
    NarrativeUpdateRequest,
    NarrativeApproveRequest,
    NarrativeDetailResponse,
    NarrativeExportResponse,
    ManagerDashboardResponse,
    UserResponse,
    CompanyDashboardResponse,
    CompanySubmissionSectionResponse,
    CompanySubmissionReviewResponse,
    CompanyActionPlanResponse,
    CompanyActionPlansPageResponse,
    CompanyActionPlanCreateRequest,
    CompanyActionPlanUpdateRequest,
    CompanySubmissionDataUpdateRequest,
    DocumentExtractionSuggestion,
    SupportingDocumentResponse,
    SupportingDocumentUploadResponse,
    ValidationErrorResponse,
    SubmissionDataFieldResponse,
    MetricReviewDecisionRequest,
    MetricReviewDecisionResponse,
    ManagerAnalyticsResponse,
    GlobalSearchResponse,
)
from new_esg_module import router as new_esg_router
from storage import ensure_local_export_dir, is_blob_storage_enabled, list_export_artifacts, save_export_artifact
from non_prod_guard import build_non_prod_company_clause

load_local_env()

BASE_DIR = Path(__file__).resolve().parent
EXPORT_DIR = ensure_local_export_dir() if not is_blob_storage_enabled() else BASE_DIR / 'exports'
STARTUP_STATUS = {
    'completed': False,
    'error': None,
    'completed_at': None,
    'duration_ms': None,
    'steps': [],
    'maintenance': {
        'status': 'not_started',
        'completed_at': None,
        'error': None,
        'duration_ms': None,
        'steps': [],
    },
}

ALLOWED_REPORT_TYPES = {'edci', 'sfdr'}
NARRATIVE_STATE_LABELS = {
    'current': 'Current narrative',
    'stale': 'Stale narrative',
    'missing': 'No approved narrative',
}
ALLOWED_CYCLE_STATUSES = {'draft', 'active', 'closed'}
ALLOWED_REVIEW_STATUSES = {'submitted', 'under review', 'approved', 'rejected', 'resubmission requested'}
ALLOWED_REVIEW_TRANSITIONS = {
    'submitted': {'under review', 'approved', 'rejected', 'resubmission requested'},
    'under review': {'approved', 'rejected', 'resubmission requested'},
    'resubmission requested': {'submitted'},
}
ALLOWED_CYCLE_TRANSITIONS = {
    'draft': {'active'},
    'active': {'closed'},
    'closed': set(),
}

NARRATIVE_AUDIENCES = {'company', 'lp', 'board'}
NARRATIVE_SCOPE_BY_AUDIENCE = {
    'company': 'company',
    'lp': 'portfolio',
    'board': 'portfolio',
}
NARRATIVE_TONES = {'board-ready', 'lp-letter', 'exec-summary'}
NARRATIVE_TONE_LABELS = {
    'board-ready': 'Board-ready',
    'lp-letter': 'LP letter',
    'exec-summary': 'Executive summary',
}
OPENAI_DEFAULT_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
ANALYTICS_CACHE_TTL_SECONDS = max(10, int(os.getenv('ANALYTICS_CACHE_TTL_SECONDS', '60') or '60'))
EXCLUDE_NON_PROD_UI_ENTITIES = str(os.getenv('EXCLUDE_NON_PROD_UI_ENTITIES', '1')).strip().lower() not in {'0', 'false', 'no'}
COLLABORATION_TTL_SECONDS = 90
MIN_REPORTING_CYCLE_YEAR = int(os.getenv('MIN_REPORTING_CYCLE_YEAR', '2000') or '2000')
MAX_REPORTING_CYCLE_YEARS_AHEAD = int(os.getenv('MAX_REPORTING_CYCLE_YEARS_AHEAD', '10') or '10')

CONFIDENCE_OPTIONS = ['High', 'Medium', 'Low', 'Estimated', 'Not Available', 'Measured']
POLICY_STATUS_OPTIONS = ['Yes', 'No', 'In Progress', 'Not Applicable']
_TIMED_COMPUTE_CACHE: Dict[str, dict] = {}

EXTERNAL_CONTEXT_REGULATORY_TEMPLATES: List[Dict[str, Any]] = [
    {
        'id': 'climate_disclosure',
        'title': 'Climate disclosure expectations are tightening across institutional reporting',
        'summary': 'Disclosure scrutiny is rising around emissions baselines, transition plans, and evidence-backed narrative claims.',
        'priority': 'high',
        'geography': 'Global',
        'related_topics': ['climate disclosure', 'transition planning', 'assurance'],
        'impact_hint': 'Weak evidence trails and stale emissions narratives are more likely to be challenged.',
        'action_prompt': 'Refresh approved-data disclosures and confirm that report inserts still match the latest reporting year.',
    },
    {
        'id': 'supply_chain_due_diligence',
        'title': 'Supply-chain and human-rights due diligence remain active board topics',
        'summary': 'Portfolio companies are increasingly expected to show how labour, supplier, and governance controls are documented and monitored.',
        'priority': 'medium',
        'geography': 'Global',
        'related_topics': ['human rights', 'supplier risk', 'policy controls'],
        'impact_hint': 'Missing policy evidence or weak oversight can create avoidable diligence friction.',
        'action_prompt': 'Confirm policy references, board oversight, and follow-up actions are visible in the latest approved submission.',
    },
    {
        'id': 'greenwashing_controls',
        'title': 'Anti-greenwashing risk is pushing teams toward evidence-backed ESG claims',
        'summary': 'Narratives, investor updates, and dashboard callouts need stronger alignment with approved underlying data and benchmark context.',
        'priority': 'high',
        'geography': 'Global',
        'related_topics': ['greenwashing', 'marketing claims', 'investor communications'],
        'impact_hint': 'Overstated progress claims can create reputational and regulatory risk.',
        'action_prompt': 'Use approved data only in newsletters, reports, and investor updates, and keep benchmark explanations concise and auditable.',
    },
    {
        'id': 'cyber_governance',
        'title': 'Cyber governance is staying inside the ESG and risk conversation',
        'summary': 'Boards and investors increasingly expect cyber incidents, policy coverage, and oversight to sit inside the same reporting discussion as other governance controls.',
        'priority': 'medium',
        'geography': 'Global',
        'related_topics': ['cybersecurity', 'board oversight', 'governance'],
        'impact_hint': 'A cyber policy gap or incident without clear governance response can stand out quickly.',
        'action_prompt': 'Check cybersecurity policy coverage, incident counts, and board oversight before the next portfolio update.',
    },
]

EXTERNAL_CONTEXT_SECTOR_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    'technology': [
        {
            'id': 'tech_energy_intensity',
            'title': 'Technology operators are under growing pressure to explain energy intensity',
            'summary': 'Investors increasingly want clearer context on electricity demand, renewable sourcing, and the operational footprint behind digital growth.',
            'priority': 'medium',
            'related_topics': ['energy use', 'renewables', 'digital infrastructure'],
            'impact_hint': 'Energy growth without a matching renewable plan can become a watchlist topic quickly.',
            'action_prompt': 'Highlight electricity trends, renewable uptake, and any active decarbonization actions in the next update.',
        },
    ],
    'consumer goods': [
        {
            'id': 'consumer_packaging_supply_chain',
            'title': 'Consumer goods reporting is leaning harder into packaging, suppliers, and workforce signals',
            'summary': 'Teams are being asked for clearer proof of waste diversion, supplier oversight, and workforce stability in addition to core emissions numbers.',
            'priority': 'medium',
            'related_topics': ['waste diversion', 'suppliers', 'workforce'],
            'impact_hint': 'Packaging and labour questions often surface together during investor diligence.',
            'action_prompt': 'Bring waste, supplier, and workforce trends into the same board-ready summary instead of treating them as separate follow-ups.',
        },
    ],
    'renewable energy': [
        {
            'id': 'renewable_execution',
            'title': 'Renewable-energy businesses are still being asked to prove operational resilience, not just climate alignment',
            'summary': 'Safety execution, governance controls, and delivery discipline remain important even when the sector narrative is already climate-positive.',
            'priority': 'high',
            'related_topics': ['operational resilience', 'safety', 'governance'],
            'impact_hint': 'A climate-positive sector does not offset weak safety or governance execution.',
            'action_prompt': 'Balance the emissions story with safety, oversight, and execution quality in the next report or investor note.',
        },
    ],
    'testing': [
        {
            'id': 'testing_data_quality',
            'title': 'Testing and service-heavy businesses are being judged on data quality as much as emissions scale',
            'summary': 'Measured confidence, stable year-on-year fields, and evidence-backed policy references matter when physical emissions are relatively low.',
            'priority': 'medium',
            'related_topics': ['data quality', 'assurance', 'policy evidence'],
            'impact_hint': 'Low-impact sectors still need high-trust reporting discipline.',
            'action_prompt': 'Use measured confidence and document references to strengthen comparability in the next cycle.',
        },
    ],
}

# Legacy field aliases -> canonical keys (for old drafts/backward compatibility)
LEGACY_FIELD_ALIASES = {
    'scope_2_emissions': 'scope_2_location_based',
    'energy_consumption': 'total_energy_consumption',
    'renewable_energy': 'renewable_energy_consumption',
    'water_usage': 'total_water_withdrawal',
    'waste_generated': 'total_waste_generated',
    'total_employees': 'total_employees_fte',
    'female_representation': 'female_representation_percent',
    'fatalities': 'total_fatalities',
    'community_investment': 'community_investment_spend',
    'esg_policy': 'esg_policy_in_place',
    'board_esg_oversight': 'board_level_esg_oversight',
    'cybersecurity_policy': 'cybersecurity_policy_in_place',
    'cyber_incidents': 'cyber_incidents_in_reporting_period',
}


ESG_FIELD_CATALOG: Dict[str, List[Dict[str, Any]]] = {
    'Submission Context': [
        {
            'field_key': 'company_id',
            'field_label': 'Company ID',
            'subsection': 'Reporting Context',
            'input_type': 'integer',
            'unit': None,
            'required': True,
            'read_only': True,
            'helper_text': 'Automatically populated based on logged-in company.',
            'supports_reporting': True,
        },
        {
            'field_key': 'reporting_year',
            'field_label': 'Reporting Year',
            'subsection': 'Reporting Context',
            'input_type': 'integer',
            'unit': 'year',
            'required': True,
            'read_only': True,
            'helper_text': 'Automatically populated from the active reporting cycle.',
            'supports_reporting': True,
        },
    ],
    'Environmental': [
        {
            'field_key': 'scope_1_emissions',
            'field_label': 'Scope 1 Emissions',
            'subsection': 'Emissions',
            'input_type': 'number',
            'unit': 'tCO2e',
            'required': True,
            'confidence_field': 'scope_1_emissions_confidence',
            'helper_text': 'Direct GHG emissions from owned or controlled sources.',
            'supports_reporting': True,
        },
        {
            'field_key': 'scope_2_location_based',
            'field_label': 'Scope 2 Emissions (Location-based)',
            'subsection': 'Emissions',
            'input_type': 'number',
            'unit': 'tCO2e',
            'required': True,
            'confidence_field': 'scope_2_location_based_confidence',
            'helper_text': 'Indirect emissions from purchased electricity (location method).',
            'supports_reporting': True,
        },
        {
            'field_key': 'scope_2_market_based',
            'field_label': 'Scope 2 Emissions (Market-based)',
            'subsection': 'Emissions',
            'input_type': 'number',
            'unit': 'tCO2e',
            'required': False,
            'confidence_field': 'scope_2_market_based_confidence',
            'helper_text': 'Indirect emissions from purchased electricity (market method).',
            'supports_reporting': True,
        },
        {
            'field_key': 'scope_3_emissions',
            'field_label': 'Scope 3 Emissions',
            'subsection': 'Emissions',
            'input_type': 'number',
            'unit': 'tCO2e',
            'required': True,
            'confidence_field': 'scope_3_emissions_confidence',
            'helper_text': 'Value chain emissions upstream and downstream.',
            'supports_reporting': True,
        },
        {
            'field_key': 'total_ghg_emissions',
            'field_label': 'Total GHG Emissions',
            'subsection': 'Emissions',
            'input_type': 'number',
            'unit': 'tCO2e',
            'required': True,
            'confidence_field': 'total_ghg_emissions_confidence',
            'helper_text': 'Normally equals Scope 1 + Scope 2 (location-based) + Scope 3.',
            'supports_reporting': True,
        },
        {
            'field_key': 'reduction_target_percent',
            'field_label': 'Reduction Target',
            'subsection': 'Targets & Strategy',
            'input_type': 'percent',
            'unit': '%',
            'required': False,
            'confidence_field': 'reduction_target_percent_confidence',
            'helper_text': 'Targeted emissions reduction percentage.',
            'supports_reporting': True,
        },
        {
            'field_key': 'reduction_target_year',
            'field_label': 'Reduction Target Year',
            'subsection': 'Targets & Strategy',
            'input_type': 'integer',
            'unit': 'year',
            'required': False,
            'confidence_field': 'reduction_target_year_confidence',
            'helper_text': 'Year by which target percentage should be achieved.',
            'supports_reporting': True,
        },
        {
            'field_key': 'reduction_strategy_description',
            'field_label': 'Reduction Strategy Description',
            'subsection': 'Targets & Strategy',
            'input_type': 'textarea',
            'unit': None,
            'required': False,
            'helper_text': 'Provide strategy details, especially when targets are set.',
            'supports_reporting': True,
        },
        {
            'field_key': 'total_energy_consumption',
            'field_label': 'Total Energy Consumption',
            'subsection': 'Energy',
            'input_type': 'number',
            'unit': 'MWh',
            'required': True,
            'confidence_field': 'total_energy_consumption_confidence',
            'helper_text': 'Total energy consumed in the reporting period.',
            'supports_reporting': True,
        },
        {
            'field_key': 'renewable_energy_consumption',
            'field_label': 'Renewable Energy Consumption',
            'subsection': 'Energy',
            'input_type': 'number',
            'unit': 'MWh',
            'required': True,
            'confidence_field': 'renewable_energy_consumption_confidence',
            'helper_text': 'Portion of total energy sourced from renewables.',
            'supports_reporting': True,
        },
        {
            'field_key': 'total_water_withdrawal',
            'field_label': 'Total Water Withdrawal',
            'subsection': 'Water',
            'input_type': 'number',
            'unit': 'm3',
            'required': True,
            'confidence_field': 'total_water_withdrawal_confidence',
            'helper_text': 'Total water withdrawn during the reporting period.',
            'supports_reporting': True,
        },
        {
            'field_key': 'water_recycled_reused',
            'field_label': 'Water Recycled / Reused',
            'subsection': 'Water',
            'input_type': 'number',
            'unit': 'm3',
            'required': True,
            'confidence_field': 'water_recycled_reused_confidence',
            'helper_text': 'Water volume recycled or reused.',
            'supports_reporting': True,
        },
        {
            'field_key': 'total_waste_generated',
            'field_label': 'Total Waste Generated',
            'subsection': 'Waste',
            'input_type': 'number',
            'unit': 'tonnes',
            'required': True,
            'confidence_field': 'total_waste_generated_confidence',
            'helper_text': 'Total waste produced in reporting period.',
            'supports_reporting': True,
        },
        {
            'field_key': 'waste_diverted_from_landfill',
            'field_label': 'Waste Diverted from Landfill',
            'subsection': 'Waste',
            'input_type': 'number',
            'unit': 'tonnes',
            'required': True,
            'confidence_field': 'waste_diverted_from_landfill_confidence',
            'helper_text': 'Waste diverted via recycling, recovery, or reuse.',
            'supports_reporting': True,
        },
        {
            'field_key': 'hazardous_waste_generated',
            'field_label': 'Hazardous Waste Generated',
            'subsection': 'Waste',
            'input_type': 'number',
            'unit': 'tonnes',
            'required': False,
            'confidence_field': 'hazardous_waste_generated_confidence',
            'helper_text': 'Hazardous waste generated during the period.',
            'supports_reporting': True,
        },
        {
            'field_key': 'air_quality_control_measures',
            'field_label': 'Air Quality Control Measures',
            'subsection': 'Air Quality',
            'input_type': 'select',
            'unit': None,
            'required': True,
            'confidence_field': 'air_quality_control_measures_confidence',
            'policy_options': POLICY_STATUS_OPTIONS,
            'helper_text': 'Status of air quality controls and mitigation measures.',
            'supports_reporting': True,
        },
        {
            'field_key': 'nox_sox_emissions',
            'field_label': 'NOx / SOx Emissions',
            'subsection': 'Air Quality',
            'input_type': 'number',
            'unit': 'tonnes',
            'required': False,
            'confidence_field': 'nox_sox_emissions_confidence',
            'helper_text': 'Combined NOx and SOx emissions.',
            'supports_reporting': True,
        },
    ],
    'Social': [
        {
            'field_key': 'whs_policy_in_place',
            'field_label': 'WHS Policy in Place',
            'subsection': 'Health & Safety',
            'input_type': 'select',
            'unit': None,
            'required': True,
            'confidence_field': 'whs_policy_in_place_confidence',
            'policy_options': POLICY_STATUS_OPTIONS,
            'helper_text': 'Work Health & Safety policy implementation status.',
            'supports_reporting': True,
        },
        {
            'field_key': 'whs_policy_document_reference',
            'field_label': 'WHS Policy Document Reference',
            'subsection': 'Health & Safety',
            'input_type': 'text',
            'unit': None,
            'required': False,
            'helper_text': 'Document name, URL, or evidence reference.',
            'supports_reporting': True,
        },
        {
            'field_key': 'trifr',
            'field_label': 'TRIFR',
            'subsection': 'Health & Safety',
            'input_type': 'number',
            'unit': 'rate',
            'required': True,
            'confidence_field': 'trifr_confidence',
            'helper_text': 'Total Recordable Injury Frequency Rate.',
            'supports_reporting': True,
        },
        {
            'field_key': 'total_fatalities',
            'field_label': 'Total Fatalities',
            'subsection': 'Health & Safety',
            'input_type': 'integer',
            'unit': 'count',
            'required': True,
            'confidence_field': 'total_fatalities_confidence',
            'helper_text': 'Total fatal incidents in period.',
            'supports_reporting': True,
        },
        {
            'field_key': 'total_lost_time_injuries',
            'field_label': 'Total Lost Time Injuries',
            'subsection': 'Health & Safety',
            'input_type': 'integer',
            'unit': 'count',
            'required': True,
            'confidence_field': 'total_lost_time_injuries_confidence',
            'helper_text': 'Total lost-time injuries in period.',
            'supports_reporting': True,
        },
        {
            'field_key': 'total_incidents_reported',
            'field_label': 'Total Incidents Reported',
            'subsection': 'Health & Safety',
            'input_type': 'integer',
            'unit': 'count',
            'required': True,
            'confidence_field': 'total_incidents_reported_confidence',
            'helper_text': 'All incidents reported in period.',
            'supports_reporting': True,
        },
        {
            'field_key': 'total_employees_fte',
            'field_label': 'Total Employees (FTE)',
            'subsection': 'Workforce',
            'input_type': 'integer',
            'unit': 'count',
            'required': True,
            'confidence_field': 'total_employees_fte_confidence',
            'helper_text': 'Full-time equivalent employees.',
            'supports_reporting': True,
        },
        {
            'field_key': 'employee_turnover_rate',
            'field_label': 'Employee Turnover Rate',
            'subsection': 'Workforce',
            'input_type': 'percent',
            'unit': '%',
            'required': True,
            'confidence_field': 'employee_turnover_rate_confidence',
            'helper_text': 'Annual turnover rate.',
            'supports_reporting': True,
        },
        {
            'field_key': 'female_representation_percent',
            'field_label': 'Female Workforce Representation',
            'subsection': 'Diversity',
            'input_type': 'percent',
            'unit': '%',
            'required': True,
            'confidence_field': 'female_representation_percent_confidence',
            'helper_text': 'Female representation across workforce.',
            'supports_reporting': True,
        },
        {
            'field_key': 'female_leadership_representation_percent',
            'field_label': 'Female Leadership Representation',
            'subsection': 'Diversity',
            'input_type': 'percent',
            'unit': '%',
            'required': True,
            'confidence_field': 'female_leadership_representation_percent_confidence',
            'helper_text': 'Female representation in leadership roles.',
            'supports_reporting': True,
        },
        {
            'field_key': 'community_investment_spend',
            'field_label': 'Community Investment Spend',
            'subsection': 'Community',
            'input_type': 'currency',
            'unit': 'currency',
            'required': False,
            'confidence_field': 'community_investment_spend_confidence',
            'helper_text': 'Monetary investment in community initiatives.',
            'supports_reporting': True,
        },
    ],
    'Governance': [
        {
            'field_key': 'esg_policy_in_place',
            'field_label': 'ESG Policy in Place',
            'subsection': 'ESG Governance',
            'input_type': 'select',
            'unit': None,
            'required': True,
            'confidence_field': 'esg_policy_in_place_confidence',
            'policy_options': POLICY_STATUS_OPTIONS,
            'helper_text': 'Status of formal ESG policy.',
            'supports_reporting': True,
        },
        {
            'field_key': 'esg_policy_document_reference',
            'field_label': 'ESG Policy Document Reference',
            'subsection': 'ESG Governance',
            'input_type': 'text',
            'unit': None,
            'required': False,
            'helper_text': 'Document name, URL, or evidence reference.',
            'supports_reporting': True,
        },
        {
            'field_key': 'board_level_esg_oversight',
            'field_label': 'Board-Level ESG Oversight',
            'subsection': 'Board Oversight',
            'input_type': 'select',
            'unit': None,
            'required': True,
            'confidence_field': 'board_level_esg_oversight_confidence',
            'policy_options': POLICY_STATUS_OPTIONS,
            'helper_text': 'Whether board-level ESG oversight exists.',
            'supports_reporting': True,
        },
        {
            'field_key': 'esg_kpis_linked_to_remuneration',
            'field_label': 'ESG KPIs Linked to Remuneration',
            'subsection': 'Board Oversight',
            'input_type': 'select',
            'unit': None,
            'required': False,
            'confidence_field': 'esg_kpis_linked_to_remuneration_confidence',
            'policy_options': POLICY_STATUS_OPTIONS,
            'helper_text': 'Whether ESG KPIs influence compensation.',
            'supports_reporting': True,
        },
        {
            'field_key': 'cybersecurity_policy_in_place',
            'field_label': 'Cybersecurity Policy in Place',
            'subsection': 'Cybersecurity',
            'input_type': 'select',
            'unit': None,
            'required': True,
            'confidence_field': 'cybersecurity_policy_in_place_confidence',
            'policy_options': POLICY_STATUS_OPTIONS,
            'helper_text': 'Status of cybersecurity policy.',
            'supports_reporting': True,
        },
        {
            'field_key': 'cybersecurity_policy_document_reference',
            'field_label': 'Cybersecurity Policy Document Reference',
            'subsection': 'Cybersecurity',
            'input_type': 'text',
            'unit': None,
            'required': False,
            'helper_text': 'Document name, URL, or evidence reference.',
            'supports_reporting': True,
        },
        {
            'field_key': 'cyber_incidents_in_reporting_period',
            'field_label': 'Cyber Incidents in Reporting Period',
            'subsection': 'Cybersecurity',
            'input_type': 'integer',
            'unit': 'count',
            'required': True,
            'confidence_field': 'cyber_incidents_in_reporting_period_confidence',
            'helper_text': 'Number of cyber incidents during period.',
            'supports_reporting': True,
        },
        {
            'field_key': 'anti_bribery_corruption_policy',
            'field_label': 'Anti-Bribery & Corruption Policy',
            'subsection': 'Ethics & Anti-Corruption',
            'input_type': 'select',
            'unit': None,
            'required': True,
            'confidence_field': 'anti_bribery_corruption_policy_confidence',
            'policy_options': POLICY_STATUS_OPTIONS,
            'helper_text': 'Status of anti-bribery/corruption policy.',
            'supports_reporting': True,
        },
        {
            'field_key': 'confirmed_cases_of_corruption',
            'field_label': 'Confirmed Cases of Corruption',
            'subsection': 'Ethics & Anti-Corruption',
            'input_type': 'integer',
            'unit': 'count',
            'required': True,
            'confidence_field': 'confirmed_cases_of_corruption_confidence',
            'helper_text': 'Confirmed corruption cases in period.',
            'supports_reporting': True,
        },
        {
            'field_key': 'total_board_members',
            'field_label': 'Total Board Members',
            'subsection': 'Board Composition',
            'input_type': 'integer',
            'unit': 'count',
            'required': True,
            'confidence_field': 'total_board_members_confidence',
            'helper_text': 'Total number of board members.',
            'supports_reporting': True,
        },
        {
            'field_key': 'independent_board_members_percent',
            'field_label': 'Independent Board Members',
            'subsection': 'Board Composition',
            'input_type': 'percent',
            'unit': '%',
            'required': True,
            'confidence_field': 'independent_board_members_percent_confidence',
            'helper_text': 'Percentage of independent board members.',
            'supports_reporting': True,
        },
        {
            'field_key': 'female_board_members_percent',
            'field_label': 'Female Board Members',
            'subsection': 'Board Composition',
            'input_type': 'percent',
            'unit': '%',
            'required': True,
            'confidence_field': 'female_board_members_percent_confidence',
            'helper_text': 'Percentage of female board members.',
            'supports_reporting': True,
        },
    ],
    'Supporting Notes': [
        {
            'field_key': 'submission_notes',
            'field_label': 'Submission Notes',
            'subsection': 'Notes',
            'input_type': 'textarea',
            'unit': None,
            'required': False,
            'helper_text': 'Provide clarifications, caveats, and context for reviewers.',
            'supports_reporting': True,
        }
    ],
}


def _build_field_meta_index() -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for section, fields in ESG_FIELD_CATALOG.items():
        for order, field in enumerate(fields):
            field_meta = dict(field)
            field_meta.setdefault('section', section)
            field_meta.setdefault('subsection', 'General')
            field_meta.setdefault('input_type', 'text')
            field_meta.setdefault('required', False)
            field_meta.setdefault('read_only', False)
            field_meta.setdefault('supports_reporting', True)
            field_meta.setdefault('helper_text', '')
            field_meta.setdefault('policy_options', [])
            field_meta.setdefault('confidence_field', None)
            field_meta.setdefault('order', order)
            index[field_meta['field_key']] = field_meta
    return index


FIELD_META_BY_KEY = _build_field_meta_index()


app = FastAPI(title='ESG Data App')
app.include_router(new_esg_router, prefix="/api/v2")
if not is_blob_storage_enabled():
    app.mount('/exports', StaticFiles(directory=EXPORT_DIR), name='exports')


def normalize_role(role: Any) -> str:
    if role is None:
        return ''
    value = role.value if hasattr(role, 'value') else str(role)
    normalized = value.strip().lower()
    if normalized in {'admin', 'manager'}:
        return 'manager'
    if normalized in {'company', 'investor'}:
        return normalized
    if normalized == 'managerrole':
        return 'manager'
    if normalized == 'companyrole':
        return 'company'
    return normalized


def to_user_role_enum(role: str) -> UserRole:
    normalized = normalize_role(role)
    if normalized == 'company':
        return UserRole.COMPANY
    if normalized == 'investor':
        return UserRole.INVESTOR
    return UserRole.MANAGER


def serialize_user(user: User):
    return {
        'id': user.id,
        'name': user.name,
        'email': user.email,
        'role': normalize_role(user.role),
    }


def parse_json_or_default(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        parsed = json.loads(value)
        return parsed if parsed is not None else default
    except (TypeError, ValueError):
        return default


def normalize_reminder_days(value: Any) -> List[int]:
    if not isinstance(value, list):
        return []
    normalized: List[int] = []
    for item in value:
        if isinstance(item, int):
            normalized.append(item)
            continue
        if isinstance(item, str):
            match = re.search(r'\d+', item)
            if match:
                normalized.append(int(match.group(0)))
    return normalized


def normalize_cycle_status(value: Any) -> str:
    normalized = str(value or '').strip().lower()
    if normalized in ALLOWED_CYCLE_STATUSES:
        return normalized
    return 'draft'


def serialize_cycle(cycle: CollectionCycle):
    template_config = parse_json_or_default(cycle.template_config, {})
    prefill_summary = parse_json_or_default(cycle.prefill_summary, {})
    reminder_schedule = normalize_reminder_days(parse_json_or_default(cycle.reminder_schedule, []))
    return CycleInfo(
        id=cycle.id,
        cycle_year=cycle.cycle_year,
        submission_open_date=cycle.submission_open_date,
        submission_deadline=cycle.submission_deadline,
        extension_date=cycle.extension_date,
        reminder_days_before_deadline=reminder_schedule,
        private_equity_template=template_config.get('private_equity', ''),
        real_estate_template=template_config.get('real_estate', ''),
        debt_template=template_config.get('debt', ''),
        status=normalize_cycle_status(cycle.status),
        carry_forward_prefill=bool(prefill_summary.get('carry_forward_prefill', True)),
        prefill_company_count=int(prefill_summary.get('prefill_company_count', 0)),
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://localhost:5173',
        'http://127.0.0.1:5173',
        *([os.getenv('FRONTEND_ORIGIN')] if os.getenv('FRONTEND_ORIGIN') else []),
    ],
    allow_origin_regex=r'https://.*\.vercel\.app',
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# A helper to get a database session inside path operations.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# RBAC Dependencies
# ==========================================
def get_user_role(x_user_role: str = Header(None)):
    return normalize_role(x_user_role)


def get_user_email(x_user_email: str | None = Header(default=None)) -> str | None:
    return x_user_email.strip().lower() if x_user_email else None

def require_manager(role: str = Depends(get_user_role)):
    if role != 'manager':
        raise HTTPException(status_code=403, detail='Access restricted to ESG Managers')


def require_manager_or_investor(role: str = Depends(get_user_role)):
    if role not in {'manager', 'investor'}:
        raise HTTPException(status_code=403, detail='Access restricted to Managers and Investors')


def require_company_or_manager(role: str = Depends(get_user_role)):
    if role not in {'manager', 'company'}:
        raise HTTPException(status_code=403, detail='Access restricted to Managers and Company users')


def require_company(role: str = Depends(get_user_role)):
    if role != 'company':
        raise HTTPException(status_code=403, detail='Access restricted to Portfolio Company users')


async def require_company_access(
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
    company_id: int | None = None,
):
    """
    Verifies that a company user can only access their own company's data.
    Prevents unauthorized access to other companies' submissions.
    """
    if role != 'company':
        raise HTTPException(status_code=403, detail='Access restricted to Portfolio Company users')
    
    if not email:
        raise HTTPException(status_code=401, detail='Email header required')
    
    # Find the user
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    
    # Find the company for this user
    company = db.query(Company).filter(Company.user_id == user.id).first()
    if not company:
        raise HTTPException(status_code=404, detail='No company associated with this user')
    
    # If company_id is provided, verify it matches
    if company_id and company.id != company_id:
        raise HTTPException(status_code=403, detail='Unauthorized access to this company')
    
    return company


def enforce_company_scope_for_path(
    db: Session,
    *,
    role: str,
    user_email: str | None,
    company_id: int,
):
    """Allow manager on any company, but scope company users to their own company only."""
    if role != 'company':
        return
    if not user_email:
        raise HTTPException(status_code=401, detail='Email header required')
    user = find_request_user(db, user_email)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    owned_company = db.query(Company).filter(Company.user_id == user.id).first()
    if not owned_company or owned_company.id != company_id:
        raise HTTPException(status_code=403, detail='Unauthorized access to this company')


def block_investors(role: str = Depends(get_user_role)):
    if role == 'investor':
        raise HTTPException(status_code=403, detail='Investors are blocked from individual company-level data')


def find_request_user(db: Session, email: str | None) -> User | None:
    if email:
        return db.query(User).filter(User.email == email).first()
    return None


def find_company_for_user(db: Session, user: User | None) -> Company | None:
    if not user:
        return None
    return db.query(Company).filter(Company.user_id == user.id).first()


def cleanup_expired_collaboration_sessions(db: Session):
    now = datetime.utcnow()
    sessions = (
        db.query(SubmissionCollaborationSession)
        .filter(
            SubmissionCollaborationSession.status == 'active',
            SubmissionCollaborationSession.expires_at <= now,
        )
        .all()
    )
    if not sessions:
        return
    for session in sessions:
        session.status = 'released'
        session.release_reason = session.release_reason or 'expired'
        session.updated_at = now
    db.commit()


def _serialize_activity_event(record: ActivityEvent) -> ActivityEventResponse:
    company_name = None
    if getattr(record, 'company', None) is not None:
        company_name = record.company.name
    metadata = parse_json_or_default(record.metadata_json, {})
    return ActivityEventResponse(
        id=record.id,
        event_type=record.event_type,
        title=record.title,
        message=record.message,
        severity=record.severity or 'info',
        actor_role=record.actor_role,
        actor_email=record.actor_email,
        company_id=record.company_id,
        company_name=company_name,
        submission_id=record.submission_id,
        cycle_id=record.cycle_id,
        entity_status=record.entity_status,
        is_toast=bool(record.is_toast),
        visible_to_investors=bool(record.visible_to_investors),
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=record.created_at.isoformat() if record.created_at else datetime.utcnow().isoformat(),
    )


def _serialize_collaboration_session(
    session: SubmissionCollaborationSession,
    *,
    viewer_email: str | None,
) -> CollaborationSessionResponse:
    normalized_viewer_email = (viewer_email or '').strip().lower()
    owner_email = (session.owner_email or '').strip().lower()
    return CollaborationSessionResponse(
        id=session.id,
        submission_id=session.submission_id,
        company_id=session.company_id,
        cycle_id=session.cycle_id,
        section=session.section,
        owner_role=session.owner_role,
        owner_email=session.owner_email,
        owner_name=session.owner_name,
        status=session.status,
        lock_mode=session.lock_mode or 'soft',
        is_you=bool(normalized_viewer_email and normalized_viewer_email == owner_email),
        expires_at=session.expires_at.isoformat(),
        last_seen_at=session.last_seen_at.isoformat(),
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


def _viewer_company_id_for_live_access(db: Session, *, role: str, email: str | None) -> Optional[int]:
    if role != 'company':
        return None
    user = find_request_user(db, email)
    company = find_company_for_user(db, user)
    return company.id if company else None


def _activity_event_visible_to_role(
    record: ActivityEvent,
    *,
    role: str,
    viewer_email: str | None,
    viewer_company_id: Optional[int],
) -> bool:
    normalized_role = normalize_role(role)
    if normalized_role == 'manager':
        return True
    if normalized_role == 'investor':
        return bool(record.visible_to_investors)
    if normalized_role == 'company':
        if viewer_company_id is None:
            return False
        return record.company_id == viewer_company_id
    return False


def _build_submission_collaboration(
    db: Session,
    *,
    submission: Submission,
    viewer_role: str,
    viewer_email: str | None,
) -> SubmissionCollaborationResponse:
    cleanup_expired_collaboration_sessions(db)
    sessions = (
        db.query(SubmissionCollaborationSession)
        .filter(
            SubmissionCollaborationSession.submission_id == submission.id,
            SubmissionCollaborationSession.status == 'active',
        )
        .order_by(SubmissionCollaborationSession.section.asc(), SubmissionCollaborationSession.updated_at.desc())
        .all()
    )

    deduped_by_section: Dict[str, SubmissionCollaborationSession] = {}
    for session in sessions:
        deduped_by_section.setdefault(session.section, session)

    active_sections = [
        _serialize_collaboration_session(session, viewer_email=viewer_email)
        for session in deduped_by_section.values()
    ]
    current_user_sections = [item.section for item in active_sections if item.is_you]
    return SubmissionCollaborationResponse(
        submission_id=submission.id,
        company_id=submission.company_id,
        cycle_id=submission.cycle_id or 0,
        lock_mode='soft',
        active_sections=active_sections,
        current_user_sections=current_user_sections,
        viewer_role=normalize_role(viewer_role),
        viewer_email=viewer_email,
    )


def _queue_activity_event(
    db: Session,
    *,
    event_type: str,
    title: str,
    message: str,
    severity: str = 'info',
    actor_role: str | None = None,
    actor_email: str | None = None,
    company: Company | None = None,
    submission: Submission | None = None,
    cycle: CollectionCycle | None = None,
    entity_status: str | None = None,
    is_toast: bool = True,
    visible_to_investors: bool = False,
    metadata: Dict[str, Any] | None = None,
) -> ActivityEvent:
    record = ActivityEvent(
        event_type=event_type,
        title=title,
        message=message,
        severity=severity,
        actor_role=normalize_role(actor_role),
        actor_email=(actor_email or '').strip().lower() or None,
        company_id=company.id if company else (submission.company_id if submission else None),
        submission_id=submission.id if submission else None,
        cycle_id=cycle.id if cycle else (submission.cycle_id if submission else None),
        entity_status=entity_status,
        is_toast=is_toast,
        visible_to_investors=visible_to_investors,
        metadata_json=json.dumps(metadata or {}),
    )
    db.add(record)
    db.flush()
    return record


def _load_table_columns_map(db: Session, target_tables: Optional[List[str]] = None) -> Dict[str, set[str]]:
    bind = db.get_bind() or engine
    inspector = inspect(bind)
    table_names = set(inspector.get_table_names())
    if target_tables is None:
        target_tables = sorted(table_names)
    columns_by_table: Dict[str, set[str]] = {}
    for table_name in target_tables:
        if table_name not in table_names:
            continue
        columns_by_table[table_name] = {column.get('name') for column in inspector.get_columns(table_name)}
    return columns_by_table


def _mark_table_column(columns_by_table: Dict[str, set[str]], table_name: str, column_name: str):
    columns_by_table.setdefault(table_name, set()).add(column_name)


def table_has_column(
    db: Session,
    table_name: str,
    column_name: str,
    columns_by_table: Optional[Dict[str, set[str]]] = None,
) -> bool:
    if columns_by_table is not None:
        return column_name in columns_by_table.get(table_name, set())
    bind = db.get_bind() or engine
    inspector = inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(column.get('name') == column_name for column in inspector.get_columns(table_name))


def ensure_submission_cycle_column(db: Session, columns_by_table: Optional[Dict[str, set[str]]] = None):
    if table_has_column(db, 'submissions', 'cycle_id', columns_by_table):
        return
    db.execute(text('ALTER TABLE submissions ADD COLUMN cycle_id INTEGER'))
    db.commit()
    if columns_by_table is not None:
        _mark_table_column(columns_by_table, 'submissions', 'cycle_id')


def ensure_user_lp_columns(
    db: Session,
    columns_by_table: Optional[Dict[str, set[str]]] = None,
    *,
    ensure_columns: bool = True,
    normalize: bool = True,
):
    if ensure_columns:
        changed = False
        if not table_has_column(db, 'users', 'lp_type', columns_by_table):
            db.execute(text('ALTER TABLE users ADD COLUMN lp_type VARCHAR'))
            if columns_by_table is not None:
                _mark_table_column(columns_by_table, 'users', 'lp_type')
            changed = True
        if not table_has_column(db, 'users', 'company_permissions', columns_by_table):
            db.execute(text('ALTER TABLE users ADD COLUMN company_permissions VARCHAR'))
            if columns_by_table is not None:
                _mark_table_column(columns_by_table, 'users', 'company_permissions')
            changed = True
        if not table_has_column(db, 'users', 'portfolio_id', columns_by_table):
            db.execute(text('ALTER TABLE users ADD COLUMN portfolio_id INTEGER'))
            if columns_by_table is not None:
                _mark_table_column(columns_by_table, 'users', 'portfolio_id')
            changed = True
        if changed:
            db.commit()

    if not normalize:
        return

    normalization_needed = db.execute(
        text(
            """
            SELECT 1
            FROM users
            WHERE lp_type IS NULL
               OR TRIM(CAST(lp_type AS TEXT)) = ''
               OR LOWER(CAST(lp_type AS TEXT)) IN ('standard', 'authorised')
               OR company_permissions IS NULL
               OR TRIM(CAST(company_permissions AS TEXT)) = ''
            LIMIT 1
            """
        )
    ).first()
    if not normalization_needed:
        return

    db.execute(
        text(
            """
            UPDATE users
            SET
                lp_type = CASE
                    WHEN lp_type IS NULL OR TRIM(CAST(lp_type AS TEXT)) = '' OR LOWER(CAST(lp_type AS TEXT)) = 'standard' THEN 'STANDARD'
                    WHEN LOWER(CAST(lp_type AS TEXT)) = 'authorised' THEN 'AUTHORISED'
                    ELSE lp_type
                END,
                company_permissions = CASE
                    WHEN company_permissions IS NULL OR TRIM(CAST(company_permissions AS TEXT)) = '' THEN '[]'
                    ELSE company_permissions
                END
            WHERE lp_type IS NULL
               OR TRIM(CAST(lp_type AS TEXT)) = ''
               OR LOWER(CAST(lp_type AS TEXT)) IN ('standard', 'authorised')
               OR company_permissions IS NULL
               OR TRIM(CAST(company_permissions AS TEXT)) = ''
            """
        )
    )
    db.commit()


def ensure_action_plan_columns(
    db: Session,
    columns_by_table: Optional[Dict[str, set[str]]] = None,
    *,
    ensure_columns: bool = True,
    backfill_timestamps: bool = True,
):
    if ensure_columns:
        changed = False
        if not table_has_column(db, 'action_plans', 'description', columns_by_table):
            db.execute(text('ALTER TABLE action_plans ADD COLUMN description TEXT'))
            if columns_by_table is not None:
                _mark_table_column(columns_by_table, 'action_plans', 'description')
            changed = True
        if not table_has_column(db, 'action_plans', 'linked_metric', columns_by_table):
            db.execute(text('ALTER TABLE action_plans ADD COLUMN linked_metric VARCHAR'))
            if columns_by_table is not None:
                _mark_table_column(columns_by_table, 'action_plans', 'linked_metric')
            changed = True
        if not table_has_column(db, 'action_plans', 'created_at', columns_by_table):
            db.execute(text('ALTER TABLE action_plans ADD COLUMN created_at DATETIME'))
            if columns_by_table is not None:
                _mark_table_column(columns_by_table, 'action_plans', 'created_at')
            changed = True
        if not table_has_column(db, 'action_plans', 'updated_at', columns_by_table):
            db.execute(text('ALTER TABLE action_plans ADD COLUMN updated_at DATETIME'))
            if columns_by_table is not None:
                _mark_table_column(columns_by_table, 'action_plans', 'updated_at')
            changed = True
        if changed:
            db.commit()

    if not backfill_timestamps:
        return

    needs_backfill = db.execute(
        text('SELECT 1 FROM action_plans WHERE created_at IS NULL OR updated_at IS NULL LIMIT 1')
    ).first()
    if not needs_backfill:
        return

    now_iso = datetime.utcnow().isoformat()
    db.execute(
        text(
            """
            UPDATE action_plans
            SET
                created_at = COALESCE(created_at, :now),
                updated_at = COALESCE(updated_at, :now)
            WHERE created_at IS NULL OR updated_at IS NULL
            """
        ),
        {'now': now_iso},
    )
    db.commit()


def ensure_narrative_columns(db: Session, columns_by_table: Optional[Dict[str, set[str]]] = None):
    if columns_by_table is not None:
        if 'narrative_summaries' not in columns_by_table:
            return
        columns = set(columns_by_table.get('narrative_summaries', set()))
    else:
        inspector = inspect(engine)
        if 'narrative_summaries' not in inspector.get_table_names():
            return
        columns = {column['name'] for column in inspector.get_columns('narrative_summaries')}
    if not columns:
        return
    statements = {
        'tone': "ALTER TABLE narrative_summaries ADD COLUMN tone VARCHAR DEFAULT 'board-ready'",
        'status': "ALTER TABLE narrative_summaries ADD COLUMN status VARCHAR DEFAULT 'generated'",
        'framework_tags_json': "ALTER TABLE narrative_summaries ADD COLUMN framework_tags_json TEXT DEFAULT '[]'",
        'generation_context_json': "ALTER TABLE narrative_summaries ADD COLUMN generation_context_json TEXT DEFAULT '{}'",
        'generated_payload_json': "ALTER TABLE narrative_summaries ADD COLUMN generated_payload_json TEXT DEFAULT '{}'",
        'edited_payload_json': "ALTER TABLE narrative_summaries ADD COLUMN edited_payload_json TEXT DEFAULT '{}'",
        'published_payload_json': "ALTER TABLE narrative_summaries ADD COLUMN published_payload_json TEXT DEFAULT '{}'",
        'approved_by_role': 'ALTER TABLE narrative_summaries ADD COLUMN approved_by_role VARCHAR',
        'approved_at': 'ALTER TABLE narrative_summaries ADD COLUMN approved_at DATETIME',
        'edited_by_role': 'ALTER TABLE narrative_summaries ADD COLUMN edited_by_role VARCHAR',
        'edited_at': 'ALTER TABLE narrative_summaries ADD COLUMN edited_at DATETIME',
    }
    changed = False
    for column_name, statement in statements.items():
        if column_name not in columns:
            db.execute(text(statement))
            if columns_by_table is not None:
                _mark_table_column(columns_by_table, 'narrative_summaries', column_name)
            changed = True
    if changed:
        db.commit()


def _max_reporting_cycle_year() -> int:
    return datetime.utcnow().year


def _is_valid_reporting_cycle_year(year: int | None) -> bool:
    if year is None:
        return False
    try:
        year_value = int(year)
    except (TypeError, ValueError):
        return False
    current_year = datetime.utcnow().year
    return year_value in {current_year, current_year - 1}


def _apply_valid_cycle_year_filter(query):
    current_year = datetime.utcnow().year
    previous_year = current_year - 1
    return query.filter(
        CollectionCycle.cycle_year >= previous_year,
        CollectionCycle.cycle_year <= current_year,
    )


def _normalize_reporting_period(period: str | None) -> tuple[str, int]:
    current_year = datetime.utcnow().year
    previous_year = current_year - 1
    normalized = str(period or '').strip().lower()
    if normalized in {'', 'current cycle', 'current year', f'fy{current_year}', str(current_year)}:
        return (f'FY{current_year}', current_year)
    if normalized in {'previous year', f'fy{previous_year}', str(previous_year)}:
        return (f'FY{previous_year}', previous_year)

    match = re.search(r'fy\s*(\d{4})', normalized, flags=re.IGNORECASE)
    if match:
        selected_year = int(match.group(1))
        if selected_year in {current_year, previous_year}:
            return (f'FY{selected_year}', selected_year)

    raise HTTPException(
        status_code=422,
        detail=f'period must be FY{current_year} (current year) or FY{previous_year} (previous year)',
    )


def ensure_current_previous_cycles(db: Session):
    current_year = datetime.utcnow().year
    previous_year = current_year - 1
    changed = False

    current_cycle = db.query(CollectionCycle).filter(CollectionCycle.cycle_year == current_year).first()
    if not current_cycle:
        current_cycle = CollectionCycle(
            cycle_year=current_year,
            submission_open_date=f'{current_year}-01-01',
            submission_deadline=f'{current_year}-12-31',
            extension_date=None,
            reminder_schedule=json.dumps([30, 14, 7]),
            template_config=json.dumps({'private_equity': '', 'real_estate': '', 'debt': ''}),
            prefill_summary=json.dumps({'carry_forward_prefill': True, 'prefill_company_count': 0}),
            status='active',
            created_by_user_id=None,
        )
        db.add(current_cycle)
        changed = True
    elif normalize_cycle_status(current_cycle.status) != 'active':
        current_cycle.status = 'active'
        changed = True

    previous_cycle = db.query(CollectionCycle).filter(CollectionCycle.cycle_year == previous_year).first()
    if not previous_cycle:
        previous_cycle = CollectionCycle(
            cycle_year=previous_year,
            submission_open_date=f'{previous_year}-01-01',
            submission_deadline=f'{previous_year}-12-31',
            extension_date=None,
            reminder_schedule=json.dumps([30, 14, 7]),
            template_config=json.dumps({'private_equity': '', 'real_estate': '', 'debt': ''}),
            prefill_summary=json.dumps({'carry_forward_prefill': False, 'prefill_company_count': 0}),
            status='closed',
            created_by_user_id=None,
        )
        db.add(previous_cycle)
        changed = True
    elif normalize_cycle_status(previous_cycle.status) == 'active':
        previous_cycle.status = 'closed'
        changed = True

    other_active_cycles = (
        db.query(CollectionCycle)
        .filter(CollectionCycle.status == 'active', CollectionCycle.cycle_year != current_year)
        .all()
    )
    for cycle in other_active_cycles:
        cycle.status = 'draft'
        changed = True

    if changed:
        db.commit()


def get_active_cycle(db: Session) -> CollectionCycle | None:
    ensure_current_previous_cycles(db)
    return (
        _apply_valid_cycle_year_filter(db.query(CollectionCycle))
        .filter(CollectionCycle.status == 'active')
        .order_by(CollectionCycle.cycle_year.desc())
        .first()
    )


def get_latest_cycle(db: Session) -> CollectionCycle | None:
    ensure_current_previous_cycles(db)
    return (
        _apply_valid_cycle_year_filter(db.query(CollectionCycle))
        .order_by(CollectionCycle.cycle_year.desc(), CollectionCycle.id.desc())
        .first()
    )


def get_or_create_reserved_cycle(db: Session) -> CollectionCycle:
    reserved = db.query(CollectionCycle).filter(CollectionCycle.cycle_year == 0).first()
    if reserved:
        if normalize_cycle_status(reserved.status) != 'closed':
            reserved.status = 'closed'
            db.commit()
            db.refresh(reserved)
        return reserved

    reserved = CollectionCycle(
        cycle_year=0,
        submission_open_date='1970-01-01',
        submission_deadline='1970-01-01',
        extension_date=None,
        reminder_schedule=json.dumps([]),
        template_config=json.dumps({'private_equity': '', 'real_estate': '', 'debt': ''}),
        prefill_summary=json.dumps({'carry_forward_prefill': False, 'prefill_company_count': 0}),
        status='closed',
        created_by_user_id=None,
    )
    db.add(reserved)
    db.commit()
    db.refresh(reserved)
    return reserved


def migrate_legacy_user_roles(db: Session):
    legacy_present = db.execute(
        text(
            """
            SELECT 1
            FROM users
            WHERE LOWER(CAST(role AS TEXT)) IN ('admin', 'manager', 'managerrole', 'company', 'companyrole', 'investor')
            LIMIT 1
            """
        )
    ).first()
    if not legacy_present:
        return

    db.execute(
        text(
            """
            UPDATE users
            SET role = CASE
                WHEN LOWER(CAST(role AS TEXT)) IN ('admin', 'manager', 'managerrole') THEN 'MANAGER'
                WHEN LOWER(CAST(role AS TEXT)) IN ('company', 'companyrole') THEN 'COMPANY'
                WHEN LOWER(CAST(role AS TEXT)) = 'investor' THEN 'INVESTOR'
                ELSE role
            END
            WHERE LOWER(CAST(role AS TEXT)) IN ('admin', 'manager', 'managerrole', 'company', 'companyrole', 'investor')
            """
        )
    )
    db.commit()


def fix_cycle_statuses_and_active_conflicts(db: Session):
    cycles = db.query(CollectionCycle).order_by(CollectionCycle.cycle_year.desc()).all()
    active_cycles: list[CollectionCycle] = []
    changed = False

    for cycle in cycles:
        normalized = normalize_cycle_status(cycle.status)
        if cycle.status != normalized:
            cycle.status = normalized
            changed = True
        if normalized == 'active':
            active_cycles.append(cycle)

    if len(active_cycles) > 1:
        keeper = active_cycles[0]
        for cycle in active_cycles[1:]:
            if cycle.id != keeper.id:
                cycle.status = 'draft'
                changed = True

    if changed:
        db.commit()


def ensure_submission_cycle_backfill(db: Session):
    fallback_cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)
    orphan_count = (
        db.query(Submission)
        .filter(Submission.cycle_id.is_(None))
        .update({Submission.cycle_id: fallback_cycle.id}, synchronize_session=False)
    )
    if orphan_count:
        db.commit()

    valid_cycle_ids = [cycle_id for (cycle_id,) in db.query(CollectionCycle.id).all()]
    invalid_query = db.query(Submission).filter(Submission.cycle_id.is_not(None))
    if valid_cycle_ids:
        invalid_query = invalid_query.filter(~Submission.cycle_id.in_(valid_cycle_ids))
    invalid_count = invalid_query.update({Submission.cycle_id: fallback_cycle.id}, synchronize_session=False)
    if invalid_count:
        db.commit()


def deactivate_expired_unlocks(db: Session):
    now = datetime.utcnow()
    updated = (
        db.query(SubmissionUnlock)
        .filter(SubmissionUnlock.active.is_(True), SubmissionUnlock.expires_at <= now)
        .update({SubmissionUnlock.active: False}, synchronize_session=False)
    )
    if not updated:
        return
    db.commit()


def resolve_submission_cycle(db: Session) -> CollectionCycle:
    return get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)


def get_company_reporting_field_count() -> int:
    return sum(1 for meta in FIELD_META_BY_KEY.values() if meta.get('supports_reporting'))


def has_active_unlock(db: Session, submission_id: int, company_id: int, cycle_id: int) -> bool:
    deactivate_expired_unlocks(db)
    now = datetime.utcnow()
    unlock = (
        db.query(SubmissionUnlock)
        .filter(
            SubmissionUnlock.submission_id == submission_id,
            SubmissionUnlock.company_id == company_id,
            SubmissionUnlock.cycle_id == cycle_id,
            SubmissionUnlock.active.is_(True),
            SubmissionUnlock.expires_at > now,
        )
        .order_by(SubmissionUnlock.id.desc())
        .first()
    )
    return unlock is not None


LOCKED_COMPANY_EDIT_STATUSES = {'submitted', 'under review', 'approved', 'rejected'}


def enforce_company_write_lock(
    db: Session,
    *,
    submission: Submission,
    cycle: CollectionCycle,
):
    unlocked = has_active_unlock(db, submission.id, submission.company_id, cycle.id)
    if normalize_cycle_status(cycle.status) == 'closed' and not unlocked:
        raise HTTPException(status_code=423, detail='This cycle is closed. Request a manager unlock.')

    status = normalize_submission_status(submission.status)
    if status in LOCKED_COMPANY_EDIT_STATUSES and not unlocked:
        raise HTTPException(
            status_code=423,
            detail='Submission is locked after submit. Request manager unlock to edit.',
        )


def normalize_submission_status(value: Any) -> str:
    normalized = str(value or '').strip().lower()
    if not normalized:
        return 'not started'
    return normalized


def enforce_transition(current_status: str, next_status: str):
    current = normalize_submission_status(current_status)
    target = normalize_submission_status(next_status)
    if current == target:
        return
    allowed_next = ALLOWED_REVIEW_TRANSITIONS.get(current, set())
    if target not in allowed_next:
        raise HTTPException(status_code=422, detail=f'Invalid status transition: {current} -> {target}')


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ''
    return False


def _normalize_confidence(value: Any) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    lower = raw.lower()
    aliases = {
        'high': 'High',
        'medium': 'Medium',
        'low': 'Low',
        'estimated': 'Estimated',
        'not available': 'Not Available',
        'not_available': 'Not Available',
        'measured': 'Measured',
    }
    return aliases.get(lower, raw)


def _normalize_policy_status(value: Any) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    lower = raw.lower()
    aliases = {
        'yes': 'Yes',
        'no': 'No',
        'in progress': 'In Progress',
        'in_progress': 'In Progress',
        'not applicable': 'Not Applicable',
        'not_applicable': 'Not Applicable',
        'na': 'Not Applicable',
        'n/a': 'Not Applicable',
    }
    return aliases.get(lower, raw)


def _as_float(value: Any) -> Optional[float]:
    if _is_blank(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text_value = str(value).strip().replace(',', '')
    if not text_value:
        return None
    try:
        return float(text_value)
    except ValueError:
        return None


def _as_int(value: Any) -> Optional[int]:
    float_value = _as_float(value)
    if float_value is None:
        return None
    if abs(float_value - int(float_value)) > 1e-9:
        return None
    return int(float_value)


def _coerce_payload_value(value: Any, input_type: str) -> Any:
    if _is_blank(value):
        return None
    if input_type == 'integer':
        parsed = _as_int(value)
        return parsed if parsed is not None else str(value).strip()
    if input_type in {'number', 'percent', 'currency'}:
        parsed = _as_float(value)
        return parsed if parsed is not None else str(value).strip()
    if input_type == 'select':
        return _normalize_policy_status(value)
    return str(value).strip()


def _canonicalize_field_key(field_key: str) -> str:
    return LEGACY_FIELD_ALIASES.get(field_key, field_key)


def _legacy_keys_for(canonical_key: str) -> List[str]:
    return [legacy for legacy, canonical in LEGACY_FIELD_ALIASES.items() if canonical == canonical_key]


def _find_field_row(rows: List[SubmissionDataField], field_key: str) -> Optional[SubmissionDataField]:
    for row in rows:
        if row.field_key == field_key:
            return row
    return None


def _collect_submission_values(
    db: Session,
    submission: Submission,
    *,
    cycle_year: Optional[int] = None,
) -> Tuple[Dict[str, Any], List[SubmissionDataField]]:
    rows = db.query(SubmissionDataField).filter(SubmissionDataField.submission_id == submission.id).all()
    payload = parse_json_or_default(submission.esg_data, {})
    values: Dict[str, Any] = dict(payload)

    for row in rows:
        if not _is_blank(row.value):
            values[row.field_key] = row.value
        meta = FIELD_META_BY_KEY.get(_canonicalize_field_key(row.field_key), {})
        confidence_field = meta.get('confidence_field')
        if confidence_field and not _is_blank(row.confidence_level):
            values[confidence_field] = _normalize_confidence(row.confidence_level)

    # Legacy alias fallback into canonical keys
    for legacy_key, canonical_key in LEGACY_FIELD_ALIASES.items():
        if _is_blank(values.get(canonical_key)) and not _is_blank(values.get(legacy_key)):
            values[canonical_key] = values.get(legacy_key)

    if _is_blank(values.get('company_id')):
        values['company_id'] = submission.company_id
    if cycle_year is not None and _is_blank(values.get('reporting_year')):
        values['reporting_year'] = cycle_year

    return values, rows


def _evaluate_submission_validation(values: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    def add_issue(field_key: str, error_type: str, message: str, severity: str = 'error'):
        meta = FIELD_META_BY_KEY.get(_canonicalize_field_key(field_key), {})
        issues.append(
            {
                'section': str(meta.get('section') or 'General'),
                'field_key': field_key,
                'field_label': str(meta.get('field_label') or field_key),
                'error_type': error_type,
                'error_message': message,
                'severity': severity,
            }
        )

    for field_key, meta in FIELD_META_BY_KEY.items():
        value = values.get(field_key)
        has_value = not _is_blank(value)

        if meta.get('required') and not has_value:
            add_issue(field_key, 'required', f"{meta.get('field_label')} is required.", 'error')

        confidence_field = str(meta.get('confidence_field') or '')
        if confidence_field and has_value:
            confidence = _normalize_confidence(values.get(confidence_field))
            if not confidence:
                add_issue(field_key, 'confidence', 'Confidence level is missing for this value.', 'warning')
            elif confidence not in CONFIDENCE_OPTIONS:
                add_issue(field_key, 'confidence', 'Confidence level is not recognized.', 'warning')
            elif confidence in {'Low', 'Not Available'}:
                add_issue(field_key, 'confidence', f"Confidence marked as {confidence}. Consider adding notes.", 'warning')

        if not has_value:
            continue

        input_type = str(meta.get('input_type') or 'text')
        if input_type == 'integer':
            parsed_int = _as_int(value)
            if parsed_int is None:
                add_issue(field_key, 'format', f"{meta.get('field_label')} must be a whole number.", 'error')
            elif parsed_int < 0:
                add_issue(field_key, 'range', f"{meta.get('field_label')} cannot be negative.", 'error')
        elif input_type in {'number', 'currency', 'percent'}:
            parsed_float = _as_float(value)
            if parsed_float is None:
                add_issue(field_key, 'format', f"{meta.get('field_label')} must be numeric.", 'error')
            elif parsed_float < 0:
                add_issue(field_key, 'range', f"{meta.get('field_label')} cannot be negative.", 'error')
            elif input_type == 'percent' and (parsed_float < 0 or parsed_float > 100):
                add_issue(field_key, 'range', f"{meta.get('field_label')} must be between 0 and 100.", 'error')
        elif input_type == 'select':
            normalized = _normalize_policy_status(value)
            if normalized and normalized not in POLICY_STATUS_OPTIONS:
                add_issue(field_key, 'format', f"{meta.get('field_label')} must be one of: {', '.join(POLICY_STATUS_OPTIONS)}.", 'error')

    reporting_year = _as_int(values.get('reporting_year'))
    reduction_target_percent = _as_float(values.get('reduction_target_percent'))
    reduction_target_year = _as_int(values.get('reduction_target_year'))

    if reduction_target_percent is not None and reduction_target_percent > 0:
        if reduction_target_year is None:
            add_issue('reduction_target_year', 'required', 'Reduction target year is required when reduction target percent is set.', 'error')
        if _is_blank(values.get('reduction_strategy_description')):
            add_issue('reduction_strategy_description', 'required', 'Reduction strategy description is required when reduction target percent is set.', 'error')

    if reporting_year is not None and reduction_target_year is not None and reduction_target_year < reporting_year:
        add_issue('reduction_target_year', 'range', 'Reduction target year must be greater than or equal to reporting year.', 'error')

    comparisons = [
        ('renewable_energy_consumption', 'total_energy_consumption', 'Renewable energy consumption cannot exceed total energy consumption.'),
        ('water_recycled_reused', 'total_water_withdrawal', 'Water recycled/reused cannot exceed total water withdrawal.'),
        ('waste_diverted_from_landfill', 'total_waste_generated', 'Waste diverted cannot exceed total waste generated.'),
    ]
    for child_key, parent_key, message in comparisons:
        child_val = _as_float(values.get(child_key))
        parent_val = _as_float(values.get(parent_key))
        if child_val is not None and parent_val is not None and child_val > parent_val:
            add_issue(child_key, 'range', message, 'error')

    s1 = _as_float(values.get('scope_1_emissions'))
    s2 = _as_float(values.get('scope_2_location_based'))
    s3 = _as_float(values.get('scope_3_emissions'))
    total = _as_float(values.get('total_ghg_emissions'))
    if s1 is not None and s2 is not None and s3 is not None and total is not None:
        expected = round(s1 + s2 + s3, 6)
        if abs(total - expected) > 0.01 and _is_blank(values.get('reduction_strategy_description')):
            add_issue(
                'total_ghg_emissions',
                'variance',
                'Total GHG differs from Scope 1 + Scope 2 (location-based) + Scope 3. Add strategy/override explanation in notes.',
                'warning',
            )

    if _normalize_policy_status(values.get('whs_policy_in_place')) == 'Yes' and _is_blank(values.get('whs_policy_document_reference')):
        add_issue('whs_policy_document_reference', 'required', 'WHS policy document reference is required when WHS policy is Yes.', 'error')
    if _normalize_policy_status(values.get('esg_policy_in_place')) == 'Yes' and _is_blank(values.get('esg_policy_document_reference')):
        add_issue('esg_policy_document_reference', 'required', 'ESG policy document reference is required when ESG policy is Yes.', 'error')
    if _normalize_policy_status(values.get('cybersecurity_policy_in_place')) == 'Yes' and _is_blank(values.get('cybersecurity_policy_document_reference')):
        add_issue('cybersecurity_policy_document_reference', 'required', 'Cybersecurity policy document reference is required when cybersecurity policy is Yes.', 'error')

    return issues


def _replace_validation_errors(db: Session, submission: Submission, company_id: int, issues: List[Dict[str, str]]):
    db.query(ValidationError).filter(ValidationError.submission_id == submission.id).delete(synchronize_session=False)
    for issue in issues:
        db.add(
            ValidationError(
                submission_id=submission.id,
                company_id=company_id,
                section=issue['section'],
                field_key=issue['field_key'],
                field_label=issue['field_label'],
                error_type=issue['error_type'],
                error_message=issue['error_message'],
                severity=issue['severity'],
                resolved=False,
            )
        )


def _sync_submission_payload(db: Session, submission: Submission, *, cycle_year: Optional[int] = None):
    values, rows = _collect_submission_values(db, submission, cycle_year=cycle_year)
    payload = parse_json_or_default(submission.esg_data, {})

    for row in rows:
        canonical_key = _canonicalize_field_key(row.field_key)
        meta = FIELD_META_BY_KEY.get(canonical_key, {})
        input_type = str(meta.get('input_type') or 'text')
        coerced = _coerce_payload_value(row.value, input_type)
        if coerced is None:
            payload.pop(canonical_key, None)
        else:
            payload[canonical_key] = coerced

        confidence_field = str(meta.get('confidence_field') or '')
        normalized_conf = _normalize_confidence(row.confidence_level)
        if confidence_field:
            if normalized_conf:
                payload[confidence_field] = normalized_conf
            else:
                payload.pop(confidence_field, None)

    if _is_blank(payload.get('company_id')):
        payload['company_id'] = submission.company_id
    if cycle_year is not None and _is_blank(payload.get('reporting_year')):
        payload['reporting_year'] = cycle_year

    submission.esg_data = json.dumps(payload)



# ==========================================
# LP (LIMITED PARTNER / INVESTOR) RBAC
# ==========================================
def require_lp(role: str = Depends(get_user_role)):
    """Require user to be an investor/LP"""
    if role != 'investor':
        raise HTTPException(status_code=403, detail='Access restricted to Limited Partner / Investor role')


def get_lp_user(db: Session, email: str | None) -> User | None:
    """Get LP user and validate they exist"""
    if not email:
        raise HTTPException(status_code=401, detail='User identification required')
    user = find_request_user(db, email)
    if not user or user.role != UserRole.INVESTOR:
        raise HTTPException(status_code=403, detail='Not an LP/Investor user')
    return user


def parse_lp_company_permissions(permissions_json: str | None) -> List[int]:
    """Parse company permissions from JSON string"""
    if not permissions_json:
        return []
    try:
        perms = json.loads(permissions_json)
        return [int(x) for x in perms if str(x).isdigit()]
    except (json.JSONDecodeError, ValueError, TypeError):
        return []


def get_lp_accessible_company_ids(user: User) -> List[int]:
    """Get list of company IDs that an LP user can access"""
    lp_type = user.lp_type.value if hasattr(user.lp_type, 'value') else str(user.lp_type or '')
    if lp_type.strip().lower() == 'authorised':
        return parse_lp_company_permissions(user.company_permissions)
    # Standard LP has no specific company access (portfolio-only)
    return []


def _env_enabled(name: str, *, default: bool) -> bool:
    value = str(os.getenv(name) or '').strip().lower()
    if not value:
        return default
    if value in {'1', 'true', 'yes', 'on'}:
        return True
    if value in {'0', 'false', 'no', 'off'}:
        return False
    return default


def _should_seed_sample_data(db: Session) -> bool:
    if not _env_enabled('SEED_SAMPLE_DATA_ON_STARTUP', default=True):
        return False
    has_user = db.query(User.id).first() is not None
    has_company = db.query(Company.id).first() is not None
    has_cycle = db.query(CollectionCycle.id).first() is not None
    return not (has_user and has_company and has_cycle)


def _core_schema_is_current(db: Session) -> bool:
    checks = [
        'SELECT id, role, lp_type, company_permissions, portfolio_id FROM users LIMIT 1',
        'SELECT id, cycle_id FROM submissions LIMIT 1',
        'SELECT id, description, linked_metric, created_at, updated_at FROM action_plans LIMIT 1',
        'SELECT id, tone, status, framework_tags_json, generation_context_json, generated_payload_json, edited_payload_json, published_payload_json, approved_by_role, approved_at, edited_by_role, edited_at FROM narrative_summaries LIMIT 1',
    ]
    try:
        for statement in checks:
            db.execute(text(statement))
        return True
    except Exception:
        return False


def _set_startup_maintenance_status(
    *,
    status: str,
    completed_at: Optional[str] = None,
    error: Optional[str] = None,
    duration_ms: Optional[float] = None,
    steps: Optional[List[dict]] = None,
):
    STARTUP_STATUS['maintenance'] = {
        'status': status,
        'completed_at': completed_at,
        'error': error,
        'duration_ms': duration_ms,
        'steps': steps or [],
    }


def _run_deferred_startup_maintenance():
    db = SessionLocal()
    maintenance_begin = time.perf_counter()
    maintenance_steps: List[dict] = []

    def run_step(name: str, fn):
        step_begin = time.perf_counter()
        fn()
        maintenance_steps.append(
            {
                'name': name,
                'duration_ms': round((time.perf_counter() - step_begin) * 1000, 2),
            }
        )

    try:
        run_step(
            'schema.normalize_user_lp_columns',
            lambda: ensure_user_lp_columns(db, ensure_columns=False, normalize=True),
        )
        run_step(
            'schema.backfill_action_plan_timestamps',
            lambda: ensure_action_plan_columns(db, ensure_columns=False, backfill_timestamps=True),
        )
        run_step('migrations.legacy_user_roles', lambda: migrate_legacy_user_roles(db))
        run_step('cycles.fix_active_conflicts', lambda: fix_cycle_statuses_and_active_conflicts(db))
        run_step('submissions.ensure_cycle_backfill', lambda: ensure_submission_cycle_backfill(db))
        run_step('locks.deactivate_expired_unlocks', lambda: deactivate_expired_unlocks(db))
        _set_startup_maintenance_status(
            status='completed',
            completed_at=datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
            error=None,
            duration_ms=round((time.perf_counter() - maintenance_begin) * 1000, 2),
            steps=maintenance_steps,
        )
    except Exception as exc:
        _set_startup_maintenance_status(
            status='failed',
            completed_at=datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
            error=str(exc),
            duration_ms=round((time.perf_counter() - maintenance_begin) * 1000, 2),
            steps=maintenance_steps,
        )
    finally:
        db.close()


@app.on_event('startup')
def startup_event():
    db = SessionLocal()
    startup_begin = time.perf_counter()
    startup_steps: List[dict] = []
    STARTUP_STATUS['steps'] = []
    STARTUP_STATUS['duration_ms'] = None

    def run_step(name: str, fn):
        step_begin = time.perf_counter()
        fn()
        startup_steps.append(
            {
                'name': name,
                'duration_ms': round((time.perf_counter() - step_begin) * 1000, 2),
            }
        )

    try:
        defer_maintenance = _env_enabled('STARTUP_DEFER_MAINTENANCE', default=True)
        if str(os.getenv('SELF_TEST_FULL') or '').strip().lower() in {'1', 'true', 'yes'}:
            defer_maintenance = False
        _set_startup_maintenance_status(status='running' if defer_maintenance else 'not_started')
        schema_state = {'current': False}
        run_step('schema.preflight', lambda: schema_state.update({'current': _core_schema_is_current(db)}))

        if schema_state['current']:
            startup_steps.append({'name': 'schema.migrations(skipped)', 'duration_ms': 0.0})
        else:
            columns_by_table: Dict[str, set[str]] = {}
            startup_schema_tables = [
                'users',
                'companies',
                'submissions',
                'collection_cycles',
                'action_plans',
                'narrative_summaries',
            ]
            run_step(
                'schema.snapshot',
                lambda: columns_by_table.update(_load_table_columns_map(db, startup_schema_tables)),
            )
            run_step('schema.ensure_submission_cycle_column', lambda: ensure_submission_cycle_column(db, columns_by_table))
            run_step(
                'schema.ensure_user_lp_columns',
                lambda: ensure_user_lp_columns(
                    db,
                    columns_by_table,
                    ensure_columns=True,
                    normalize=not defer_maintenance,
                ),
            )
            run_step(
                'schema.ensure_action_plan_columns',
                lambda: ensure_action_plan_columns(
                    db,
                    columns_by_table,
                    ensure_columns=True,
                    backfill_timestamps=not defer_maintenance,
                ),
            )
            run_step('schema.ensure_narrative_columns', lambda: ensure_narrative_columns(db, columns_by_table))

            core_tables = {'users', 'companies', 'submissions', 'collection_cycles'}
            missing_tables = [table_name for table_name in sorted(core_tables) if table_name not in columns_by_table]
            if missing_tables:
                run_step('schema.create_all', lambda: Base.metadata.create_all(bind=engine))
            else:
                startup_steps.append({'name': 'schema.create_all(skipped)', 'duration_ms': 0.0})

        skip_sample_seed = str(os.getenv('SELF_TEST_FAST', '')).strip().lower() in {'1', 'true', 'yes', 'fast'}
        if not skip_sample_seed and _should_seed_sample_data(db):
            run_step('bootstrap.seed_sample_data', lambda: seed_sample_data(db))
        else:
            startup_steps.append({'name': 'bootstrap.seed_sample_data(skipped)', 'duration_ms': 0.0})

        if defer_maintenance:
            startup_steps.append({'name': 'maintenance.deferred(background)', 'duration_ms': 0.0})
        else:
            run_step('migrations.legacy_user_roles', lambda: migrate_legacy_user_roles(db))
            run_step('cycles.fix_active_conflicts', lambda: fix_cycle_statuses_and_active_conflicts(db))
            run_step('submissions.ensure_cycle_backfill', lambda: ensure_submission_cycle_backfill(db))
            run_step('locks.deactivate_expired_unlocks', lambda: deactivate_expired_unlocks(db))
            _set_startup_maintenance_status(
                status='completed',
                completed_at=datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
                error=None,
                duration_ms=0.0,
                steps=[],
            )

        STARTUP_STATUS['completed'] = True
        STARTUP_STATUS['error'] = None
        STARTUP_STATUS['completed_at'] = datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
        STARTUP_STATUS['duration_ms'] = round((time.perf_counter() - startup_begin) * 1000, 2)
        STARTUP_STATUS['steps'] = startup_steps
        if defer_maintenance:
            threading.Thread(
                target=_run_deferred_startup_maintenance,
                name='deferred-startup-maintenance',
                daemon=True,
            ).start()
    except Exception as exc:
        STARTUP_STATUS['completed'] = False
        STARTUP_STATUS['error'] = str(exc)
        STARTUP_STATUS['completed_at'] = None
        STARTUP_STATUS['duration_ms'] = round((time.perf_counter() - startup_begin) * 1000, 2)
        STARTUP_STATUS['steps'] = startup_steps
        _set_startup_maintenance_status(status='failed', completed_at=None, error=str(exc), duration_ms=None, steps=[])
        raise
    finally:
        db.close()


def _runtime_health_snapshot(db: Session) -> dict:
    database_ok = True
    database_error = None
    try:
        db.execute(text('SELECT 1'))
    except Exception as exc:
        database_ok = False
        database_error = str(exc)

    vercel_runtime = str(os.getenv('VERCEL') or '').strip() == '1'
    blob_enabled = is_blob_storage_enabled()
    frontend_origin = str(os.getenv('FRONTEND_ORIGIN') or '').strip()
    openai_configured = bool(str(os.getenv('OPENAI_API_KEY') or '').strip())

    checks = {
        'startup': {
            'ok': bool(STARTUP_STATUS['completed']) and not STARTUP_STATUS['error'],
            'completed_at': STARTUP_STATUS['completed_at'],
            'duration_ms': STARTUP_STATUS.get('duration_ms'),
            'steps': STARTUP_STATUS.get('steps') or [],
            'error': STARTUP_STATUS['error'],
        },
        'maintenance': {
            'status': (STARTUP_STATUS.get('maintenance') or {}).get('status'),
            'completed_at': (STARTUP_STATUS.get('maintenance') or {}).get('completed_at'),
            'duration_ms': (STARTUP_STATUS.get('maintenance') or {}).get('duration_ms'),
            'steps': (STARTUP_STATUS.get('maintenance') or {}).get('steps') or [],
            'error': (STARTUP_STATUS.get('maintenance') or {}).get('error'),
        },
        'database': {
            'ok': database_ok,
            'error': database_error,
        },
        'storage': {
            'ok': blob_enabled if vercel_runtime else True,
            'mode': 'blob' if blob_enabled else 'filesystem',
            'error': None if (blob_enabled or not vercel_runtime) else 'BLOB_READ_WRITE_TOKEN is required on Vercel for export storage.',
        },
        'frontend_origin': {
            'ok': bool(frontend_origin) if vercel_runtime else True,
            'value': frontend_origin or None,
            'error': None if (frontend_origin or not vercel_runtime) else 'FRONTEND_ORIGIN must be set in production.',
        },
        'openai': {
            'ok': openai_configured,
            'configured': openai_configured,
            'error': None if openai_configured else 'OPENAI_API_KEY is not configured. AI-assisted features will fall back where possible.',
        },
    }
    ready = all(
        bool(checks[key]['ok'])
        for key in ('startup', 'database', 'storage', 'frontend_origin')
    )
    overall = 'ok' if ready else 'degraded'
    return {
        'status': overall,
        'ready': ready,
        'environment': 'vercel' if vercel_runtime else 'local',
        'timestamp': datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
        'checks': checks,
    }


@app.get('/health')
def health(db: Session = Depends(get_db)):
    snapshot = _runtime_health_snapshot(db)
    snapshot['message'] = 'Application health snapshot'
    return snapshot


@app.get('/health/ready')
def health_ready(db: Session = Depends(get_db)):
    snapshot = _runtime_health_snapshot(db)
    if not snapshot['ready']:
        raise HTTPException(status_code=503, detail=snapshot)
    snapshot['message'] = 'Application is ready to serve requests'
    return snapshot

@app.post('/login', response_model=UserResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    normalized_email = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if not user or user.password != request.password:
        raise HTTPException(status_code=401, detail='Invalid email or password')
    return serialize_user(user)


@app.post('/auth/forgot-password', response_model=ForgotPasswordResponse)
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Deliberately return a generic message to avoid revealing account existence.
    _ = db.query(User).filter(User.email == request.email).first()
    return ForgotPasswordResponse(
        message='If an account with that email exists, password reset instructions have been sent.'
    )


@app.post('/auth/sso/{provider}', response_model=UserResponse)
def sso_login(provider: str, payload: SSOLoginRequest | None = None, db: Session = Depends(get_db)):
    normalized_provider = provider.strip().lower()
    allowed_providers = {'google', 'microsoft'}
    if normalized_provider not in allowed_providers:
        raise HTTPException(status_code=400, detail='Unsupported SSO provider')

    email_hint = (payload.email_hint if payload else None) or ''
    provider_default_email = 'manager@example.com' if normalized_provider == 'google' else 'investor@example.com'
    target_email = email_hint.strip().lower() or provider_default_email

    user = db.query(User).filter(User.email == target_email).first()
    if not user:
        # Fallback to the provider default user if hint email does not exist.
        user = db.query(User).filter(User.email == provider_default_email).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail='No configured SSO account found. Load fixture users from server/fixtures/users.csv.',
        )

    return serialize_user(user)


@app.get('/users', response_model=List[UserResponse], dependencies=[Depends(require_manager)])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [serialize_user(user) for user in users]


@app.post('/companies', response_model=CompanyCreateResponse, dependencies=[Depends(require_manager)])
def create_company(
    payload: CompanyCreateRequest,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
):
    existing_user = db.query(User).filter(User.email == payload.contact_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail='A user with this contact email already exists')

    portfolio_user = User(
        name=payload.contact_name,
        email=payload.contact_email,
        password=payload.temporary_password,
        role=UserRole.COMPANY,
    )
    db.add(portfolio_user)
    db.commit()
    db.refresh(portfolio_user)

    company = Company(
        name=payload.name,
        sector=payload.sector,
        user_id=portfolio_user.id,
        current_status=payload.current_status,
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    _queue_activity_event(
        db,
        event_type='company_created',
        title='Company added',
        message=f'{company.name} was added to the portfolio workspace.',
        severity='success',
        actor_role='manager',
        actor_email=user_email,
        company=company,
        entity_status=company.current_status,
        is_toast=True,
        visible_to_investors=False,
        metadata={'sector': company.sector or '', 'status': company.current_status or ''},
    )
    db.commit()

    return CompanyCreateResponse(
        id=company.id,
        name=company.name,
        sector=company.sector,
        portfolio_user_email=portfolio_user.email,
        portfolio_user_password=payload.temporary_password,
    )


@app.post('/cycles', response_model=CycleInfo, dependencies=[Depends(require_manager)])
def create_cycle(
    payload: CycleCreateRequest,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
):
    if not _is_valid_reporting_cycle_year(payload.cycle_year):
        current_year = datetime.utcnow().year
        raise HTTPException(
            status_code=422,
            detail=f'cycle_year must be {current_year} (current year) or {current_year - 1} (previous year)',
        )

    existing_cycle = db.query(CollectionCycle).filter(CollectionCycle.cycle_year == payload.cycle_year).first()
    if existing_cycle:
        raise HTTPException(status_code=400, detail='A cycle for this year already exists')

    latest_submissions = 0
    if payload.carry_forward_prefill:
        for company in db.query(Company).all():
            if company.submissions:
                latest_submissions += 1

    if payload.activate_on_create:
        active_cycles = db.query(CollectionCycle).filter(CollectionCycle.status == 'active').all()
        for active_cycle in active_cycles:
            active_cycle.status = 'draft'

    cycle = CollectionCycle(
        cycle_year=payload.cycle_year,
        submission_open_date=payload.submission_open_date,
        submission_deadline=payload.submission_deadline,
        extension_date=payload.extension_date,
        reminder_schedule=json.dumps(payload.reminder_days_before_deadline),
        template_config=json.dumps({
            'private_equity': payload.private_equity_template,
            'real_estate': payload.real_estate_template,
            'debt': payload.debt_template,
        }),
        prefill_summary=json.dumps({
            'carry_forward_prefill': payload.carry_forward_prefill,
            'prefill_company_count': latest_submissions,
        }),
        status='active' if payload.activate_on_create else 'draft',
    )
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    _queue_activity_event(
        db,
        event_type='cycle_created',
        title='Reporting cycle created',
        message=f'FY{cycle.cycle_year} reporting cycle was created as {cycle.status}.',
        severity='success',
        actor_role='manager',
        actor_email=user_email,
        cycle=cycle,
        entity_status=cycle.status,
        is_toast=True,
        visible_to_investors=False,
        metadata={'cycle_year': cycle.cycle_year, 'status': cycle.status},
    )
    db.commit()
    return serialize_cycle(cycle)


@app.get('/cycles', response_model=List[CycleInfo], dependencies=[Depends(require_manager)])
def list_cycles(db: Session = Depends(get_db)):
    cycles = (
        _apply_valid_cycle_year_filter(db.query(CollectionCycle))
        .order_by(CollectionCycle.cycle_year.desc(), CollectionCycle.id.desc())
        .all()
    )
    return [serialize_cycle(cycle) for cycle in cycles]

@app.patch('/cycles/{cycle_id}/status', response_model=CycleInfo, dependencies=[Depends(require_manager)])
def update_cycle_status(
    cycle_id: int,
    payload: CycleStatusUpdateRequest,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
):
    cycle = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail='Cycle not found')

    current_status = normalize_cycle_status(cycle.status)
    next_status = normalize_cycle_status(payload.status)
    if next_status == current_status:
        return serialize_cycle(cycle)

    allowed_next = ALLOWED_CYCLE_TRANSITIONS.get(current_status, set())
    if next_status not in allowed_next:
        raise HTTPException(status_code=422, detail=f'Invalid cycle transition: {current_status} -> {next_status}')

    if next_status == 'active':
        active_cycles = db.query(CollectionCycle).filter(CollectionCycle.status == 'active').all()
        for active_cycle in active_cycles:
            if active_cycle.id != cycle.id:
                active_cycle.status = 'draft'

    cycle.status = next_status
    previous_status = current_status
    _queue_activity_event(
        db,
        event_type='cycle_status_changed',
        title='Reporting cycle updated',
        message=f'FY{cycle.cycle_year} reporting cycle moved from {previous_status} to {next_status}.',
        severity='info' if next_status != 'active' else 'success',
        actor_role='manager',
        actor_email=user_email,
        cycle=cycle,
        entity_status=next_status,
        is_toast=True,
        visible_to_investors=next_status in {'active', 'closed'},
        metadata={'cycle_year': cycle.cycle_year, 'previous_status': previous_status, 'status': next_status},
    )
    db.commit()
    db.refresh(cycle)
    return serialize_cycle(cycle)


@app.post('/company/{company_id}/onboarding/complete', dependencies=[Depends(require_manager)])
def complete_onboarding(
    company_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    company.current_status = 'active'
    _queue_activity_event(
        db,
        event_type='company_onboarded',
        title='Company onboarding completed',
        message=f'{company.name} is now active in the portfolio.',
        severity='success',
        actor_role='manager',
        actor_email=user_email,
        company=company,
        entity_status=company.current_status,
        is_toast=True,
        visible_to_investors=True,
        metadata={'status': company.current_status},
    )
    db.commit()
    return {"message": "Onboarding complete. Company is now active in the portfolio."}

@app.post('/company/{company_id}/submissions', response_model=SubmissionInfo, dependencies=[Depends(require_company_or_manager)])
def add_submission(
    company_id: int,
    submission: SubmissionCreateRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    user_email: str | None = Depends(get_user_email),
):
    enforce_company_scope_for_path(db, role=role, user_email=user_email, company_id=company_id)
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')

    target_cycle = resolve_submission_cycle(db)
    if not target_cycle:
        raise HTTPException(status_code=400, detail='No collection cycle is configured')

    latest_for_cycle = (
        db.query(Submission)
        .filter(Submission.company_id == company_id, Submission.cycle_id == target_cycle.id)
        .order_by(Submission.id.desc())
        .first()
    )

    if normalize_cycle_status(target_cycle.status) == 'closed':
        if not latest_for_cycle:
            raise HTTPException(status_code=423, detail='This cycle is closed and no unlock is available')
        if not has_active_unlock(db, latest_for_cycle.id, company_id, target_cycle.id):
            raise HTTPException(status_code=423, detail='This cycle is closed. Request a manager unlock.')

    if latest_for_cycle and normalize_submission_status(latest_for_cycle.status) == 'resubmission requested':
        enforce_transition(latest_for_cycle.status, 'submitted')
        latest_for_cycle.esg_data = json.dumps(submission.model_dump())
        latest_for_cycle.status = 'submitted'
        _queue_activity_event(
            db,
            event_type='submission_submitted',
            title='Submission resubmitted',
            message=f'{company.name} resubmitted ESG data for FY{target_cycle.cycle_year}.',
            severity='success',
            actor_role=role,
            actor_email=user_email,
            company=company,
            submission=latest_for_cycle,
        cycle=target_cycle,
        entity_status=latest_for_cycle.status,
        is_toast=True,
        visible_to_investors=True,
        metadata={'cycle_year': target_cycle.cycle_year, 'resubmission': True},
    )
        db.commit()
        db.refresh(latest_for_cycle)
        return latest_for_cycle

    submission_record = Submission(
        company_id=company_id,
        cycle_id=target_cycle.id,
        esg_data=json.dumps(submission.model_dump()),
        status='submitted',
    )
    db.add(submission_record)
    db.flush()
    _queue_activity_event(
        db,
        event_type='submission_submitted',
        title='Submission submitted',
        message=f'{company.name} submitted ESG data for FY{target_cycle.cycle_year}.',
        severity='success',
        actor_role=role,
        actor_email=user_email,
        company=company,
        submission=submission_record,
        cycle=target_cycle,
        entity_status='submitted',
        is_toast=True,
        visible_to_investors=True,
        metadata={'cycle_year': target_cycle.cycle_year},
    )
    db.commit()
    db.refresh(submission_record)
    return submission_record

@app.get('/dashboard/company/{user_id}', response_model=List[CompanyDetail], dependencies=[Depends(block_investors)])
def company_dashboard(
    user_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    user_email: str | None = Depends(get_user_email),
):
    if role not in {'manager', 'company'}:
        raise HTTPException(status_code=403, detail='Access restricted to Managers and Company users')
    if role == 'company':
        if not user_email:
            raise HTTPException(status_code=401, detail='Email header required')
        request_user = find_request_user(db, user_email)
        if not request_user or request_user.id != user_id:
            raise HTTPException(status_code=403, detail='Unauthorized access to this company dashboard')
    companies = db.query(Company).filter(Company.user_id == user_id).all()
    return companies

@app.patch('/submissions/{submission_id}/status', response_model=SubmissionInfo, dependencies=[Depends(require_manager)])
def update_submission_status(
    submission_id: int,
    payload: SubmissionStatusUpdateRequest,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
):
    next_status = normalize_submission_status(payload.status)
    if next_status not in ALLOWED_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail='Invalid submission status')

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    enforce_transition(submission.status, next_status)
    submission.status = next_status
    company = db.query(Company).filter(Company.id == submission.company_id).first()
    cycle = submission.cycle or resolve_submission_cycle(db)
    _queue_activity_event(
        db,
        event_type='submission_status_changed',
        title='Submission status changed',
        message=f'{company.name if company else "A company"} moved to {next_status.title()}.',
        severity='info' if next_status != 'approved' else 'success',
        actor_role='manager',
        actor_email=user_email,
        company=company,
        submission=submission,
        cycle=cycle,
        entity_status=next_status,
        is_toast=True,
        visible_to_investors=next_status == 'approved',
        metadata={'status': next_status},
    )
    db.commit()
    db.refresh(submission)
    return submission

@app.post('/company/{company_id}/action-plans', response_model=ActionPlanInfo, dependencies=[Depends(require_company_or_manager)])
def create_action_plan(
    company_id: int,
    payload: ActionPlanCreateRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    user_email: str | None = Depends(get_user_email),
):
    enforce_company_scope_for_path(db, role=role, user_email=user_email, company_id=company_id)
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    plan = ActionPlan(
        company_id=company.id,
        initiative_name=payload.initiative_name,
        target_completion_date=payload.target_completion_date,
        assigned_owner=payload.assigned_owner,
        status='planned'
    )
    db.add(plan)
    db.flush()
    _queue_activity_event(
        db,
        event_type='action_plan_created',
        title='Action plan created',
        message=f'{company.name} added action plan "{plan.initiative_name}".',
        severity='info',
        actor_role=role,
        actor_email=user_email,
        company=company,
        cycle=resolve_submission_cycle(db),
        is_toast=True,
        visible_to_investors=True,
        metadata={'action_plan_id': plan.id, 'status': plan.status, 'owner': plan.assigned_owner or ''},
    )
    db.commit()
    db.refresh(plan)
    return plan

@app.post('/calculator/ghg', response_model=GHGCalculatorResponse)
def calculate_ghg(payload: GHGCalculatorRequest):
    fuel_factor = safe_number(getattr(payload, 'fuel_emission_factor', 0.00268), 0.00268)
    electricity_factor = safe_number(getattr(payload, 'electricity_emission_factor', 0.0005), 0.0005)
    diesel_factor = safe_number(getattr(payload, 'diesel_emission_factor', 0.00268), 0.00268)
    natural_gas_factor = safe_number(getattr(payload, 'natural_gas_emission_factor', 0.0053), 0.0053)
    vehicle_factor = safe_number(getattr(payload, 'vehicle_emission_factor', 0.00018), 0.00018)
    flight_factor = safe_number(getattr(payload, 'flight_emission_factor', 0.00015), 0.00015)

    fuel_scope_1 = payload.fuel_liters * fuel_factor
    diesel_scope_1 = payload.diesel_liters * diesel_factor
    gas_scope_1 = payload.natural_gas_therms * natural_gas_factor
    scope_1 = fuel_scope_1 + diesel_scope_1 + gas_scope_1
    scope_2 = payload.electricity_kwh * electricity_factor
    scope_3 = (payload.vehicle_km * vehicle_factor) + (payload.flight_km * flight_factor)
    total = scope_1 + scope_2 + scope_3

    def equivalent_text(value_tco2e: float) -> str:
        if value_tco2e <= 0:
            return 'No material emissions recorded.'
        vehicle_years = value_tco2e / IMPACT_TCO2E_PER_PASSENGER_VEHICLE_YEAR
        return f'Equivalent to roughly {vehicle_years:,.0f} passenger vehicles driven for a year.'

    activity_breakdown = []
    activity_rows = [
        ('fuel_liters', 'Fuel combustion', payload.fuel_liters, fuel_factor, 'Scope 1'),
        ('diesel_liters', 'Diesel combustion', payload.diesel_liters, diesel_factor, 'Scope 1'),
        ('natural_gas_therms', 'Natural gas', payload.natural_gas_therms, natural_gas_factor, 'Scope 1'),
        ('electricity_kwh', 'Electricity', payload.electricity_kwh, electricity_factor, 'Scope 2'),
        ('vehicle_km', 'Vehicle travel', payload.vehicle_km, vehicle_factor, 'Scope 3'),
        ('flight_km', 'Air travel', payload.flight_km, flight_factor, 'Scope 3'),
    ]
    for field_key, label, input_value, factor, scope_label in activity_rows:
        if input_value <= 0:
            continue
        emissions = round(input_value * factor, 4)
        activity_breakdown.append(
            {
                'field_key': field_key,
                'activity': label,
                'scope': scope_label,
                'input_value': round(input_value, 4),
                'unit': 'km' if 'km' in field_key else 'kWh' if field_key == 'electricity_kwh' else 'liters' if 'liters' in field_key else 'therms',
                'emissions_tco2e': emissions,
            }
        )

    scope_1_activities = [row for row in activity_breakdown if row['scope'] == 'Scope 1']
    scope_2_activities = [row for row in activity_breakdown if row['scope'] == 'Scope 2']
    scope_3_activities = [row for row in activity_breakdown if row['scope'] == 'Scope 3']

    if total <= 0:
        recommendation = 'Enter at least one activity input to calculate the carbon footprint.'
    elif scope_1 >= scope_2 and scope_1 >= scope_3:
        recommendation = 'Scope 1 is the largest source, so prioritize on-site fuel and process efficiency.'
    elif scope_2 >= scope_1 and scope_2 >= scope_3:
        recommendation = 'Scope 2 is the largest source, so prioritize electricity sourcing and efficiency.'
    else:
        recommendation = 'Scope 3 is the largest source, so prioritize travel and supplier reduction opportunities.'

    return GHGCalculatorResponse(
        scope_1_tco2e=round(scope_1, 4),
        scope_2_tco2e=round(scope_2, 4),
        scope_3_tco2e=round(scope_3, 4),
        total_tco2e=round(total, 4),
        scope_1_equivalent=equivalent_text(scope_1),
        scope_2_equivalent=equivalent_text(scope_2),
        scope_3_equivalent=equivalent_text(scope_3),
        total_equivalent=equivalent_text(total),
        summary=(
            f'Scope 1 totals {round(scope_1, 4)} tCO2e, Scope 2 totals {round(scope_2, 4)} tCO2e, '
            f'and Scope 3 totals {round(scope_3, 4)} tCO2e. The combined carbon footprint is {round(total, 4)} tCO2e.'
        ),
        fuel_emission_factor=round(fuel_factor, 5),
        electricity_emission_factor=round(electricity_factor, 5),
        diesel_emission_factor=round(diesel_factor, 5),
        natural_gas_emission_factor=round(natural_gas_factor, 5),
        vehicle_emission_factor=round(vehicle_factor, 5),
        flight_emission_factor=round(flight_factor, 5),
        activity_breakdown=activity_breakdown,
        scope_breakdown={
            'scope_1': {
                'total_tco2e': round(scope_1, 4),
                'activities': scope_1_activities,
            },
            'scope_2': {
                'total_tco2e': round(scope_2, 4),
                'activities': scope_2_activities,
            },
            'scope_3': {
                'total_tco2e': round(scope_3, 4),
                'activities': scope_3_activities,
            },
            'total': {
                'total_tco2e': round(total, 4),
                'scope_1_share_percent': round((scope_1 / total) * 100, 2) if total else 0.0,
                'scope_2_share_percent': round((scope_2 / total) * 100, 2) if total else 0.0,
                'scope_3_share_percent': round((scope_3 / total) * 100, 2) if total else 0.0,
            },
        },
        recommendation=recommendation,
    )

DOCUMENT_EXTRACTION_RULES = [
    {
        'field_key': 'whs_policy_document_reference',
        'kind': 'reference',
        'keywords': ['whs', 'health and safety', 'work health safety', 'safety policy'],
        'confidence_level': 'High',
        'explanation': 'The file appears to support the work health and safety policy field.',
    },
    {
        'field_key': 'esg_policy_document_reference',
        'kind': 'reference',
        'keywords': ['esg policy', 'environmental social governance', 'sustainability policy', 'policy'],
        'confidence_level': 'High',
        'explanation': 'The file appears to support the ESG policy field.',
    },
    {
        'field_key': 'cybersecurity_policy_document_reference',
        'kind': 'reference',
        'keywords': ['cyber', 'information security', 'security policy', 'incident response'],
        'confidence_level': 'High',
        'explanation': 'The file appears to support the cybersecurity policy field.',
    },
    {
        'field_key': 'whs_policy_in_place',
        'kind': 'boolean',
        'keywords': ['work health safety policy', 'whs policy', 'health and safety policy', 'safety policy'],
        'negative_keywords': ['no whs policy', 'without whs policy', 'not have a whs policy'],
        'confidence_level': 'High',
        'explanation': 'The file appears to confirm whether a work health and safety policy is in place.',
    },
    {
        'field_key': 'esg_policy_in_place',
        'kind': 'boolean',
        'keywords': ['esg policy', 'sustainability policy', 'environmental social governance policy'],
        'negative_keywords': ['no esg policy', 'without esg policy', 'not have an esg policy'],
        'confidence_level': 'High',
        'explanation': 'The file appears to confirm whether an ESG policy is in place.',
    },
    {
        'field_key': 'cybersecurity_policy_in_place',
        'kind': 'boolean',
        'keywords': ['cybersecurity policy', 'information security policy', 'security policy', 'incident response policy'],
        'negative_keywords': ['no cybersecurity policy', 'without cybersecurity policy', 'not have a cybersecurity policy'],
        'confidence_level': 'High',
        'explanation': 'The file appears to confirm whether a cybersecurity policy is in place.',
    },
    {
        'field_key': 'anti_bribery_corruption_policy',
        'kind': 'boolean',
        'keywords': ['anti-bribery', 'anti bribery', 'anti-corruption', 'bribery and corruption policy'],
        'negative_keywords': ['no anti-bribery', 'without anti-bribery', 'not have an anti-bribery policy'],
        'confidence_level': 'High',
        'explanation': 'The file appears to confirm whether an anti-bribery / anti-corruption policy is in place.',
    },
    {
        'field_key': 'scope_1_emissions',
        'kind': 'numeric',
        'keywords': ['scope 1 emissions', 'scope 1', 'direct emissions'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain Scope 1 emissions data.',
    },
    {
        'field_key': 'scope_2_location_based',
        'kind': 'numeric',
        'keywords': ['scope 2 location based', 'scope 2', 'purchased electricity emissions'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain Scope 2 location-based emissions data.',
    },
    {
        'field_key': 'scope_3_emissions',
        'kind': 'numeric',
        'keywords': ['scope 3 emissions', 'scope 3', 'value chain emissions'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain Scope 3 emissions data.',
    },
    {
        'field_key': 'total_ghg_emissions',
        'kind': 'numeric',
        'keywords': ['total ghg emissions', 'greenhouse gas emissions', 'ghg emissions total'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain a total greenhouse gas emissions figure.',
    },
    {
        'field_key': 'total_energy_consumption',
        'kind': 'numeric',
        'keywords': ['total energy consumption', 'energy consumption', 'energy use'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain total energy consumption data.',
    },
    {
        'field_key': 'renewable_energy_consumption',
        'kind': 'numeric',
        'keywords': ['renewable energy consumption', 'renewable energy', 'clean energy'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain renewable energy consumption data.',
    },
    {
        'field_key': 'total_water_withdrawal',
        'kind': 'numeric',
        'keywords': ['total water withdrawal', 'water withdrawal', 'water use'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain total water withdrawal data.',
    },
    {
        'field_key': 'water_recycled_reused',
        'kind': 'numeric',
        'keywords': ['water recycled', 'water reused', 'recycled water'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain water recycled or reused data.',
    },
    {
        'field_key': 'total_waste_generated',
        'kind': 'numeric',
        'keywords': ['total waste generated', 'waste generated', 'waste total'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain total waste generated data.',
    },
    {
        'field_key': 'waste_diverted_from_landfill',
        'kind': 'numeric',
        'keywords': ['waste diverted from landfill', 'diverted from landfill', 'waste diversion'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain landfill diversion data.',
    },
    {
        'field_key': 'trifr',
        'kind': 'numeric',
        'keywords': ['trifr', 'total recordable injury frequency rate', 'recordable injury frequency'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain a TRIFR value.',
    },
    {
        'field_key': 'total_incidents_reported',
        'kind': 'numeric',
        'keywords': ['total incidents reported', 'incidents reported', 'incident count'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain incident reporting data.',
    },
    {
        'field_key': 'employee_turnover_rate',
        'kind': 'numeric',
        'keywords': ['employee turnover rate', 'turnover rate', 'staff turnover'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain employee turnover data.',
    },
    {
        'field_key': 'female_representation_percent',
        'kind': 'numeric',
        'keywords': ['female representation', 'women representation', 'gender diversity'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain overall female representation data.',
    },
    {
        'field_key': 'female_leadership_representation_percent',
        'kind': 'numeric',
        'keywords': ['female leadership', 'women in leadership', 'leadership representation'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain female leadership representation data.',
    },
    {
        'field_key': 'community_investment_spend',
        'kind': 'numeric',
        'keywords': ['community investment', 'community spend', 'social investment'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain community investment spend data.',
    },
    {
        'field_key': 'reduction_target_percent',
        'kind': 'numeric',
        'keywords': ['reduction target', 'target reduction', 'emissions target'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain a reduction target.',
    },
    {
        'field_key': 'reduction_target_year',
        'kind': 'numeric',
        'keywords': ['target year', 'reduction year', 'net zero year', 'carbon neutral year'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain a target year.',
    },
    {
        'field_key': 'board_level_esg_oversight',
        'kind': 'boolean',
        'keywords': ['board oversight', 'board level esg', 'esg oversight', 'board governance'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to describe board-level ESG oversight.',
    },
    {
        'field_key': 'esg_kpis_linked_to_remuneration',
        'kind': 'boolean',
        'keywords': ['kpis linked to remuneration', 'linked to remuneration', 'incentive linked', 'compensation linked'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to describe ESG KPI linkage to remuneration.',
    },
    {
        'field_key': 'cyber_incidents_in_reporting_period',
        'kind': 'numeric',
        'keywords': ['cyber incidents', 'security incidents', 'reporting period incidents'],
        'confidence_level': 'Medium',
        'explanation': 'The file appears to contain cybersecurity incident data.',
    },
]

DOCUMENT_PROFILE_RULES = [
    {
        'document_type': 'policy',
        'keywords': [
            'policy',
            'policies',
            'code of conduct',
            'governance framework',
            'compliance manual',
            'procedures manual',
            'work health and safety',
            'cybersecurity policy',
            'esg policy',
        ],
        'topics': ['policy', 'governance', 'compliance'],
    },
    {
        'document_type': 'report',
        'keywords': [
            'report',
            'sustainability report',
            'annual report',
            'esg report',
            'impact report',
            'emissions inventory',
            'ghg inventory',
            'environmental report',
            'social report',
            'emissions',
            'scope 1',
            'scope 2',
            'scope 3',
            'energy',
            'water',
            'waste',
            'trifr',
        ],
        'topics': ['report', 'emissions', 'energy', 'water', 'waste', 'social'],
    },
    {
        'document_type': 'governance',
        'keywords': [
            'board',
            'committee',
            'oversight',
            'remuneration',
            'governance',
            'minutes',
            'charter',
        ],
        'topics': ['governance', 'board'],
    },
    {
        'document_type': 'certificate',
        'keywords': [
            'certificate',
            'certification',
            'assurance',
            'attestation',
            'iso',
            'accreditation',
            'audit report',
        ],
        'topics': ['assurance', 'certificate', 'audit'],
    },
    {
        'document_type': 'incident_log',
        'keywords': [
            'incident',
            'incident log',
            'incident register',
            'security incident',
            'safety incident',
            'breach',
            'near miss',
        ],
        'topics': ['incident', 'safety', 'cybersecurity'],
    },
]


def _promote_confidence(base_confidence: str, target_confidence: str) -> str:
    confidence_order = {'Low': 0, 'Medium': 1, 'High': 2}
    base_rank = confidence_order.get(base_confidence, 1)
    target_rank = confidence_order.get(target_confidence, base_rank)
    if target_rank > base_rank:
        return target_confidence
    return base_confidence


def _detect_document_profile(file_name: str, content_text: str) -> dict:
    normalized_name = _search_normalize(file_name)
    normalized_content = _search_normalize(content_text)
    combined = f'{normalized_name} {normalized_content}'.strip()
    matched_types: List[str] = []
    matched_topics: List[str] = []
    matched_keywords: List[str] = []

    for family in DOCUMENT_PROFILE_RULES:
        matched_keyword = next(
            (
                keyword
                for keyword in family['keywords']
                if _search_normalize(keyword) in combined
            ),
            None,
        )
        if not matched_keyword:
            continue
        matched_types.append(family['document_type'])
        matched_topics.extend(family['topics'])
        matched_keywords.append(matched_keyword)

    suffix = Path(file_name or '').suffix.lower()
    if suffix in {'.csv', '.tsv', '.xlsx', '.xlsm'}:
        matched_types.append('spreadsheet')
        matched_topics.append('tabular data')

    unique_types = list(dict.fromkeys(matched_types)) or ['document']
    unique_topics = list(dict.fromkeys(topic for topic in matched_topics if topic))
    if len(unique_types) == 1:
        document_type = unique_types[0]
    elif unique_types == ['spreadsheet']:
        document_type = 'spreadsheet'
    else:
        document_type = 'mixed'

    if not unique_topics:
        if document_type == 'spreadsheet':
            unique_topics = ['tabular data']
        elif document_type == 'document':
            unique_topics = ['general']

    return {
        'document_type': document_type,
        'document_types': unique_types,
        'document_topics': unique_topics,
        'matched_keywords': matched_keywords,
    }


def _rule_document_types(rule: dict) -> set[str]:
    field_key = rule.get('field_key', '')
    kind = rule.get('kind')
    if field_key in {'board_level_esg_oversight', 'esg_kpis_linked_to_remuneration'}:
        return {'governance', 'report', 'mixed'}
    if field_key.endswith('_policy_document_reference') or field_key.endswith('_policy_in_place'):
        return {'policy', 'certificate', 'mixed'}
    if 'anti_bribery' in field_key:
        return {'policy', 'report', 'mixed'}
    if field_key in {
        'scope_1_emissions',
        'scope_2_location_based',
        'scope_3_emissions',
        'total_ghg_emissions',
        'total_energy_consumption',
        'renewable_energy_consumption',
        'total_water_withdrawal',
        'water_recycled_reused',
        'total_waste_generated',
        'waste_diverted_from_landfill',
        'trifr',
        'total_incidents_reported',
        'employee_turnover_rate',
        'female_representation_percent',
        'female_leadership_representation_percent',
        'community_investment_spend',
        'reduction_target_percent',
        'reduction_target_year',
        'cyber_incidents_in_reporting_period',
    }:
        return {'report', 'spreadsheet', 'mixed'}
    if kind == 'numeric':
        return {'report', 'spreadsheet', 'mixed'}
    if kind == 'boolean':
        return {'policy', 'report', 'mixed'}
    return {'document', 'mixed'}


def _format_document_type_label(document_type: str) -> str:
    if not document_type:
        return 'Document'
    return document_type.replace('_', ' ').title()


def _build_extraction_summary(profile: dict, suggestions: List[dict]) -> str:
    suggestion_count = len(suggestions)
    document_label = _format_document_type_label(profile.get('document_type', 'document'))
    topics = profile.get('document_topics') or []
    if suggestion_count:
        topic_fragment = f" covering {', '.join(topics[:4])}" if topics else ''
        plural = 'suggestion' if suggestion_count == 1 else 'suggestions'
        return f"Detected {document_label.lower()} with {suggestion_count} extraction {plural}{topic_fragment}."
    if topics:
        return f"Detected {document_label.lower()} covering {', '.join(topics[:4])}."
    return f"Detected {document_label.lower()} with no extraction suggestions."


def _extract_plain_text(content: bytes) -> str:
    for encoding in ('utf-8', 'utf-16', 'cp1252', 'latin-1'):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if text.strip():
            return text
    return content.decode('utf-8', errors='ignore')


def _extract_xml_text(xml_bytes: bytes) -> str:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ''
    return ' '.join(part.strip() for part in root.itertext() if part and part.strip())


def _extract_zip_xml_text(content: bytes, prefixes: List[str]) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            parts: List[str] = []
            for name in archive.namelist():
                if not any(name.startswith(prefix) for prefix in prefixes):
                    continue
                if not name.endswith('.xml'):
                    continue
                try:
                    xml_text = _extract_xml_text(archive.read(name))
                except KeyError:
                    continue
                if xml_text:
                    parts.append(xml_text)
            return '\n'.join(parts).strip()
    except (zipfile.BadZipFile, OSError, ValueError):
        return ''


def _extract_pdf_text(content: bytes) -> str:
    text = _extract_plain_text(content)
    matches: List[str] = []
    for match in re.finditer(r'\(((?:\\.|[^()]){1,5000})\)\s*T[Jj]', text, flags=re.S):
        segment = match.group(1)
        segment = segment.replace(r'\\', '\\').replace(r'\(', '(').replace(r'\)', ')')
        cleaned = segment.strip()
        if cleaned:
            matches.append(cleaned)
    if matches:
        return '\n'.join(matches).strip()
    return text


def _extract_document_text(file_name: str, content: bytes, content_type: str | None) -> str:
    lower_name = (file_name or '').lower()
    lower_type = (content_type or '').lower()
    suffix = Path(lower_name).suffix

    if suffix == '.pdf' or lower_type == 'application/pdf':
        return _extract_pdf_text(content)

    if suffix in {'.docx'} or 'wordprocessingml.document' in lower_type:
        text = _extract_zip_xml_text(content, ['word/'])
        if text:
            return text

    if suffix in {'.xlsx', '.xlsm'} or 'spreadsheetml.sheet' in lower_type:
        text = _extract_zip_xml_text(content, ['xl/'])
        if text:
            return text

    if suffix in {'.csv', '.tsv', '.json', '.xml', '.txt', '.md', '.log', '.html', '.htm'} or lower_type.startswith('text/') or 'json' in lower_type or 'xml' in lower_type:
        return _extract_plain_text(content)

    if zipfile.is_zipfile(io.BytesIO(content)):
        text = _extract_zip_xml_text(content, ['word/', 'xl/'])
        if text:
            return text

    return _extract_plain_text(content)


def _extract_document_reference(file_name: str, content_text: str, keywords: Optional[List[str]] = None) -> str:
    normalized_file_name = _search_normalize(file_name)
    reference_patterns = [
        r'\b(?:POL|WHS|ESG|CYBER)[-_][A-Z0-9]+(?:[-_/][A-Z0-9]+)*\b',
        r'\b[A-Z]{2,}(?:[-_/][A-Z0-9]+){1,}\b',
        r'\b[A-Z]{2,}\d{2,}(?:[-_/][A-Z0-9]+)*\b',
    ]

    search_terms = sorted(
        {_search_normalize(keyword) for keyword in (keywords or []) if _search_normalize(keyword)},
        key=len,
        reverse=True,
    )
    if content_text and search_terms:
        lowered_content = str(content_text or '').lower()
        for keyword in search_terms:
            index = lowered_content.find(keyword)
            if index < 0:
                continue
            forward_window_end = min(len(content_text), index + len(keyword) + 160)
            source_excerpt = content_text[index:forward_window_end]
            for pattern in reference_patterns:
                match = re.search(pattern, source_excerpt or '')
                if match:
                    return match.group(0)
            window_start = max(0, index - 24)
            source_excerpt = content_text[window_start:forward_window_end]
            for pattern in reference_patterns:
                match = re.search(pattern, source_excerpt or '')
                if match:
                    return match.group(0)

    for source in (content_text, file_name):
        for pattern in reference_patterns:
            match = re.search(pattern, source or '')
            if match:
                return match.group(0)

    if normalized_file_name:
        return Path(file_name or 'document').stem.replace('_', ' ').replace('-', ' ').strip() or 'document'
    return 'document'


def _extract_excerpt(content_text: str, keyword: str) -> str | None:
    normalized_content = _search_normalize(content_text)
    normalized_keyword = _search_normalize(keyword)
    if not normalized_content or not normalized_keyword:
        return None
    index = normalized_content.find(normalized_keyword)
    if index < 0:
        return None
    start = max(0, index - 80)
    end = min(len(normalized_content), index + len(normalized_keyword) + 160)
    excerpt = normalized_content[start:end].strip()
    return excerpt or None


def _extract_numeric_value(content_text: str, keywords: List[str]) -> tuple[str | None, str | None]:
    normalized_content = _search_normalize(content_text)
    for keyword in keywords:
        normalized_keyword = _search_normalize(keyword)
        if not normalized_keyword:
            continue
        direct_patterns = [
            rf'{re.escape(normalized_keyword)}[^0-9]{{0,80}}(?P<value>\d[\d,]*(?:\.\d+)?)',
            rf'(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?:%|percent|pct|tco2e|tco2e\.)?[^a-z0-9]{{0,60}}{re.escape(normalized_keyword)}',
        ]
        for pattern in direct_patterns:
            match = re.search(pattern, normalized_content, flags=re.I | re.S)
            if match:
                value = match.group('value').replace(',', '')
                return value, _extract_excerpt(content_text, keyword) or keyword
    return None, None


def _extract_boolean_value(content_text: str, positive_keywords: List[str], negative_keywords: List[str] | None = None) -> tuple[str | None, str | None]:
    normalized_content = _search_normalize(content_text)
    for keyword in positive_keywords:
        normalized_keyword = _search_normalize(keyword)
        if normalized_keyword and normalized_keyword in normalized_content:
            return 'Yes', _extract_excerpt(content_text, keyword) or keyword
    for keyword in negative_keywords or []:
        normalized_keyword = _search_normalize(keyword)
        if normalized_keyword and normalized_keyword in normalized_content:
            return 'No', _extract_excerpt(content_text, keyword) or keyword
    return None, None


def _detect_document_suggestions(file_name: str, content_text: str) -> List[dict]:
    normalized_name = _search_normalize(file_name)
    normalized_content = _search_normalize(content_text)
    combined = f'{normalized_name} {normalized_content}'.strip()
    document_profile = _detect_document_profile(file_name, content_text)
    suggestions: List[dict] = []
    seen_fields: set[str] = set()

    for rule in DOCUMENT_EXTRACTION_RULES:
        if rule['field_key'] in seen_fields:
            continue

        matched_keyword = next(
            (
                keyword
                for keyword in rule['keywords']
                if _search_normalize(keyword) in combined
            ),
            None,
        )
        if not matched_keyword:
            continue

        confidence = rule['confidence_level']
        if _search_normalize(matched_keyword) in normalized_name and _search_normalize(matched_keyword) in normalized_content:
            confidence = 'High'
        elif normalized_content and normalized_name:
            confidence = 'Medium'
        elif normalized_content or normalized_name:
            confidence = 'Low'

        rule_document_types = _rule_document_types(rule)
        profile_document_types = set(document_profile.get('document_types', []))
        matched_document_types = profile_document_types.intersection(rule_document_types)
        if matched_document_types:
            confidence = _promote_confidence(confidence, 'High')
        elif document_profile.get('document_type') == 'mixed' and rule_document_types.intersection({'policy', 'report', 'governance', 'certificate', 'incident_log'}):
            confidence = _promote_confidence(confidence, 'Medium')

        suggested_value = None
        source_excerpt = _extract_excerpt(content_text, matched_keyword) or file_name

        if rule['kind'] == 'reference':
            suggested_value = _extract_document_reference(file_name, content_text, rule.get('keywords'))
        elif rule['kind'] == 'numeric':
            suggested_value, numeric_excerpt = _extract_numeric_value(content_text, rule['keywords'])
            if numeric_excerpt:
                source_excerpt = numeric_excerpt
        elif rule['kind'] == 'boolean':
            suggested_value, boolean_excerpt = _extract_boolean_value(content_text, rule['keywords'], rule.get('negative_keywords'))
            if boolean_excerpt:
                source_excerpt = boolean_excerpt

        if suggested_value is None:
            continue

        seen_fields.add(rule['field_key'])
        suggestions.append(
            {
                'field_key': rule['field_key'],
                'suggested_value': suggested_value,
                'confidence_level': confidence,
                'explanation': rule['explanation'],
                'source_excerpt': source_excerpt,
                'needs_confirmation': True,
                'document_type': document_profile.get('document_type', 'document'),
                'document_topics': document_profile.get('document_topics', []),
            }
        )

    return suggestions


@app.post('/company/{company_id}/upload-evidence', response_model=SupportingDocumentUploadResponse, dependencies=[Depends(require_company_or_manager)])
def upload_evidence(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    user_email: str | None = Depends(get_user_email),
):
    enforce_company_scope_for_path(db, role=role, user_email=user_email, company_id=company_id)
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    latest_submission = company.submissions[-1] if company.submissions else None
    if not latest_submission:
        raise HTTPException(status_code=404, detail='No submission available for this company')

    content = file.file.read()
    file_name = Path(file.filename or 'evidence').name
    safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', file_name) or 'evidence'
    document_dir = EXPORT_DIR / 'supporting-documents' / f'company_{company_id}'
    document_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f'{datetime.utcnow().strftime("%Y%m%dT%H%M%S")}_{safe_name}'
    file_path = document_dir / stored_name
    file_path.write_bytes(content)

    document = SupportingDocument(
        submission_id=latest_submission.id,
        company_id=company_id,
        field_key='supporting_document',
        file_name=file_name,
        file_size=len(content),
        file_type=file.content_type or 'application/octet-stream',
        file_path=str(file_path),
        uploaded_by_email=user_email,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    content_text = _extract_document_text(file_name, content, file.content_type)

    document_profile = _detect_document_profile(file_name, content_text)
    suggestions = _detect_document_suggestions(file_name, content_text)
    return SupportingDocumentUploadResponse(
        message='Evidence uploaded successfully',
        document=SupportingDocumentResponse(
            id=document.id,
            field_key=document.field_key,
            file_name=document.file_name,
            file_size=document.file_size,
            file_type=document.file_type,
            uploaded_at=document.uploaded_at.isoformat(),
            uploaded_by_email=document.uploaded_by_email,
        ),
        document_type=document_profile.get('document_type', 'document'),
        document_topics=document_profile.get('document_topics', []),
        matched_keywords=document_profile.get('matched_keywords', []),
        extraction_summary=_build_extraction_summary(document_profile, suggestions),
        suggestion_count=len(suggestions),
        extraction_suggestions=[
            DocumentExtractionSuggestion(**suggestion)
            for suggestion in suggestions
        ],
    )

@app.post('/submissions/{submission_id}/review', dependencies=[Depends(require_manager)])
def review_submission(
    submission_id: int,
    payload: ReviewSubmissionRequest,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    next_status = normalize_submission_status(payload.review_status)
    if next_status not in ALLOWED_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail='Invalid review status')

    enforce_transition(submission.status, next_status)
    submission.status = next_status
    reporting_year = submission.cycle.cycle_year if submission.cycle else datetime.utcnow().year
    review_action = ReviewAction(
        company_id=submission.company_id,
        reporting_year=reporting_year,
        review_status=next_status,
        reviewer_role=payload.reviewer_role or 'manager',
        review_comment=payload.review_comment,
    )
    db.add(review_action)
    company = db.query(Company).filter(Company.id == submission.company_id).first()
    _queue_activity_event(
        db,
        event_type='submission_review_logged',
        title='Review recorded',
        message=f'{company.name if company else "A company"} review is now {next_status.title()}.',
        severity='success' if next_status == 'approved' else 'info',
        actor_role=payload.reviewer_role or 'manager',
        actor_email=user_email,
        company=company,
        submission=submission,
        cycle=submission.cycle,
        entity_status=next_status,
        is_toast=True,
        visible_to_investors=next_status == 'approved',
        metadata={'review_comment': payload.review_comment or '', 'status': next_status},
    )
    db.commit()
    db.refresh(submission)
    return {"message": "Review logged successfully", "status": submission.status}

@app.post('/submissions/{submission_id}/validate', dependencies=[Depends(require_manager)])
def validate_submission(submission_id: int, db: Session = Depends(get_db)):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')
    
    data = parse_json_or_default(submission.esg_data, {})
    if not isinstance(data, dict):
        data = {}
    flags_created = 0
    reporting_year = submission.cycle.cycle_year if submission.cycle else datetime.utcnow().year

    def _numeric_value(field_name: str) -> Optional[float]:
        if field_name not in data:
            return None
        return _as_float(data.get(field_name))
    
    # Define required fields for validation
    required_fields = [
        'scope_1_emissions', 'scope_2_location_based', 'scope_3_emissions',
        'total_ghg_emissions', 'total_energy_consumption', 'renewable_energy_consumption',
        'total_water_withdrawal', 'total_waste_generated', 'total_employees_fte',
        'employee_turnover_rate', 'female_representation_percent'
    ]
    
    # Check for missing required fields
    for field in required_fields:
        if field not in data or data[field] is None:
            db.add(ValidationFlag(
                company_id=submission.company_id, reporting_year=reporting_year,
                flag_type='Missing Data', field_name=field,
                issue_description=f'Required field "{field}" is missing or null.',
                severity='High'
            ))
            flags_created += 1
    
    # Data quality checks - only if fields exist
    if all(field in data and data[field] is not None for field in ['scope_1_emissions', 'scope_2_location_based', 'scope_2_market_based', 'scope_3_emissions', 'total_ghg_emissions']):
        scope_1 = _numeric_value('scope_1_emissions')
        scope_2_loc = _numeric_value('scope_2_location_based')
        scope_2_mkt = _numeric_value('scope_2_market_based')
        scope_3 = _numeric_value('scope_3_emissions')
        total_ghg = _numeric_value('total_ghg_emissions')

        if None in {scope_1, scope_2_loc, scope_2_mkt, scope_3, total_ghg}:
            db.add(ValidationFlag(
                company_id=submission.company_id, reporting_year=reporting_year,
                flag_type='Data Quality', field_name='emissions',
                issue_description='Emission fields contain non-numeric values and could not be validated.',
                severity='High'
            ))
            flags_created += 1
        else:
            # Check for negative emissions
            if scope_1 < 0 or scope_2_loc < 0 or scope_3 < 0:
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name='emissions',
                    issue_description='Negative emissions detected. Scopes 1, 2, and 3 should be non-negative.',
                    severity='High'
                ))
                flags_created += 1
        
            # Check GHG total consistency (allow 5% tolerance for rounding)
            calculated_total = scope_1 + scope_2_loc + scope_3
            if calculated_total > 0 and abs(total_ghg - calculated_total) / calculated_total > 0.05:
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name='total_ghg_emissions',
                    issue_description=f'Total GHG emissions ({total_ghg}) does not match sum of scopes ({calculated_total:.1f}). Variance: {abs(total_ghg - calculated_total) / calculated_total:.1%}',
                    severity='Medium'
                ))
                flags_created += 1
    
    # Check energy consumption consistency
    if 'total_energy_consumption' in data and 'renewable_energy_consumption' in data:
        total_energy = _numeric_value('total_energy_consumption')
        renewable_energy = _numeric_value('renewable_energy_consumption')
        if total_energy is not None and renewable_energy is not None:
            if renewable_energy > total_energy:
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name='renewable_energy_consumption',
                    issue_description='Renewable energy consumption exceeds total energy consumption.',
                    severity='High'
                ))
                flags_created += 1
    
    # Check water recycling consistency
    if 'total_water_withdrawal' in data and 'water_recycled_reused' in data:
        total_water = _numeric_value('total_water_withdrawal')
        recycled_water = _numeric_value('water_recycled_reused')
        if total_water is not None and recycled_water is not None:
            if recycled_water > total_water:
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name='water_recycled_reused',
                    issue_description='Water recycled/reused exceeds total water withdrawal.',
                    severity='High'
                ))
                flags_created += 1
    
    # Check waste diversion consistency
    if 'total_waste_generated' in data and 'waste_diverted_from_landfill' in data:
        total_waste = _numeric_value('total_waste_generated')
        diverted_waste = _numeric_value('waste_diverted_from_landfill')
        if total_waste is not None and diverted_waste is not None:
            if diverted_waste > total_waste:
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name='waste_diverted_from_landfill',
                    issue_description='Waste diverted from landfill exceeds total waste generated.',
                    severity='High'
                ))
                flags_created += 1
    
    # Check percentage fields are in valid range (0-100)
    percentage_fields = [
        'employee_turnover_rate', 'female_representation_percent',
        'female_leadership_representation_percent', 'independent_board_members_percent',
        'female_board_members_percent'
    ]
    for field in percentage_fields:
        if field in data and data[field] is not None:
            value = _numeric_value(field)
            if value is None:
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name=field,
                    issue_description=f'Percentage field "{field}" contains a non-numeric value.',
                    severity='High'
                ))
                flags_created += 1
            elif value < 0 or value > 100:
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name=field,
                    issue_description=f'Percentage field "{field}" must be between 0-100. Current value: {value}',
                    severity='High'
                ))
                flags_created += 1
    
    # Check female leadership vs overall female representation (proportionality)
    if 'female_representation_percent' in data and 'female_leadership_representation_percent' in data:
        female_overall = _numeric_value('female_representation_percent')
        female_leadership = _numeric_value('female_leadership_representation_percent')
        if female_overall is not None and female_leadership is not None:
            if female_leadership > female_overall + 5:  # Allow 5% tolerance
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name='female_leadership_representation_percent',
                    issue_description=f'Female leadership representation ({female_leadership}%) exceeds overall female representation ({female_overall}%) by more than 5%.',
                    severity='Medium'
                ))
                flags_created += 1
    
    # Year-over-year variance check
    prev_submission = db.query(Submission).filter(
        Submission.company_id == submission.company_id,
        Submission.id != submission.id
    ).order_by(Submission.id.desc()).first()
    
    if prev_submission:
        prev_data = parse_json_or_default(prev_submission.esg_data, {})
        if not isinstance(prev_data, dict):
            prev_data = {}
        for field in ['total_ghg_emissions', 'total_energy_consumption', 'total_water_withdrawal']:
            curr_val, prev_val = _as_float(data.get(field)), _as_float(prev_data.get(field))
            if curr_val is not None and prev_val is not None and prev_val > 0:
                variance = (curr_val - prev_val) / prev_val
                if abs(variance) > 0.30:
                    db.add(ValidationFlag(
                        company_id=submission.company_id, reporting_year=reporting_year,
                        flag_type='Variance Alert', field_name=field,
                        issue_description=f'YoY variance for {field} is {variance:.1%}, exceeding +/-30% threshold.',
                        severity='High'
                    ))
                    flags_created += 1

    db.commit()
    return {"message": f"Validation complete. {flags_created} anomalies flagged.", "flagged": flags_created > 0}


@app.get(
    '/submissions/{submission_id}/validation-errors',
    response_model=List[ValidationErrorResponse],
    dependencies=[Depends(require_manager)],
)
def get_submission_validation_errors(
    submission_id: int,
    include_resolved: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    query = db.query(ValidationError).filter(ValidationError.submission_id == submission_id)
    if not include_resolved:
        query = query.filter(ValidationError.resolved == False)

    rows = query.order_by(ValidationError.created_at.desc(), ValidationError.id.desc()).all()
    return [
        ValidationErrorResponse(
            id=row.id,
            section=row.section,
            field_key=row.field_key,
            field_label=row.field_label,
            error_type=row.error_type,
            error_message=row.error_message,
            severity=row.severity,
            resolved=row.resolved,
        )
        for row in rows
    ]


@app.post(
    '/submissions/{submission_id}/validation-errors/decision',
    response_model=MetricReviewDecisionResponse,
    dependencies=[Depends(require_manager)],
)
def apply_metric_review_decision(
    submission_id: int,
    payload: MetricReviewDecisionRequest,
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    field_key = _canonicalize_field_key(str(payload.field_key or '').strip())
    if not field_key:
        raise HTTPException(status_code=400, detail='field_key is required')

    comment = str(payload.comment or '').strip()
    meta = FIELD_META_BY_KEY.get(field_key, {})
    section = str(meta.get('section') or 'General')
    field_label = str(meta.get('field_label') or field_key.replace('_', ' ').title())

    unresolved = db.query(ValidationError).filter(
        ValidationError.submission_id == submission.id,
        ValidationError.field_key == field_key,
        ValidationError.resolved == False,
    ).all()

    if payload.decision == 'pass':
        updated = 0
        for issue in unresolved:
            issue.resolved = True
            updated += 1
        db.commit()
        return MetricReviewDecisionResponse(
            submission_id=submission.id,
            field_key=field_key,
            decision='pass',
            updated_errors=updated,
            message='Field marked as pass. Outstanding validation issues resolved for this metric.',
        )

    reviewer_flag = db.query(ValidationError).filter(
        ValidationError.submission_id == submission.id,
        ValidationError.field_key == field_key,
        ValidationError.error_type == 'reviewer_decision',
    ).order_by(ValidationError.id.desc()).first()

    fail_message = comment or 'Marked as fail by reviewer.'
    if reviewer_flag:
        reviewer_flag.section = section
        reviewer_flag.field_label = field_label
        reviewer_flag.error_message = fail_message
        reviewer_flag.severity = 'error'
        reviewer_flag.resolved = False
    else:
        db.add(
            ValidationError(
                submission_id=submission.id,
                company_id=submission.company_id,
                section=section,
                field_key=field_key,
                field_label=field_label,
                error_type='reviewer_decision',
                error_message=fail_message,
                severity='error',
                resolved=False,
            )
        )
    db.commit()

    return MetricReviewDecisionResponse(
        submission_id=submission.id,
        field_key=field_key,
        decision='fail',
        updated_errors=1,
        message='Field marked as fail for reviewer follow-up.',
    )


def parse_date_string(date_string: str | None):
    if not date_string:
        return None
    try:
        return datetime.strptime(date_string, '%Y-%m-%d').date()
    except ValueError:
        return None


def get_days_to_deadline(deadline: str | None):
    parsed = parse_date_string(deadline)
    if not parsed:
        return None
    return (parsed - datetime.now().date()).days


def normalize_manager_bucket(status: str | None) -> str:
    normalized = normalize_submission_status(status)
    mapping = {
        'not started': 'Not Started',
        'in progress': 'In Progress',
        'submitted': 'Submitted',
        'pending review': 'Under Review',
        'under review': 'Under Review',
        'approved': 'Approved',
        'rejected': 'Resubmission Requested',
        'resubmission requested': 'Resubmission Requested',
        'pre-acquisition': 'Not Started',
        'active': 'In Progress',
    }
    return mapping.get(normalized, 'Not Started')


def build_manager_summary(db: Session, companies: List[Company]) -> dict:
    cache_key = 'build_manager_summary'
    cached = _get_timed_cache(cache_key)
    if cached is not None:
        return cached

    cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)
    cycle_deadline = cycle.submission_deadline if cycle else None
    cycle_days_remaining = get_days_to_deadline(cycle_deadline)
    status_breakdown = {
        'Not Started': 0,
        'In Progress': 0,
        'Submitted': 0,
        'Under Review': 0,
        'Approved': 0,
        'Resubmission Requested': 0,
    }
    upcoming_deadlines = []
    progress_rows = []
    reporting_field_keys = list(FIELD_META_BY_KEY.keys())

    for company in companies:
        submissions = company.submissions or []
        cycle_submissions = [item for item in submissions if cycle and item.cycle_id == cycle.id]
        latest_submission = (cycle_submissions or submissions)[-1] if (cycle_submissions or submissions) else None
        status_source = latest_submission.status if latest_submission else company.current_status
        bucket = normalize_manager_bucket(status_source)
        status_breakdown[bucket] += 1
        latest_payload = parse_submission(latest_submission) if latest_submission else {}
        completed_fields = sum(
            1
            for field_key in reporting_field_keys
            if latest_payload.get(field_key) is not None and str(latest_payload.get(field_key)).strip() != ''
        )
        completion = round((completed_fields / max(len(reporting_field_keys), 1)) * 100)
        esg_score = round(score_company_payload(latest_payload)[0], 2) if latest_payload else None
        days_remaining = cycle_days_remaining

        progress_rows.append({
            'company_id': company.id,
            'company_name': company.name,
            'asset_class': company.asset_class,
            'sector': company.sector,
            'status': bucket,
            'completion_percent': completion,
            'esg_score': esg_score,
            'risk_level': getattr(company, 'reporting_risk_level', None),
            'last_activity': f'Submission #{latest_submission.id}' if latest_submission else 'No submission yet',
            'deadline': cycle_deadline,
            'actions': ['Validate', 'Approve', 'Request Resubmission', 'Reject', 'Unlock', 'Send Reminder'],
        })

        if days_remaining is not None and 0 <= days_remaining <= 7 and bucket not in {'Submitted', 'Under Review', 'Approved'}:
            upcoming_deadlines.append({
                'company_id': company.id,
                'submission_id': latest_submission.id if latest_submission else None,
                'company_name': company.name,
                'asset_class': company.asset_class,
                'sector': company.sector,
                'status': bucket,
                'completion_percent': completion,
                'esg_score': esg_score,
                'risk_level': getattr(company, 'reporting_risk_level', None),
                'deadline': cycle_deadline,
                'days_remaining': days_remaining,
            })

    upcoming_deadlines.sort(key=lambda row: row['days_remaining'] if row['days_remaining'] is not None else 99999)
    result = {
        'status_breakdown': status_breakdown,
        'cycle_banner': {
            'active_cycle_year': cycle.cycle_year if cycle else None,
            'submission_open_date': cycle.submission_open_date if cycle else None,
            'submission_deadline': cycle_deadline,
            'days_remaining': cycle_days_remaining,
            'cycle_status': normalize_cycle_status(cycle.status) if cycle else 'closed',
        },
        'upcoming_deadlines': upcoming_deadlines,
        'progress_rows': progress_rows,
    }
    return _set_timed_cache(cache_key, result)


def slugify(value: str) -> str:
    sanitized = re.sub(r'[^a-zA-Z0-9]+', '_', str(value or '').strip()).strip('_')
    return sanitized.lower() or 'all'


def build_report_rows(db: Session, portfolio: str, period: str):
    normalized_period, period_year = _normalize_reporting_period(period)
    selected_cycle = (
        _apply_valid_cycle_year_filter(db.query(CollectionCycle))
        .filter(CollectionCycle.cycle_year == period_year)
        .order_by(CollectionCycle.id.desc())
        .first()
    )
    if not selected_cycle:
        selected_cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)
    companies_query = _query_ui_visible_companies(db).options(selectinload(Company.submissions))
    normalized_portfolio = (portfolio or 'all').strip()
    if normalized_portfolio and normalized_portfolio.lower() not in {'all', 'all portfolio companies'}:
        companies_query = companies_query.filter(Company.name == normalized_portfolio)
    companies = companies_query.order_by(Company.name.asc()).all()
    reporting_field_keys = list(FIELD_META_BY_KEY.keys())

    rows = []
    for company in companies:
        cycle_submissions = [item for item in company.submissions if item.cycle_id == selected_cycle.id]
        latest_submission = (cycle_submissions or company.submissions)[-1] if (cycle_submissions or company.submissions) else None
        bucket = normalize_manager_bucket(latest_submission.status if latest_submission else company.current_status)
        payload = parse_submission(latest_submission)
        completed_fields = sum(
            1
            for field_key in reporting_field_keys
            if payload.get(field_key) is not None and str(payload.get(field_key)).strip() != ''
        )
        completion_percent = round((completed_fields / max(len(reporting_field_keys), 1)) * 100)
        esg_score = round(score_company_payload(payload)[0], 2) if payload else None
        rows.append({
            'company_name': company.name,
            'asset_class': company.asset_class or '',
            'sector': company.sector,
            'status': bucket,
            'completion_percent': completion_percent,
            'total_ghg_emissions': round(safe_number(payload.get('total_ghg_emissions')), 2),
            'female_representation_percent': round(safe_number(payload.get('female_representation_percent')), 2),
            'esg_score': esg_score,
            'period': normalized_period,
            'cycle_year': selected_cycle.cycle_year,
        })
    return rows, selected_cycle, normalized_period


def build_csv_export_bytes(rows: List[dict]) -> bytes:
    headers = [
        'company_name',
        'asset_class',
        'sector',
        'status',
        'completion_percent',
        'total_ghg_emissions',
        'female_representation_percent',
        'esg_score',
        'period',
        'cycle_year',
    ]
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode('utf-8')


def escape_pdf_text(text_value: str) -> str:
    return str(text_value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def wrap_pdf_lines(lines: List[str], max_length: int = 92) -> List[str]:
    wrapped_lines: List[str] = []
    for raw_line in lines or []:
        text = str(raw_line or '').strip()
        if not text:
            wrapped_lines.append('')
            continue
        if len(text) <= max_length:
            wrapped_lines.append(text)
            continue

        current = ''
        for word in text.split():
            candidate = word if not current else f'{current} {word}'
            if len(candidate) <= max_length:
                current = candidate
            else:
                if current:
                    wrapped_lines.append(current)
                current = word
        if current:
            wrapped_lines.append(current)
    return wrapped_lines or ['No data']


PDF_PAGE_WIDTH = 612
PDF_PAGE_HEIGHT = 792
PDF_MARGIN_X = 44
PDF_HEADER_HEIGHT = 52
PDF_CONTENT_TOP = 708
PDF_CONTENT_BOTTOM = 52
PDF_CONTENT_WIDTH = PDF_PAGE_WIDTH - (PDF_MARGIN_X * 2)


def _truncate_pdf_text(text: str, max_chars: int) -> str:
    clean = str(text or '').strip()
    if len(clean) <= max_chars:
        return clean
    if max_chars <= 3:
        return clean[:max_chars]
    return clean[: max_chars - 3].rstrip() + '...'


def _pdf_escape_text(text_value: str) -> str:
    return escape_pdf_text(text_value)


def _format_pdf_metric(value: Any, *, decimals: int = 1, prefix: str = '', suffix: str = '') -> str:
    if value is None or value == '':
        return 'N/A'
    try:
        number = float(value)
    except (TypeError, ValueError):
        return f'{prefix}{value}{suffix}'
    if abs(number - round(number)) < 1e-9:
        formatted = f'{int(round(number)):,}'
    else:
        formatted = f'{number:,.{decimals}f}'
    return f'{prefix}{formatted}{suffix}'


def _pdf_row_value(row: dict, extractor) -> str:
    if callable(extractor):
        value = extractor(row)
    else:
        value = row.get(extractor)
    if value is None or value == '':
        return 'N/A'
    return str(value)


class _PdfReportBuilder:
    def __init__(self, title: str, subtitle: str, generated_at: str):
        self.title = str(title or '').strip() or 'ESG Report Export'
        self.subtitle = str(subtitle or '').strip()
        self.generated_at = str(generated_at or '').strip()
        self.pages: List[dict] = []
        self._new_page()

    def _new_page(self):
        self.pages.append(
            {
                'commands': [],
                'cursor_y': PDF_CONTENT_TOP,
            }
        )
        self._draw_page_banner()

    def _page(self) -> dict:
        return self.pages[-1]

    def _append(self, command: str):
        self._page()['commands'].append(command)

    def _draw_page_banner(self):
        self._append('q')
        self._append('0.10 0.18 0.34 rg')
        self._append(f'0 {PDF_PAGE_HEIGHT - 52} {PDF_PAGE_WIDTH} 52 re f')
        self._append('0.18 0.52 0.86 rg')
        self._append(f'0 {PDF_PAGE_HEIGHT - 58} {PDF_PAGE_WIDTH} 6 re f')
        self._append('BT')
        self._append('/F2 18 Tf')
        self._append('1 1 1 rg')
        self._append(f'{PDF_MARGIN_X} {PDF_PAGE_HEIGHT - 28} Td')
        self._append(f'({_pdf_escape_text(self.title)}) Tj')
        self._append('ET')
        if self.subtitle:
            self._append('BT')
            self._append('/F1 9 Tf')
            self._append('0.90 0.95 1 rg')
            self._append(f'{PDF_MARGIN_X} {PDF_PAGE_HEIGHT - 42} Td')
            self._append(f'({_pdf_escape_text(self.subtitle)}) Tj')
            self._append('ET')
        if self.generated_at:
            self._append('BT')
            self._append('/F1 8 Tf')
            self._append('0.92 0.95 1 rg')
            self._append(f'{PDF_PAGE_WIDTH - 168} {PDF_PAGE_HEIGHT - 28} Td')
            self._append(f'({_pdf_escape_text(self.generated_at)}) Tj')
            self._append('ET')
        self._append('Q')

    def _ensure_space(self, required_height: float):
        if self._page()['cursor_y'] - required_height < PDF_CONTENT_BOTTOM:
            self._new_page()

    def _draw_text_line(
        self,
        text: str,
        *,
        x: float | None = None,
        font: str = 'F1',
        size: int = 10,
        color: tuple[float, float, float] = (0.14, 0.16, 0.19),
        gap_after: float = 0,
        max_chars: int = 92,
        indent: float = 0,
    ):
        lines = wrap_pdf_lines([text], max_length=max_chars)
        line_height = max(size + 4, 12)
        for line in lines:
            self._ensure_space(line_height)
            current_y = self._page()['cursor_y']
            current_x = PDF_MARGIN_X + indent if x is None else x
            self._append('BT')
            self._append(f'/{font} {size} Tf')
            self._append(f'{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg')
            self._append(f'{current_x:.1f} {current_y:.1f} Td')
            self._append(f'({_pdf_escape_text(line)}) Tj')
            self._append('ET')
            self._page()['cursor_y'] -= line_height
        if gap_after:
            self._page()['cursor_y'] -= gap_after

    def _write_text_at(
        self,
        text: str,
        *,
        x: float,
        y: float,
        font: str = 'F1',
        size: int = 10,
        color: tuple[float, float, float] = (0.14, 0.16, 0.19),
        max_chars: int = 42,
    ):
        self._append('BT')
        self._append(f'/{font} {size} Tf')
        self._append(f'{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg')
        self._append(f'{x:.1f} {y:.1f} Td')
        self._append(f'({_pdf_escape_text(_truncate_pdf_text(text, max_chars))}) Tj')
        self._append('ET')

    def add_heading(self, text: str, *, level: int = 2):
        level_map = {
            1: ('F2', 16, (0.08, 0.13, 0.22), 6),
            2: ('F2', 13, (0.10, 0.18, 0.34), 5),
            3: ('F2', 11, (0.15, 0.22, 0.35), 4),
        }
        font, size, color, gap_after = level_map.get(level, level_map[2])
        self._draw_text_line(text, font=font, size=size, color=color, max_chars=88, gap_after=gap_after)
        self._append('0.82 0.86 0.92 RG')
        self._append(f'{PDF_MARGIN_X:.1f} {self._page()["cursor_y"]:.1f} m {PDF_PAGE_WIDTH - PDF_MARGIN_X:.1f} {self._page()["cursor_y"]:.1f} l S')
        self._page()['cursor_y'] -= 8

    def add_paragraph(self, text: str, *, size: int = 10, color: tuple[float, float, float] = (0.16, 0.18, 0.21), indent: float = 0):
        if not str(text or '').strip():
            self._page()['cursor_y'] -= 6
            return
        max_chars = 94 if size <= 10 else 84
        self._draw_text_line(text, font='F1', size=size, color=color, max_chars=max_chars, indent=indent, gap_after=4)

    def add_bullets(self, items: List[str], *, size: int = 10, color: tuple[float, float, float] = (0.16, 0.18, 0.21), indent: float = 12):
        bullet_items = [str(item or '').strip() for item in items if str(item or '').strip()]
        if not bullet_items:
            self.add_paragraph('No highlights were available for this section.', size=size, color=color, indent=indent)
            return
        for item in bullet_items:
            wrapped = wrap_pdf_lines([item], max_length=86)
            first = True
            for line in wrapped:
                prefix = '- ' if first else '  '
                self._draw_text_line(
                    f'{prefix}{line}',
                    size=size,
                    color=color,
                    max_chars=90,
                    indent=indent,
                    gap_after=1,
                )
                first = False
            self._page()['cursor_y'] -= 2

    def add_callout(self, label: str, value: str, note: str = '', *, accent: tuple[float, float, float] = (0.10, 0.18, 0.34)):
        self._ensure_space(56)
        x = PDF_MARGIN_X
        y = self._page()['cursor_y']
        width = PDF_CONTENT_WIDTH
        height = 50
        self._append('q')
        self._append('0.96 0.98 1 rg')
        self._append(f'{x} {y - height} {width} {height} re f')
        self._append(f'{accent[0]:.3f} {accent[1]:.3f} {accent[2]:.3f} RG')
        self._append('1.2 w')
        self._append(f'{x} {y - height} {width} {height} re S')
        self._append('Q')
        self._write_text_at(label, x=x + 12, y=y - 16, font='F1', size=8, color=(0.30, 0.36, 0.42), max_chars=54)
        self._write_text_at(value, x=x + 12, y=y - 31, font='F2', size=12, color=accent, max_chars=54)
        if note:
            self._write_text_at(note, x=x + 12, y=y - 44, font='F1', size=8, color=(0.32, 0.35, 0.40), max_chars=54)
        self._page()['cursor_y'] -= height + 8

    def add_card_grid(self, cards: List[dict], *, columns: int = 2):
        if not cards:
            return
        gap = 12
        card_width = (PDF_CONTENT_WIDTH - gap * (columns - 1)) / columns
        card_height = 74
        card_count = len(cards)
        idx = 0
        while idx < card_count:
            row_cards = cards[idx: idx + columns]
            self._ensure_space(card_height + 8)
            y = self._page()['cursor_y']
            for col_index, card in enumerate(row_cards):
                x = PDF_MARGIN_X + (card_width + gap) * col_index
                label = str(card.get('label') or '').strip()
                value = str(card.get('value') or '').strip()
                note = str(card.get('note') or '').strip()
                self._append('q')
                self._append('0.97 0.98 1 rg')
                self._append(f'{x:.1f} {y - card_height:.1f} {card_width:.1f} {card_height:.1f} re f')
                self._append('0.78 0.84 0.92 RG')
                self._append('1 w')
                self._append(f'{x:.1f} {y - card_height:.1f} {card_width:.1f} {card_height:.1f} re S')
                self._append('Q')
                self._write_text_at(label, x=x + 10, y=y - 18, font='F1', size=8, color=(0.31, 0.35, 0.42), max_chars=24)
                self._write_text_at(value, x=x + 10, y=y - 36, font='F2', size=13, color=(0.11, 0.20, 0.36), max_chars=24)
                if note:
                    self._write_text_at(note, x=x + 10, y=y - 52, font='F1', size=8, color=(0.35, 0.39, 0.44), max_chars=28)
            self._page()['cursor_y'] -= card_height + 10
            idx += columns

    def add_bar_chart(self, title: str, series: List[dict], *, note: str = '', accent: tuple[float, float, float] = (0.10, 0.18, 0.34)):
        if title:
            self.add_heading(title, level=2)
        if not series:
            self.add_paragraph('No chart data was available for this section.', size=10)
            return

        clean_series = [
            {
                'label': str(item.get('label') or '').strip(),
                'value': safe_number(item.get('value')),
                'note': str(item.get('note') or '').strip(),
            }
            for item in series
            if str(item.get('label') or '').strip()
        ]
        if not clean_series:
            self.add_paragraph('No chart data was available for this section.', size=10)
            return

        visible_series = clean_series[:5]
        chart_height = 24 + (len(visible_series) * 18) + (16 if note else 0)
        self._ensure_space(chart_height + 12)
        x = PDF_MARGIN_X
        y = self._page()['cursor_y']
        width = PDF_CONTENT_WIDTH
        self._append('q')
        self._append('0.97 0.98 1 rg')
        self._append(f'{x} {y - chart_height} {width} {chart_height} re f')
        self._append('0.78 0.84 0.92 RG')
        self._append('1 w')
        self._append(f'{x} {y - chart_height} {width} {chart_height} re S')
        self._append('Q')

        self._write_text_at(title, x=x + 10, y=y - 16, font='F2', size=11, color=accent, max_chars=60)
        if note:
            self._write_text_at(note, x=x + 10, y=y - 28, font='F1', size=8, color=(0.34, 0.38, 0.43), max_chars=88)

        max_value = max((float(item['value']) for item in visible_series), default=0.0)
        bar_left = x + 126
        bar_area_width = width - 172
        row_y = y - 42
        for item in visible_series:
            value = float(item['value'])
            label = _truncate_pdf_text(item['label'], 24)
            bar_width = (bar_area_width * (value / max_value)) if max_value > 0 else 0
            self._write_text_at(label, x=x + 10, y=row_y, font='F1', size=8, color=(0.24, 0.28, 0.34), max_chars=24)
            self._append('q')
            self._append('0.91 0.94 0.98 rg')
            self._append(f'{bar_left:.1f} {row_y - 4:.1f} {bar_area_width:.1f} 10 re f')
            self._append(f'{accent[0]:.3f} {accent[1]:.3f} {accent[2]:.3f} rg')
            self._append(f'{bar_left:.1f} {row_y - 4:.1f} {bar_width:.1f} 10 re f')
            self._append('Q')
            value_text = f"{_format_pdf_metric(value, decimals=1)}"
            self._write_text_at(value_text, x=bar_left + bar_area_width + 6, y=row_y, font='F2', size=8, color=accent, max_chars=12)
            if item['note']:
                self._write_text_at(_truncate_pdf_text(item['note'], 30), x=bar_left, y=row_y - 10, font='F1', size=7, color=(0.38, 0.42, 0.47), max_chars=30)
            row_y -= 18
        self._page()['cursor_y'] -= chart_height + 6

    def add_attachment_list(self, title: str, attachments: List[str]):
        if title:
            self.add_heading(title, level=2)
        if not attachments:
            self.add_paragraph('No supporting attachments were found for this export.', size=10)
            return
        self.add_bullets(attachments[:8], size=10)

    def add_table(self, title: str, columns: List[dict], rows: List[dict]):
        if title:
            self.add_heading(title, level=2)

        if not rows:
            self.add_paragraph('No companies were available for this portfolio snapshot.', size=10)
            return

        row_height = 18
        header_height = 20

        def draw_header():
            self._ensure_space(header_height + 6)
            y = self._page()['cursor_y']
            x = PDF_MARGIN_X
            self._append('q')
            self._append('0.89 0.93 0.98 rg')
            self._append(f'{x:.1f} {y - header_height:.1f} {PDF_CONTENT_WIDTH:.1f} {header_height:.1f} re f')
            self._append('0.72 0.79 0.88 RG')
            self._append('1 w')
            self._append(f'{x:.1f} {y - header_height:.1f} {PDF_CONTENT_WIDTH:.1f} {header_height:.1f} re S')
            self._append('Q')

            current_x = x
            for col in columns:
                width = float(col['width'])
                label = str(col['label'])
                self._write_text_at(
                    label,
                    x=current_x + 4,
                    y=y - 13,
                    font='F2',
                    size=8,
                    color=(0.14, 0.21, 0.34),
                    max_chars=max(6, int(width / 5.5)),
                )
                current_x += width
            self._page()['cursor_y'] -= header_height

        draw_header()

        for index, row in enumerate(rows):
            if self._page()['cursor_y'] - row_height < PDF_CONTENT_BOTTOM + 4:
                self._new_page()
                if title:
                    self.add_heading(f'{title} (continued)', level=3)
                draw_header()

            y = self._page()['cursor_y']
            x = PDF_MARGIN_X
            fill = '0.98 0.99 1 rg' if index % 2 == 0 else '1 1 1 rg'
            self._append('q')
            self._append(fill)
            self._append(f'{x:.1f} {y - row_height:.1f} {PDF_CONTENT_WIDTH:.1f} {row_height:.1f} re f')
            self._append('0.88 0.90 0.94 RG')
            self._append('0.8 w')
            self._append(f'{x:.1f} {y - row_height:.1f} {PDF_CONTENT_WIDTH:.1f} {row_height:.1f} re S')
            self._append('Q')

            current_x = x
            for col in columns:
                width = float(col['width'])
                extractor = col.get('value')
                raw_value = _pdf_row_value(row, extractor)
                cell_text = _truncate_pdf_text(raw_value, max(6, int(width / 5.3)))
                self._write_text_at(
                    cell_text,
                    x=current_x + 4,
                    y=y - 13,
                    font='F1',
                    size=8,
                    color=(0.15, 0.18, 0.22),
                    max_chars=max(6, int(width / 5.5)),
                )
                current_x += width
            self._page()['cursor_y'] -= row_height

    def add_footer_page_number(self, page_number: int, total_pages: int):
        footer = f'Page {page_number} of {total_pages}'
        self._append('BT')
        self._append('/F1 8 Tf')
        self._append('0.45 0.49 0.55 rg')
        self._append(f'{PDF_PAGE_WIDTH - 110} 24 Td')
        self._append(f'({_pdf_escape_text(footer)}) Tj')
        self._append('ET')

    def finalize(self) -> bytes:
        pages_count = len(self.pages)
        for index, page in enumerate(self.pages, start=1):
            page['commands'].append(
                f'BT /F1 8 Tf 0.40 0.43 0.48 rg {PDF_MARGIN_X} 24 Td ({_pdf_escape_text("Generated for internal reporting use only")}) Tj ET'
            )
            self.add_footer_page_number(index, pages_count)

        content_start = 3
        page_start = content_start + pages_count
        font1_id = page_start + pages_count
        font2_id = font1_id + 1

        objects = [
            b'1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n',
        ]

        page_obj_ids = [page_start + index for index in range(pages_count)]
        objects.append(
            ('2 0 obj << /Type /Pages /Kids [' + ' '.join(f'{page_id} 0 R' for page_id in page_obj_ids) + f'] /Count {pages_count} >> endobj\n').encode('ascii')
        )

        for index, page in enumerate(self.pages):
            content_obj_id = content_start + index
            page_obj_id = page_start + index
            stream = '\n'.join(page['commands']).encode('utf-8')
            objects.append(
                f'{content_obj_id} 0 obj << /Length {len(stream)} >> stream\n'.encode('ascii') + stream + b'\nendstream endobj\n'
            )
            objects.append(
                (
                    f'{page_obj_id} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 {PDF_PAGE_WIDTH} {PDF_PAGE_HEIGHT}] '
                    f'/Contents {content_obj_id} 0 R /Resources << /Font << /F1 {font1_id} 0 R /F2 {font2_id} 0 R >> >> >> endobj\n'
                ).encode('ascii')
            )

        objects.append(f'{font1_id} 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n'.encode('ascii'))
        objects.append(f'{font2_id} 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> endobj\n'.encode('ascii'))

        output = bytearray(b'%PDF-1.4\n')
        offsets = [0]
        for obj in objects:
            offsets.append(len(output))
            output.extend(obj)
        xref_offset = len(output)
        output.extend(f'xref\n0 {len(objects) + 1}\n'.encode('ascii'))
        output.extend(b'0000000000 65535 f \n')
        for offset in offsets[1:]:
            output.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
        output.extend((f'trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n').encode('ascii'))
        return bytes(output)


def build_simple_pdf(lines: List[str]) -> bytes:
    builder = _PdfReportBuilder(
        title='ESG Report Export',
        subtitle='Simple text export view',
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    builder.add_paragraph('\n'.join(lines or ['No data']))
    return builder.finalize()


def build_pdf_export_bytes(
    report_type: str,
    period: str,
    cycle: CollectionCycle,
    rows: List[dict],
    context_lines: Optional[List[str]] = None,
    narrative_lines: Optional[List[str]] = None,
    attachment_lines: Optional[List[str]] = None,
    impact_story: Optional[dict] = None,
    anomaly_summary: Optional[dict] = None,
    external_context_items: Optional[List[dict]] = None,
) -> bytes:
    status_counts: Dict[str, int] = {}
    for row in rows:
        status_counts[row['status']] = status_counts.get(row['status'], 0) + 1

    def _avg(values: List[Any]) -> float | None:
        numeric_values = [safe_number(value) for value in values if value is not None and str(value).strip() != '']
        numeric_values = [value for value in numeric_values if value is not None]
        if not numeric_values:
            return None
        return sum(numeric_values) / len(numeric_values)

    total_rows = len(rows)
    approved_count = status_counts.get('Approved', 0)
    in_progress_count = status_counts.get('In Progress', 0)
    submitted_count = status_counts.get('Submitted', 0)
    under_review_count = status_counts.get('Under Review', 0)
    resubmission_count = status_counts.get('Resubmission Requested', 0)
    active_count = approved_count + in_progress_count + submitted_count + under_review_count
    coverage_percent = round((active_count / total_rows) * 100, 1) if total_rows else 0.0

    avg_esg = _avg([row.get('esg_score') for row in rows])
    avg_ghg = _avg([row.get('total_ghg_emissions') for row in rows])
    avg_female = _avg([row.get('female_representation_percent') for row in rows])
    avg_completion = _avg([row.get('completion_percent') for row in rows])

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            -safe_number(row.get('esg_score')),
            str(row.get('company_name') or ''),
        ),
    )

    title = f'{report_type.upper()} Smart PDF Report'
    subtitle_bits = [f'Period: {period}', f'Cycle Year: {cycle.cycle_year}', f'Portfolio rows: {total_rows}']
    subtitle = ' | '.join(subtitle_bits)
    generated_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    builder = _PdfReportBuilder(title=title, subtitle=subtitle, generated_at=generated_at)
    impact_story = impact_story or {}
    anomaly_summary = anomaly_summary or {}
    external_context_items = [item for item in (external_context_items or []) if isinstance(item, dict)]

    builder.add_heading('Executive Summary', level=1)
    cards = [
        {'label': 'Companies in scope', 'value': f'{total_rows}', 'note': f'{coverage_percent:.1f}% active coverage'},
        {'label': 'Approved', 'value': f'{approved_count}', 'note': 'fully reviewed'},
        {'label': 'In progress', 'value': f'{in_progress_count + submitted_count + under_review_count}', 'note': f'{resubmission_count} need follow-up'},
        {'label': 'Average ESG score', 'value': _format_pdf_metric(avg_esg, decimals=1), 'note': 'portfolio average'},
        {'label': 'Average total GHG', 'value': _format_pdf_metric(avg_ghg, decimals=1, suffix=' tCO2e'), 'note': 'reported emissions'},
        {'label': 'Female representation', 'value': _format_pdf_metric(avg_female, decimals=1, suffix='%'), 'note': 'workforce average'},
    ]
    builder.add_card_grid(cards, columns=2)

    if sorted_rows:
        leader = sorted_rows[0]
        laggard = sorted_rows[-1]
        builder.add_callout(
            'Top performing company',
            f"{leader['company_name']} - ESG {_format_pdf_metric(leader.get('esg_score'), decimals=1)}",
            f"Sector: {leader.get('sector') or 'Unknown'} | Status: {leader.get('status') or 'Unknown'}",
        )
        if laggard.get('company_name') != leader.get('company_name'):
            builder.add_callout(
                'Lowest ESG company',
                f"{laggard['company_name']} - ESG {_format_pdf_metric(laggard.get('esg_score'), decimals=1)}",
                f"Sector: {laggard.get('sector') or 'Unknown'} | Status: {laggard.get('status') or 'Unknown'}",
                accent=(0.46, 0.16, 0.18),
            )

    if report_type.strip().lower() in {'edci', 'sfdr'}:
        builder.add_heading('Impact Intelligence', level=2)
        impact_summary = str(impact_story.get('summary') or '').strip() or ((context_lines or [])[0] if context_lines else '')
        if impact_summary:
            builder.add_paragraph(impact_summary, size=10)
        impact_bullets = list(
            dict.fromkeys(
                [
                    *[str(item).strip() for item in (impact_story.get('highlights') or [])[:2] if str(item).strip()],
                    str(impact_story.get('trend_summary') or '').strip(),
                    f"Anomaly watchlist: {str(anomaly_summary.get('headline') or '').strip()}" if anomaly_summary.get('headline') else '',
                    *[
                        line
                        for line in [
                            f"{'Regulatory watch' if item.get('item_type') == 'regulation' else (item.get('sector') or 'Sector context')}: {str(item.get('title') or '').strip()}"
                            for item in external_context_items[:2]
                            if str(item.get('title') or '').strip()
                        ]
                    ],
                ]
            )
        )
        impact_bullets = [line for line in impact_bullets if line]
        if impact_bullets:
            builder.add_bullets(impact_bullets[:5], size=10)
        if narrative_lines:
            builder.add_paragraph('An approved narrative insert is attached to this PDF package.', size=10)

        if anomaly_summary.get('headline') or anomaly_summary.get('summary'):
            builder.add_callout(
                'Anomaly Watchlist',
                str(anomaly_summary.get('headline') or 'No anomaly summary available').strip(),
                str(anomaly_summary.get('summary') or 'No anomaly summary was supplied for this export.').strip(),
                accent=(0.64, 0.33, 0.07),
            )

        if external_context_items:
            builder.add_heading('Sector & Regulatory Context', level=2)
            builder.add_bullets(
                [
                    f"{str(item.get('title') or '').strip()} - {str(item.get('action_prompt') or item.get('impact_hint') or item.get('summary') or '').strip()}"
                    for item in external_context_items[:4]
                    if str(item.get('title') or '').strip()
                ],
                size=10,
            )
    else:
        builder.add_heading('Report Context', level=2)
        if context_lines:
            builder.add_bullets(context_lines[:4], size=10)
        else:
            builder.add_paragraph('No additional context lines were supplied for this export.', size=10)

    builder.add_heading('Portfolio Snapshot', level=2)
    table_columns = [
        {'label': 'Company', 'value': 'company_name', 'width': 154},
        {'label': 'Sector', 'value': 'sector', 'width': 96},
        {'label': 'Status', 'value': 'status', 'width': 76},
        {'label': 'ESG', 'value': lambda row: _format_pdf_metric(row.get('esg_score'), decimals=1), 'width': 58},
        {'label': 'GHG', 'value': lambda row: _format_pdf_metric(row.get('total_ghg_emissions'), decimals=1), 'width': 70},
        {'label': 'Female %', 'value': lambda row: _format_pdf_metric(row.get('female_representation_percent'), decimals=1), 'width': 70},
    ]
    builder.add_table('Company performance table', table_columns, sorted_rows)

    builder.add_heading('Benchmark Callouts', level=2)
    benchmark_lines = list(
        dict.fromkeys(
            [str(item).strip() for item in (impact_story.get('benchmark_callouts') or []) if str(item).strip()]
            or (context_lines or [])[:8]
        )
    )
    if benchmark_lines:
        builder.add_bullets(benchmark_lines, size=10)
    else:
        builder.add_paragraph('No benchmark callouts were generated for this report type.', size=10)

    if narrative_lines:
        builder.add_heading('Narrative Appendix', level=2)
        for line in narrative_lines:
            builder.add_paragraph(line, size=10)

    chart_status_series = [
        {'label': 'Approved', 'value': approved_count, 'note': 'Reviewed and approved submissions'},
        {'label': 'In progress', 'value': in_progress_count + submitted_count + under_review_count, 'note': 'Open items and review queue'},
        {'label': 'Follow-up', 'value': resubmission_count, 'note': 'Resubmission requests'},
    ]
    builder.add_bar_chart(
        'Submission Status Mix',
        chart_status_series,
        note='Shows the current reporting posture of the portfolio in the selected cycle.',
    )

    score_series = [
        {'label': row['company_name'], 'value': row.get('esg_score'), 'note': row.get('sector') or 'Unknown sector'}
        for row in sorted_rows[:5]
    ]
    builder.add_bar_chart(
        'Top ESG Scores',
        score_series,
        note='Leaders in the selected report period, ranked by ESG score.',
        accent=(0.07, 0.44, 0.31),
    )

    builder.add_attachment_list('Supporting Attachments', attachment_lines or [])

    builder.add_heading('Report Notes', level=2)
    notes = [
        f'Status distribution: {json.dumps(status_counts, sort_keys=True)}',
        f'Average completion: {_format_pdf_metric(avg_completion, decimals=1, suffix="%")}',
        'CSV export remains available for a machine-readable version of the same portfolio data.',
    ]
    builder.add_bullets(notes, size=10)

    return builder.finalize()


def _build_report_export_context(
    db: Session,
    *,
    report_name: str,
    period: str,
    portfolio: str,
    rows: List[dict],
    narrative_id: int | None = None,
) -> dict:
    context_lines = [
        f'Report focus: {report_name.upper()}',
        f'Portfolio: {portfolio}',
        f'Period: {period}',
        f'Companies in scope: {len(rows)}',
    ]
    narrative_lines: List[str] = []
    narrative_headline = None
    narrative_included = False
    trend_summary = None
    narrative_record = _get_narrative_record_or_404(db, narrative_id) if narrative_id is not None else None
    narrative_state = _build_report_narrative_state(
        db,
        portfolio=portfolio,
        period=period,
        narrative_record=narrative_record,
    )
    if narrative_record is not None:
        narrative_headline = narrative_record.headline
        context_lines.append(f'Narrative status: {narrative_state["narrative_status_label"]}')
        if narrative_state.get('narrative_status_reason'):
            context_lines.append(narrative_state['narrative_status_reason'])
        if narrative_state['narrative_status'] == 'current':
            narrative_lines = _render_narrative_file_lines(narrative_record)
            narrative_included = True
            context_lines.append(f'Narrative insert: {narrative_record.headline or "Approved narrative attached"}')
    else:
        context_lines.append(f'Narrative status: {narrative_state["narrative_status_label"]}')

    impact_headline = None
    benchmark_callouts: List[str] = []
    comparison_rows: List[dict] = []
    impact_story: dict = {}
    external_context_items: List[dict] = []
    anomaly_summary: dict = {}
    attachment_lines: List[str] = []
    impact_story = _build_report_impact_story(db, report_name=report_name, portfolio=portfolio, rows=rows)
    if impact_story:
        impact_headline = impact_story.get('headline')
        context_lines.append(impact_story.get('summary', ''))
        context_lines.extend((impact_story.get('highlights') or [])[:2])
        trend_summary = impact_story.get('trend_summary')
        context_lines.append(trend_summary or '')
        benchmark_callouts = (impact_story.get('benchmark_callouts') or [])[:3]
        comparison_rows = impact_story.get('comparison_rows') or []
    elif rows:
        top_row = rows[0]
        context_lines.append(f"Top row: {top_row['company_name']} | {top_row['sector']} | ESG {top_row['esg_score']}")

    external_context_items, anomaly_summary = _report_scope_signal_payload(db, portfolio=portfolio)
    if anomaly_summary.get('headline'):
        context_lines.append(f"Anomaly watchlist: {anomaly_summary['headline']}")
    if anomaly_summary.get('summary'):
        context_lines.append(str(anomaly_summary.get('summary') or '').strip())
    context_lines.extend(
        [
            line
            for line in (_format_external_context_export_line(item) for item in external_context_items[:2])
            if line
        ]
    )

    row_company_names = {str(row.get('company_name') or '').strip() for row in rows if str(row.get('company_name') or '').strip()}
    attachment_company_ids: set[int] = set()
    if narrative_id is not None:
        narrative_record = _get_narrative_record_or_404(db, narrative_id)
        if narrative_record.company_id:
            attachment_company_ids.add(narrative_record.company_id)
    if row_company_names:
        for company in _query_ui_visible_companies(db).filter(Company.name.in_(sorted(row_company_names))).all():
            attachment_company_ids.add(company.id)

    if attachment_company_ids:
        attachment_rows = (
            db.query(SupportingDocument, Company.name)
            .join(Company, SupportingDocument.company_id == Company.id)
            .filter(SupportingDocument.company_id.in_(sorted(attachment_company_ids)))
            .order_by(SupportingDocument.uploaded_at.desc())
            .all()
        )
        for document, company_name in attachment_rows[:8]:
            size_kb = max(float(document.file_size or 0) / 1024, 0.1)
            attachment_lines.append(
                f'{company_name} - {document.file_name} ({document.field_key}, {size_kb:.0f} KB)'
            )

    if not attachment_lines:
        attachment_lines.append('No supporting attachments were found for this report.')

    context_lines = [line for line in context_lines if str(line or '').strip()]

    return {
        'context_lines': context_lines,
        'narrative_lines': narrative_lines,
        'narrative_headline': narrative_headline,
        'narrative_included': narrative_included,
        'narrative_status': narrative_state['narrative_status'],
        'narrative_status_label': narrative_state['narrative_status_label'],
        'narrative_status_reason': narrative_state.get('narrative_status_reason'),
        'impact_headline': impact_headline,
        'benchmark_callouts': benchmark_callouts,
        'comparison_rows': comparison_rows,
        'trend_summary': trend_summary,
        'impact_story': impact_story,
        'external_context_items': external_context_items,
        'anomaly_summary': anomaly_summary,
        'attachment_lines': attachment_lines,
    }


def create_unlock_record(
    db: Session,
    *,
    submission: Submission,
    reason: str,
    expiry_hours: int,
    manager_user: User | None,
) -> SubmissionUnlock:
    cycle = submission.cycle or resolve_submission_cycle(db)
    if submission.cycle_id is None:
        submission.cycle_id = cycle.id
        db.commit()
        db.refresh(submission)

    db.query(SubmissionUnlock).filter(
        SubmissionUnlock.submission_id == submission.id,
        SubmissionUnlock.company_id == submission.company_id,
        SubmissionUnlock.cycle_id == cycle.id,
        SubmissionUnlock.active.is_(True),
    ).update({'active': False}, synchronize_session=False)

    unlock = SubmissionUnlock(
        submission_id=submission.id,
        company_id=submission.company_id,
        cycle_id=cycle.id,
        unlocked_by_user_id=manager_user.id if manager_user else None,
        reason=reason,
        expires_at=datetime.utcnow() + timedelta(hours=expiry_hours),
        active=True,
    )
    db.add(unlock)
    db.commit()
    db.refresh(unlock)
    return unlock


@app.post('/submissions/{submission_id}/unlock', response_model=SubmissionUnlockInfo, dependencies=[Depends(require_manager)])
def unlock_submission(
    submission_id: int,
    payload: SubmissionUnlockRequest,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    manager_user = find_request_user(db, user_email)
    unlock = create_unlock_record(
        db,
        submission=submission,
        reason=payload.reason,
        expiry_hours=payload.expiry_hours,
        manager_user=manager_user,
    )
    company = db.query(Company).filter(Company.id == submission.company_id).first()
    _queue_activity_event(
        db,
        event_type='submission_unlock_granted',
        title='Submission unlocked',
        message=f'{company.name if company else "A company"} was unlocked for edits.',
        severity='warning',
        actor_role='manager',
        actor_email=user_email,
        company=company,
        submission=submission,
        cycle=submission.cycle,
        entity_status=submission.status,
        is_toast=True,
        visible_to_investors=False,
        metadata={'reason': payload.reason, 'expiry_hours': payload.expiry_hours},
    )
    db.commit()
    return SubmissionUnlockInfo(
        id=unlock.id,
        submission_id=unlock.submission_id,
        company_id=unlock.company_id,
        cycle_id=unlock.cycle_id,
        unlocked_by_user_id=unlock.unlocked_by_user_id,
        reason=unlock.reason,
        expires_at=unlock.expires_at.isoformat(),
        created_at=unlock.created_at.isoformat(),
        active=unlock.active,
    )


@app.post('/companies/{company_id}/unlock', response_model=SubmissionUnlockInfo, dependencies=[Depends(require_manager)])
def unlock_company_for_cycle(
    company_id: int,
    payload: SubmissionUnlockRequest,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')

    target_cycle = resolve_submission_cycle(db)
    submission = (
        db.query(Submission)
        .filter(Submission.company_id == company_id, Submission.cycle_id == target_cycle.id)
        .order_by(Submission.id.desc())
        .first()
    )
    if not submission:
        raise HTTPException(
            status_code=404,
            detail='No submission found for this company in the target cycle to unlock',
        )

    manager_user = find_request_user(db, user_email)
    unlock = create_unlock_record(
        db,
        submission=submission,
        reason=payload.reason,
        expiry_hours=payload.expiry_hours,
        manager_user=manager_user,
    )
    _queue_activity_event(
        db,
        event_type='submission_unlock_granted',
        title='Submission unlocked',
        message=f'{company.name} was unlocked for edits.',
        severity='warning',
        actor_role='manager',
        actor_email=user_email,
        company=company,
        submission=submission,
        cycle=submission.cycle,
        entity_status=submission.status,
        is_toast=True,
        visible_to_investors=False,
        metadata={'reason': payload.reason, 'expiry_hours': payload.expiry_hours},
    )
    db.commit()
    return SubmissionUnlockInfo(
        id=unlock.id,
        submission_id=unlock.submission_id,
        company_id=unlock.company_id,
        cycle_id=unlock.cycle_id,
        unlocked_by_user_id=unlock.unlocked_by_user_id,
        reason=unlock.reason,
        expires_at=unlock.expires_at.isoformat(),
        created_at=unlock.created_at.isoformat(),
        active=unlock.active,
    )


@app.post('/companies/{company_id}/reminders', response_model=ReminderInfo, dependencies=[Depends(require_manager)])
def send_reminder(
    company_id: int,
    payload: ReminderRequest,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')

    if payload.cycle_id is not None:
        cycle = db.query(CollectionCycle).filter(CollectionCycle.id == payload.cycle_id).first()
        if not cycle:
            raise HTTPException(status_code=404, detail='Cycle not found')
    else:
        cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)

    manager_user = find_request_user(db, user_email)
    reminder = ReminderLog(
        company_id=company.id,
        cycle_id=cycle.id,
        sent_by_user_id=manager_user.id if manager_user else None,
        channel=(payload.channel or 'email').strip().lower() or 'email',
        message=payload.message.strip(),
        delivery_status='logged',
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    _queue_activity_event(
        db,
        event_type='reminder_sent',
        title='Reminder sent',
        message=f'Reminder sent to {company.name} for FY{cycle.cycle_year}.',
        severity='info',
        actor_role='manager',
        actor_email=user_email,
        company=company,
        cycle=cycle,
        entity_status=company.current_status,
        is_toast=True,
        visible_to_investors=False,
        metadata={'channel': reminder.channel, 'message': reminder.message},
    )
    db.commit()
    return ReminderInfo(
        id=reminder.id,
        company_id=reminder.company_id,
        cycle_id=reminder.cycle_id,
        sent_by_user_id=reminder.sent_by_user_id,
        channel=reminder.channel,
        message=reminder.message,
        created_at=reminder.created_at.isoformat(),
        delivery_status=reminder.delivery_status,
    )


@app.get('/reports/{report_type}', dependencies=[Depends(require_manager_or_investor)])
def generate_report(report_type: str, db: Session = Depends(get_db)):
    report_name = report_type.strip().lower()
    if report_name not in ALLOWED_REPORT_TYPES:
        raise HTTPException(status_code=400, detail='Invalid report type')

    active_cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)
    return {
        'report_type': report_name.upper(),
        'available_formats': ['csv', 'pdf'],
        'active_cycle_year': active_cycle.cycle_year,
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }


@app.get('/reports/{report_type}/preview', response_model=ReportPreviewResponse, dependencies=[Depends(require_manager_or_investor)])
def preview_report_export(
    report_type: str,
    period: str = Query(default=f"FY{datetime.utcnow().year}"),
    portfolio: str = Query(default='All Portfolio Companies'),
    narrative_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    report_name = report_type.strip().lower()
    if report_name not in ALLOWED_REPORT_TYPES:
        raise HTTPException(status_code=400, detail='Invalid report type')

    rows, _cycle, normalized_period = build_report_rows(db, portfolio=portfolio, period=period)
    report_context = _build_report_export_context(
        db,
        report_name=report_name,
        period=normalized_period,
        portfolio=portfolio,
        rows=rows,
        narrative_id=narrative_id,
    )
    return ReportPreviewResponse(
        report_type=report_name.upper(),
        period=normalized_period,
        portfolio=portfolio,
        rows_in_scope=len(rows),
        context_summary=report_context['context_lines'][:8],
        impact_headline=report_context['impact_headline'],
        benchmark_callouts=report_context['benchmark_callouts'],
        comparison_rows=report_context['comparison_rows'],
        trend_summary=report_context['trend_summary'],
        impact_story=report_context['impact_story'],
        external_context_items=report_context['external_context_items'],
        anomaly_summary=report_context['anomaly_summary'],
        narrative_id=narrative_id,
        narrative_headline=report_context['narrative_headline'],
        narrative_status=report_context['narrative_status'],
        narrative_status_label=report_context['narrative_status_label'],
        narrative_status_reason=report_context['narrative_status_reason'],
        narrative_included=bool(report_context['narrative_included']),
    )


@app.get('/reports/{report_type}/export', response_model=ReportExportResponse, dependencies=[Depends(require_manager_or_investor)])
def export_report(
    report_type: str,
    format: str = Query(default='csv'),
    period: str = Query(default=f"FY{datetime.utcnow().year}"),
    portfolio: str = Query(default='All Portfolio Companies'),
    narrative_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    report_name = report_type.strip().lower()
    if report_name not in ALLOWED_REPORT_TYPES:
        raise HTTPException(status_code=400, detail='Invalid report type')

    export_format = format.strip().lower()
    if export_format not in {'csv', 'pdf'}:
        raise HTTPException(status_code=400, detail='format must be csv or pdf')

    rows, cycle, normalized_period = build_report_rows(db, portfolio=portfolio, period=period)
    report_context = _build_report_export_context(
        db,
        report_name=report_name,
        period=normalized_period,
        portfolio=portfolio,
        rows=rows,
        narrative_id=narrative_id,
    )
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    file_name = f'{report_name}_{slugify(normalized_period)}_{slugify(portfolio)}_{timestamp}.{export_format}'
    if export_format == 'csv':
        artifact = save_export_artifact(file_name, build_csv_export_bytes(rows), 'text/csv')
        content_type = 'text/csv'
    else:
        artifact = save_export_artifact(
            file_name,
              build_pdf_export_bytes(
                  report_name,
                  normalized_period,
                  cycle,
                  rows,
                  context_lines=report_context['context_lines'],
                  narrative_lines=report_context['narrative_lines'],
                  attachment_lines=report_context['attachment_lines'],
                  impact_story=report_context['impact_story'],
                  anomaly_summary=report_context['anomaly_summary'],
                  external_context_items=report_context['external_context_items'],
              ),
              'application/pdf',
          )
        content_type = 'application/pdf'

    return ReportExportResponse(
        report_type=report_name.upper(),
        format=export_format,
        period=normalized_period,
        portfolio=portfolio,
        generated_at=datetime.now(timezone.utc).isoformat(),
        file_name=file_name,
        file_path=str(artifact['file_path']),
        download_url=str(artifact['download_url']),
        content_type=content_type,
        rows_exported=len(rows),
        context_summary=report_context['context_lines'][:8],
        impact_headline=report_context['impact_headline'],
        narrative_headline=report_context['narrative_headline'],
        narrative_included=bool(report_context['narrative_included']),
        narrative_status=report_context['narrative_status'],
        narrative_status_label=report_context['narrative_status_label'],
        narrative_status_reason=report_context['narrative_status_reason'],
        benchmark_callouts=report_context['benchmark_callouts'],
        comparison_rows=report_context['comparison_rows'],
        trend_summary=report_context['trend_summary'],
        impact_story=report_context['impact_story'],
        external_context_items=report_context['external_context_items'],
        anomaly_summary=report_context['anomaly_summary'],
    )


def _build_newsletter_response_payload(db: Session, *, audience: str, tone: str) -> dict:
    normalized_tone = normalize_narrative_tone(tone)
    context = _build_newsletter_context(db, audience=audience, tone=normalized_tone)
    prompt = _build_newsletter_prompt(context)
    openai_payload = _call_openai_summary(prompt)
    fallback_payload = _build_fallback_newsletter(context)
    normalized_payload = _normalize_newsletter_payload(openai_payload, fallback_payload)
    active_cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)
    analytics = build_investor_analytics(db)

    return {
        'available': True,
        'audience': audience,
        'tone': normalized_tone,
        'generated_at': datetime.utcnow().isoformat(),
        **normalized_payload,
        'source_years': [active_cycle.cycle_year] if active_cycle else [],
        'source_company_count': int(context.get('portfolio', {}).get('total_companies') or 0),
        'source_submission_count': int(analytics.get('total_submissions') or 0),
        'impact_headline': (context.get('impact_story') or {}).get('headline'),
        'trend_summary': (context.get('impact_story') or {}).get('trend_summary'),
        'benchmark_callouts': ((context.get('impact_story') or {}).get('benchmark_callouts') or [])[:4],
        'external_context_items': (context.get('external_context_items') or [])[:4],
        'anomaly_summary': context.get('anomaly_summary') or None,
        'cached': False,
        'fallback_used': not bool(openai_payload),
        'message': None,
    }


def _build_newsletter_export_lines(newsletter_payload: dict) -> List[str]:
    lines: List[str] = []
    subject_line = str(newsletter_payload.get('subject_line') or '').strip()
    preheader = str(newsletter_payload.get('preheader') or '').strip()
    headline = str(newsletter_payload.get('headline') or '').strip()
    summary = str(newsletter_payload.get('summary') or '').strip()
    highlights = [str(item or '').strip() for item in newsletter_payload.get('highlights') or [] if str(item or '').strip()]
    watchouts = [str(item or '').strip() for item in newsletter_payload.get('watchouts') or [] if str(item or '').strip()]
    recommendations = [str(item or '').strip() for item in newsletter_payload.get('recommendations') or [] if str(item or '').strip()]
    call_to_action = str(newsletter_payload.get('call_to_action') or '').strip()

    lines.append('ESG Newsletter Draft')
    lines.append('')
    if subject_line:
        lines.append(f'Subject: {subject_line}')
    if preheader:
        lines.append(f'Preheader: {preheader}')
    if headline:
        lines.append(f'Headline: {headline}')
    if subject_line or preheader or headline:
        lines.append('')
    if summary:
        lines.append('Summary:')
        lines.extend(summary.splitlines())
        lines.append('')
    if highlights:
        lines.append('Highlights:')
        lines.extend([f'- {item}' for item in highlights])
        lines.append('')
    if watchouts:
        lines.append('Watchouts:')
        lines.extend([f'- {item}' for item in watchouts])
        lines.append('')
    if recommendations:
        lines.append('Recommendations:')
        lines.extend([f'- {item}' for item in recommendations])
        lines.append('')
    if call_to_action:
        lines.append('Call to Action:')
        lines.append(call_to_action)
        lines.append('')
    if newsletter_payload.get('impact_headline'):
        lines.append(f"Impact headline: {newsletter_payload.get('impact_headline')}")
    source_years = newsletter_payload.get('source_years') or []
    if source_years:
        lines.append(f"Source years: {', '.join(str(year) for year in source_years)}")
    source_company_count = newsletter_payload.get('source_company_count')
    source_submission_count = newsletter_payload.get('source_submission_count')
    if source_company_count is not None or source_submission_count is not None:
        lines.append(
            f"Sources: {int(source_submission_count or 0)} submissions across {int(source_company_count or 0)} companies"
        )
    benchmark_callouts = [str(item or '').strip() for item in newsletter_payload.get('benchmark_callouts') or [] if str(item or '').strip()]
    if benchmark_callouts:
        lines.append('')
        lines.append('Benchmark Callouts:')
        lines.extend([f'- {item}' for item in benchmark_callouts])
    anomaly_summary = newsletter_payload.get('anomaly_summary') or {}
    if anomaly_summary.get('headline') or anomaly_summary.get('summary'):
        lines.append('')
        lines.append('Anomaly Watchlist:')
        if anomaly_summary.get('headline'):
            lines.append(str(anomaly_summary.get('headline')).strip())
        if anomaly_summary.get('summary'):
            lines.append(str(anomaly_summary.get('summary')).strip())
        anomaly_items = [
            f"{str(item.get('company_name') or '').strip() + ': ' if str(item.get('company_name') or '').strip() else ''}{str(item.get('metric_name') or '').strip()} - {str(item.get('recommendation') or item.get('rationale') or '').strip()}"
            for item in (anomaly_summary.get('items') or [])[:3]
            if str(item.get('metric_name') or '').strip()
        ]
        lines.extend([f'- {item}' for item in anomaly_items if item.strip()])
    external_context_lines = [
        line
        for line in (_format_external_context_export_line(item) for item in (newsletter_payload.get('external_context_items') or [])[:3])
        if line
    ]
    if external_context_lines:
        lines.append('')
        lines.append('Sector & Regulatory Context:')
        lines.extend([f'- {item}' for item in external_context_lines])

    return lines or ['ESG newsletter draft unavailable.']


def _newsletter_delivery_config() -> dict:
    host = str(os.getenv('NEWSLETTER_SMTP_HOST') or os.getenv('SMTP_HOST') or '').strip()
    port_value = str(os.getenv('NEWSLETTER_SMTP_PORT') or os.getenv('SMTP_PORT') or '587').strip()
    username = str(os.getenv('NEWSLETTER_SMTP_USERNAME') or os.getenv('SMTP_USERNAME') or '').strip()
    password = str(os.getenv('NEWSLETTER_SMTP_PASSWORD') or os.getenv('SMTP_PASSWORD') or '').strip()
    from_email = str(
        os.getenv('NEWSLETTER_FROM_EMAIL')
        or os.getenv('SMTP_FROM_EMAIL')
        or os.getenv('SMTP_USERNAME')
        or ''
    ).strip()
    from_name = str(os.getenv('NEWSLETTER_FROM_NAME') or 'ESG Newsletter').strip()
    use_tls = str(os.getenv('NEWSLETTER_SMTP_USE_TLS') or '1').strip().lower() not in {'0', 'false', 'no'}

    if not host or not from_email:
        return {}

    try:
        port = int(port_value)
    except (TypeError, ValueError):
        port = 587

    return {
        'host': host,
        'port': port,
        'username': username,
        'password': password,
        'from_email': from_email,
        'from_name': from_name,
        'use_tls': use_tls,
    }


def _newsletter_default_recipients(db: Session, audience: str) -> List[str]:
    role = normalize_role('manager' if audience == 'manager' else 'investor')
    users = db.query(User).filter(User.role == role).order_by(User.email.asc()).all()
    emails: List[str] = []
    for user in users:
        email = str(getattr(user, 'email', '') or '').strip().lower()
        if email and email not in emails:
            emails.append(email)
    return emails


def _newsletter_plain_text_body(newsletter_payload: dict) -> str:
    return '\n'.join(_build_newsletter_export_lines(newsletter_payload)).strip() + '\n'


def _newsletter_html_body(newsletter_payload: dict) -> str:
    subject_line = html_lib.escape(str(newsletter_payload.get('subject_line') or '').strip())
    preheader = html_lib.escape(str(newsletter_payload.get('preheader') or '').strip())
    headline = html_lib.escape(str(newsletter_payload.get('headline') or '').strip())
    summary = html_lib.escape(str(newsletter_payload.get('summary') or '').strip()).replace('\n', '<br>')
    call_to_action = html_lib.escape(str(newsletter_payload.get('call_to_action') or '').strip())

    def render_list(title: str, items: List[str]) -> str:
        clean_items = [html_lib.escape(str(item or '').strip()) for item in items if str(item or '').strip()]
        if not clean_items:
            return ''
        bullets = ''.join(f'<li style="margin:0 0 8px 0;">{item}</li>' for item in clean_items)
        return (
            f'<div style="margin-top:20px;">'
            f'<h3 style="margin:0 0 10px 0;font-size:15px;color:#183153;">{html_lib.escape(title)}</h3>'
            f'<ul style="margin:0;padding-left:20px;color:#24364b;line-height:1.6;">{bullets}</ul>'
            f'</div>'
        )

    highlights = render_list('Highlights', newsletter_payload.get('highlights') or [])
    watchouts = render_list('Watchouts', newsletter_payload.get('watchouts') or [])
    recommendations = render_list('Recommendations', newsletter_payload.get('recommendations') or [])
    benchmark_callouts = render_list('Benchmark Callouts', newsletter_payload.get('benchmark_callouts') or [])
    anomaly_summary = newsletter_payload.get('anomaly_summary') or {}
    anomaly_items = [
        f"{str(item.get('company_name') or '').strip() + ': ' if str(item.get('company_name') or '').strip() else ''}{str(item.get('metric_name') or '').strip()} - {str(item.get('recommendation') or item.get('rationale') or '').strip()}"
        for item in (anomaly_summary.get('items') or [])[:3]
        if str(item.get('metric_name') or '').strip()
    ]
    anomaly_block = ''
    if anomaly_summary.get('headline') or anomaly_summary.get('summary') or anomaly_items:
        anomaly_block = (
            '<div style="margin-top:20px;padding:18px;border:1px solid #f1c27d;background:#fff7ed;border-radius:14px;">'
            f'<h3 style="margin:0 0 10px 0;font-size:15px;color:#8a4510;">{html_lib.escape(str(anomaly_summary.get("headline") or "Anomaly Watchlist").strip())}</h3>'
            f'<p style="margin:0;color:#5b3416;line-height:1.6;">{html_lib.escape(str(anomaly_summary.get("summary") or "").strip()).replace(chr(10), "<br>")}</p>'
            f'{render_list("Recommended Follow-up", anomaly_items)}'
            '</div>'
        )
    external_context_items = [
        _format_external_context_export_line(item)
        for item in (newsletter_payload.get('external_context_items') or [])[:3]
        if isinstance(item, dict)
    ]
    external_context = render_list('Sector & Regulatory Context', [item for item in external_context_items if item])

    return f'''
    <html>
      <body style="margin:0;padding:0;background:#f4f7fb;font-family:Arial,Helvetica,sans-serif;color:#132238;">
        <div style="max-width:720px;margin:0 auto;padding:32px 20px;">
          <div style="background:#ffffff;border:1px solid #dbe3ee;border-radius:16px;padding:28px;">
            <div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#6a7788;">ESG Newsletter</div>
            <h1 style="margin:12px 0 8px 0;font-size:28px;line-height:1.2;color:#0f2747;">{subject_line or 'Portfolio update'}</h1>
            {'<p style="margin:0 0 18px 0;color:#5e6b7a;font-size:14px;">' + preheader + '</p>' if preheader else ''}
            {'<h2 style="margin:0 0 14px 0;font-size:20px;color:#16355e;">' + headline + '</h2>' if headline else ''}
            <div style="font-size:15px;line-height:1.7;color:#223449;">{summary}</div>
            {highlights}
            {watchouts}
            {recommendations}
            {benchmark_callouts}
            {anomaly_block}
            {external_context}
            {'<div style="margin-top:24px;padding:16px;border-left:4px solid #2b6cb0;background:#eef5ff;color:#153054;border-radius:10px;"><strong>Call to action:</strong> ' + call_to_action + '</div>' if call_to_action else ''}
          </div>
        </div>
      </body>
    </html>
    '''.strip()


def _newsletter_send_message(config: dict, recipient_email: str, newsletter_payload: dict) -> tuple[bool, str | None, str | None]:
    message = EmailMessage()
    subject_line = str(newsletter_payload.get('subject_line') or 'ESG Newsletter Update').strip()
    message['Subject'] = subject_line
    message['From'] = f"{config['from_name']} <{config['from_email']}>"
    message['To'] = recipient_email
    message['Message-ID'] = (
        '<'
        + hashlib.sha1(
            f"{recipient_email}:{subject_line}:{newsletter_payload.get('generated_at')}".encode('utf-8')
        ).hexdigest()
        + '@esg-app.local>'
    )
    message.set_content(_newsletter_plain_text_body(newsletter_payload))
    message.add_alternative(_newsletter_html_body(newsletter_payload), subtype='html')

    with smtplib.SMTP(config['host'], config['port'], timeout=20) as smtp:
        if config.get('use_tls'):
            smtp.starttls()
        if config.get('username'):
            smtp.login(config['username'], config.get('password') or '')
        refused = smtp.send_message(message)
    if refused:
        return False, None, f'Recipient rejected by SMTP server: {json.dumps(refused, sort_keys=True)}'
    return True, message['Message-ID'], None


def _send_newsletter_campaign(
    db: Session,
    *,
    audience: str,
    tone: str,
    dry_run: bool = False,
    recipient_emails: Optional[List[str]] = None,
    force_refresh: bool = False,
    scheduled_for: datetime | None = None,
) -> dict:
    newsletter_payload = _build_newsletter_response_payload(db, audience=audience, tone=tone)
    if force_refresh:
        newsletter_payload['cached'] = False

    recipients = [str(email or '').strip().lower() for email in (recipient_emails or []) if str(email or '').strip()]
    if not recipients:
        recipients = _newsletter_default_recipients(db, audience)
    if not recipients:
        raise HTTPException(status_code=404, detail=f'No recipients found for {audience} newsletter')

    payload_hash = hashlib.sha256(
        json.dumps(
            {
                'audience': audience,
                'tone': newsletter_payload.get('tone'),
                'subject_line': newsletter_payload.get('subject_line'),
                'summary': newsletter_payload.get('summary'),
                'highlights': newsletter_payload.get('highlights'),
                'watchouts': newsletter_payload.get('watchouts'),
                'recommendations': newsletter_payload.get('recommendations'),
                'call_to_action': newsletter_payload.get('call_to_action'),
            },
            sort_keys=True,
            default=str,
        ).encode('utf-8')
    ).hexdigest()

    if dry_run:
        return {
            'available': True,
            'audience': audience,
            'tone': str(newsletter_payload.get('tone') or tone),
            'generated_at': str(newsletter_payload.get('generated_at') or datetime.utcnow().isoformat()),
            'delivery_status': 'dry_run',
            'provider': 'smtp',
            'recipient_count': len(recipients),
            'sent_count': 0,
            'failed_count': 0,
            'skipped_count': 0,
            'subject_line': str(newsletter_payload.get('subject_line') or ''),
            'preheader': str(newsletter_payload.get('preheader') or ''),
            'headline': str(newsletter_payload.get('headline') or ''),
            'dry_run': True,
            'message': 'Dry run completed. No email was sent.',
        }

    config = _newsletter_delivery_config()
    if not config:
        raise HTTPException(
            status_code=503,
            detail='Newsletter SMTP is not configured. Set NEWSLETTER_SMTP_HOST and NEWSLETTER_FROM_EMAIL to send emails.',
        )

    sent_count = 0
    failed_count = 0
    skipped_count = 0
    provider = 'smtp'
    log_rows: List[NewsletterDispatchLog] = []

    for recipient_email in recipients:
        duplicate_log = db.query(NewsletterDispatchLog).filter(
            NewsletterDispatchLog.audience == audience,
            NewsletterDispatchLog.tone == newsletter_payload.get('tone'),
            NewsletterDispatchLog.recipient_email == recipient_email,
            NewsletterDispatchLog.payload_hash == payload_hash,
            NewsletterDispatchLog.delivery_status == 'sent',
        ).order_by(NewsletterDispatchLog.id.desc()).first()
        if duplicate_log:
            skipped_count += 1
            continue

        dispatch_log = NewsletterDispatchLog(
            audience=audience,
            tone=str(newsletter_payload.get('tone') or tone),
            recipient_email=recipient_email,
            payload_hash=payload_hash,
            subject_line=str(newsletter_payload.get('subject_line') or ''),
            provider=provider,
            delivery_status='queued',
            scheduled_for=scheduled_for,
        )
        db.add(dispatch_log)
        log_rows.append(dispatch_log)
        db.flush()

        try:
            delivered, provider_message_id, error_message = _newsletter_send_message(config, recipient_email, newsletter_payload)
            dispatch_log.delivery_status = 'sent' if delivered else 'failed'
            dispatch_log.provider_message_id = provider_message_id
            dispatch_log.error_message = error_message
            dispatch_log.sent_at = datetime.utcnow()
            if delivered:
                sent_count += 1
            else:
                failed_count += 1
        except Exception as exc:
            dispatch_log.delivery_status = 'failed'
            dispatch_log.error_message = str(exc)
            dispatch_log.sent_at = datetime.utcnow()
            failed_count += 1

    db.commit()

    delivery_status = 'sent' if sent_count and not failed_count else 'failed' if failed_count else 'skipped'
    if sent_count == 0 and skipped_count > 0 and failed_count == 0:
        delivery_status = 'skipped'

    return {
        'available': True,
        'audience': audience,
        'tone': str(newsletter_payload.get('tone') or tone),
        'generated_at': str(newsletter_payload.get('generated_at') or datetime.utcnow().isoformat()),
        'delivery_status': delivery_status,
        'provider': provider,
        'recipient_count': len(recipients),
        'sent_count': sent_count,
        'failed_count': failed_count,
        'skipped_count': skipped_count,
        'subject_line': str(newsletter_payload.get('subject_line') or ''),
        'preheader': str(newsletter_payload.get('preheader') or ''),
        'headline': str(newsletter_payload.get('headline') or ''),
        'dry_run': False,
        'message': 'Newsletter sent.' if sent_count else 'Newsletter send completed with no new deliveries.',
    }


def require_cron_secret(authorization: str | None = Header(default=None)):
    expected_secret = str(os.getenv('CRON_SECRET') or '').strip()
    if not expected_secret:
        raise HTTPException(status_code=503, detail='CRON_SECRET is not configured')
    if authorization != f'Bearer {expected_secret}':
        raise HTTPException(status_code=401, detail='Invalid cron secret')
    return True


@app.post('/newsletter/generate', response_model=NewsletterSummaryResponse)
def generate_newsletter(
    payload: NewsletterGenerateRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    normalized_role = normalize_role(role)
    audience = _newsletter_audience_for_role(normalized_role)
    if not audience:
        raise HTTPException(status_code=403, detail='Newsletter access is restricted to managers and investors')
    if payload.audience != audience:
        raise HTTPException(status_code=403, detail='Newsletter audience does not match the authenticated user role')

    newsletter_payload = _build_newsletter_response_payload(db, audience=audience, tone=payload.tone)
    return NewsletterSummaryResponse(**newsletter_payload)


@app.post('/newsletter/export', response_model=NewsletterExportResponse)
def export_newsletter(
    payload: NewsletterGenerateRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    normalized_role = normalize_role(role)
    audience = _newsletter_audience_for_role(normalized_role)
    if not audience:
        raise HTTPException(status_code=403, detail='Newsletter access is restricted to managers and investors')
    if payload.audience != audience:
        raise HTTPException(status_code=403, detail='Newsletter audience does not match the authenticated user role')

    newsletter_payload = _build_newsletter_response_payload(db, audience=audience, tone=payload.tone)
    export_timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    file_name = f'newsletter_{audience}_{export_timestamp}.txt'
    export_lines = _build_newsletter_export_lines(newsletter_payload)
    artifact = save_export_artifact(
        file_name,
        '\n'.join(export_lines).encode('utf-8'),
        'text/plain',
    )
    return NewsletterExportResponse(
        available=True,
        audience=audience,
        tone=str(newsletter_payload.get('tone') or payload.tone),
        generated_at=str(newsletter_payload.get('generated_at') or datetime.utcnow().isoformat()),
        file_name=file_name,
        file_path=str(artifact['file_path']),
        download_url=str(artifact['download_url']),
        content_type='text/plain',
        subject_line=str(newsletter_payload.get('subject_line') or ''),
        preheader=str(newsletter_payload.get('preheader') or ''),
        headline=str(newsletter_payload.get('headline') or ''),
        impact_headline=str(newsletter_payload.get('impact_headline') or '') or None,
        trend_summary=str(newsletter_payload.get('trend_summary') or '') or None,
        benchmark_callouts=list(newsletter_payload.get('benchmark_callouts') or []),
        external_context_items=list(newsletter_payload.get('external_context_items') or []),
        anomaly_summary=newsletter_payload.get('anomaly_summary') or None,
        message='Newsletter export is ready.',
    )


@app.post('/newsletter/send', response_model=NewsletterSendResponse)
@app.post('/api/newsletter/send', response_model=NewsletterSendResponse)
def send_newsletter(
    payload: NewsletterGenerateRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    normalized_role = normalize_role(role)
    audience = _newsletter_audience_for_role(normalized_role)
    if not audience:
        raise HTTPException(status_code=403, detail='Newsletter access is restricted to managers and investors')
    if payload.audience != audience:
        raise HTTPException(status_code=403, detail='Newsletter audience does not match the authenticated user role')

    newsletter_payload = _send_newsletter_campaign(
        db,
        audience=audience,
        tone=payload.tone,
        dry_run=bool(payload.dry_run),
        recipient_emails=payload.recipient_emails,
        force_refresh=payload.force_refresh,
    )
    return NewsletterSendResponse(**newsletter_payload)


@app.get('/cron/newsletter/manager', response_model=NewsletterSendResponse, dependencies=[Depends(require_cron_secret)])
@app.get('/api/cron/newsletter/manager', response_model=NewsletterSendResponse, dependencies=[Depends(require_cron_secret)])
def cron_send_manager_newsletter(db: Session = Depends(get_db)):
    newsletter_payload = _send_newsletter_campaign(
        db,
        audience='manager',
        tone='board-ready',
        dry_run=False,
    )
    return NewsletterSendResponse(**newsletter_payload)


@app.get('/cron/newsletter/investor', response_model=NewsletterSendResponse, dependencies=[Depends(require_cron_secret)])
@app.get('/api/cron/newsletter/investor', response_model=NewsletterSendResponse, dependencies=[Depends(require_cron_secret)])
def cron_send_investor_newsletter(db: Session = Depends(get_db)):
    newsletter_payload = _send_newsletter_campaign(
        db,
        audience='investor',
        tone='lp-letter',
        dry_run=False,
    )
    return NewsletterSendResponse(**newsletter_payload)


@app.get('/narrative/summary', response_model=NarrativeDetailResponse)
def narrative_summary(
    audience: str = Query(default='company'),
    company_id: int | None = Query(default=None),
    tone: str = Query(default='board-ready'),
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    return build_narrative_summary(
        db,
        audience=audience,
        role=role,
        email=email,
        company_id=company_id,
        tone=tone,
        force_refresh=force_refresh,
    )


@app.get('/dashboard/manager', response_model=ManagerDashboardResponse, dependencies=[Depends(require_manager)])
def manager_dashboard(db: Session = Depends(get_db)):
    cache_key = 'dashboard:manager'
    cached = _get_timed_cache(cache_key)
    if cached is not None:
        return cached

    companies = _load_companies_with_related_data(db)
    analytics = build_investor_analytics(db, companies=companies)
    summary = build_manager_summary(db, companies)
    impact_story = _build_impact_intelligence(db, analytics, companies)
    result = ManagerDashboardResponse(
        companies=companies,
        summary=summary,
        impact_story=impact_story,
    ).model_dump()
    return _set_timed_cache(cache_key, result)


@app.get('/external-context/feed', response_model=ExternalContextFeedResponse)
def external_context_feed(
    limit: int = Query(default=8, ge=1, le=20),
    sector: str | None = Query(default=None),
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    normalized_role = normalize_role(role)
    if normalized_role not in {'manager', 'investor', 'company'}:
        raise HTTPException(status_code=403, detail='External context feed is restricted to authenticated portal users')

    target_company = None
    if company_id is not None:
        target_company = _ui_visible_company_by_id(db, company_id)
        if not target_company:
            raise HTTPException(status_code=404, detail='Company not found')

    if normalized_role == 'investor' and company_id is not None:
        raise HTTPException(status_code=403, detail='Investors are blocked from company-level external context feeds')

    if normalized_role == 'company':
        request_user = find_request_user(db, email)
        owned_company = find_company_for_user(db, request_user)
        if not owned_company:
            raise HTTPException(status_code=404, detail='Company not found for authenticated user')
        if target_company is not None and target_company.id != owned_company.id:
            raise HTTPException(status_code=403, detail='Unauthorized access to this company')
        target_company = owned_company

    return ExternalContextFeedResponse(
        **_build_external_context_feed(
            db,
            role=normalized_role,
            company=target_company,
            sector_filter=sector,
            limit=limit,
        )
    )


@app.get('/anomalies/summary', response_model=AnomalySummaryResponse)
def anomaly_summary(
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    normalized_role = normalize_role(role)
    if normalized_role not in {'manager', 'investor', 'company'}:
        raise HTTPException(status_code=403, detail='Anomaly summary is restricted to authenticated portal users')

    if normalized_role == 'investor' and company_id is not None:
        raise HTTPException(status_code=403, detail='Investors are blocked from company-level anomaly summaries')

    if normalized_role == 'company':
        request_user = find_request_user(db, email)
        company = find_company_for_user(db, request_user)
        if not company:
            raise HTTPException(status_code=404, detail='Company not found for authenticated user')
        return AnomalySummaryResponse(**_build_company_anomaly_summary(db, company))

    if company_id is not None:
        company = _ui_visible_company_by_id(db, company_id)
        if not company:
            raise HTTPException(status_code=404, detail='Company not found')
        return AnomalySummaryResponse(**_build_company_anomaly_summary(db, company))

    return AnomalySummaryResponse(**_build_portfolio_anomaly_summary(db))


@app.get('/company/anomalies', response_model=AnomalySummaryResponse, dependencies=[Depends(require_company)])
def company_anomalies(
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    user = find_request_user(db, email)
    company = find_company_for_user(db, user)
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    return AnomalySummaryResponse(**_build_company_anomaly_summary(db, company))


def safe_number(value, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def _clone_cache_value(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _get_timed_cache(key: str) -> Any:
    cached = _TIMED_COMPUTE_CACHE.get(key)
    if not cached:
        return None
    if time.monotonic() - cached['stored_at'] > ANALYTICS_CACHE_TTL_SECONDS:
        _TIMED_COMPUTE_CACHE.pop(key, None)
        return None
    return _clone_cache_value(cached['value'])


def _set_timed_cache(key: str, value: Any) -> Any:
    cloned = _clone_cache_value(value)
    _TIMED_COMPUTE_CACHE[key] = {
        'stored_at': time.monotonic(),
        'value': cloned,
    }
    return _clone_cache_value(cloned)


def _priority_rank(value: str) -> int:
    return {'high': 0, 'medium': 1, 'low': 2}.get(str(value or 'medium').strip().lower(), 1)


def _published_iso(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=max(days_ago, 0))).replace(microsecond=0).isoformat() + 'Z'


def _format_anomaly_value(value: Any, *, suffix: str = '', decimals: int = 1) -> str:
    if value is None or value == '':
        return 'n/a'
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number - round(number)) < 1e-9:
        return f'{int(round(number)):,}{suffix}'
    return f'{number:,.{decimals}f}{suffix}'


def _top_sectors_for_feed(companies: List[Company], *, company: Company | None = None) -> List[str]:
    if company is not None:
        return [str(company.sector or 'Unknown').strip() or 'Unknown']

    sector_counts: Dict[str, int] = {}
    for item in companies:
        sector = str(item.sector or 'Unknown').strip() or 'Unknown'
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
    ranked = sorted(sector_counts.items(), key=lambda row: (-row[1], row[0]))
    return [sector for sector, _ in ranked[:3]]


def _sector_template_bundle(sector: str) -> List[Dict[str, Any]]:
    normalized = _normalize_impact_text(sector)
    for key, items in EXTERNAL_CONTEXT_SECTOR_TEMPLATES.items():
        if key in normalized:
            return items
    return [
        {
            'id': f'{slugify(sector)}_general_reporting',
            'title': f'{sector} operators are being asked for clearer ESG evidence trails',
            'summary': 'Reporting teams are expected to pair metrics with practical policy references, action ownership, and consistent year-on-year context.',
            'priority': 'medium',
            'related_topics': ['data quality', 'evidence', 'benchmarking'],
            'impact_hint': 'Weak comparability tends to create more follow-up questions than low absolute impact alone.',
            'action_prompt': 'Keep approved metrics, policy references, and action plans tightly connected in the next update.',
        },
    ]


def _build_external_context_feed(
    db: Session,
    *,
    role: str,
    company: Company | None = None,
    sector_filter: str | None = None,
    limit: int = 8,
) -> dict:
    normalized_role = normalize_role(role)
    cache_scope = f'{normalized_role}:{company.id if company else "portfolio"}:{slugify(sector_filter or "")}:{limit}'
    cache_key = f'external_context_feed:{cache_scope}'
    cached = _get_timed_cache(cache_key)
    if cached is not None:
        return cached

    companies = _load_companies_with_related_data(db)
    sectors_in_view = _top_sectors_for_feed(companies, company=company)
    if sector_filter:
        requested = str(sector_filter).strip()
        sectors_in_view = [sector for sector in sectors_in_view if _normalize_impact_text(sector) == _normalize_impact_text(requested)]
        if not sectors_in_view and requested:
            sectors_in_view = [requested]

    items: List[dict] = []
    for index, template in enumerate(EXTERNAL_CONTEXT_REGULATORY_TEMPLATES):
        items.append(
            {
                'id': template['id'],
                'item_type': 'regulation',
                'title': template['title'],
                'summary': template['summary'],
                'sector': sectors_in_view[0] if len(sectors_in_view) == 1 and company is not None else None,
                'geography': template.get('geography'),
                'priority': template.get('priority', 'medium'),
                'source_label': 'Curated regulatory monitor',
                'source_type': 'curated',
                'published_at': _published_iso(index + 1),
                'related_topics': template.get('related_topics') or [],
                'impact_hint': template.get('impact_hint'),
                'action_prompt': template.get('action_prompt'),
                'company_id': company.id if company else None,
                'company_name': company.name if company else None,
            }
        )

    for sector_index, sector in enumerate(sectors_in_view):
        for item_index, template in enumerate(_sector_template_bundle(sector)):
            items.append(
                {
                    'id': f'{slugify(sector)}_{template["id"]}',
                    'item_type': 'sector-news',
                    'title': template['title'],
                    'summary': template['summary'],
                    'sector': sector,
                    'geography': company.geography if company else None,
                    'priority': template.get('priority', 'medium'),
                    'source_label': 'Sector context brief',
                    'source_type': 'portfolio-derived',
                    'published_at': _published_iso(sector_index + item_index + 1),
                    'related_topics': template.get('related_topics') or [],
                    'impact_hint': template.get('impact_hint'),
                    'action_prompt': template.get('action_prompt'),
                    'company_id': company.id if company else None,
                    'company_name': company.name if company else None,
                }
            )

    if company is not None:
        snapshot = _build_company_snapshot(db, company)
        if snapshot:
            items.insert(
                0,
                {
                    'id': f'company_focus_{company.id}',
                    'item_type': 'sector-news',
                    'title': f'{company.name} should keep its next ESG update tightly tied to approved operating signals',
                    'summary': (
                        f'The latest approved snapshot for {company.name} shows {snapshot["metrics"]["total_ghg_emissions"]} tCO2e, '
                        f'{snapshot["metrics"]["female_representation_percent"]}% female representation, and TRIFR at {snapshot["metrics"]["trifr"]}.'
                    ),
                    'sector': company.sector,
                    'geography': company.geography,
                    'priority': 'high',
                    'source_label': 'Company context brief',
                    'source_type': 'portfolio-derived',
                    'published_at': _published_iso(0),
                    'related_topics': ['approved data', 'company reporting', 'board updates'],
                    'impact_hint': 'The company dashboard, report exports, and narrative inserts should stay aligned with this approved baseline.',
                    'action_prompt': 'Use the approved snapshot as the source of truth for the next company submission review and any outward-facing summary.',
                    'company_id': company.id,
                    'company_name': company.name,
                },
            )

    items.sort(key=lambda item: (_priority_rank(item.get('priority', 'medium')), item.get('published_at', '')), reverse=False)
    result = {
        'available': True,
        'role': normalized_role,
        'scope': 'company' if company is not None else 'portfolio',
        'generated_at': datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
        'sectors_in_view': sectors_in_view,
        'items': items[:limit],
        'message': None if items else 'No sector or regulatory context items are available yet.',
    }
    return _set_timed_cache(cache_key, result)


def _company_anomaly_items(snapshot: dict) -> List[dict]:
    metrics = snapshot.get('metrics') or {}
    policy_snapshot = snapshot.get('policy_snapshot') or {}
    confidence = snapshot.get('confidence') or {}
    action_plan_summary = snapshot.get('action_plan_summary') or {}
    items: List[dict] = []

    def add_item(
        anomaly_type: str,
        severity: str,
        metric_name: str,
        current_value: str,
        rationale: str,
        recommendation: str,
        *,
        previous_value: str | None = None,
        delta_percent: float | None = None,
    ):
        items.append(
            {
                'id': f'{anomaly_type}_{snapshot["company_id"]}_{len(items) + 1}',
                'anomaly_type': anomaly_type,
                'severity': severity,
                'company_id': snapshot['company_id'],
                'company_name': snapshot['company_name'],
                'sector': snapshot.get('sector'),
                'reporting_year': snapshot.get('current_year'),
                'metric_name': metric_name,
                'current_value': current_value,
                'previous_value': previous_value,
                'delta_percent': delta_percent,
                'rationale': rationale,
                'recommendation': recommendation,
                'source_submission_id': snapshot.get('submission_id'),
            }
        )

    emissions_delta = metrics.get('emissions_delta_pct')
    if emissions_delta is not None and emissions_delta >= 30:
        add_item(
            'emissions_spike',
            'high' if emissions_delta >= 50 else 'medium',
            'Total GHG Emissions',
            _format_anomaly_value(metrics.get('total_ghg_emissions'), suffix=' tCO2e'),
            f'Approved emissions increased {emissions_delta:+.1f}% versus the prior approved submission.',
            'Review the underlying drivers, document the variance clearly, and confirm an action owner is assigned.',
            previous_value='Prior approved period',
            delta_percent=float(emissions_delta),
        )

    trifr_value = safe_number(metrics.get('trifr'))
    if trifr_value >= 5:
        add_item(
            'safety_watchlist',
            'high',
            'TRIFR',
            _format_anomaly_value(trifr_value, decimals=2),
            f'TRIFR is elevated at {trifr_value:.2f}, which is above the usual portfolio watchlist threshold.',
            'Escalate the safety review, capture remediation steps, and link a concrete action plan before the next reporting pack.',
        )

    female_rep = safe_number(metrics.get('female_representation_percent'))
    if female_rep < 30:
        add_item(
            'diversity_gap',
            'medium',
            'Female Representation',
            _format_anomaly_value(female_rep, suffix='%'),
            f'Female workforce representation is {female_rep:.1f}%, which sits below a common portfolio attention threshold.',
            'Flag the workforce mix trend in the next management update and decide whether a targeted people initiative should be added.',
        )

    renewable_ratio = safe_number(metrics.get('renewable_ratio_percent'))
    if renewable_ratio < 20:
        add_item(
            'renewables_gap',
            'medium',
            'Renewable Energy Share',
            _format_anomaly_value(renewable_ratio, suffix='%'),
            f'Renewable energy covers only {renewable_ratio:.1f}% of total energy use in the latest approved data.',
            'Confirm the electricity sourcing plan and log any active procurement or efficiency action already underway.',
        )

    if int(metrics.get('confirmed_cases_of_corruption') or 0) > 0:
        add_item(
            'governance_incident',
            'high',
            'Confirmed Cases of Corruption',
            str(int(metrics.get('confirmed_cases_of_corruption') or 0)),
            'Confirmed corruption cases were reported in the approved period.',
            'Keep governance remediation and board oversight visible in the next review cycle.',
        )

    if int(metrics.get('cyber_incidents_in_reporting_period') or 0) > 0:
        add_item(
            'cyber_incident',
            'medium',
            'Cyber Incidents',
            str(int(metrics.get('cyber_incidents_in_reporting_period') or 0)),
            'Cyber incidents were recorded in the latest approved period.',
            'Confirm the incident response, policy coverage, and oversight response before the next investor or board update.',
        )

    governance_gaps = [
        label
        for label, key in [
            ('ESG policy', 'esg_policy_in_place'),
            ('Board ESG oversight', 'board_level_esg_oversight'),
            ('Cybersecurity policy', 'cybersecurity_policy_in_place'),
            ('Anti-bribery policy', 'anti_bribery_corruption_policy'),
        ]
        if _normalize_policy_status(policy_snapshot.get(key)) != 'Yes'
    ]
    if governance_gaps:
        add_item(
            'policy_gap',
            'medium',
            'Governance Policy Coverage',
            ', '.join(governance_gaps),
            'One or more core governance controls are missing or not fully in place in the approved submission.',
            'Prioritise closing the most material governance policy gap and document timing in the action-plan tracker.',
        )

    measured_percent = safe_number(confidence.get('measured_percent'))
    if confidence.get('total') and measured_percent < 60:
        add_item(
            'low_confidence',
            'low',
            'Measured Data Confidence',
            _format_anomaly_value(measured_percent, suffix='%'),
            f'Only {measured_percent:.1f}% of confidence-tagged fields are marked as measured.',
            'Improve evidence quality or explain the estimation basis before the next approval cycle.',
        )

    if safe_number(action_plan_summary.get('overdue')) > 0:
        add_item(
            'overdue_actions',
            'medium',
            'Overdue Action Plans',
            str(int(safe_number(action_plan_summary.get('overdue')))),
            'Overdue ESG action plans remain open against the approved reporting context.',
            'Confirm whether overdue actions need reprioritisation, revised timing, or escalation.',
        )

    items.sort(key=lambda item: (_priority_rank(item['severity']), item['metric_name']))
    return items


def _build_anomaly_summary_prompt(scope: str, items: List[dict], *, company_name: str | None = None) -> str:
    label = company_name or 'Portfolio'
    compact_items = [
        {
            'company_name': item.get('company_name'),
            'severity': item.get('severity'),
            'metric_name': item.get('metric_name'),
            'rationale': item.get('rationale'),
            'recommendation': item.get('recommendation'),
            'delta_percent': item.get('delta_percent'),
        }
        for item in items[:8]
    ]
    return (
        'You are writing a short anomaly summary for an ESG platform.\n'
        'Return valid JSON only with exactly this shape: {"headline":"...","summary":"..."}.\n'
        'Keep both fields plain-English, concise, and decision-ready.\n'
        f'Scope: {scope}\n'
        f'Entity: {label}\n'
        f'Anomalies:\n{json.dumps(compact_items, indent=2, sort_keys=True, default=str)}'
    )


def _anomaly_summary_from_items(scope: str, items: List[dict], *, company_name: str | None = None) -> dict:
    severity_counts = {
        'high': sum(1 for item in items if item['severity'] == 'high'),
        'medium': sum(1 for item in items if item['severity'] == 'medium'),
        'low': sum(1 for item in items if item['severity'] == 'low'),
    }
    label = company_name or 'Portfolio'
    if not items:
        return {
            'available': True,
            'scope': scope,
            'generated_at': datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
            'headline': f'{label} anomaly watchlist is clear',
            'summary': 'No material anomalies were triggered from the latest approved-data checks.',
            'severity_counts': severity_counts,
            'watchlist_companies': [],
            'items': [],
            'fallback_used': True,
            'model': None,
            'message': 'No approved-data anomalies were triggered.',
        }

    high_count = severity_counts['high']
    medium_count = severity_counts['medium']
    headline = (
        f'{label} has {high_count} high-severity anomaly' + ('ies' if high_count != 1 else 'y')
        if high_count
        else f'{label} has {medium_count} medium-severity anomaly' + ('ies' if medium_count != 1 else 'y')
    )
    summary = (
        f'{label} anomaly screening flagged {len(items)} issue(s) from the latest approved data. '
        f'{severity_counts["high"]} high, {severity_counts["medium"]} medium, and {severity_counts["low"]} low-severity items need attention.'
    )
    use_ai_summary = str(os.getenv('ANOMALY_ENABLE_AI_SUMMARY', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
    ai_payload = _call_openai_summary(_build_anomaly_summary_prompt(scope, items, company_name=company_name)) if use_ai_summary else None
    return {
        'available': True,
        'scope': scope,
        'generated_at': datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
        'headline': str((ai_payload or {}).get('headline') or headline).strip(),
        'summary': str((ai_payload or {}).get('summary') or summary).strip(),
        'severity_counts': severity_counts,
        'watchlist_companies': [],
        'items': items,
        'fallback_used': not bool(ai_payload),
        'model': OPENAI_DEFAULT_MODEL if ai_payload else None,
        'message': None,
    }


def _build_portfolio_anomaly_summary(db: Session, companies: Optional[List[Company]] = None) -> dict:
    cache_key = 'portfolio_anomaly_summary'
    cached = _get_timed_cache(cache_key)
    if cached is not None and companies is None:
        return cached

    companies = companies if companies is not None else _load_companies_with_related_data(db)
    portfolio_snapshot = _build_portfolio_snapshot(db, companies=companies)
    if not portfolio_snapshot:
        result = _anomaly_summary_from_items('portfolio', [])
        return _set_timed_cache(cache_key, result) if companies is None else result

    anomaly_items: List[dict] = []
    watchlist_companies: List[dict] = []
    for company in companies:
        snapshot = _build_company_snapshot(db, company)
        if not snapshot:
            continue
        company_items = _company_anomaly_items(snapshot)
        anomaly_items.extend(company_items)
        if company_items:
            highest = sorted(company_items, key=lambda item: _priority_rank(item['severity']))[0]
            watchlist_companies.append(
                {
                    'company_id': company.id,
                    'company_name': company.name,
                    'sector': company.sector,
                    'top_anomaly': highest['metric_name'],
                    'severity': highest['severity'],
                }
            )

    anomaly_items.sort(key=lambda item: (_priority_rank(item['severity']), item['company_name'] or '', item['metric_name']))
    result = _anomaly_summary_from_items('portfolio', anomaly_items[:18], company_name='Portfolio')
    result['watchlist_companies'] = watchlist_companies[:6]
    return _set_timed_cache(cache_key, result) if companies is None else result


def _build_company_anomaly_summary(db: Session, company: Company) -> dict:
    cache_key = f'company_anomaly_summary:{company.id}'
    cached = _get_timed_cache(cache_key)
    if cached is not None:
        return cached

    snapshot = _build_company_snapshot(db, company)
    items = _company_anomaly_items(snapshot) if snapshot else []
    result = _anomaly_summary_from_items('company', items, company_name=company.name)
    return _set_timed_cache(cache_key, result)


def _query_ui_visible_companies(db: Session):
    query = db.query(Company)
    if EXCLUDE_NON_PROD_UI_ENTITIES:
        query = query.join(User, Company.user_id == User.id).filter(~build_non_prod_company_clause())
    return query


def _ui_visible_company_by_id(db: Session, company_id: int) -> Company | None:
    return _query_ui_visible_companies(db).filter(Company.id == company_id).first()


def _load_companies_with_related_data(db: Session) -> List[Company]:
    return (
        _query_ui_visible_companies(db)
        .options(
            selectinload(Company.submissions).selectinload(Submission.cycle),
            selectinload(Company.action_plans),
            selectinload(Company.review_actions),
            selectinload(Company.validation_flags),
        )
        .order_by(Company.name.asc())
        .all()
    )


def _load_companies_with_submission_data(db: Session) -> List[Company]:
    """
    Lean loader for dashboard/analytics surfaces that only need submissions.
    This avoids extra round trips for unrelated relations.
    """
    return (
        _query_ui_visible_companies(db)
        .options(selectinload(Company.submissions))
        .order_by(Company.name.asc())
        .all()
    )


def normalize_status_label(status: str | None) -> str:
    normalized = str(status or '').strip().lower()
    mapping = {
        'not started': 'Not Started',
        'in progress': 'In Progress',
        'submitted': 'Submitted',
        'under review': 'Submitted',
        'approved': 'Approved',
        'rejected': 'Rejected',
        'resubmission requested': 'In Progress',
        'pre-acquisition': 'Not Started',
        'active': 'In Progress',
    }
    return mapping.get(normalized, 'Not Started')


def parse_submission(submission: Submission | None) -> dict:
    if not submission:
        return {}
    try:
        payload = json.loads(submission.esg_data)
        return payload if isinstance(payload, dict) else {}
    except (TypeError, ValueError):
        return {}


def _percent_change(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)


def _trend_direction(current: float, previous: float) -> str:
    if current > previous:
        return 'up'
    if current < previous:
        return 'down'
    return 'neutral'


def _build_cycle_summaries(db: Session) -> list[dict]:
    cycles = (
        _apply_valid_cycle_year_filter(db.query(CollectionCycle))
        .order_by(CollectionCycle.cycle_year.asc(), CollectionCycle.id.asc())
        .all()
    )
    required_fields = [
        'scope_1_emissions',
        'scope_2_location_based',
        'scope_3_emissions',
        'total_ghg_emissions',
        'total_energy_consumption',
        'total_water_withdrawal',
        'total_waste_generated',
        'female_representation_percent',
        'trifr',
        'independent_board_members_percent',
    ]
    policy_fields = [
        'esg_policy_in_place',
        'whs_policy_in_place',
        'cybersecurity_policy_in_place',
        'anti_bribery_corruption_policy',
    ]

    submissions_by_cycle: Dict[int, List[Submission]] = {}
    submission_query = db.query(Submission).filter(Submission.cycle_id.is_not(None))
    if EXCLUDE_NON_PROD_UI_ENTITIES:
        submission_query = (
            submission_query
            .join(Company, Submission.company_id == Company.id)
            .join(User, Company.user_id == User.id)
            .filter(~build_non_prod_company_clause())
        )
    for submission in submission_query.order_by(Submission.cycle_id.asc(), Submission.id.asc()).all():
        if submission.cycle_id is None:
            continue
        submissions_by_cycle.setdefault(submission.cycle_id, []).append(submission)

    summaries: list[dict] = []
    for cycle in cycles:
        payloads = [
            payload
            for payload in (parse_submission(submission) for submission in submissions_by_cycle.get(cycle.id, []))
            if payload
        ]
        if not payloads:
            continue

        reporting_count = len(payloads)
        total_scope_1 = 0.0
        total_scope_2 = 0.0
        total_scope_3 = 0.0
        total_energy = 0.0
        total_water = 0.0
        total_waste = 0.0
        total_female_rep = 0.0
        total_trifr = 0.0
        governance_yes = 0.0
        governance_checks = 0.0
        score_e_total = 0.0
        score_s_total = 0.0
        score_g_total = 0.0
        score_total = 0.0
        completeness_total = 0.0
        confidence_total = 0.0
        accuracy_total = 0.0

        for payload in payloads:
            esg_score, e_score, s_score, g_score = score_company_payload(payload)
            scope_1 = safe_number(payload.get('scope_1_emissions'))
            scope_2 = safe_number(payload.get('scope_2_location_based'))
            scope_3 = safe_number(payload.get('scope_3_emissions'))
            total_ghg = safe_number(payload.get('total_ghg_emissions'))
            energy = safe_number(payload.get('total_energy_consumption'))
            renewable = safe_number(payload.get('renewable_energy_consumption'))
            water = safe_number(payload.get('total_water_withdrawal'))
            waste = safe_number(payload.get('total_waste_generated'))
            female_rep = safe_number(payload.get('female_representation_percent'))
            trifr = safe_number(payload.get('trifr'))
            turnover = safe_number(payload.get('employee_turnover_rate'))

            total_scope_1 += scope_1
            total_scope_2 += scope_2
            total_scope_3 += scope_3
            total_energy += energy
            total_water += water
            total_waste += waste
            total_female_rep += female_rep
            total_trifr += trifr
            score_e_total += e_score
            score_s_total += s_score
            score_g_total += g_score
            score_total += esg_score

            governance_yes += 1 if str(payload.get('esg_policy_in_place', '')).strip().lower() == 'yes' else 0
            governance_yes += 1 if str(payload.get('whs_policy_in_place', '')).strip().lower() == 'yes' else 0
            governance_yes += 1 if str(payload.get('cybersecurity_policy_in_place', '')).strip().lower() == 'yes' else 0
            governance_yes += 1 if str(payload.get('anti_bribery_corruption_policy', '')).strip().lower() == 'yes' else 0
            governance_checks += len(policy_fields)

            filled_fields = sum(1 for field in required_fields if payload.get(field) is not None)
            completeness_total += (filled_fields / len(required_fields)) * 100

            confidence_values = [str(value).strip().lower() for key, value in payload.items() if key.endswith('_confidence')]
            if confidence_values:
                measured_count = sum(1 for value in confidence_values if value == 'measured')
                confidence_total += (measured_count / len(confidence_values)) * 100

            scope_total = scope_1 + scope_2 + scope_3
            accuracy = 100.0
            if total_ghg > 0:
                delta = abs(total_ghg - scope_total) / max(total_ghg, 1)
                if delta > 0.05:
                    accuracy -= min(30, delta * 100)
            if renewable > energy and energy > 0:
                accuracy -= 10
            accuracy_total += clamp(accuracy)

        summaries.append(
            {
                'cycle_id': cycle.id,
                'cycle_year': cycle.cycle_year,
                'reporting_companies': reporting_count,
                'scope_1_total': round(total_scope_1, 2),
                'scope_2_total': round(total_scope_2, 2),
                'scope_3_total': round(total_scope_3, 2),
                'total_ghg': round(total_scope_1 + total_scope_2 + total_scope_3, 2),
                'total_energy': round(total_energy, 2),
                'total_water': round(total_water, 2),
                'total_waste': round(total_waste, 2),
                'average_female_representation': round(total_female_rep / reporting_count, 2),
                'trifr': round(total_trifr / reporting_count, 2),
                'governance_adoption_percent': round((governance_yes / governance_checks) * 100, 2) if governance_checks else 0.0,
                'portfolio_esg_score': round(score_total / reporting_count, 2),
                'score_breakdown': {
                    'E': round(score_e_total / reporting_count, 2),
                    'S': round(score_s_total / reporting_count, 2),
                    'G': round(score_g_total / reporting_count, 2),
                },
                'data_quality': {
                    'completeness': round(completeness_total / reporting_count, 2),
                    'accuracy': round(accuracy_total / reporting_count, 2),
                    'confidence': round(confidence_total / reporting_count, 2),
                },
            }
        )

    return summaries


def _build_cycle_emissions_trend(cycle_summaries: list[dict]) -> list[dict]:
    return [
        {
            'period': str(summary['cycle_year']),
            'total_emissions': round(summary['total_ghg'], 2),
        }
        for summary in cycle_summaries
    ]


def score_company_payload(payload: dict) -> tuple[float, float, float, float]:
    scope_1 = safe_number(payload.get('scope_1_emissions'))
    scope_2 = safe_number(payload.get('scope_2_location_based'))
    scope_3 = safe_number(payload.get('scope_3_emissions'))
    energy = safe_number(payload.get('total_energy_consumption'))
    renewable = safe_number(payload.get('renewable_energy_consumption'))
    female_rep = safe_number(payload.get('female_representation_percent'))
    trifr = safe_number(payload.get('trifr'))
    turnover = safe_number(payload.get('employee_turnover_rate'))
    independent_board = safe_number(payload.get('independent_board_members_percent'))
    corruption_cases = safe_number(payload.get('confirmed_cases_of_corruption'))

    renewable_ratio = (renewable / energy) if energy > 0 else 0
    scope_total = scope_1 + scope_2 + scope_3

    e_score = clamp(
        30
        + max(0, 35 - (scope_total / 60))
        + min(20, safe_number(payload.get('reduction_target_percent')) * 0.25)
        + min(15, renewable_ratio * 100 * 0.2)
    )
    s_score = clamp(
        25
        + min(25, female_rep * 0.35)
        + max(0, 20 - trifr * 2.5)
        + max(0, 15 - turnover * 0.3)
        + (15 if str(payload.get('whs_policy_in_place', '')).strip().lower() == 'yes' else 0)
    )
    g_score = clamp(
        (20 if str(payload.get('esg_policy_in_place', '')).strip().lower() == 'yes' else 0)
        + (20 if str(payload.get('board_level_esg_oversight', '')).strip().lower() == 'yes' else 0)
        + (20 if str(payload.get('cybersecurity_policy_in_place', '')).strip().lower() == 'yes' else 0)
        + (20 if str(payload.get('anti_bribery_corruption_policy', '')).strip().lower() == 'yes' else 0)
        + min(20, independent_board * 0.4)
        - min(10, corruption_cases * 2)
    )
    esg_score = round((0.45 * e_score) + (0.30 * s_score) + (0.25 * g_score), 2)
    return esg_score, e_score, s_score, g_score


def normalize_narrative_audience(value: Any) -> str:
    normalized = str(value or 'company').strip().lower()
    if normalized not in NARRATIVE_AUDIENCES:
        raise HTTPException(status_code=400, detail='Invalid narrative audience')
    return normalized


def normalize_narrative_tone(value: Any) -> str:
    normalized = str(value or 'board-ready').strip().lower()
    if normalized not in NARRATIVE_TONES:
        raise HTTPException(status_code=400, detail='Invalid narrative tone')
    return normalized


def normalize_action_plan_status(value: Any) -> str:
    normalized = str(value or '').strip().lower()
    if normalized in {'in progress', 'in_progress'}:
        return 'in progress'
    if normalized in {'completed', 'complete'}:
        return 'completed'
    return 'planned'


def get_framework_tags_for_audience(audience: str) -> List[str]:
    if audience == 'company':
        return ['GRI', 'TCFD', 'EDCI']
    if audience == 'lp':
        return ['SFDR', 'EDCI', 'TCFD']
    return ['TCFD', 'GRI', 'SFDR', 'EDCI']


def _tone_title(tone: str) -> str:
    return NARRATIVE_TONE_LABELS.get(tone, 'Board-ready')


def _tone_brief(tone: str, audience: str) -> str:
    if tone == 'lp-letter' or audience == 'lp':
        return 'Write as a concise LP letter with portfolio framing, downside watchpoints, and decision-useful commentary.'
    if tone == 'exec-summary':
        return 'Write as an executive summary with direct business language and short paragraphs.'
    return 'Write as a board-ready summary with clear strengths, risks, and next actions.'


def _framework_insertions(snapshot: dict, audience: str) -> dict:
    entity_label = snapshot.get('company_name') or 'this portfolio'
    metrics = snapshot.get('metrics') or {}
    female_representation = safe_number(
        snapshot.get('avg_female_representation', metrics.get('female_representation_percent'))
    )
    trifr = safe_number(snapshot.get('avg_trifr', metrics.get('trifr')))
    return {
        'TCFD': {
            'climate_risk': f"{entity_label} has approved climate data suitable for TCFD-style disclosure, including emissions, energy mix, and transition signals.",
            'governance': 'Refer to board oversight, policy adoption, and management controls.',
        },
        'GRI': {
            'workforce': f"GRI-style workforce disclosure can cite female representation at {female_representation:.1f}% and TRIFR at {trifr:.1f}.",
            'community': 'Use the approved submission to support community and social impact discussion.',
        },
        'SFDR': {
            'principal_adverse_impact': 'Use approved emissions, safety, and governance indicators to evidence principal adverse impact commentary.',
            'sustainability': 'The approved snapshot can support sustainability narrative in LP reporting.',
        },
        'EDCI': {
            'data_quality': f"Approved-data completeness and measured confidence are available for {entity_label}.",
            'comparability': 'Year-over-year comparisons are already precomputed for the approved submission.',
        },
    }


def _action_plan_summary(db: Session, company_id: int, plans: Optional[List[ActionPlan]] = None) -> dict:
    plans = sorted(plans if plans is not None else db.query(ActionPlan).filter(ActionPlan.company_id == company_id).all(), key=lambda plan: plan.created_at or datetime.min)
    if not plans:
        return {
            'total': 0,
            'planned': 0,
            'in_progress': 0,
            'completed': 0,
            'overdue': 0,
            'summary': 'No action plans have been logged yet.',
            'items': [],
        }
    planned = sum(1 for plan in plans if normalize_action_plan_status(plan.status) == 'planned')
    in_progress = sum(1 for plan in plans if normalize_action_plan_status(plan.status) == 'in progress')
    completed = sum(1 for plan in plans if normalize_action_plan_status(plan.status) == 'completed')
    today = datetime.utcnow().date()
    overdue = 0
    items = []
    for plan in plans:
        due_date = _parse_date_string(plan.target_completion_date)
        is_overdue = bool(due_date and due_date < today and normalize_action_plan_status(plan.status) != 'completed')
        overdue += 1 if is_overdue else 0
        items.append(
            {
                'initiative_name': plan.initiative_name,
                'status': normalize_action_plan_status(plan.status),
                'target_completion_date': plan.target_completion_date,
                'assigned_owner': plan.assigned_owner,
                'overdue': is_overdue,
            }
        )
    summary = (
        f"{completed} of {len(plans)} action plans are completed, {in_progress} are in progress, and {planned} remain planned."
    )
    if overdue:
        summary += f' {overdue} action plan(s) are overdue and should be highlighted in the narrative.'
    return {
        'total': len(plans),
        'planned': planned,
        'in_progress': in_progress,
        'completed': completed,
        'overdue': overdue,
        'summary': summary,
        'items': items[:5],
    }


def _parse_date_string(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    text_value = str(value).strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(text_value, fmt).date()
        except ValueError:
            continue
    return None


def _compact_float(value: Any, digits: int = 1) -> Optional[float]:
    number = _as_float(value)
    if number is None:
        return None
    return round(number, digits)


def _company_submission_payloads(company: Company) -> List[Submission]:
    return sorted(company.submissions or [], key=lambda item: item.id)


def _latest_approved_submission(company: Company) -> tuple[Optional[Submission], Optional[Submission]]:
    submissions = _company_submission_payloads(company)
    approved_submissions = [item for item in submissions if normalize_submission_status(item.status) == 'approved']
    if not approved_submissions:
        return None, None
    latest = approved_submissions[-1]
    previous = approved_submissions[-2] if len(approved_submissions) > 1 else None
    return latest, previous


def _safe_json_loads(text_value: str | None, default: Any) -> Any:
    if not text_value:
        return default
    try:
        parsed = json.loads(text_value)
        return parsed if parsed is not None else default
    except (TypeError, ValueError):
        return default


def _measure_confidence(payload: dict) -> dict:
    confidence_values = [str(value).strip().lower() for key, value in payload.items() if key.endswith('_confidence')]
    measured_count = sum(1 for value in confidence_values if value == 'measured')
    estimated_count = sum(1 for value in confidence_values if value == 'estimated')
    unavailable_count = sum(1 for value in confidence_values if value == 'not available')
    total = len(confidence_values)
    return {
        'total': total,
        'measured_count': measured_count,
        'estimated_count': estimated_count,
        'unavailable_count': unavailable_count,
        'measured_percent': round((measured_count / total) * 100, 2) if total else 0.0,
    }


def _build_company_snapshot(db: Session, company: Company) -> Optional[dict]:
    latest, previous = _latest_approved_submission(company)
    if not latest:
        return None

    latest_payload = parse_submission(latest)
    previous_payload = parse_submission(previous)
    if not latest_payload:
        return None

    esg_score, e_score, s_score, g_score = score_company_payload(latest_payload)
    current_year = latest.cycle.cycle_year if latest.cycle else _as_int(latest_payload.get('reporting_year')) or datetime.utcnow().year
    previous_year = previous.cycle.cycle_year if previous and previous.cycle else _as_int(previous_payload.get('reporting_year'))
    scope_1 = safe_number(latest_payload.get('scope_1_emissions'))
    scope_2 = safe_number(latest_payload.get('scope_2_location_based'))
    scope_3 = safe_number(latest_payload.get('scope_3_emissions'))
    total_ghg = safe_number(latest_payload.get('total_ghg_emissions'))
    energy = safe_number(latest_payload.get('total_energy_consumption'))
    renewable = safe_number(latest_payload.get('renewable_energy_consumption'))
    water = safe_number(latest_payload.get('total_water_withdrawal'))
    recycled_water = safe_number(latest_payload.get('water_recycled_reused'))
    waste = safe_number(latest_payload.get('total_waste_generated'))
    diverted_waste = safe_number(latest_payload.get('waste_diverted_from_landfill'))
    female_rep = safe_number(latest_payload.get('female_representation_percent'))
    female_leadership = safe_number(latest_payload.get('female_leadership_representation_percent'))
    trifr = safe_number(latest_payload.get('trifr'))
    turnover = safe_number(latest_payload.get('employee_turnover_rate'))
    independent_board = safe_number(latest_payload.get('independent_board_members_percent'))
    board_female = safe_number(latest_payload.get('female_board_members_percent'))
    board_members = safe_number(latest_payload.get('total_board_members'))
    corruption_cases = safe_number(latest_payload.get('confirmed_cases_of_corruption'))
    cyber_incidents = safe_number(latest_payload.get('cyber_incidents_in_reporting_period'))
    renewable_ratio = round((renewable / energy) * 100, 1) if energy else 0.0
    water_reuse_ratio = round((recycled_water / water) * 100, 1) if water else 0.0
    waste_diversion_ratio = round((diverted_waste / waste) * 100, 1) if waste else 0.0
    emissions_delta_pct = None
    if previous_payload:
        previous_total = safe_number(previous_payload.get('total_ghg_emissions'))
        if previous_total > 0:
            emissions_delta_pct = round(((total_ghg - previous_total) / previous_total) * 100, 2)

    policy_snapshot = {
        'esg_policy_in_place': _normalize_policy_status(latest_payload.get('esg_policy_in_place')),
        'whs_policy_in_place': _normalize_policy_status(latest_payload.get('whs_policy_in_place')),
        'cybersecurity_policy_in_place': _normalize_policy_status(latest_payload.get('cybersecurity_policy_in_place')),
        'anti_bribery_corruption_policy': _normalize_policy_status(latest_payload.get('anti_bribery_corruption_policy')),
        'board_level_esg_oversight': _normalize_policy_status(latest_payload.get('board_level_esg_oversight')),
        'esg_kpis_linked_to_remuneration': _normalize_policy_status(latest_payload.get('esg_kpis_linked_to_remuneration')),
        'air_quality_control_measures': _normalize_policy_status(latest_payload.get('air_quality_control_measures')),
    }

    confidence = _measure_confidence(latest_payload)
    narrative_signals = {
        'strengths': [],
        'watchouts': [],
        'opportunities': [],
    }

    if renewable_ratio >= 50:
        narrative_signals['strengths'].append(f'Renewable electricity covers {renewable_ratio:.1f}% of total energy use.')
    else:
        narrative_signals['opportunities'].append('Renewable energy uptake can be lifted to reduce exposure to purchased electricity.')
    if female_rep >= 40:
        narrative_signals['strengths'].append(f'Female representation sits at {female_rep:.1f}% across the workforce.')
    else:
        narrative_signals['opportunities'].append('Workforce gender balance remains a practical medium-term improvement area.')
    if trifr <= 2:
        narrative_signals['strengths'].append(f'TRIFR is low at {trifr:.1f}, indicating stronger safety performance.')
    elif trifr >= 5:
        narrative_signals['watchouts'].append(f'TRIFR remains elevated at {trifr:.1f}, so safety execution needs attention.')
    if corruption_cases > 0:
        narrative_signals['watchouts'].append(f'{int(corruption_cases)} confirmed corruption case(s) were recorded in the approved data.')
    if cyber_incidents > 0:
        narrative_signals['watchouts'].append(f'{int(cyber_incidents)} cyber incident(s) were reported in the approved period.')
    if board_members > 0 and independent_board > 50:
        narrative_signals['strengths'].append(f'Independent board representation is {independent_board:.1f}%.')
    elif board_members > 0:
        narrative_signals['opportunities'].append('Board independence can be strengthened further to improve governance resilience.')

    return {
        'company_id': company.id,
        'company_name': company.name,
        'sector': company.sector,
        'asset_class': company.asset_class,
        'geography': company.geography,
        'current_year': current_year,
        'previous_year': previous_year,
        'submission_id': latest.id,
        'current_status': normalize_submission_status(latest.status),
        'previous_status': normalize_submission_status(previous.status) if previous else None,
        'esg_score': esg_score,
        'e_score': e_score,
        's_score': s_score,
        'g_score': g_score,
        'metrics': {
            'scope_1_emissions': _compact_float(scope_1, 1),
            'scope_2_location_based': _compact_float(scope_2, 1),
            'scope_3_emissions': _compact_float(scope_3, 1),
            'total_ghg_emissions': _compact_float(total_ghg, 1),
            'emissions_delta_pct': emissions_delta_pct,
            'total_energy_consumption': _compact_float(energy, 1),
            'renewable_energy_consumption': _compact_float(renewable, 1),
            'renewable_ratio_percent': renewable_ratio,
            'total_water_withdrawal': _compact_float(water, 1),
            'water_recycled_reused': _compact_float(recycled_water, 1),
            'water_reuse_ratio_percent': water_reuse_ratio,
            'total_waste_generated': _compact_float(waste, 1),
            'waste_diverted_from_landfill': _compact_float(diverted_waste, 1),
            'waste_diversion_ratio_percent': waste_diversion_ratio,
            'female_representation_percent': _compact_float(female_rep, 1),
            'female_leadership_representation_percent': _compact_float(female_leadership, 1),
            'trifr': _compact_float(trifr, 2),
            'employee_turnover_rate': _compact_float(turnover, 1),
            'independent_board_members_percent': _compact_float(independent_board, 1),
            'female_board_members_percent': _compact_float(board_female, 1),
            'confirmed_cases_of_corruption': int(corruption_cases),
            'cyber_incidents_in_reporting_period': int(cyber_incidents),
        },
        'policy_snapshot': policy_snapshot,
        'confidence': confidence,
        'submission_notes': (latest_payload.get('submission_notes') or '').strip(),
        'narrative_signals': narrative_signals,
        'action_plan_summary': _action_plan_summary(db, company.id, plans=company.action_plans or []),
        'framework_tags': get_framework_tags_for_audience('company'),
    }


def _build_portfolio_snapshot(db: Session, companies: Optional[List[Company]] = None) -> Optional[dict]:
    cache_key = 'build_portfolio_snapshot'
    if companies is None:
        cached = _get_timed_cache(cache_key)
        if cached is not None:
            return cached

    companies = companies if companies is not None else _load_companies_with_related_data(db)
    approved_company_snapshots = []
    for company in companies:
        snapshot = _build_company_snapshot(db, company)
        if snapshot:
            approved_company_snapshots.append(snapshot)

    if not approved_company_snapshots:
        return None

    total_companies = len(companies)
    approved_company_count = len(approved_company_snapshots)
    total_esg_score = sum(item['esg_score'] for item in approved_company_snapshots)
    total_scope_1 = sum(safe_number(item['metrics']['scope_1_emissions']) for item in approved_company_snapshots)
    total_scope_2 = sum(safe_number(item['metrics']['scope_2_location_based']) for item in approved_company_snapshots)
    total_scope_3 = sum(safe_number(item['metrics']['scope_3_emissions']) for item in approved_company_snapshots)
    total_emissions = total_scope_1 + total_scope_2 + total_scope_3
    avg_female_rep = sum(safe_number(item['metrics']['female_representation_percent']) for item in approved_company_snapshots) / approved_company_count
    avg_trifr = sum(safe_number(item['metrics']['trifr']) for item in approved_company_snapshots) / approved_company_count
    avg_renewable_ratio = sum(safe_number(item['metrics']['renewable_ratio_percent']) for item in approved_company_snapshots) / approved_company_count
    avg_waste_diversion = sum(safe_number(item['metrics']['waste_diversion_ratio_percent']) for item in approved_company_snapshots) / approved_company_count
    avg_independent_board = sum(safe_number(item['metrics']['independent_board_members_percent']) for item in approved_company_snapshots) / approved_company_count
    avg_esg_score = total_esg_score / approved_company_count
    top_companies = sorted(approved_company_snapshots, key=lambda item: item['esg_score'], reverse=True)[:5]
    bottom_companies = sorted(approved_company_snapshots, key=lambda item: item['esg_score'])[:5]
    high_trifr_companies = [item for item in approved_company_snapshots if safe_number(item['metrics']['trifr']) >= 5]
    low_renewable_companies = [item for item in approved_company_snapshots if safe_number(item['metrics']['renewable_ratio_percent']) < 25]
    sectors: Dict[str, List[float]] = {}
    years = set()
    for item in approved_company_snapshots:
        sectors.setdefault(item['sector'], []).append(item['esg_score'])
        if item['current_year']:
            years.add(int(item['current_year']))

    sector_rankings = sorted(
        (
            {'sector': sector, 'avg_esg_score': round(sum(scores) / len(scores), 2), 'company_count': len(scores)}
            for sector, scores in sectors.items()
            if scores
        ),
        key=lambda item: item['avg_esg_score']
    )

    policy_adoption = {
        'esg_policy_in_place': round((sum(1 for item in approved_company_snapshots if _normalize_policy_status(item['policy_snapshot'].get('esg_policy_in_place')) == 'Yes') / approved_company_count) * 100, 1),
        'whs_policy_in_place': round((sum(1 for item in approved_company_snapshots if _normalize_policy_status(item['policy_snapshot'].get('whs_policy_in_place')) == 'Yes') / approved_company_count) * 100, 1),
        'cybersecurity_policy_in_place': round((sum(1 for item in approved_company_snapshots if _normalize_policy_status(item['policy_snapshot'].get('cybersecurity_policy_in_place')) == 'Yes') / approved_company_count) * 100, 1),
        'anti_bribery_corruption_policy': round((sum(1 for item in approved_company_snapshots if _normalize_policy_status(item['policy_snapshot'].get('anti_bribery_corruption_policy')) == 'Yes') / approved_company_count) * 100, 1),
    }

    confidence_samples = [item['confidence']['measured_percent'] for item in approved_company_snapshots if item['confidence']['total']]
    average_confidence = sum(confidence_samples) / len(confidence_samples) if confidence_samples else 0.0
    action_plan_total = 0
    action_plan_in_progress = 0
    action_plan_completed = 0
    action_plan_overdue = 0
    action_plan_items = []
    for item in approved_company_snapshots:
        action_plan_summary = item.get('action_plan_summary') or {}
        action_plan_total += int(action_plan_summary.get('total', 0) or 0)
        action_plan_in_progress += int(action_plan_summary.get('in_progress', 0) or 0)
        action_plan_completed += int(action_plan_summary.get('completed', 0) or 0)
        action_plan_overdue += int(action_plan_summary.get('overdue', 0) or 0)
        action_plan_items.extend(action_plan_summary.get('items', []))

    result = {
        'total_companies': total_companies,
        'approved_company_count': approved_company_count,
        'avg_esg_score': round(avg_esg_score, 2),
        'total_emissions': round(total_emissions, 2),
        'total_scope_1': round(total_scope_1, 2),
        'total_scope_2': round(total_scope_2, 2),
        'total_scope_3': round(total_scope_3, 2),
        'avg_female_representation': round(avg_female_rep, 2),
        'avg_trifr': round(avg_trifr, 2),
        'avg_renewable_ratio': round(avg_renewable_ratio, 2),
        'avg_waste_diversion': round(avg_waste_diversion, 2),
        'avg_independent_board': round(avg_independent_board, 2),
        'average_confidence': round(average_confidence, 2),
        'top_companies': [
            {
                'company_id': item['company_id'],
                'company_name': item['company_name'],
                'sector': item['sector'],
                'esg_score': item['esg_score'],
            }
            for item in top_companies
        ],
        'bottom_companies': [
            {
                'company_id': item['company_id'],
                'company_name': item['company_name'],
                'sector': item['sector'],
                'esg_score': item['esg_score'],
            }
            for item in bottom_companies
        ],
        'watchlist_companies': [
            {
                'company_id': item['company_id'],
                'company_name': item['company_name'],
                'sector': item['sector'],
                'reason': 'Elevated TRIFR' if safe_number(item['metrics']['trifr']) >= 5 else 'Low renewable energy share',
            }
            for item in (high_trifr_companies[:3] + [item for item in low_renewable_companies if item not in high_trifr_companies][:3])
        ],
        'sector_rankings': sector_rankings[:5],
        'policy_adoption': policy_adoption,
        'narrative_signals': {
            'strengths': [
                f'{approved_company_count} approved submissions are available for the narrative sample.',
                f'Average ESG score across approved companies is {avg_esg_score:.1f}.',
                f'Average renewable energy share is {avg_renewable_ratio:.1f}%.',
            ],
            'watchouts': [
                f'{len(high_trifr_companies)} approved company(ies) have TRIFR at or above 5.',
                f'{len(low_renewable_companies)} approved company(ies) still have renewable energy below 25% of total energy.',
            ] if (high_trifr_companies or low_renewable_companies) else [],
            'opportunities': [
                'Lift renewable energy adoption and improve workforce representation in lower-ranked sectors.',
                'Use the strongest performers as internal benchmarks for company feedback letters.',
            ],
        },
        'source_years': sorted(years),
        'source_company_count': approved_company_count,
        'source_submission_count': approved_company_count,
        'action_plan_summary': {
            'total': action_plan_total,
            'in_progress': action_plan_in_progress,
            'completed': action_plan_completed,
            'overdue': action_plan_overdue,
            'summary': (
                f'{action_plan_completed} of {action_plan_total} portfolio action plans are completed, '
                f'{action_plan_in_progress} are in progress, and {action_plan_overdue} are overdue.'
            ) if action_plan_total else 'No portfolio action plans have been logged yet.',
            'items': action_plan_items[:5],
        },
        'framework_tags': get_framework_tags_for_audience('lp'),
    }
    return _set_timed_cache(cache_key, result)


def _build_narrative_prompt(audience: str, scope: str, tone: str, context: dict) -> str:
    audience_notes = {
        'company': 'Write like a constructive feedback letter to a portfolio company.',
        'lp': 'Write like a portfolio update for an LP/investor pack.',
        'board': 'Write like a board pack summary for executives and directors.',
    }
    return (
        f'You are writing an ESG narrative summary for the {audience} audience.\n'
        f'{audience_notes.get(audience, audience_notes["board"])}\n'
        f'Tone: {_tone_title(tone)}. {_tone_brief(tone, audience)}\n'
        'Use only the approved data provided below. Do not invent facts or speculate. '
        'If a value is missing, say it plainly or omit it.\n'
        'Keep the language plain-English, concise, and businesslike. Avoid markdown, emojis, and generic filler.\n'
        'Prioritize decision-useful language: what changed, why it matters, and what should happen next.\n'
        'Weave in framework-aware language where relevant for TCFD, GRI, SFDR, and EDCI.\n'
        'Output requirements:\n'
        '- Return valid JSON only.\n'
        '- Headline: 8-14 words.\n'
        '- Summary: 2 short paragraphs, roughly 90-140 words total.\n'
        '- Highlights, watchouts, and recommendations: exactly 3 items each.\n'
        '- Each bullet should be one sentence and tied to approved data.\n'
        '- Keep the result readable in a board pack or investor letter without extra editing.\n'
        'Return valid JSON only with this exact shape:\n'
        '{'
        '"headline":"string",'
        '"summary":"string",'
        '"highlights":["string","string","string"],'
        '"watchouts":["string","string","string"],'
        '"recommendations":["string","string","string"]'
        '}\n'
        f'Decision brief:\n{_build_narrative_brief(context)}\n'
        f'Scope: {scope}\n'
        f'Approved data:\n{json.dumps(context, indent=2, sort_keys=True, default=str)}'
    )


def _extract_json_object(text_value: str) -> Optional[dict]:
    if not text_value:
        return None
    candidate = text_value.strip()
    if candidate.startswith('```'):
        candidate = re.sub(r'^```(?:json)?\s*', '', candidate, flags=re.IGNORECASE)
        candidate = re.sub(r'\s*```$', '', candidate)
    start = candidate.find('{')
    end = candidate.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = candidate[start:end + 1]
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError):
        return None


def _coerce_narrative_items(value: object) -> List[str]:
    if isinstance(value, (list, tuple)):
        source_items = value
    elif isinstance(value, str):
        source_items = [value]
    else:
        source_items = []

    items: List[str] = []
    for item in source_items:
        text = str(item).strip()
        if text and text not in items:
            items.append(text)
    return items


def _normalize_narrative_items(value: object, fallback_value: object, *, limit: int = 3) -> List[str]:
    items = _coerce_narrative_items(value)[:limit]
    if len(items) >= limit:
        return items[:limit]

    for fallback_item in _coerce_narrative_items(fallback_value):
        if len(items) >= limit:
            break
        if fallback_item not in items:
            items.append(fallback_item)
    return items[:limit]


def _build_narrative_brief(context: dict) -> str:
    company = context.get('company') or {}
    metrics = context.get('metrics') or {}
    action_plan_summary = context.get('action_plan_summary') or {}
    narrative_signals = context.get('narrative_signals') or {}
    framework_tags = context.get('framework_tags') or []

    def metric_text(label: str, value: object, suffix: str = '') -> str:
        if value is None or value == '':
            return f'{label}: n/a'
        try:
            numeric_value = float(value)
            rendered = f'{int(numeric_value)}' if numeric_value.is_integer() else f'{numeric_value:.1f}'
        except (TypeError, ValueError):
            rendered = str(value).strip()
        return f'{label}: {rendered}{suffix}'

    lines = [
        f"Audience: {context.get('audience')} | Tone: {_tone_title(context.get('tone') or 'board-ready')}",
        (
            'Entity: '
            f"{company.get('name') or 'n/a'} | "
            f"Sector: {company.get('sector') or 'n/a'} | "
            f"Asset class: {company.get('asset_class') or 'n/a'} | "
            f"Geography: {company.get('geography') or 'n/a'}"
        ),
    ]

    if company.get('current_year') is not None or company.get('previous_year') is not None:
        report_years = f"{company.get('current_year') or 'n/a'}"
        if company.get('previous_year'):
            report_years += f" vs {company.get('previous_year')}"
        lines.append(
            f"Reporting years: {report_years} | Status: {company.get('status') or 'n/a'} | "
            f"ESG score: {metric_text('', company.get('esg_score')).split(': ', 1)[-1]}"
        )

    metric_summary = [
        metric_text('Renewable energy', metrics.get('renewable_ratio_percent'), '%'),
        metric_text('Female representation', metrics.get('female_representation_percent'), '%'),
        metric_text('TRIFR', metrics.get('trifr')),
        metric_text('Emissions delta', metrics.get('emissions_delta_pct'), '%'),
    ]
    lines.append('Key metrics: ' + '; '.join(metric_summary))

    strengths = _coerce_narrative_items(narrative_signals.get('strengths'))[:2]
    watchouts = _coerce_narrative_items(narrative_signals.get('watchouts'))[:2]
    opportunities = _coerce_narrative_items(narrative_signals.get('opportunities'))[:2]
    lines.append(
        f"Signals: strengths={strengths or ['n/a']}; watchouts={watchouts or ['n/a']}; "
        f"opportunities={opportunities or ['n/a']}"
    )

    action_plan_text = action_plan_summary.get('summary') or 'No action plan summary is available.'
    lines.append(f"Action plan: {action_plan_text}")

    if action_plan_summary.get('items'):
        first_item = action_plan_summary['items'][0]
        lines.append(
            'Action plan example: '
            f"{first_item.get('initiative_name') or 'n/a'} "
            f"({first_item.get('status') or 'n/a'})"
        )

    lines.append(f"Framework tags: {', '.join(framework_tags) if framework_tags else 'n/a'}")
    lines.append(
        'Write a plain-English, decision-ready narrative that explains what changed, why it matters, '
        'and what should happen next. Use only approved data and do not invent missing facts.'
    )
    return '\n'.join(lines)


def _call_openai_summary(prompt: str, *, model: str = OPENAI_DEFAULT_MODEL) -> Optional[dict]:
    api_key = os.getenv('OPENAI_API_KEY', '').strip()
    if not api_key or OpenAI is None:
        return None

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model,
            input=prompt,
            temperature=0.2,
            max_output_tokens=900,
            text={
                'format': {
                    'type': 'json_object',
                },
            },
        )
        text_value = getattr(response, 'output_text', '') or ''
        parsed = _extract_json_object(text_value)
        return parsed if parsed else None
    except Exception:
        return None


def _build_fallback_company_narrative(snapshot: dict, audience: str, tone: str) -> dict:
    company_name = snapshot['company_name']
    metrics = snapshot['metrics']
    action_plan_summary = snapshot.get('action_plan_summary') or {}
    narrative = (
        f'{company_name} is reporting an approved ESG score of {snapshot["esg_score"]:.1f}/100 for {snapshot["current_year"]}. '
        f'The strongest signals are {metrics["renewable_ratio_percent"]:.1f}% renewable energy use, '
        f'{metrics["female_representation_percent"]:.1f}% female workforce representation, and '
        f'TRIFR at {metrics["trifr"]:.1f}. '
    )
    if snapshot['metrics']['emissions_delta_pct'] is not None:
        narrative += f'Total GHG emissions moved {snapshot["metrics"]["emissions_delta_pct"]:+.1f}% versus the prior approved submission. '
    if action_plan_summary.get('summary'):
        narrative += f'{action_plan_summary["summary"]} '
    if audience == 'company':
        narrative += 'The main feedback is to keep momentum on safety, emissions intensity, and governance controls.'
    elif audience == 'lp':
        narrative += 'From an LP perspective, the company shows credible progress with a manageable watchlist on operational execution.'
    else:
        narrative += 'For board reporting, the data supports a concise update with clear strengths and a small set of execution risks.'

    highlights = snapshot['narrative_signals']['strengths'][:3] or [
        f'Approved submission for {snapshot["current_year"]} is available.',
        f'ESG score is {snapshot["esg_score"]:.1f}/100.',
        f'Renewable energy share is {metrics["renewable_ratio_percent"]:.1f}%.',
    ]
    if action_plan_summary.get('items'):
        first_item = action_plan_summary['items'][0]
        highlights.append(f'Action plan focus: {first_item["initiative_name"]} ({first_item["status"]}).')
    watchouts = snapshot['narrative_signals']['watchouts'][:3] or [
        'No material watchouts were flagged in the approved data.',
    ]
    recommendations = snapshot['narrative_signals']['opportunities'][:3] or [
        'Continue improving data quality and maintain current momentum.',
    ]
    if tone == 'lp-letter':
        recommendations.insert(0, 'Use the approved snapshot as the basis for a short LP update and follow-up discussion.')
    elif tone == 'exec-summary':
        recommendations.insert(0, 'Keep the narrative short, direct, and suitable for leadership circulation.')
    return {
        'headline': f'{company_name}: approved ESG snapshot',
        'summary': narrative.strip(),
        'highlights': highlights[:3],
        'watchouts': watchouts[:3],
        'recommendations': recommendations[:3],
    }


def _build_fallback_portfolio_narrative(snapshot: dict, audience: str, tone: str) -> dict:
    prefix = 'LP portfolio' if audience == 'lp' else 'portfolio board'
    action_plan_summary = snapshot.get('action_plan_summary') or {}
    narrative = (
        f'The {prefix} view includes {snapshot["approved_company_count"]} approved submissions across {snapshot["total_companies"]} companies. '
        f'The average approved ESG score is {snapshot["avg_esg_score"]:.1f}/100, with total approved emissions of {snapshot["total_emissions"]:,.0f} tCO2e. '
        f'Average renewable energy share is {snapshot["avg_renewable_ratio"]:.1f}%, average female representation is {snapshot["avg_female_representation"]:.1f}%, '
        f'and average TRIFR is {snapshot["avg_trifr"]:.2f}.'
    )
    if action_plan_summary.get('summary'):
        narrative += f' {action_plan_summary["summary"]}'
    if audience == 'lp':
        narrative += ' The portfolio reads as stable, with clear leaders and a few operating risks to watch.'
    else:
        narrative += ' The narrative is suitable for board reporting and highlights where management attention should stay focused.'

    highlights = snapshot['narrative_signals']['strengths'][:3]
    watchouts = snapshot['narrative_signals']['watchouts'][:3] or [
        'No concentrated portfolio risks were detected in the approved-data sample.',
    ]
    recommendations = snapshot['narrative_signals']['opportunities'][:3]
    if snapshot['top_companies']:
        highlights.append(
            f'Top approved performer: {snapshot["top_companies"][0]["company_name"]} ({snapshot["top_companies"][0]["esg_score"]:.1f}/100).'
        )
    if snapshot['bottom_companies']:
        watchouts.append(
            f'Lowest approved performer: {snapshot["bottom_companies"][0]["company_name"]} ({snapshot["bottom_companies"][0]["esg_score"]:.1f}/100).'
        )
    if tone == 'exec-summary':
        recommendations.insert(0, 'Use the summary for leadership updates and keep the language concise.')
    return {
        'headline': f'{prefix.title()} ESG narrative summary',
        'summary': narrative.strip(),
        'highlights': highlights[:3],
        'watchouts': watchouts[:3],
        'recommendations': recommendations[:3] if recommendations else [
            'Use the approved-data snapshot to inform portfolio letters and board packs.',
        ],
    }


def _narrative_payload_dict(
    *,
    headline: str,
    summary: str,
    highlights: List[str],
    watchouts: List[str],
    recommendations: List[str],
) -> dict:
    return {
        'headline': str(headline or '').strip(),
        'summary': str(summary or '').strip(),
        'highlights': _coerce_narrative_items(highlights),
        'watchouts': _coerce_narrative_items(watchouts),
        'recommendations': _coerce_narrative_items(recommendations),
    }


def _normalize_narrative_payload(payload: Optional[dict], fallback_payload: dict) -> dict:
    safe_payload = payload if isinstance(payload, dict) else {}
    normalized = _narrative_payload_dict(
        headline=safe_payload.get('headline') or fallback_payload.get('headline') or '',
        summary=safe_payload.get('summary') or fallback_payload.get('summary') or '',
        highlights=_normalize_narrative_items(safe_payload.get('highlights'), fallback_payload.get('highlights')),
        watchouts=_normalize_narrative_items(safe_payload.get('watchouts'), fallback_payload.get('watchouts')),
        recommendations=_normalize_narrative_items(
            safe_payload.get('recommendations'),
            fallback_payload.get('recommendations'),
        ),
    )
    if not normalized['headline']:
        normalized['headline'] = fallback_payload.get('headline') or 'ESG narrative summary'
    if not normalized['summary']:
        normalized['summary'] = fallback_payload.get('summary') or 'Approved data is available, but the narrative text could not be generated.'
    return normalized


def _build_snapshot_signature(snapshot: Optional[dict]) -> str:
    if not isinstance(snapshot, dict) or not snapshot:
        return ''
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, default=str).encode('utf-8')
    ).hexdigest()


def _source_reference_from_snapshot(snapshot: Optional[dict]) -> tuple[str, List[int], int, int]:
    if not isinstance(snapshot, dict) or not snapshot:
        return '', [], 0, 0

    years = snapshot.get('source_years')
    if not years:
        current_year = snapshot.get('current_year')
        years = [current_year] if current_year else []
    normalized_years = sorted(
        {
            int(year)
            for year in years or []
            if str(year).strip().lstrip('-').isdigit()
        }
    )
    company_count = int(snapshot.get('source_company_count') or (1 if snapshot.get('company_id') else 0))
    submission_count = int(snapshot.get('source_submission_count') or (1 if snapshot.get('submission_id') else 0))
    return _build_snapshot_signature(snapshot), normalized_years, company_count, submission_count


def _missing_narrative_state(reason: Optional[str] = None) -> dict:
    return {
        'freshness_status': 'missing',
        'freshness_label': NARRATIVE_STATE_LABELS['missing'],
        'freshness_reason': reason,
        'latest_source_years': [],
        'latest_source_company_count': 0,
        'latest_source_submission_count': 0,
    }


def _build_narrative_freshness(
    record: NarrativeSummary,
    *,
    latest_snapshot_signature: str,
    latest_source_years: List[int],
    latest_source_company_count: int,
    latest_source_submission_count: int,
) -> dict:
    generation_context = _safe_json_loads(getattr(record, 'generation_context_json', None), {})
    saved_snapshot_signature = str(generation_context.get('snapshot_signature') or '').strip()
    saved_source_years = _narrative_source_years(record)
    reasons: List[str] = []

    if latest_snapshot_signature and saved_snapshot_signature and latest_snapshot_signature != saved_snapshot_signature:
        reasons.append('Approved data changed since this narrative was generated.')

    if saved_source_years != list(latest_source_years or []):
        reasons.append('Narrative years do not match the latest approved reporting context.')

    if int(getattr(record, 'source_company_count', 0) or 0) != int(latest_source_company_count or 0):
        reasons.append('Narrative company coverage no longer matches the latest approved scope.')

    if int(getattr(record, 'source_submission_count', 0) or 0) != int(latest_source_submission_count or 0):
        reasons.append('Narrative submission coverage no longer matches the latest approved scope.')

    freshness_status = 'stale' if reasons else 'current'
    return {
        'freshness_status': freshness_status,
        'freshness_label': NARRATIVE_STATE_LABELS[freshness_status],
        'freshness_reason': reasons[0] if reasons else 'Narrative matches the latest approved data.',
        'latest_source_years': list(latest_source_years or []),
        'latest_source_company_count': int(latest_source_company_count or 0),
        'latest_source_submission_count': int(latest_source_submission_count or 0),
    }


def _load_cached_narrative(
    db: Session,
    *,
    audience: str,
    scope: str,
    company_id: Optional[int],
    source_hash: str,
    tone: str,
) -> Optional[NarrativeSummary]:
    return (
        db.query(NarrativeSummary)
        .filter(
            NarrativeSummary.audience == audience,
            NarrativeSummary.scope == scope,
            NarrativeSummary.company_id == company_id,
            NarrativeSummary.source_hash == source_hash,
            NarrativeSummary.tone == tone,
            NarrativeSummary.provider != 'claude',
        )
        .order_by(NarrativeSummary.id.desc())
        .first()
    )


def _store_narrative_record(
    db: Session,
    *,
    audience: str,
    scope: str,
    tone: str,
    company_id: Optional[int],
    source_hash: str,
    model: Optional[str],
    source_years: List[int],
    source_company_count: int,
    source_submission_count: int,
    generated_payload: dict,
    generation_context: dict,
    framework_tags: List[str],
    status: str = 'generated',
) -> NarrativeSummary:
    record = NarrativeSummary(
        audience=audience,
        scope=scope,
        tone=tone,
        company_id=company_id,
        source_hash=source_hash,
        provider='openai' if model else 'fallback',
        model=model,
        status=status,
        headline=str(generated_payload.get('headline') or '').strip(),
        narrative=str(generated_payload.get('summary') or '').strip(),
        highlights_json=json.dumps(generated_payload.get('highlights') or []),
        watchouts_json=json.dumps(generated_payload.get('watchouts') or []),
        recommendations_json=json.dumps(generated_payload.get('recommendations') or []),
        source_years_json=json.dumps(source_years),
        framework_tags_json=json.dumps(framework_tags),
        generation_context_json=json.dumps(generation_context, sort_keys=True, default=str),
        generated_payload_json=json.dumps(generated_payload, sort_keys=True, default=str),
        edited_payload_json=json.dumps({}),
        published_payload_json=json.dumps({}),
        source_company_count=source_company_count,
        source_submission_count=source_submission_count,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _narrative_active_payload(record: NarrativeSummary) -> dict:
    published = _safe_json_loads(getattr(record, 'published_payload_json', None), {})
    edited = _safe_json_loads(getattr(record, 'edited_payload_json', None), {})
    generated = _safe_json_loads(getattr(record, 'generated_payload_json', None), {})
    payload = published if record.status == 'approved' and published else edited if edited else generated
    if not isinstance(payload, dict):
        payload = {}
    return _narrative_payload_dict(
        headline=payload.get('headline') or record.headline,
        summary=payload.get('summary') or record.narrative,
        highlights=payload.get('highlights') or _safe_json_loads(record.highlights_json, []),
        watchouts=payload.get('watchouts') or _safe_json_loads(record.watchouts_json, []),
        recommendations=payload.get('recommendations') or _safe_json_loads(record.recommendations_json, []),
    )


def _narrative_record_history_item(
    record: NarrativeSummary,
    *,
    company_name: str | None,
    latest_snapshot_signature: str = '',
    latest_source_years: Optional[List[int]] = None,
    latest_source_company_count: int = 0,
    latest_source_submission_count: int = 0,
) -> NarrativeHistoryItem:
    freshness = _build_narrative_freshness(
        record,
        latest_snapshot_signature=latest_snapshot_signature,
        latest_source_years=latest_source_years or [],
        latest_source_company_count=latest_source_company_count,
        latest_source_submission_count=latest_source_submission_count,
    )
    return NarrativeHistoryItem(
        narrative_id=record.id,
        audience=record.audience,
        scope=record.scope,
        tone=getattr(record, 'tone', 'board-ready'),
        status=getattr(record, 'status', 'generated'),
        company_id=record.company_id,
        company_name=company_name,
        generated_at=(record.created_at or datetime.utcnow()).isoformat(),
        updated_at=(record.updated_at or datetime.utcnow()).isoformat(),
        headline=getattr(record, 'headline', '') or '',
        source_years=_narrative_source_years(record),
        source_company_count=getattr(record, 'source_company_count', 0) or 0,
        source_submission_count=getattr(record, 'source_submission_count', 0) or 0,
        freshness_status=freshness['freshness_status'],
        freshness_label=freshness['freshness_label'],
        approved_by_role=getattr(record, 'approved_by_role', None),
        approved_at=(record.approved_at.isoformat() if getattr(record, 'approved_at', None) else None),
    )


def _narrative_record_response(
    record: NarrativeSummary,
    *,
    audience: str,
    scope: str,
    company_id: Optional[int],
    company_name: Optional[str],
    source_years: List[int],
    cached: bool,
    fallback_used: bool,
    can_edit: bool,
    can_approve: bool,
    can_export: bool,
    latest_snapshot_signature: str = '',
    latest_source_years: Optional[List[int]] = None,
    latest_source_company_count: int = 0,
    latest_source_submission_count: int = 0,
) -> NarrativeDetailResponse:
    payload = _narrative_active_payload(record)
    freshness = _build_narrative_freshness(
        record,
        latest_snapshot_signature=latest_snapshot_signature,
        latest_source_years=latest_source_years or source_years,
        latest_source_company_count=latest_source_company_count or record.source_company_count,
        latest_source_submission_count=latest_source_submission_count or record.source_submission_count,
    )
    return NarrativeDetailResponse(
        available=True,
        audience=audience,
        scope=scope,
        tone=getattr(record, 'tone', 'board-ready'),
        status=getattr(record, 'status', 'generated'),
        narrative_id=record.id,
        company_id=company_id,
        company_name=company_name,
        source_years=source_years,
        source_company_count=record.source_company_count,
        source_submission_count=record.source_submission_count,
        latest_source_years=freshness['latest_source_years'],
        latest_source_company_count=freshness['latest_source_company_count'],
        latest_source_submission_count=freshness['latest_source_submission_count'],
        provider=record.provider,
        model=record.model,
        cached=cached,
        fallback_used=fallback_used,
        freshness_status=freshness['freshness_status'],
        freshness_label=freshness['freshness_label'],
        freshness_reason=freshness['freshness_reason'],
        generated_at=(record.created_at or datetime.utcnow()).isoformat(),
        updated_at=(record.updated_at or datetime.utcnow()).isoformat(),
        headline=payload['headline'],
        summary=payload['summary'],
        highlights=payload['highlights'],
        watchouts=payload['watchouts'],
        recommendations=payload['recommendations'],
        message=None,
        framework_tags=_safe_json_loads(record.framework_tags_json, []),
        generated_payload=_safe_json_loads(record.generated_payload_json, {}),
        edited_payload=_safe_json_loads(record.edited_payload_json, {}),
        published_payload=_safe_json_loads(record.published_payload_json, {}),
        approved_by_role=getattr(record, 'approved_by_role', None),
        approved_at=(record.approved_at.isoformat() if getattr(record, 'approved_at', None) else None),
        edited_by_role=getattr(record, 'edited_by_role', None),
        edited_at=(record.edited_at.isoformat() if getattr(record, 'edited_at', None) else None),
        can_edit=can_edit,
        can_approve=can_approve,
        can_export=can_export,
    )


def _narrative_response_from_payload(
    *,
    audience: str,
    scope: str,
    tone: str,
    company_id: Optional[int],
    company_name: Optional[str],
    payload: dict,
    source_years: List[int],
    source_company_count: int,
    source_submission_count: int,
    provider: str,
    model: Optional[str],
    cached: bool,
    fallback_used: bool,
    can_edit: bool,
    can_approve: bool,
    can_export: bool,
    latest_source_years: Optional[List[int]] = None,
    latest_source_company_count: int = 0,
    latest_source_submission_count: int = 0,
) -> NarrativeDetailResponse:
    safe_payload = _narrative_payload_dict(
        headline=payload.get('headline') or '',
        summary=payload.get('summary') or '',
        highlights=payload.get('highlights') or [],
        watchouts=payload.get('watchouts') or [],
        recommendations=payload.get('recommendations') or [],
    )
    return NarrativeDetailResponse(
        available=True,
        audience=audience,
        scope=scope,
        tone=tone,
        status='generated',
        narrative_id=0,
        company_id=company_id,
        company_name=company_name,
        source_years=source_years,
        source_company_count=source_company_count,
        source_submission_count=source_submission_count,
        latest_source_years=list(latest_source_years or source_years),
        latest_source_company_count=int(latest_source_company_count or source_company_count),
        latest_source_submission_count=int(latest_source_submission_count or source_submission_count),
        provider=provider,
        model=model,
        cached=cached,
        fallback_used=fallback_used,
        freshness_status='current',
        freshness_label=NARRATIVE_STATE_LABELS['current'],
        freshness_reason='Narrative matches the latest approved data.',
        generated_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat(),
        headline=safe_payload['headline'],
        summary=safe_payload['summary'],
        highlights=safe_payload['highlights'],
        watchouts=safe_payload['watchouts'],
        recommendations=safe_payload['recommendations'],
        message=None,
        framework_tags=get_framework_tags_for_audience(audience),
        generated_payload=safe_payload,
        edited_payload={},
        published_payload={},
        approved_by_role=None,
        approved_at=None,
        edited_by_role=None,
        edited_at=None,
        can_edit=can_edit,
        can_approve=can_approve,
        can_export=can_export,
    )


def _narrative_unavailable_response(*, audience: str, scope: str, tone: str, company_id: Optional[int], company_name: Optional[str], message: str) -> NarrativeSummaryResponse:
    missing_state = _missing_narrative_state(message)
    return NarrativeDetailResponse(
        available=False,
        audience=audience,
        scope=scope,
        tone=tone,
        status='generated',
        narrative_id=0,
        company_id=company_id,
        company_name=company_name,
        source_years=[],
        source_company_count=0,
        source_submission_count=0,
        latest_source_years=missing_state['latest_source_years'],
        latest_source_company_count=missing_state['latest_source_company_count'],
        latest_source_submission_count=missing_state['latest_source_submission_count'],
        provider='openai',
        model=OPENAI_DEFAULT_MODEL,
        cached=False,
        fallback_used=False,
        freshness_status=missing_state['freshness_status'],
        freshness_label=missing_state['freshness_label'],
        freshness_reason=missing_state['freshness_reason'],
        generated_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat(),
        headline='',
        summary='',
        highlights=[],
        watchouts=[],
        recommendations=[],
        message=message,
        framework_tags=get_framework_tags_for_audience(audience),
        generated_payload={},
        edited_payload={},
        published_payload={},
        approved_by_role=None,
        approved_at=None,
        edited_by_role=None,
        edited_at=None,
        can_edit=False,
        can_approve=False,
        can_export=False,
    )


def _build_narrative_context(snapshot: dict, *, audience: str, tone: str) -> dict:
    return {
        'audience': audience,
        'tone': tone,
        'snapshot_signature': _build_snapshot_signature(snapshot),
        'framework_tags': snapshot.get('framework_tags') or get_framework_tags_for_audience(audience),
        'framework_insertions': _framework_insertions(snapshot, audience),
        'action_plan_summary': snapshot.get('action_plan_summary') or {},
        'narrative_signals': snapshot.get('narrative_signals') or {},
        'company': {
            'id': snapshot.get('company_id'),
            'name': snapshot.get('company_name'),
            'sector': snapshot.get('sector'),
            'asset_class': snapshot.get('asset_class'),
            'geography': snapshot.get('geography'),
            'current_year': snapshot.get('current_year'),
            'previous_year': snapshot.get('previous_year'),
            'status': snapshot.get('current_status'),
            'esg_score': snapshot.get('esg_score'),
        },
        'metrics': snapshot.get('metrics') or {},
        'policy_snapshot': snapshot.get('policy_snapshot') or {},
        'confidence': snapshot.get('confidence') or {},
    }


def build_narrative_summary(
    db: Session,
    *,
    audience: str,
    role: str,
    email: str | None,
    company_id: Optional[int] = None,
    tone: str = 'board-ready',
    force_refresh: bool = False,
) -> NarrativeSummaryResponse:
    if role not in {'company', 'manager', 'investor'}:
        raise HTTPException(status_code=401, detail='User role header required')

    normalized_audience = normalize_narrative_audience(audience)
    normalized_tone = normalize_narrative_tone(tone)
    scope = NARRATIVE_SCOPE_BY_AUDIENCE[normalized_audience]

    if scope == 'company':
        if role == 'investor':
            raise HTTPException(status_code=403, detail='Investors cannot access company-level narrative summaries')
        target_company: Optional[Company] = None
        if company_id is not None:
            target_company = (
                _ui_visible_company_by_id(db, company_id)
                if role != 'company'
                else db.query(Company).filter(Company.id == company_id).first()
            )
            if not target_company:
                raise HTTPException(status_code=404, detail='Company not found')
            enforce_company_scope_for_path(db, role=role, user_email=email, company_id=target_company.id)
        else:
            if role != 'company':
                raise HTTPException(status_code=400, detail='company_id is required for manager company-level summaries')
            if not email:
                raise HTTPException(status_code=401, detail='Email header required')
            user = find_request_user(db, email)
            if not user:
                raise HTTPException(status_code=404, detail='User not found')
            target_company = db.query(Company).filter(Company.user_id == user.id).first()
            if not target_company:
                raise HTTPException(status_code=404, detail='No company associated with this user')

        snapshot = _build_company_snapshot(db, target_company)
        if not snapshot:
            return _narrative_unavailable_response(
                audience=normalized_audience,
                scope=scope,
                tone=normalized_tone,
                company_id=target_company.id,
                company_name=target_company.name,
                message='No approved submission is available yet. The narrative unlocks after a submission is approved.',
            )

        context = _build_narrative_context(snapshot, audience=normalized_audience, tone=normalized_tone)
        latest_snapshot_signature, latest_source_years, latest_source_company_count, latest_source_submission_count = _source_reference_from_snapshot(snapshot)
        source_hash = hashlib.sha256(json.dumps({'snapshot': snapshot, 'tone': normalized_tone}, sort_keys=True, default=str).encode('utf-8')).hexdigest()
        if not force_refresh:
            cached_record = _load_cached_narrative(
                db,
                audience=normalized_audience,
                scope=scope,
                company_id=target_company.id,
                source_hash=source_hash,
                tone=normalized_tone,
            )
            if cached_record:
                return _narrative_record_response(
                    cached_record,
                    audience=normalized_audience,
                    scope=scope,
                    company_id=target_company.id,
                    company_name=target_company.name,
                    source_years=latest_source_years,
                    cached=True,
                    fallback_used=False,
                    can_edit=role == 'manager',
                    can_approve=role == 'manager',
                    can_export=True,
                    latest_snapshot_signature=latest_snapshot_signature,
                    latest_source_years=latest_source_years,
                    latest_source_company_count=latest_source_company_count,
                    latest_source_submission_count=latest_source_submission_count,
                )

        prompt = _build_narrative_prompt(normalized_audience, scope, normalized_tone, context)
        openai_payload = _call_openai_summary(prompt)
        fallback_payload = _build_fallback_company_narrative(snapshot, normalized_audience, normalized_tone)
        normalized_payload = _normalize_narrative_payload(openai_payload, fallback_payload)

        record = _store_narrative_record(
            db,
            audience=normalized_audience,
            scope=scope,
            tone=normalized_tone,
            company_id=target_company.id,
            source_hash=source_hash,
            model=OPENAI_DEFAULT_MODEL if openai_payload else None,
            source_years=latest_source_years,
            source_company_count=latest_source_company_count,
            source_submission_count=latest_source_submission_count,
            generated_payload=normalized_payload,
            generation_context=context,
            framework_tags=context.get('framework_tags') or [],
            status='generated',
        )
        return _narrative_record_response(
            record,
            audience=normalized_audience,
            scope=scope,
            company_id=target_company.id,
            company_name=target_company.name,
            source_years=latest_source_years,
            cached=False,
            fallback_used=not bool(openai_payload),
            can_edit=role == 'manager',
            can_approve=role == 'manager',
            can_export=True,
            latest_snapshot_signature=latest_snapshot_signature,
            latest_source_years=latest_source_years,
            latest_source_company_count=latest_source_company_count,
            latest_source_submission_count=latest_source_submission_count,
        )

    if role == 'company':
        raise HTTPException(status_code=403, detail='Company users cannot access portfolio-level narrative summaries')

    snapshot = _build_portfolio_snapshot(db)
    if not snapshot:
        return _narrative_unavailable_response(
            audience=normalized_audience,
            scope=scope,
            tone=normalized_tone,
            company_id=None,
            company_name=None,
            message='No approved submissions are available yet. The narrative unlocks after at least one submission is approved.',
        )

    context = _build_narrative_context(snapshot, audience=normalized_audience, tone=normalized_tone)
    latest_snapshot_signature, latest_source_years, latest_source_company_count, latest_source_submission_count = _source_reference_from_snapshot(snapshot)
    source_hash = hashlib.sha256(json.dumps({'snapshot': snapshot, 'tone': normalized_tone}, sort_keys=True, default=str).encode('utf-8')).hexdigest()
    if not force_refresh:
        cached_record = _load_cached_narrative(
            db,
            audience=normalized_audience,
            scope=scope,
            company_id=None,
            source_hash=source_hash,
            tone=normalized_tone,
        )
        if cached_record:
            return _narrative_record_response(
                cached_record,
                audience=normalized_audience,
                scope=scope,
                company_id=None,
                company_name=None,
                source_years=latest_source_years,
                cached=True,
                fallback_used=False,
                can_edit=role == 'manager',
                can_approve=role == 'manager',
                can_export=True,
                latest_snapshot_signature=latest_snapshot_signature,
                latest_source_years=latest_source_years,
                latest_source_company_count=latest_source_company_count,
                latest_source_submission_count=latest_source_submission_count,
            )

    prompt = _build_narrative_prompt(normalized_audience, scope, normalized_tone, context)
    openai_payload = _call_openai_summary(prompt)
    fallback_payload = _build_fallback_portfolio_narrative(snapshot, normalized_audience, normalized_tone)
    normalized_payload = _normalize_narrative_payload(openai_payload, fallback_payload)

    record = _store_narrative_record(
        db,
        audience=normalized_audience,
        scope=scope,
        tone=normalized_tone,
        company_id=None,
        source_hash=source_hash,
        model=OPENAI_DEFAULT_MODEL if openai_payload else None,
        source_years=latest_source_years,
        source_company_count=latest_source_company_count,
        source_submission_count=latest_source_submission_count,
        generated_payload=normalized_payload,
        generation_context=context,
        framework_tags=context.get('framework_tags') or [],
        status='generated',
    )
    return _narrative_record_response(
        record,
        audience=normalized_audience,
        scope=scope,
        company_id=None,
        company_name=None,
        source_years=latest_source_years,
        cached=False,
        fallback_used=not bool(openai_payload),
        can_edit=role == 'manager',
        can_approve=role == 'manager',
        can_export=True,
        latest_snapshot_signature=latest_snapshot_signature,
        latest_source_years=latest_source_years,
        latest_source_company_count=latest_source_company_count,
        latest_source_submission_count=latest_source_submission_count,
    )


def _get_narrative_record_or_404(db: Session, narrative_id: int) -> NarrativeSummary:
    record = db.query(NarrativeSummary).filter(NarrativeSummary.id == narrative_id).first()
    if not record:
        raise HTTPException(status_code=404, detail='Narrative summary not found')
    return record


def _narrative_source_years(record: NarrativeSummary) -> List[int]:
    years = _safe_json_loads(record.source_years_json, [])
    return [int(year) for year in years if str(year).strip().isdigit()]


def _render_narrative_file_lines(record: NarrativeSummary) -> List[str]:
    payload = _narrative_active_payload(record)
    lines = [
        'ESG Narrative Summary',
        f'Headline: {payload["headline"]}',
        f'Audience: {record.audience}',
        f'Tone: {_tone_title(getattr(record, "tone", "board-ready"))}',
        f'Status: {getattr(record, "status", "generated")}',
        f'Generated at: {(record.created_at or datetime.utcnow()).strftime("%Y-%m-%d %H:%M:%S UTC")}',
        '',
        'Summary:',
        payload['summary'],
        '',
        'Highlights:',
    ]
    lines.extend([f'- {item}' for item in (payload['highlights'][:3] or ['None'])])
    lines.append('')
    lines.append('Watchouts:')
    lines.extend([f'- {item}' for item in (payload['watchouts'][:3] or ['None'])])
    lines.append('')
    lines.append('Next Steps:')
    lines.extend([f'- {item}' for item in (payload['recommendations'][:3] or ['None'])])
    return lines


def _authorize_narrative_record_access(
    db: Session,
    *,
    record: NarrativeSummary,
    role: str,
    email: str | None,
) -> None:
    normalized_role = normalize_role(role)
    if record.scope == 'portfolio':
        if normalized_role == 'company':
            raise HTTPException(status_code=403, detail='Company users cannot access portfolio narrative records')
        return

    if normalized_role == 'investor':
        raise HTTPException(status_code=403, detail='Investors cannot access company narrative records')

    if normalized_role == 'manager':
        return

    if normalized_role != 'company':
        raise HTTPException(status_code=403, detail='Narrative access is restricted')

    if not email:
        raise HTTPException(status_code=401, detail='Email header required')

    user = find_request_user(db, email)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')

    company = db.query(Company).filter(Company.user_id == user.id).first()
    if not company or company.id != record.company_id:
        raise HTTPException(status_code=403, detail='You do not have access to this narrative record')


def _latest_reference_for_narrative_record(db: Session, record: NarrativeSummary) -> tuple[str, List[int], int, int]:
    if record.scope == 'company' and record.company_id:
        company = db.query(Company).filter(Company.id == record.company_id).first()
        snapshot = _build_company_snapshot(db, company) if company else None
    else:
        snapshot = _build_portfolio_snapshot(db)
    return _source_reference_from_snapshot(snapshot)


@app.get('/narrative/history', response_model=NarrativeHistoryResponse)
def narrative_history(
    audience: str = Query(default='board'),
    company_id: int | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=25),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    normalized_audience = normalize_narrative_audience(audience)
    scope = NARRATIVE_SCOPE_BY_AUDIENCE[normalized_audience]

    query = db.query(NarrativeSummary).filter(
        NarrativeSummary.audience == normalized_audience,
        NarrativeSummary.scope == scope,
    )

    if scope == 'company':
        if role == 'investor':
            raise HTTPException(status_code=403, detail='Investors cannot access company narrative history')
        if company_id is not None:
            query = query.filter(NarrativeSummary.company_id == company_id)
        elif role == 'company':
            if not email:
                raise HTTPException(status_code=401, detail='Email header required')
            user = find_request_user(db, email)
            if not user:
                raise HTTPException(status_code=404, detail='User not found')
            company = db.query(Company).filter(Company.user_id == user.id).first()
            if not company:
                raise HTTPException(status_code=404, detail='No company associated with this user')
            query = query.filter(NarrativeSummary.company_id == company.id)
        elif role != 'manager':
            raise HTTPException(status_code=403, detail='Narrative history access is restricted')
    elif role == 'company':
        raise HTTPException(status_code=403, detail='Company users cannot access portfolio narrative history')

    records = query.order_by(NarrativeSummary.updated_at.desc(), NarrativeSummary.id.desc()).limit(limit).all()
    latest_snapshot_signature = ''
    latest_source_years: List[int] = []
    latest_source_company_count = 0
    latest_source_submission_count = 0
    if scope == 'company':
        reference_company_id = company_id or (records[0].company_id if records else None)
        if reference_company_id:
            company = db.query(Company).filter(Company.id == reference_company_id).first()
            latest_snapshot_signature, latest_source_years, latest_source_company_count, latest_source_submission_count = _source_reference_from_snapshot(
                _build_company_snapshot(db, company) if company else None
            )
    else:
        latest_snapshot_signature, latest_source_years, latest_source_company_count, latest_source_submission_count = _source_reference_from_snapshot(
            _build_portfolio_snapshot(db)
        )

    items = [
        _narrative_record_history_item(
            record,
            company_name=record.company.name if record.company else None,
            latest_snapshot_signature=latest_snapshot_signature,
            latest_source_years=latest_source_years,
            latest_source_company_count=latest_source_company_count,
            latest_source_submission_count=latest_source_submission_count,
        )
        for record in records
    ]
    return NarrativeHistoryResponse(
        available=True,
        audience=normalized_audience,
        scope=scope,
        items=items,
        message=None,
    )


@app.post('/narrative/generate', response_model=NarrativeDetailResponse)
def generate_narrative_summary(
    payload: NarrativeGenerateRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    return build_narrative_summary(
        db,
        audience=payload.audience,
        role=role,
        email=email,
        company_id=payload.company_id,
        tone=payload.tone,
        force_refresh=payload.force_refresh,
    )


@app.get('/narrative/{narrative_id}', response_model=NarrativeDetailResponse)
def get_narrative_summary(
    narrative_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    record = _get_narrative_record_or_404(db, narrative_id)
    _authorize_narrative_record_access(db, record=record, role=role, email=email)
    company_name = record.company.name if record.company else None
    latest_snapshot_signature, latest_source_years, latest_source_company_count, latest_source_submission_count = _latest_reference_for_narrative_record(db, record)
    return _narrative_record_response(
        record,
        audience=record.audience,
        scope=record.scope,
        company_id=record.company_id,
        company_name=company_name,
        source_years=_narrative_source_years(record),
        cached=True,
        fallback_used=record.provider != 'openai',
        can_edit=normalize_role(role) == 'manager',
        can_approve=normalize_role(role) == 'manager',
        can_export=True,
        latest_snapshot_signature=latest_snapshot_signature,
        latest_source_years=latest_source_years,
        latest_source_company_count=latest_source_company_count,
        latest_source_submission_count=latest_source_submission_count,
    )


@app.patch('/narrative/{narrative_id}', response_model=NarrativeDetailResponse, dependencies=[Depends(require_manager)])
def update_narrative_summary(
    narrative_id: int,
    payload: NarrativeUpdateRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
):
    record = _get_narrative_record_or_404(db, narrative_id)
    current_payload = _narrative_active_payload(record)
    merged_payload = _narrative_payload_dict(
        headline=payload.headline or current_payload['headline'],
        summary=payload.summary or current_payload['summary'],
        highlights=payload.highlights or current_payload['highlights'],
        watchouts=payload.watchouts or current_payload['watchouts'],
        recommendations=payload.recommendations or current_payload['recommendations'],
    )
    record.headline = merged_payload['headline']
    record.narrative = merged_payload['summary']
    record.highlights_json = json.dumps(merged_payload['highlights'])
    record.watchouts_json = json.dumps(merged_payload['watchouts'])
    record.recommendations_json = json.dumps(merged_payload['recommendations'])
    if payload.tone:
        record.tone = normalize_narrative_tone(payload.tone)
    record.edited_payload_json = json.dumps(merged_payload, sort_keys=True, default=str)
    record.edited_by_role = role
    record.edited_at = datetime.utcnow()
    record.status = 'edited'
    record.approved_by_role = None
    record.approved_at = None
    record.published_payload_json = json.dumps({})
    db.commit()
    db.refresh(record)
    latest_snapshot_signature, latest_source_years, latest_source_company_count, latest_source_submission_count = _latest_reference_for_narrative_record(db, record)
    return _narrative_record_response(
        record,
        audience=record.audience,
        scope=record.scope,
        company_id=record.company_id,
        company_name=record.company.name if record.company else None,
        source_years=_narrative_source_years(record),
        cached=False,
        fallback_used=record.provider != 'openai',
        can_edit=True,
        can_approve=True,
        can_export=True,
        latest_snapshot_signature=latest_snapshot_signature,
        latest_source_years=latest_source_years,
        latest_source_company_count=latest_source_company_count,
        latest_source_submission_count=latest_source_submission_count,
    )


@app.post('/narrative/{narrative_id}/approve', response_model=NarrativeDetailResponse, dependencies=[Depends(require_manager)])
def approve_narrative_summary(
    narrative_id: int,
    payload: NarrativeApproveRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
):
    record = _get_narrative_record_or_404(db, narrative_id)
    active_payload = _narrative_active_payload(record)
    record.published_payload_json = json.dumps(active_payload, sort_keys=True, default=str)
    record.status = 'approved' if payload.approved else 'generated'
    record.approved_by_role = role if payload.approved else None
    record.approved_at = datetime.utcnow() if payload.approved else None
    db.commit()
    db.refresh(record)
    latest_snapshot_signature, latest_source_years, latest_source_company_count, latest_source_submission_count = _latest_reference_for_narrative_record(db, record)
    return _narrative_record_response(
        record,
        audience=record.audience,
        scope=record.scope,
        company_id=record.company_id,
        company_name=record.company.name if record.company else None,
        source_years=_narrative_source_years(record),
        cached=False,
        fallback_used=record.provider != 'openai',
        can_edit=True,
        can_approve=True,
        can_export=True,
        latest_snapshot_signature=latest_snapshot_signature,
        latest_source_years=latest_source_years,
        latest_source_company_count=latest_source_company_count,
        latest_source_submission_count=latest_source_submission_count,
    )


@app.get('/narrative/{narrative_id}/export', response_model=NarrativeExportResponse, dependencies=[Depends(require_manager)])
def export_narrative_summary(
    narrative_id: int,
    db: Session = Depends(get_db),
):
    record = _get_narrative_record_or_404(db, narrative_id)
    file_name = f'narrative_{record.id}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.pdf'
    artifact = save_export_artifact(
        file_name,
        build_simple_pdf(_render_narrative_file_lines(record)),
        'application/pdf',
    )
    return NarrativeExportResponse(
        narrative_id=record.id,
        file_name=file_name,
        file_path=str(artifact['file_path']),
        download_url=str(artifact['download_url']),
        content_type='application/pdf',
    )


def build_investor_analytics(db: Session, companies: Optional[List[Company]] = None, cycle_summaries: Optional[List[dict]] = None) -> dict:
    cache_key = 'build_investor_analytics'
    if companies is None and cycle_summaries is None:
        cached = _get_timed_cache(cache_key)
        if cached is not None:
            return cached

    companies = companies if companies is not None else _load_companies_with_related_data(db)
    cycle_summaries = cycle_summaries if cycle_summaries is not None else _build_cycle_summaries(db)

    status_counts = {
        'Not Started': 0,
        'In Progress': 0,
        'Submitted': 0,
        'Approved': 0,
        'Rejected': 0,
    }

    required_fields = [
        'scope_1_emissions',
        'scope_2_location_based',
        'scope_3_emissions',
        'total_ghg_emissions',
        'total_energy_consumption',
        'total_water_withdrawal',
        'total_waste_generated',
        'female_representation_percent',
        'trifr',
        'independent_board_members_percent',
    ]

    company_scores = []
    sector_scores = {}
    total_submissions = 0
    reporting_companies = 0
    total_scope_1 = 0.0
    total_scope_2 = 0.0
    total_scope_3 = 0.0
    total_energy = 0.0
    total_water = 0.0
    total_waste = 0.0
    total_female_rep = 0.0
    total_trifr = 0.0
    governance_yes = 0.0
    governance_checks = 0.0
    score_e_total = 0.0
    score_s_total = 0.0
    score_g_total = 0.0
    score_total = 0.0
    completeness_total = 0.0
    confidence_total = 0.0
    accuracy_total = 0.0
    high_variance_count = 0

    for company in companies:
        submissions = company.submissions or []
        total_submissions += len(submissions)
        latest = submissions[-1] if submissions else None
        previous = submissions[-2] if len(submissions) > 1 else None

        status = normalize_status_label((latest.status if latest else company.current_status))
        status_counts[status] = status_counts.get(status, 0) + 1
        payload = parse_submission(latest)
        previous_payload = parse_submission(previous)
        if not payload:
            continue

        reporting_companies += 1

        scope_1 = safe_number(payload.get('scope_1_emissions'))
        scope_2 = safe_number(payload.get('scope_2_location_based'))
        scope_3 = safe_number(payload.get('scope_3_emissions'))
        total_ghg = safe_number(payload.get('total_ghg_emissions'))
        energy = safe_number(payload.get('total_energy_consumption'))
        renewable = safe_number(payload.get('renewable_energy_consumption'))
        water = safe_number(payload.get('total_water_withdrawal'))
        waste = safe_number(payload.get('total_waste_generated'))
        female_rep = safe_number(payload.get('female_representation_percent'))
        trifr = safe_number(payload.get('trifr'))
        independent_board = safe_number(payload.get('independent_board_members_percent'))
        turnover = safe_number(payload.get('employee_turnover_rate'))
        corruption_cases = safe_number(payload.get('confirmed_cases_of_corruption'))

        total_scope_1 += scope_1
        total_scope_2 += scope_2
        total_scope_3 += scope_3
        total_energy += energy
        total_water += water
        total_waste += waste
        total_female_rep += female_rep
        total_trifr += trifr

        renewable_ratio = (renewable / energy) if energy > 0 else 0
        scope_total = scope_1 + scope_2 + scope_3

        e_score = clamp(
            30
            + max(0, 35 - (scope_total / 60))
            + min(20, safe_number(payload.get('reduction_target_percent')) * 0.25)
            + min(15, renewable_ratio * 100 * 0.2)
        )
        s_score = clamp(
            25
            + min(25, female_rep * 0.35)
            + max(0, 20 - trifr * 2.5)
            + max(0, 15 - turnover * 0.3)
            + (15 if str(payload.get('whs_policy_in_place', '')).strip().lower() == 'yes' else 0)
        )
        g_score = clamp(
            (20 if str(payload.get('esg_policy_in_place', '')).strip().lower() == 'yes' else 0)
            + (20 if str(payload.get('board_level_esg_oversight', '')).strip().lower() == 'yes' else 0)
            + (20 if str(payload.get('cybersecurity_policy_in_place', '')).strip().lower() == 'yes' else 0)
            + (20 if str(payload.get('anti_bribery_corruption_policy', '')).strip().lower() == 'yes' else 0)
            + min(20, independent_board * 0.4)
            - min(10, corruption_cases * 2)
        )
        esg_score = round((0.45 * e_score) + (0.30 * s_score) + (0.25 * g_score), 2)

        score_e_total += e_score
        score_s_total += s_score
        score_g_total += g_score
        score_total += esg_score

        company_scores.append({
            'company_name': company.name,
            'sector': company.sector,
            'esg_score': esg_score,
        })
        sector_scores.setdefault(company.sector, []).append(esg_score)

        governance_checks += 4
        governance_yes += 1 if str(payload.get('esg_policy_in_place', '')).strip().lower() == 'yes' else 0
        governance_yes += 1 if str(payload.get('board_level_esg_oversight', '')).strip().lower() == 'yes' else 0
        governance_yes += 1 if str(payload.get('cybersecurity_policy_in_place', '')).strip().lower() == 'yes' else 0
        governance_yes += 1 if str(payload.get('anti_bribery_corruption_policy', '')).strip().lower() == 'yes' else 0

        filled_fields = sum(1 for field in required_fields if payload.get(field) is not None)
        completeness_total += (filled_fields / len(required_fields)) * 100

        confidence_values = [str(value).strip().lower() for key, value in payload.items() if key.endswith('_confidence')]
        if confidence_values:
            measured_count = sum(1 for value in confidence_values if value == 'measured')
            confidence_total += (measured_count / len(confidence_values)) * 100
        else:
            confidence_total += 0

        accuracy = 100.0
        if total_ghg > 0:
            delta = abs(total_ghg - scope_total) / max(total_ghg, 1)
            if delta > 0.05:
                accuracy -= min(30, delta * 100)
        if renewable > energy and energy > 0:
            accuracy -= 10
        accuracy_total += clamp(accuracy)

        prev_total_ghg = safe_number(previous_payload.get('total_ghg_emissions'))
        if prev_total_ghg > 0:
            variance = abs(total_ghg - prev_total_ghg) / prev_total_ghg
            if variance > 0.30:
                high_variance_count += 1

    reporting_count = max(reporting_companies, 1)
    portfolio_total_emissions = total_scope_1 + total_scope_2 + total_scope_3
    sector_underperforming = sorted(
        (
            (sector, sum(values) / len(values))
            for sector, values in sector_scores.items()
            if values
        ),
        key=lambda item: item[1]
    )

    top_performers = sorted(company_scores, key=lambda item: item['esg_score'], reverse=True)[:5]
    bottom_performers = sorted(company_scores, key=lambda item: item['esg_score'])[:5]

    current_cycle_summary = cycle_summaries[-1] if cycle_summaries else None
    previous_cycle_summary = cycle_summaries[-2] if len(cycle_summaries) > 1 else None
    current_cycle_reporting = safe_number((current_cycle_summary or {}).get('reporting_companies'), reporting_companies)
    previous_cycle_reporting = safe_number((previous_cycle_summary or {}).get('reporting_companies'), current_cycle_reporting)
    current_cycle_score = safe_number((current_cycle_summary or {}).get('portfolio_esg_score'), round(score_total / reporting_count, 2))
    previous_cycle_score = safe_number((previous_cycle_summary or {}).get('portfolio_esg_score'), current_cycle_score)
    current_cycle_total_ghg = safe_number((current_cycle_summary or {}).get('total_ghg'), portfolio_total_emissions)
    previous_cycle_total_ghg = safe_number((previous_cycle_summary or {}).get('total_ghg'), current_cycle_total_ghg)
    current_cycle_female_rep = safe_number(
        (current_cycle_summary or {}).get('average_female_representation'),
        round(total_female_rep / reporting_count, 2),
    )
    previous_cycle_female_rep = safe_number(
        (previous_cycle_summary or {}).get('average_female_representation'),
        current_cycle_female_rep,
    )
    current_cycle_trifr = safe_number((current_cycle_summary or {}).get('trifr'), round(total_trifr / reporting_count, 2))
    previous_cycle_trifr = safe_number((previous_cycle_summary or {}).get('trifr'), current_cycle_trifr)
    current_cycle_governance = safe_number(
        (current_cycle_summary or {}).get('governance_adoption_percent'),
        round((governance_yes / governance_checks) * 100, 2) if governance_checks else 0.0,
    )
    previous_cycle_governance = safe_number((previous_cycle_summary or {}).get('governance_adoption_percent'), current_cycle_governance)
    current_cycle_completeness = safe_number(
        (current_cycle_summary or {}).get('completeness'),
        round(completeness_total / reporting_count, 2),
    )
    previous_cycle_completeness = safe_number((previous_cycle_summary or {}).get('completeness'), current_cycle_completeness)

    result = {
        'total_companies': len(companies),
        'reporting_companies': reporting_companies,
        'total_submissions': total_submissions,
        'status_counts': status_counts,
        'submission_funnel': status_counts,
        'portfolio_esg_score': round(score_total / reporting_count, 2),
        'score_breakdown': {
            'E': round(score_e_total / reporting_count, 2),
            'S': round(score_s_total / reporting_count, 2),
            'G': round(score_g_total / reporting_count, 2),
        },
        'average_ghg_emissions': round(portfolio_total_emissions / reporting_count, 2),
        'average_female_representation': round(total_female_rep / reporting_count, 2),
        'underperforming_sectors': [sector for sector, _ in sector_underperforming[:3]],
        'emissions_totals': {
            'scope_1': round(total_scope_1, 2),
            'scope_2': round(total_scope_2, 2),
            'scope_3': round(total_scope_3, 2),
            'total': round(portfolio_total_emissions, 2),
        },
        'emissions_trend': _build_cycle_emissions_trend(cycle_summaries),
        'resource_totals': {
            'energy': round(total_energy, 2),
            'water': round(total_water, 2),
            'waste': round(total_waste, 2),
        },
        'diversity_safety': {
            'female_representation_percent': round(total_female_rep / reporting_count, 2),
            'trifr': round(total_trifr / reporting_count, 2),
            'high_variance_flags': float(high_variance_count),
        },
        'governance_adoption_percent': round((governance_yes / governance_checks) * 100, 2) if governance_checks else 0.0,
        'top_performers': top_performers,
        'bottom_performers': bottom_performers,
        'data_quality': {
            'completeness': round(completeness_total / reporting_count, 2),
            'accuracy': round(accuracy_total / reporting_count, 2),
            'confidence': round(confidence_total / reporting_count, 2),
        },
        'comparison_rows': [
            {
                'metric_name': 'Portfolio ESG Score',
                'current_value': round(current_cycle_score, 2),
                'previous_value': round(previous_cycle_score, 2),
                'unit': 'score',
                'trend_percent': _percent_change(current_cycle_score, previous_cycle_score),
                'trend_direction': _trend_direction(current_cycle_score, previous_cycle_score),
                'narrative': 'Latest portfolio score compared with the prior cycle.',
            },
            {
                'metric_name': 'Average GHG Emissions',
                'current_value': round(current_cycle_total_ghg / max(current_cycle_reporting, 1), 2),
                'previous_value': round(previous_cycle_total_ghg / max(previous_cycle_reporting, 1), 2),
                'unit': 'tCO2e per company',
                'trend_percent': _percent_change(
                    current_cycle_total_ghg / max(current_cycle_reporting, 1),
                    previous_cycle_total_ghg / max(previous_cycle_reporting, 1),
                ),
                'trend_direction': _trend_direction(
                    current_cycle_total_ghg / max(current_cycle_reporting, 1),
                    previous_cycle_total_ghg / max(previous_cycle_reporting, 1),
                ),
                'narrative': 'Average emissions intensity for the current reporting cohort versus the prior cycle.',
            },
            {
                'metric_name': 'Average Female Representation',
                'current_value': round(current_cycle_female_rep, 2),
                'previous_value': round(previous_cycle_female_rep, 2),
                'unit': '%',
                'trend_percent': _percent_change(current_cycle_female_rep, previous_cycle_female_rep),
                'trend_direction': _trend_direction(current_cycle_female_rep, previous_cycle_female_rep),
                'narrative': 'Workforce diversity comparison across consecutive cycles.',
            },
            {
                'metric_name': 'TRIFR (Safety)',
                'current_value': round(current_cycle_trifr, 2),
                'previous_value': round(previous_cycle_trifr, 2),
                'unit': 'rate',
                'trend_percent': _percent_change(current_cycle_trifr, previous_cycle_trifr),
                'trend_direction': _trend_direction(current_cycle_trifr, previous_cycle_trifr),
                'narrative': 'Safety performance against the prior cycle.',
            },
            {
                'metric_name': 'Governance Adoption',
                'current_value': round(current_cycle_governance, 2),
                'previous_value': round(previous_cycle_governance, 2),
                'unit': '%',
                'trend_percent': _percent_change(current_cycle_governance, previous_cycle_governance),
                'trend_direction': _trend_direction(current_cycle_governance, previous_cycle_governance),
                'narrative': 'Policy adoption and board oversight coverage versus the prior cycle.',
            },
            {
                'metric_name': 'Data Completeness',
                'current_value': round(current_cycle_completeness, 2),
                'previous_value': round(previous_cycle_completeness, 2),
                'unit': '%',
                'trend_percent': _percent_change(current_cycle_completeness, previous_cycle_completeness),
                'trend_direction': _trend_direction(current_cycle_completeness, previous_cycle_completeness),
                'narrative': 'How complete the latest reporting cohort is versus the previous cycle.',
            },
        ],
    }
    return _set_timed_cache(cache_key, result) if companies is not None and cycle_summaries is not None else result


_IMPACT_INTELLIGENCE_CACHE: Dict[str, dict] = {}


def _normalize_impact_text(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _impact_sector_benchmark(sector: str | None) -> float:
    normalized = _normalize_impact_text(sector)
    if not normalized:
        return IMPACT_DEFAULT_DIVERSITY_BENCHMARK
    for key, benchmark in IMPACT_DIVERSITY_BENCHMARKS.items():
        if key in normalized:
            return benchmark
    return IMPACT_DEFAULT_DIVERSITY_BENCHMARK


def _impact_field_helper(field_key: str) -> str:
    for section_fields in ESG_FIELD_CATALOG.values():
        for field in section_fields:
            if field.get('field_key') == field_key:
                return str(field.get('helper_text') or '').strip()
    return ''


def _impact_emissions_equivalent(value_tco2e: float) -> str:
    if value_tco2e <= 0:
        return 'No material emissions recorded.'
    vehicle_years = value_tco2e / IMPACT_TCO2E_PER_PASSENGER_VEHICLE_YEAR
    if vehicle_years >= 1000:
        return f'Equivalent to roughly {vehicle_years:,.0f} passenger vehicles driven for a year.'
    return f'Equivalent to roughly {vehicle_years:,.0f} passenger vehicles driven for a year.'


def _impact_status(portfolio_value: float, benchmark_value: float, *, direction: str = 'higher') -> str:
    if benchmark_value == 0:
        return 'at'
    delta_pct = abs(portfolio_value - benchmark_value) / max(abs(benchmark_value), 1)
    if delta_pct <= 0.05:
        return 'at'
    if direction == 'lower':
        return 'above' if portfolio_value < benchmark_value else 'below'
    return 'above' if portfolio_value > benchmark_value else 'below'


def _build_impact_tooltip_bundle_prompt(metric_specs: List[dict]) -> str:
    return (
        'You are writing concise ESG metric tooltips for an LP dashboard.\n'
        'Return valid JSON only with exactly this shape: {"tooltips":{"Metric Name":"tooltip","...":"..."}}.\n'
        'Keep each tooltip to 1-2 plain-English sentences, no markdown, no bullets, and no jargon.\n'
        'Explain what the metric means and why it matters, using the benchmark and real-world equivalent where helpful.\n'
        f'Metrics:\n{json.dumps(metric_specs, indent=2, sort_keys=True, default=str)}'
    )


def _build_impact_intelligence(db: Session, analytics: dict, companies: List[Company]) -> dict:
    company_rows: List[dict] = []
    sector_buckets: Dict[str, dict] = {}

    for company in companies:
        latest_submission = company.submissions[-1] if company.submissions else None
        payload = parse_submission(latest_submission)
        if not payload:
            continue

        sector = str(company.sector or 'Unknown').strip() or 'Unknown'
        scope_1 = safe_number(payload.get('scope_1_emissions'))
        scope_2 = safe_number(payload.get('scope_2_location_based'))
        scope_3 = safe_number(payload.get('scope_3_emissions'))
        total_ghg = safe_number(payload.get('total_ghg_emissions')) or (scope_1 + scope_2 + scope_3)
        female_rep = safe_number(payload.get('female_representation_percent'))
        female_leadership = safe_number(payload.get('female_leadership_representation_percent'))
        trifr = safe_number(payload.get('trifr'))
        completed = bool(latest_submission)

        company_rows.append(
            {
                'sector': sector,
                'scope_1': scope_1,
                'scope_2': scope_2,
                'scope_3': scope_3,
                'total_ghg': total_ghg,
                'female_rep': female_rep,
                'female_leadership': female_leadership,
                'trifr': trifr,
                'completed': completed,
            }
        )

        bucket = sector_buckets.setdefault(
            sector,
            {
                'count': 0,
                'female_rep_total': 0.0,
                'female_leadership_total': 0.0,
                'trifr_total': 0.0,
            },
        )
        bucket['count'] += 1
        bucket['female_rep_total'] += female_rep
        bucket['female_leadership_total'] += female_leadership
        bucket['trifr_total'] += trifr

    reporting_companies = len(company_rows)
    scope_1_total = safe_number(analytics.get('emissions_totals', {}).get('scope_1'))
    scope_2_total = safe_number(analytics.get('emissions_totals', {}).get('scope_2'))
    scope_3_total = safe_number(analytics.get('emissions_totals', {}).get('scope_3'))
    total_emissions = safe_number(analytics.get('emissions_totals', {}).get('total'))
    female_rep = safe_number(analytics.get('diversity_safety', {}).get('female_representation_percent'))
    trifr = safe_number(analytics.get('diversity_safety', {}).get('trifr'))
    governance_adoption = safe_number(analytics.get('governance_adoption_percent'))
    completeness = safe_number(analytics.get('data_quality', {}).get('completeness'))
    portfolio_esg_score = safe_number(analytics.get('portfolio_esg_score'))

    weighted_diversity_benchmark = (
        sum(_impact_sector_benchmark(sector) * bucket['count'] for sector, bucket in sector_buckets.items())
        / max(sum(bucket['count'] for bucket in sector_buckets.values()), 1)
    )

    sector_benchmark_rows = []
    sector_gaps = []
    for sector, bucket in sorted(sector_buckets.items(), key=lambda item: item[1]['count'], reverse=True)[:5]:
        average_female_rep = bucket['female_rep_total'] / max(bucket['count'], 1)
        benchmark_value = _impact_sector_benchmark(sector)
        status = _impact_status(average_female_rep, benchmark_value, direction='higher')
        gap = round(average_female_rep - benchmark_value, 2)
        sector_gaps.append((sector, gap))
        sector_benchmark_rows.append(
            {
                'metric_name': f'{sector} Female Representation',
                'portfolio_value': round(average_female_rep, 2),
                'benchmark_value': round(benchmark_value, 2),
                'status': status,
                'industry': f'{sector} peer benchmark',
                'tooltip': f'{sector} averages {average_female_rep:.1f}% female representation versus a sector benchmark of {benchmark_value:.1f}%.',
                'real_world_equivalent': None,
                'direction': 'higher',
            }
        )

    total_emissions_equivalent = _impact_emissions_equivalent(total_emissions)
    scope_1_equivalent = _impact_emissions_equivalent(scope_1_total)
    scope_2_equivalent = _impact_emissions_equivalent(scope_2_total)
    scope_3_equivalent = _impact_emissions_equivalent(scope_3_total)

    metric_specs = [
        {
            'metric_name': 'Scope 1 Emissions',
            'field_key': 'scope_1_emissions',
            'value': scope_1_total,
            'unit': 'tCO2e',
            'benchmark_label': None,
            'benchmark_value': None,
            'real_world_equivalent': scope_1_equivalent,
        },
        {
            'metric_name': 'Scope 2 Emissions',
            'field_key': 'scope_2_location_based',
            'value': scope_2_total,
            'unit': 'tCO2e',
            'benchmark_label': None,
            'benchmark_value': None,
            'real_world_equivalent': scope_2_equivalent,
        },
        {
            'metric_name': 'Scope 3 Emissions',
            'field_key': 'scope_3_emissions',
            'value': scope_3_total,
            'unit': 'tCO2e',
            'benchmark_label': None,
            'benchmark_value': None,
            'real_world_equivalent': scope_3_equivalent,
        },
        {
            'metric_name': 'Total GHG Emissions',
            'field_key': 'total_ghg_emissions',
            'value': total_emissions,
            'unit': 'tCO2e',
            'benchmark_label': None,
            'benchmark_value': None,
            'real_world_equivalent': total_emissions_equivalent,
        },
        {
            'metric_name': 'Female Representation',
            'field_key': 'female_representation_percent',
            'value': female_rep,
            'unit': '%',
            'benchmark_label': 'Weighted sector peer benchmark',
            'benchmark_value': weighted_diversity_benchmark,
            'real_world_equivalent': None,
        },
        {
            'metric_name': 'TRIFR',
            'field_key': 'trifr',
            'value': trifr,
            'unit': 'rate',
            'benchmark_label': 'Safety peer benchmark',
            'benchmark_value': IMPACT_PORTFOLIO_TRIFR_BENCHMARK,
            'real_world_equivalent': None,
        },
        {
            'metric_name': 'Governance Adoption',
            'field_key': 'esg_policy_in_place',
            'value': governance_adoption,
            'unit': '%',
            'benchmark_label': 'Institutional peer benchmark',
            'benchmark_value': IMPACT_PORTFOLIO_POLICY_BENCHMARK,
            'real_world_equivalent': None,
        },
        {
            'metric_name': 'Data Completeness',
            'field_key': 'submission_notes',
            'value': completeness,
            'unit': '%',
            'benchmark_label': 'Portfolio target',
            'benchmark_value': 90.0,
            'real_world_equivalent': None,
        },
    ]

    cache_key = hashlib.sha256(
        json.dumps(
            {
                'companies': sorted(
                    company_rows,
                    key=lambda row: (
                        row['sector'],
                        row['scope_1'],
                        row['scope_2'],
                        row['scope_3'],
                        row['female_rep'],
                        row['trifr'],
                    ),
                ),
                'portfolio_esg_score': portfolio_esg_score,
                'female_rep': female_rep,
                'trifr': trifr,
                'governance_adoption': governance_adoption,
                'completeness': completeness,
                'total_emissions': total_emissions,
                'weighted_diversity_benchmark': weighted_diversity_benchmark,
            },
            sort_keys=True,
            default=str,
        ).encode('utf-8')
    ).hexdigest()
    cached_impact = _IMPACT_INTELLIGENCE_CACHE.get(cache_key)
    if cached_impact:
        return json.loads(json.dumps(cached_impact))

    # Reuse the ranked analytics slices so the narrative, dashboard, and newsletter
    # all point at the same company groups.
    top_performers = list(analytics.get('top_performers') or [])
    watchlist_companies = list(analytics.get('watchlist_companies') or [])

    metric_tooltip_map: Dict[str, str] = {}
    use_ai_tooltips = str(os.getenv('IMPACT_ENABLE_AI_TOOLTIPS', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
    if use_ai_tooltips:
        ai_payload = _call_openai_summary(_build_impact_tooltip_bundle_prompt(metric_specs))
        if isinstance(ai_payload, dict):
            tooltips = ai_payload.get('tooltips')
            if isinstance(tooltips, dict):
                metric_tooltip_map = {str(key): str(value).strip() for key, value in tooltips.items() if str(value).strip()}

    metric_insights = []
    for spec in metric_specs:
        helper_text = _impact_field_helper(spec['field_key'])
        benchmark_value = spec['benchmark_value']
        benchmark_label = spec['benchmark_label']
        tooltip = metric_tooltip_map.get(spec['metric_name'], '')
        if not tooltip:
            fallback_parts = [helper_text or f'{spec["metric_name"]} is a live portfolio metric.']
            if benchmark_value is not None:
                if spec['metric_name'] == 'TRIFR':
                    comparison = 'lower than' if spec['value'] <= benchmark_value else 'higher than'
                    fallback_parts.append(f'The portfolio is {comparison} the {benchmark_label.lower()} of {benchmark_value:.2f}.')
                else:
                    comparison = 'above' if spec['value'] >= benchmark_value else 'below'
                    fallback_parts.append(f'The portfolio sits {comparison} the {benchmark_label.lower()} of {benchmark_value:.2f}.')
            if spec['real_world_equivalent']:
                fallback_parts.append(spec['real_world_equivalent'])
            tooltip = ' '.join(part.strip() for part in fallback_parts if part).strip()
        metric_insights.append(
            {
                'metric_name': spec['metric_name'],
                'current_value': round(spec['value'], 2),
                'unit': spec['unit'],
                'tooltip': tooltip,
                'benchmark_label': benchmark_label,
                'benchmark_value': round(benchmark_value, 2) if benchmark_value is not None else None,
                'benchmark_status': _impact_status(spec['value'], benchmark_value, direction='lower' if spec['metric_name'] == 'TRIFR' else 'higher') if benchmark_value is not None else None,
                'real_world_equivalent': spec['real_world_equivalent'],
                'sector': 'Portfolio',
            }
        )

    top_gap_sector = None
    if sector_gaps:
        top_gap_sector = max(sector_gaps, key=lambda item: item[1])
    bottom_gap_sector = None
    if sector_gaps:
        bottom_gap_sector = min(sector_gaps, key=lambda item: item[1])

    highlights = [
        f'Portfolio emissions total {total_emissions:,.0f} tCO2e.',
        total_emissions_equivalent,
        f'Female representation averages {female_rep:.1f}% versus a weighted sector benchmark of {weighted_diversity_benchmark:.1f}%.',
        f'Data completeness sits at {completeness:.1f}% across {reporting_companies} reporting companies.',
    ]
    if top_gap_sector:
        highlights.append(f'{top_gap_sector[0]} is the strongest diversity performer at {top_gap_sector[1]:+.1f} pts versus peer benchmark.')

    watchouts = []
    if bottom_gap_sector and bottom_gap_sector[1] < 0:
        watchouts.append(f'{bottom_gap_sector[0]} trails its diversity peer benchmark by {abs(bottom_gap_sector[1]):.1f} pts.')
    if trifr > IMPACT_PORTFOLIO_TRIFR_BENCHMARK:
        watchouts.append(f'TRIFR remains above the {IMPACT_PORTFOLIO_TRIFR_BENCHMARK:.2f} safety peer benchmark.')

    recommendations = [
        'Use the strongest sectors as internal benchmarks for investor follow-up and company coaching.',
        'Prioritise diversity uplift in the sectors lagging their peer benchmark and keep tightening data completeness.',
    ]
    if governance_adoption < IMPACT_PORTFOLIO_POLICY_BENCHMARK:
        recommendations.insert(0, 'Lift policy adoption to close the gap with institutional peer benchmarks.')

    benchmark_callouts = [
        f'Weighted female representation benchmark: {weighted_diversity_benchmark:.1f}%.',
    ]
    for sector_name, gap in sorted(sector_gaps, key=lambda item: item[1], reverse=True)[:2]:
        benchmark_callouts.append(
            f'{sector_name} is {gap:+.1f} pts versus its peer benchmark for female representation.'
        )

    status_distribution = [
        {'label': 'Reporting', 'value': reporting_companies, 'note': 'Companies with approved or usable data'},
        {'label': 'Top performers', 'value': len(top_performers), 'note': 'Highest ESG score group'},
        {'label': 'Watchlist', 'value': len(watchlist_companies), 'note': 'Lower relative performance or elevated TRIFR'},
    ]
    trend_points = [
        {
            'period': item.get('period'),
            'value': item.get('total_emissions'),
            'note': 'Cycle emissions',
        }
        for item in analytics.get('emissions_trend') or []
    ]
    score_leaderboard = [
        {
            'label': item['company_name'],
            'value': item['esg_score'],
            'note': item['sector'],
        }
        for item in top_performers[:5]
    ]
    trend_summary = 'Portfolio trend data is available for the selected cycle history.'
    if len(trend_points) >= 2:
        first_point = safe_number(trend_points[0].get('value'))
        last_point = safe_number(trend_points[-1].get('value'))
        if first_point > 0:
            delta_pct = ((last_point - first_point) / first_point) * 100
            trend_summary = (
                f'Portfolio emissions moved {delta_pct:+.1f}% across the tracked cycle history, '
                f'with the latest period at {_format_pdf_metric(last_point, decimals=1, suffix=" tCO2e")} .'
            ).replace('  ', ' ')

    result = {
        'headline': 'Portfolio impact story',
        'summary': (
            f'The portfolio records {total_emissions:,.0f} tCO2e across Scope 1, 2, and 3. '
            f'{total_emissions_equivalent} '
            f'Female representation averages {female_rep:.1f}% against a weighted sector peer benchmark of {weighted_diversity_benchmark:.1f}%.'
        ),
        'highlights': highlights[:4],
        'watchouts': watchouts[:3] or ['No material watchouts were triggered in the current impact summary.'],
        'recommendations': recommendations[:3],
        'equivalents': [
            {'label': 'Scope 1', 'value': scope_1_total, 'unit': 'tCO2e', 'narrative': scope_1_equivalent},
            {'label': 'Scope 2', 'value': scope_2_total, 'unit': 'tCO2e', 'narrative': scope_2_equivalent},
            {'label': 'Scope 3', 'value': scope_3_total, 'unit': 'tCO2e', 'narrative': scope_3_equivalent},
            {'label': 'Total GHG', 'value': total_emissions, 'unit': 'tCO2e', 'narrative': total_emissions_equivalent},
        ],
        'benchmark_callouts': benchmark_callouts[:4],
        'trend_summary': trend_summary,
        'comparison_rows': analytics.get('comparison_rows') or [],
        'chart_series': {
            'status_distribution': status_distribution,
            'trend_points': trend_points,
            'score_leaderboard': score_leaderboard,
        },
        'metric_insights': metric_insights,
        'benchmark_comparisons': [
            {
                'metric_name': 'Overall ESG Score',
                'portfolio_value': round(portfolio_esg_score, 2),
                'benchmark_value': IMPACT_PORTFOLIO_ESG_BENCHMARK,
                'status': _impact_status(portfolio_esg_score, IMPACT_PORTFOLIO_ESG_BENCHMARK, direction='higher'),
                'industry': 'Multi-sector peer benchmark',
                'tooltip': f'Portfolio ESG score sits at {portfolio_esg_score:.1f} versus the multi-sector benchmark of {IMPACT_PORTFOLIO_ESG_BENCHMARK:.1f}.',
                'real_world_equivalent': None,
                'direction': 'higher',
            },
            {
                'metric_name': 'Emissions Intensity',
                'portfolio_value': round(total_emissions / max(reporting_companies, 1), 2),
                'benchmark_value': IMPACT_PORTFOLIO_EMISSIONS_INTENSITY_BENCHMARK,
                'status': _impact_status(total_emissions / max(reporting_companies, 1), IMPACT_PORTFOLIO_EMISSIONS_INTENSITY_BENCHMARK, direction='lower'),
                'industry': 'Energy & industrials peer benchmark',
                'tooltip': f'Lower emissions intensity is better. The portfolio sits at {total_emissions / max(reporting_companies, 1):.2f} versus {IMPACT_PORTFOLIO_EMISSIONS_INTENSITY_BENCHMARK:.2f}.',
                'real_world_equivalent': None,
                'direction': 'lower',
            },
            {
                'metric_name': 'Female Representation',
                'portfolio_value': round(female_rep, 2),
                'benchmark_value': round(weighted_diversity_benchmark, 2),
                'status': _impact_status(female_rep, weighted_diversity_benchmark, direction='higher'),
                'industry': 'Weighted sector peer benchmark',
                'tooltip': 'This compares the portfolio average female representation against a weighted blend of sector peer benchmarks.',
                'real_world_equivalent': None,
                'direction': 'higher',
            },
            {
                'metric_name': 'TRIFR',
                'portfolio_value': round(trifr, 2),
                'benchmark_value': IMPACT_PORTFOLIO_TRIFR_BENCHMARK,
                'status': _impact_status(trifr, IMPACT_PORTFOLIO_TRIFR_BENCHMARK, direction='lower'),
                'industry': 'Safety peer benchmark',
                'tooltip': 'Lower TRIFR is better. The portfolio is benchmarked against a peer safety target.',
                'real_world_equivalent': None,
                'direction': 'lower',
            },
            {
                'metric_name': 'Policy Compliance',
                'portfolio_value': round(governance_adoption, 2),
                'benchmark_value': IMPACT_PORTFOLIO_POLICY_BENCHMARK,
                'status': _impact_status(governance_adoption, IMPACT_PORTFOLIO_POLICY_BENCHMARK, direction='higher'),
                'industry': 'Institutional investment peer benchmark',
                'tooltip': 'Policy adoption shows how much of the portfolio has core ESG and control policies in place.',
                'real_world_equivalent': None,
                'direction': 'higher',
            },
            *sector_benchmark_rows,
        ],
    }

    _IMPACT_INTELLIGENCE_CACHE[cache_key] = json.loads(json.dumps(result))
    return json.loads(json.dumps(result))


def _build_company_comparison_row(metric_name: str, current_value: float, previous_value: float, unit: str, narrative: str) -> dict:
    return {
        'metric_name': metric_name,
        'current_value': round(current_value, 2),
        'previous_value': round(previous_value, 2),
        'trend_percent': _percent_change(current_value, previous_value),
        'trend_direction': _trend_direction(current_value, previous_value),
        'unit': unit,
        'narrative': narrative,
    }


def _build_company_impact_intelligence(db: Session, company: Company) -> dict:
    snapshot = _build_company_snapshot(db, company)
    if not snapshot:
        return {}

    latest, previous = _latest_approved_submission(company)
    latest_payload = parse_submission(latest)
    previous_payload = parse_submission(previous)
    portfolio_snapshot = _build_portfolio_snapshot(db) or {}

    metrics = snapshot.get('metrics') or {}
    policy_snapshot = snapshot.get('policy_snapshot') or {}
    current_total = safe_number(metrics.get('total_ghg_emissions'))
    current_scope_1 = safe_number(metrics.get('scope_1_emissions'))
    current_scope_2 = safe_number(metrics.get('scope_2_location_based'))
    current_scope_3 = safe_number(metrics.get('scope_3_emissions'))
    female_rep = safe_number(metrics.get('female_representation_percent'))
    trifr = safe_number(metrics.get('trifr'))
    company_esg = safe_number(snapshot.get('esg_score'))
    sector_benchmark = _impact_sector_benchmark(snapshot.get('sector'))
    policy_yes_count = sum(1 for value in policy_snapshot.values() if _normalize_policy_status(value) == 'Yes')
    policy_coverage = round((policy_yes_count / max(len(policy_snapshot), 1)) * 100, 2)

    previous_total = safe_number(previous_payload.get('total_ghg_emissions')) if previous_payload else current_total
    previous_female_rep = safe_number(previous_payload.get('female_representation_percent')) if previous_payload else female_rep
    previous_trifr = safe_number(previous_payload.get('trifr')) if previous_payload else trifr
    previous_policy_yes = 0
    if previous_payload:
        previous_policy_yes = sum(
            1
            for key in policy_snapshot.keys()
            if _normalize_policy_status(previous_payload.get(key)) == 'Yes'
        )
    previous_policy_coverage = round((previous_policy_yes / max(len(policy_snapshot), 1)) * 100, 2) if previous_payload else policy_coverage

    total_equivalent = _impact_emissions_equivalent(current_total)
    scope_1_equivalent = _impact_emissions_equivalent(current_scope_1)
    scope_2_equivalent = _impact_emissions_equivalent(current_scope_2)
    scope_3_equivalent = _impact_emissions_equivalent(current_scope_3)
    portfolio_avg_esg = safe_number(portfolio_snapshot.get('avg_esg_score'))

    benchmark_comparisons = [
        {
            'metric_name': 'Overall ESG Score',
            'portfolio_value': round(company_esg, 2),
            'benchmark_value': IMPACT_PORTFOLIO_ESG_BENCHMARK,
            'status': _impact_status(company_esg, IMPACT_PORTFOLIO_ESG_BENCHMARK, direction='higher'),
            'industry': 'Multi-sector peer benchmark',
            'tooltip': f'{company.name} scores {company_esg:.1f} versus the multi-sector benchmark of {IMPACT_PORTFOLIO_ESG_BENCHMARK:.1f}.',
            'real_world_equivalent': None,
            'direction': 'higher',
        },
        {
            'metric_name': 'Female Representation',
            'portfolio_value': round(female_rep, 2),
            'benchmark_value': round(sector_benchmark, 2),
            'status': _impact_status(female_rep, sector_benchmark, direction='higher'),
            'industry': f'{snapshot.get("sector") or "Sector"} peer benchmark',
            'tooltip': f'Female representation is benchmarked against the sector peer level of {sector_benchmark:.1f}%.',
            'real_world_equivalent': None,
            'direction': 'higher',
        },
        {
            'metric_name': 'TRIFR',
            'portfolio_value': round(trifr, 2),
            'benchmark_value': IMPACT_PORTFOLIO_TRIFR_BENCHMARK,
            'status': _impact_status(trifr, IMPACT_PORTFOLIO_TRIFR_BENCHMARK, direction='lower'),
            'industry': 'Safety peer benchmark',
            'tooltip': 'Lower TRIFR is better and is compared against a shared safety peer benchmark.',
            'real_world_equivalent': None,
            'direction': 'lower',
        },
        {
            'metric_name': 'Policy Coverage',
            'portfolio_value': round(policy_coverage, 2),
            'benchmark_value': IMPACT_PORTFOLIO_POLICY_BENCHMARK,
            'status': _impact_status(policy_coverage, IMPACT_PORTFOLIO_POLICY_BENCHMARK, direction='higher'),
            'industry': 'Institutional investment peer benchmark',
            'tooltip': 'Policy coverage reflects how many core ESG and control policies are in place for the company.',
            'real_world_equivalent': None,
            'direction': 'higher',
        },
    ]

    comparison_rows = [
        _build_company_comparison_row(
            'Total GHG Emissions',
            current_total,
            previous_total,
            'tCO2e',
            'Approved company emissions compared with the prior approved submission.',
        ),
        _build_company_comparison_row(
            'Female Representation',
            female_rep,
            previous_female_rep,
            '%',
            'Workforce diversity compared with the prior approved submission.',
        ),
        _build_company_comparison_row(
            'TRIFR',
            trifr,
            previous_trifr,
            'rate',
            'Safety performance compared with the prior approved submission.',
        ),
        _build_company_comparison_row(
            'Policy Coverage',
            policy_coverage,
            previous_policy_coverage,
            '%',
            'Core policy coverage compared with the prior approved submission.',
        ),
    ]

    metric_insights = [
        {
            'metric_name': 'Total GHG Emissions',
            'current_value': round(current_total, 2),
            'unit': 'tCO2e',
            'tooltip': 'This is the company total across Scope 1, 2, and 3 from the latest approved submission.',
            'benchmark_label': None,
            'benchmark_value': None,
            'benchmark_status': None,
            'real_world_equivalent': total_equivalent,
            'sector': snapshot.get('sector') or 'Company',
        },
        {
            'metric_name': 'Female Representation',
            'current_value': round(female_rep, 2),
            'unit': '%',
            'tooltip': f'This compares the company workforce mix against the {snapshot.get("sector") or "sector"} peer benchmark.',
            'benchmark_label': f'{snapshot.get("sector") or "Sector"} peer benchmark',
            'benchmark_value': round(sector_benchmark, 2),
            'benchmark_status': _impact_status(female_rep, sector_benchmark, direction='higher'),
            'real_world_equivalent': None,
            'sector': snapshot.get('sector') or 'Company',
        },
        {
            'metric_name': 'TRIFR',
            'current_value': round(trifr, 2),
            'unit': 'rate',
            'tooltip': 'Lower TRIFR is better and highlights how safely the company is operating.',
            'benchmark_label': 'Safety peer benchmark',
            'benchmark_value': IMPACT_PORTFOLIO_TRIFR_BENCHMARK,
            'benchmark_status': _impact_status(trifr, IMPACT_PORTFOLIO_TRIFR_BENCHMARK, direction='lower'),
            'real_world_equivalent': None,
            'sector': snapshot.get('sector') or 'Company',
        },
        {
            'metric_name': 'Policy Coverage',
            'current_value': round(policy_coverage, 2),
            'unit': '%',
            'tooltip': 'Policy coverage helps show whether governance controls are established and ready for LP scrutiny.',
            'benchmark_label': 'Institutional peer benchmark',
            'benchmark_value': IMPACT_PORTFOLIO_POLICY_BENCHMARK,
            'benchmark_status': _impact_status(policy_coverage, IMPACT_PORTFOLIO_POLICY_BENCHMARK, direction='higher'),
            'real_world_equivalent': None,
            'sector': snapshot.get('sector') or 'Company',
        },
    ]

    benchmark_callouts = [
        f'ESG score {company_esg:.1f} versus multi-sector benchmark {IMPACT_PORTFOLIO_ESG_BENCHMARK:.1f}.',
        f'Female representation {female_rep:.1f}% versus sector peer benchmark {sector_benchmark:.1f}%.',
        f'TRIFR {trifr:.2f} versus safety benchmark {IMPACT_PORTFOLIO_TRIFR_BENCHMARK:.2f}.',
    ]
    if policy_snapshot:
        benchmark_callouts.append(
            f'Policy coverage {policy_coverage:.1f}% versus institutional benchmark {IMPACT_PORTFOLIO_POLICY_BENCHMARK:.1f}%.'
        )

    trend_summary = 'Company trend data is available from the latest approved submission history.'
    if previous_payload:
        emissions_delta = _percent_change(current_total, previous_total)
        trend_summary = (
            f'{company.name} moved {emissions_delta:+.1f}% in total emissions versus the prior approved submission, '
            f'while ESG score sits at {company_esg:.1f} compared with a portfolio average of {portfolio_avg_esg:.1f}.'
        )

    highlights = list((snapshot.get('narrative_signals') or {}).get('strengths') or [])
    watchouts = list((snapshot.get('narrative_signals') or {}).get('watchouts') or [])
    recommendations = list((snapshot.get('narrative_signals') or {}).get('opportunities') or [])
    if company_esg >= portfolio_avg_esg:
        highlights.insert(0, f'{company.name} is at or above the current portfolio average ESG score.')
    else:
        watchouts.insert(0, f'{company.name} sits below the current portfolio average ESG score of {portfolio_avg_esg:.1f}.')
    if policy_coverage < IMPACT_PORTFOLIO_POLICY_BENCHMARK:
        recommendations.insert(0, 'Close remaining policy gaps before the next LP reporting cycle.')

    return {
        'headline': f'{company.name} impact story',
        'summary': (
            f'{company.name} reports {current_total:,.0f} tCO2e in the latest approved submission. '
            f'{total_equivalent} Workforce diversity is {female_rep:.1f}% against a sector benchmark of {sector_benchmark:.1f}%.'
        ),
        'highlights': (highlights or ['Approved company data is available for benchmarked review.'])[:4],
        'watchouts': (watchouts or ['No material watchouts were triggered in the latest approved submission.'])[:3],
        'recommendations': (recommendations or ['Maintain approved-data discipline and keep improvement actions moving.'])[:3],
        'equivalents': [
            {'label': 'Scope 1', 'value': current_scope_1, 'unit': 'tCO2e', 'narrative': scope_1_equivalent},
            {'label': 'Scope 2', 'value': current_scope_2, 'unit': 'tCO2e', 'narrative': scope_2_equivalent},
            {'label': 'Scope 3', 'value': current_scope_3, 'unit': 'tCO2e', 'narrative': scope_3_equivalent},
            {'label': 'Total GHG', 'value': current_total, 'unit': 'tCO2e', 'narrative': total_equivalent},
        ],
        'benchmark_callouts': benchmark_callouts[:4],
        'trend_summary': trend_summary,
        'comparison_rows': comparison_rows,
        'metric_insights': metric_insights,
        'benchmark_comparisons': benchmark_comparisons,
        'chart_series': {
            'status_distribution': [
                {'label': 'Policies in place', 'value': policy_yes_count, 'note': 'Core policy controls confirmed'},
                {'label': 'Key watchouts', 'value': len((snapshot.get('narrative_signals') or {}).get('watchouts') or []), 'note': 'Current approved-data watchouts'},
            ],
        },
    }


def _report_scope_from_portfolio(portfolio: str) -> str:
    normalized = str(portfolio or '').strip().lower()
    if normalized in {'', 'all', 'all portfolio companies'}:
        return 'portfolio'
    return 'company'


def _extract_period_year(period: str | None) -> Optional[int]:
    match = re.search(r'fy\s*(\d{4})', str(period or ''), flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _find_company_for_report_scope(db: Session, portfolio: str) -> Company | None:
    if _report_scope_from_portfolio(portfolio) != 'company':
        return None
    return _query_ui_visible_companies(db).filter(Company.name == str(portfolio or '').strip()).first()


def _format_external_context_export_line(item: dict) -> str:
    label = 'Regulatory watch' if item.get('item_type') == 'regulation' else str(item.get('sector') or 'Sector context').strip()
    title = str(item.get('title') or '').strip()
    action_prompt = str(item.get('action_prompt') or item.get('impact_hint') or '').strip()
    if not title:
        return ''
    return f'{label}: {title}' + (f'. Next move: {action_prompt}' if action_prompt else '')


def _report_scope_signal_payload(db: Session, *, portfolio: str) -> tuple[List[dict], dict]:
    company = _find_company_for_report_scope(db, portfolio)
    if company is not None:
        external_context = _build_external_context_feed(db, role='manager', company=company, limit=4)
        anomaly_summary = _build_company_anomaly_summary(db, company)
    else:
        companies = _load_companies_with_related_data(db)
        external_context = _build_external_context_feed(db, role='manager', company=None, limit=4)
        anomaly_summary = _build_portfolio_anomaly_summary(db, companies=companies)
    return (external_context.get('items') or [])[:4], anomaly_summary


def _build_report_narrative_state(
    db: Session,
    *,
    portfolio: str,
    period: str,
    narrative_record: Optional[NarrativeSummary],
) -> dict:
    if not narrative_record:
        return {
            'narrative_status': 'missing',
            'narrative_status_label': NARRATIVE_STATE_LABELS['missing'],
            'narrative_status_reason': 'No approved narrative is selected for this report context.',
        }

    if narrative_record.status != 'approved':
        return {
            'narrative_status': 'missing',
            'narrative_status_label': NARRATIVE_STATE_LABELS['missing'],
            'narrative_status_reason': 'The selected narrative is not approved for report inserts yet.',
        }

    expected_scope = _report_scope_from_portfolio(portfolio)
    if narrative_record.scope != expected_scope:
        return {
            'narrative_status': 'stale',
            'narrative_status_label': NARRATIVE_STATE_LABELS['stale'],
            'narrative_status_reason': f'The selected narrative is {narrative_record.scope}-scoped while the report is {expected_scope}-scoped.',
        }

    if expected_scope == 'company':
        company = _find_company_for_report_scope(db, portfolio)
        if not company or company.id != narrative_record.company_id:
            return {
                'narrative_status': 'stale',
                'narrative_status_label': NARRATIVE_STATE_LABELS['stale'],
                'narrative_status_reason': 'The selected narrative does not match the company in this report scope.',
            }
        latest_snapshot = _build_company_snapshot(db, company)
    else:
        latest_snapshot = _build_portfolio_snapshot(db)

    latest_snapshot_signature, latest_source_years, latest_source_company_count, latest_source_submission_count = _source_reference_from_snapshot(latest_snapshot)
    freshness = _build_narrative_freshness(
        narrative_record,
        latest_snapshot_signature=latest_snapshot_signature,
        latest_source_years=latest_source_years,
        latest_source_company_count=latest_source_company_count,
        latest_source_submission_count=latest_source_submission_count,
    )
    if freshness['freshness_status'] == 'stale':
        return {
            'narrative_status': 'stale',
            'narrative_status_label': NARRATIVE_STATE_LABELS['stale'],
            'narrative_status_reason': freshness['freshness_reason'],
        }

    period_year = _extract_period_year(period)
    if period_year is not None and latest_source_years and period_year not in latest_source_years:
        return {
            'narrative_status': 'stale',
            'narrative_status_label': NARRATIVE_STATE_LABELS['stale'],
            'narrative_status_reason': 'The selected narrative does not match the requested reporting year.',
        }

    return {
        'narrative_status': 'current',
        'narrative_status_label': NARRATIVE_STATE_LABELS['current'],
        'narrative_status_reason': 'The selected narrative matches the latest approved data for this report context.',
    }


def _build_report_impact_story(db: Session, *, report_name: str, portfolio: str, rows: List[dict]) -> dict:
    if report_name not in {'edci', 'sfdr'}:
        return {}

    company = _find_company_for_report_scope(db, portfolio)
    if company:
        return _build_company_impact_intelligence(db, company)

    companies = _load_companies_with_submission_data(db)
    analytics = build_investor_analytics(db, companies=companies)
    return _build_impact_intelligence(db, analytics, companies)


def _newsletter_audience_for_role(role: str) -> str:
    normalized = normalize_role(role)
    if normalized == 'manager':
        return 'manager'
    if normalized == 'investor':
        return 'investor'
    return ''


def _build_newsletter_context(db: Session, *, audience: str, tone: str) -> dict:
    companies = _load_companies_with_related_data(db)
    analytics = build_investor_analytics(db, companies=companies)
    impact_story = _build_impact_intelligence(db, analytics, companies)
    external_context = _build_external_context_feed(
        db,
        role='manager' if audience == 'manager' else 'investor',
        company=None,
        limit=4,
    )
    anomaly_summary = _build_portfolio_anomaly_summary(db, companies=companies)
    source_years = [item.get('period') for item in analytics.get('emissions_trend') or [] if item.get('period')]
    portfolio = {
        'portfolio_esg_score': analytics.get('portfolio_esg_score'),
        'reporting_companies': analytics.get('reporting_companies'),
        'total_companies': analytics.get('total_companies'),
        'governance_adoption_percent': analytics.get('governance_adoption_percent'),
        'average_ghg_emissions': analytics.get('average_ghg_emissions'),
        'data_quality': analytics.get('data_quality') or {},
        'score_breakdown': analytics.get('score_breakdown') or {},
    }
    top_companies = [
        f"{item.get('company_name')} ({item.get('esg_score'):.1f})"
        for item in (analytics.get('top_performers') or [])[:3]
        if item.get('company_name') is not None and item.get('esg_score') is not None
    ]
    bottom_companies = [
        f"{item.get('company_name')} ({item.get('esg_score'):.1f})"
        for item in (analytics.get('bottom_performers') or [])[:3]
        if item.get('company_name') is not None and item.get('esg_score') is not None
    ]
    audience_tags = get_framework_tags_for_audience('lp' if audience == 'investor' else 'board')
    if not audience_tags:
        audience_tags = get_framework_tags_for_audience('board')
    return {
        'audience': audience,
        'tone': tone,
        'framework_tags': audience_tags,
        'portfolio': portfolio,
        'impact_story': impact_story,
        'external_context_items': (external_context.get('items') or [])[:4],
        'anomaly_summary': anomaly_summary,
        'source_years': sorted({int(year) for year in source_years if str(year).isdigit()}),
        'top_companies': top_companies,
        'bottom_companies': bottom_companies,
        'action_cta': (
            'Use this digest in the board pack and follow up on the highlighted watchlist items.'
            if audience == 'manager'
            else 'Use this digest in the LP update and follow up on the highlighted watchlist items.'
        ),
    }


def _build_newsletter_prompt(context: dict) -> str:
    audience = context.get('audience') or 'manager'
    tone = context.get('tone') or 'board-ready'
    portfolio = context.get('portfolio') or {}
    impact_story = context.get('impact_story') or {}
    anomaly_summary = context.get('anomaly_summary') or {}
    external_context_items = context.get('external_context_items') or []
    top_companies = context.get('top_companies') or []
    bottom_companies = context.get('bottom_companies') or []
    return (
        f'Write a concise ESG newsletter for the {audience} audience.\n'
        f'Tone: {_tone_title(tone)}.\n'
        'Use only the approved data provided below. Do not invent facts or speculate.\n'
        'Keep the copy clear, polished, and easy to send in an email or board update.\n'
        'Return valid JSON only with this exact shape:\n'
        '{'
        '"subject_line":"string",'
        '"preheader":"string",'
        '"headline":"string",'
        '"summary":"string",'
        '"highlights":["string","string","string"],'
        '"watchouts":["string","string","string"],'
        '"recommendations":["string","string","string"],'
        '"call_to_action":"string"'
        '}\n'
        'Requirements:\n'
        '- Subject line should be <= 70 characters.\n'
        '- Preheader should be <= 120 characters.\n'
        '- Summary should be 1-2 short paragraphs.\n'
        '- Use a practical, decision-ready tone.\n'
        '- Tailor the call to action to the audience.\n'
        f'Decision brief:\n'
        f"Portfolio ESG score: {portfolio.get('portfolio_esg_score')}\n"
        f"Reporting companies: {portfolio.get('reporting_companies')} of {portfolio.get('total_companies')}\n"
        f"Governance adoption: {portfolio.get('governance_adoption_percent')}%\n"
        f"Average GHG emissions: {portfolio.get('average_ghg_emissions')} tCO2e\n"
        f"Top performers: {', '.join(top_companies) if top_companies else 'n/a'}\n"
        f"Watchlist: {', '.join(bottom_companies) if bottom_companies else 'n/a'}\n"
        f"Impact story summary: {impact_story.get('summary') or 'n/a'}\n"
        f"Impact story highlights: {json.dumps((impact_story.get('highlights') or [])[:2], default=str)}\n"
        f"Impact story watchouts: {json.dumps((impact_story.get('watchouts') or [])[:2], default=str)}\n"
        f"Impact story recommendations: {json.dumps((impact_story.get('recommendations') or [])[:2], default=str)}\n"
        f"Trend summary: {impact_story.get('trend_summary') or 'n/a'}\n"
        f"Benchmark callouts: {json.dumps((impact_story.get('benchmark_callouts') or [])[:3], default=str)}\n"
        f"Anomaly headline: {anomaly_summary.get('headline') or 'n/a'}\n"
        f"Anomaly summary: {anomaly_summary.get('summary') or 'n/a'}\n"
        f"Anomaly items: {json.dumps((anomaly_summary.get('items') or [])[:3], indent=2, sort_keys=True, default=str)}\n"
        f"External context: {json.dumps(external_context_items[:3], indent=2, sort_keys=True, default=str)}\n"
        f'Source years: {json.dumps(context.get("source_years") or [], default=str)}\n'
        f'Approved data:\n{json.dumps(context, indent=2, sort_keys=True, default=str)}'
    )


def _newsletter_payload_dict(
    *,
    subject_line: str,
    preheader: str,
    headline: str,
    summary: str,
    highlights: List[str],
    watchouts: List[str],
    recommendations: List[str],
    call_to_action: str,
) -> dict:
    return {
        'subject_line': str(subject_line or '').strip(),
        'preheader': str(preheader or '').strip(),
        'headline': str(headline or '').strip(),
        'summary': str(summary or '').strip(),
        'highlights': _coerce_narrative_items(highlights),
        'watchouts': _coerce_narrative_items(watchouts),
        'recommendations': _coerce_narrative_items(recommendations),
        'call_to_action': str(call_to_action or '').strip(),
    }


def _normalize_newsletter_payload(payload: Optional[dict], fallback_payload: dict) -> dict:
    safe_payload = payload if isinstance(payload, dict) else {}
    normalized = _newsletter_payload_dict(
        subject_line=safe_payload.get('subject_line') or fallback_payload.get('subject_line') or '',
        preheader=safe_payload.get('preheader') or fallback_payload.get('preheader') or '',
        headline=safe_payload.get('headline') or fallback_payload.get('headline') or '',
        summary=safe_payload.get('summary') or fallback_payload.get('summary') or '',
        highlights=_normalize_narrative_items(safe_payload.get('highlights'), fallback_payload.get('highlights')),
        watchouts=_normalize_narrative_items(safe_payload.get('watchouts'), fallback_payload.get('watchouts')),
        recommendations=_normalize_narrative_items(
            safe_payload.get('recommendations'),
            fallback_payload.get('recommendations'),
        ),
        call_to_action=safe_payload.get('call_to_action') or fallback_payload.get('call_to_action') or '',
    )
    if not normalized['subject_line']:
        normalized['subject_line'] = fallback_payload.get('subject_line') or 'ESG newsletter update'
    if not normalized['preheader']:
        normalized['preheader'] = fallback_payload.get('preheader') or 'A concise update grounded in approved portfolio data.'
    if not normalized['headline']:
        normalized['headline'] = fallback_payload.get('headline') or 'ESG newsletter update'
    if not normalized['summary']:
        normalized['summary'] = fallback_payload.get('summary') or 'Approved portfolio data is available, but the newsletter copy could not be generated.'
    if not normalized['call_to_action']:
        normalized['call_to_action'] = fallback_payload.get('call_to_action') or 'Review the approved data and follow up on the highlighted items.'
    return normalized


def _build_fallback_newsletter(context: dict) -> dict:
    audience = context.get('audience') or 'manager'
    portfolio = context.get('portfolio') or {}
    impact_story = context.get('impact_story') or {}
    anomaly_summary = context.get('anomaly_summary') or {}
    external_context_items = context.get('external_context_items') or []
    top_companies = context.get('top_companies') or []
    bottom_companies = context.get('bottom_companies') or []
    lead_context = next((item for item in external_context_items if isinstance(item, dict) and str(item.get('title') or '').strip()), None)
    lead_anomaly = next((item for item in (anomaly_summary.get('items') or []) if isinstance(item, dict) and str(item.get('metric_name') or '').strip()), None)
    subject_line = (
        f"ESG newsletter: {portfolio.get('reporting_companies') or 0} companies in view"
        if audience == 'manager'
        else f"Portfolio ESG digest: {portfolio.get('reporting_companies') or 0} reporting companies"
    )
    preheader = (
        f"Portfolio ESG score {float(portfolio.get('portfolio_esg_score') or 0):.1f}/100 with live watchlist and benchmark signals."
    )
    headline = 'Approved ESG data in plain English'
    summary = ' '.join(
        [
            f"The portfolio shows an ESG score of {float(portfolio.get('portfolio_esg_score') or 0):.1f}/100 across {int(portfolio.get('reporting_companies') or 0)} reporting companies.",
            str(impact_story.get('summary') or 'The latest impact story is available from approved portfolio data.').strip(),
            str(anomaly_summary.get('summary') or '').strip(),
        ]
    ).strip()
    highlights = [
        f"Reporting coverage stands at {int(portfolio.get('reporting_companies') or 0)} of {int(portfolio.get('total_companies') or 0)} companies.",
        (impact_story.get('highlights') or ['Portfolio momentum is holding steady.'])[0],
        (
            _format_external_context_export_line(lead_context)
            if lead_context is not None
            else f"Top performer: {top_companies[0]}" if top_companies else 'Top performers are visible in the dashboard ranking.'
        ),
    ]
    watchouts = [
        str(anomaly_summary.get('headline') or '').strip() or (impact_story.get('watchouts') or ['No major watchouts were triggered.'])[0],
        f"Watchlist item: {bottom_companies[0]}" if bottom_companies else 'No watchlist company stood out from the approved data sample.',
        (
            f"{lead_anomaly.get('metric_name')}: {lead_anomaly.get('recommendation')}"
            if lead_anomaly is not None
            else f"Governance adoption is {float(portfolio.get('governance_adoption_percent') or 0):.1f}% and can still improve."
        ),
    ]
    recommendations = [
        (impact_story.get('recommendations') or ['Keep following up on the strongest improvement opportunities.'])[0],
        (
            str(lead_context.get('action_prompt') or '').strip()
            if lead_context is not None and str(lead_context.get('action_prompt') or '').strip()
            else 'Use this digest to brief stakeholders on the current reporting cycle.'
        ),
        'Keep pushing the strongest performers as internal benchmarks for the rest of the portfolio.',
    ]
    call_to_action = context.get('action_cta') or 'Use this digest in your next portfolio update.'
    return _newsletter_payload_dict(
        subject_line=subject_line,
        preheader=preheader,
        headline=headline,
        summary=summary,
        highlights=highlights,
        watchouts=watchouts,
        recommendations=recommendations,
        call_to_action=call_to_action,
    )

    _IMPACT_INTELLIGENCE_CACHE[cache_key] = json.loads(json.dumps(result, default=str))
    return result


DASHBOARD_MATERIAL_TITLES = {
    'manager_brief': 'Portfolio Executive Brief',
    'investor_narrative': 'Investor Portfolio Narrative',
    'company_guidance': 'Submission Guidance',
    'trend_summary': 'What Changed Since Last Cycle',
    'attention_summary': 'Risk & Attention Summary',
}

DASHBOARD_MATERIAL_ALLOWED_BY_ROLE = {
    'manager': {'manager_brief', 'trend_summary', 'attention_summary'},
    'investor': {'investor_narrative', 'trend_summary', 'attention_summary'},
    'company': {'company_guidance', 'trend_summary', 'attention_summary'},
}


def _normalize_dashboard_material_text(value: Any, fallback: str = 'not available') -> str:
    text_value = str(value or '').strip()
    return text_value or fallback


def _normalize_dashboard_material_items(value: Any, fallback_value: Any, *, count: int) -> List[str]:
    items = _normalize_narrative_items(value, fallback_value, limit=count)
    normalized = [_normalize_dashboard_material_text(item) for item in items if _normalize_dashboard_material_text(item)]
    while len(normalized) < count:
        normalized.append('not available')
    return normalized[:count]


def _to_int_years(values: Any) -> List[int]:
    years: List[int] = []
    if not isinstance(values, list):
        return years
    for value in values:
        text_value = str(value or '').strip()
        if text_value.isdigit():
            years.append(int(text_value))
    return sorted(set(years))


def _build_manager_material_context(db: Session) -> dict:
    dashboard_payload = manager_dashboard(db)
    summary = (dashboard_payload or {}).get('summary') or {}
    cycle_banner = summary.get('cycle_banner') or {}
    anomaly_summary = _build_portfolio_anomaly_summary(db)
    external_context = _build_external_context_feed(db, role='manager', company=None, limit=4)
    source_years = _to_int_years([cycle_banner.get('active_cycle_year')])
    return {
        'role': 'manager',
        'manager_summary': summary,
        'cycle_banner': cycle_banner,
        'anomaly_summary': anomaly_summary,
        'external_context_items': (external_context.get('items') or [])[:4],
        'source_years': source_years,
    }


def _build_investor_material_context(db: Session) -> dict:
    dashboard_payload = investor_dashboard(db)
    emissions_trend = (dashboard_payload or {}).get('emissions_trend') or []
    source_years = _to_int_years([row.get('period') for row in emissions_trend if isinstance(row, dict)])
    return {
        'role': 'investor',
        'investor_analytics': dashboard_payload or {},
        'impact_story': (dashboard_payload or {}).get('impact_story') or {},
        'source_years': source_years,
    }


def _build_company_material_context(db: Session, *, email: str | None) -> dict:
    user = find_request_user(db, email)
    company = find_company_for_user(db, user)
    if not company:
        raise HTTPException(status_code=404, detail='Company not found for authenticated user')
    dashboard_payload = company_dashboard(db, email=email)
    source_years = _to_int_years([(dashboard_payload or {}).get('current_cycle_year')])
    return {
        'role': 'company',
        'company': {
            'id': company.id,
            'name': company.name,
            'sector': company.sector,
            'asset_class': company.asset_class,
            'geography': company.geography,
        },
        'company_dashboard': dashboard_payload or {},
        'impact_story': (dashboard_payload or {}).get('impact_story') or {},
        'anomaly_summary': _build_company_anomaly_summary(db, company),
        'source_years': source_years,
    }


def _build_attention_material_context(db: Session, *, role: str, email: str | None) -> dict:
    if role == 'manager':
        return {
            'role': 'manager',
            'anomaly_summary': _build_portfolio_anomaly_summary(db),
            'source_years': [],
        }
    if role == 'investor':
        return {
            'role': 'investor',
            'anomaly_summary': _build_portfolio_anomaly_summary(db),
            'source_years': [],
        }
    if role == 'company':
        company_context = _build_company_material_context(db, email=email)
        return {
            'role': 'company',
            'anomaly_summary': company_context.get('anomaly_summary') or {},
            'source_years': company_context.get('source_years') or [],
        }
    raise HTTPException(status_code=403, detail='Dashboard narrative materials are restricted to portal roles')


def _build_trend_material_context(db: Session, *, role: str, email: str | None) -> dict:
    if role == 'manager':
        manager_dashboard_payload = manager_dashboard(db)
        manager_context = _build_manager_material_context(db)
        return {
            'role': 'manager',
            'impact_story': (manager_dashboard_payload or {}).get('impact_story') or {},
            'source_years': manager_context.get('source_years') or [],
        }
    if role == 'investor':
        investor_context = _build_investor_material_context(db)
        return {
            'role': 'investor',
            'investor_analytics': investor_context.get('investor_analytics') or {},
            'impact_story': investor_context.get('impact_story') or {},
            'source_years': investor_context.get('source_years') or [],
        }
    if role == 'company':
        company_context = _build_company_material_context(db, email=email)
        return {
            'role': 'company',
            'impact_story': company_context.get('impact_story') or {},
            'source_years': company_context.get('source_years') or [],
        }
    raise HTTPException(status_code=403, detail='Dashboard narrative materials are restricted to portal roles')


def _build_material_context_for_role(db: Session, *, role: str, email: str | None, material_type: str) -> dict:
    if material_type == 'manager_brief':
        if role != 'manager':
            raise HTTPException(status_code=403, detail='This dashboard material is not available for your role')
        return _build_manager_material_context(db)
    if material_type == 'investor_narrative':
        if role != 'investor':
            raise HTTPException(status_code=403, detail='This dashboard material is not available for your role')
        return _build_investor_material_context(db)
    if material_type == 'company_guidance':
        if role != 'company':
            raise HTTPException(status_code=403, detail='This dashboard material is not available for your role')
        return _build_company_material_context(db, email=email)
    if material_type == 'trend_summary':
        return _build_trend_material_context(db, role=role, email=email)
    if material_type == 'attention_summary':
        return _build_attention_material_context(db, role=role, email=email)
    raise HTTPException(status_code=403, detail='Dashboard narrative materials are restricted to portal roles')


def _build_manager_brief_prompt(context: dict) -> str:
    return (
        'You are generating a manager dashboard narrative material.\n'
        'Use only the provided live JSON context.\n'
        'Do not invent facts.\n'
        'Do not speculate.\n'
        'If a value is missing, return "not available" for that field.\n'
        'Return valid JSON only with this exact shape:\n'
        '{'
        '"headline":"string",'
        '"summary":"string",'
        '"priority_actions":["string","string","string"],'
        '"watchouts":["string","string"],'
        '"deadline_note":"string"'
        '}\n'
        f'Live JSON context:\n{json.dumps(context, indent=2, sort_keys=True, default=str)}'
    )


def _build_investor_narrative_prompt(context: dict) -> str:
    return (
        'You are generating an investor dashboard narrative material.\n'
        'Use only the provided live JSON context.\n'
        'Do not invent facts.\n'
        'Do not speculate.\n'
        'If a value is missing, return "not available" for that field.\n'
        'Return valid JSON only with this exact shape:\n'
        '{'
        '"headline":"string",'
        '"summary":"string",'
        '"highlights":["string","string","string"],'
        '"watchlist":["string","string"],'
        '"board_note":"string"'
        '}\n'
        f'Live JSON context:\n{json.dumps(context, indent=2, sort_keys=True, default=str)}'
    )


def _build_company_guidance_prompt(context: dict) -> str:
    return (
        'You are generating a company dashboard narrative material.\n'
        'Use only the provided live JSON context.\n'
        'Do not invent facts.\n'
        'Do not speculate.\n'
        'If a value is missing, return "not available" for that field.\n'
        'Return valid JSON only with this exact shape:\n'
        '{'
        '"headline":"string",'
        '"status_summary":"string",'
        '"next_steps":["string","string","string"],'
        '"sections_to_focus":["string","string"],'
        '"review_readiness":"string"'
        '}\n'
        f'Live JSON context:\n{json.dumps(context, indent=2, sort_keys=True, default=str)}'
    )


def _build_trend_summary_prompt(context: dict) -> str:
    return (
        'You are generating a dashboard trend summary material.\n'
        'Use only the provided live JSON context.\n'
        'Do not invent facts.\n'
        'Do not speculate.\n'
        'If a value is missing, return "not available" for that field.\n'
        'Return valid JSON only with this exact shape:\n'
        '{'
        '"headline":"string",'
        '"summary":"string",'
        '"changes":["string","string","string"]'
        '}\n'
        f'Live JSON context:\n{json.dumps(context, indent=2, sort_keys=True, default=str)}'
    )


def _build_attention_summary_prompt(context: dict) -> str:
    return (
        'You are generating a dashboard risk and attention summary material.\n'
        'Use only the provided live JSON context.\n'
        'Do not invent facts.\n'
        'Do not speculate.\n'
        'If a value is missing, return "not available" for that field.\n'
        'Return valid JSON only with this exact shape:\n'
        '{'
        '"headline":"string",'
        '"summary":"string",'
        '"attention_items":["string","string","string"]'
        '}\n'
        f'Live JSON context:\n{json.dumps(context, indent=2, sort_keys=True, default=str)}'
    )


def _manager_brief_payload_dict(*, headline: str, summary: str, priority_actions: Any, watchouts: Any, deadline_note: str) -> dict:
    return {
        'headline': _normalize_dashboard_material_text(headline),
        'summary': _normalize_dashboard_material_text(summary),
        'priority_actions': _normalize_dashboard_material_items(priority_actions, [], count=3),
        'watchouts': _normalize_dashboard_material_items(watchouts, [], count=2),
        'deadline_note': _normalize_dashboard_material_text(deadline_note),
    }


def _investor_narrative_payload_dict(*, headline: str, summary: str, highlights: Any, watchlist: Any, board_note: str) -> dict:
    return {
        'headline': _normalize_dashboard_material_text(headline),
        'summary': _normalize_dashboard_material_text(summary),
        'highlights': _normalize_dashboard_material_items(highlights, [], count=3),
        'watchlist': _normalize_dashboard_material_items(watchlist, [], count=2),
        'board_note': _normalize_dashboard_material_text(board_note),
    }


def _company_guidance_payload_dict(*, headline: str, status_summary: str, next_steps: Any, sections_to_focus: Any, review_readiness: str) -> dict:
    return {
        'headline': _normalize_dashboard_material_text(headline),
        'status_summary': _normalize_dashboard_material_text(status_summary),
        'next_steps': _normalize_dashboard_material_items(next_steps, [], count=3),
        'sections_to_focus': _normalize_dashboard_material_items(sections_to_focus, [], count=2),
        'review_readiness': _normalize_dashboard_material_text(review_readiness),
    }


def _trend_summary_payload_dict(*, headline: str, summary: str, changes: Any) -> dict:
    return {
        'headline': _normalize_dashboard_material_text(headline),
        'summary': _normalize_dashboard_material_text(summary),
        'changes': _normalize_dashboard_material_items(changes, [], count=3),
    }


def _attention_summary_payload_dict(*, headline: str, summary: str, attention_items: Any) -> dict:
    return {
        'headline': _normalize_dashboard_material_text(headline),
        'summary': _normalize_dashboard_material_text(summary),
        'attention_items': _normalize_dashboard_material_items(attention_items, [], count=3),
    }


def _build_manager_brief_fallback(context: dict) -> dict:
    summary = context.get('manager_summary') or {}
    cycle_banner = context.get('cycle_banner') or {}
    anomaly_summary = context.get('anomaly_summary') or {}
    anomaly_items = anomaly_summary.get('items') or []
    external_context_items = context.get('external_context_items') or []
    status_breakdown = summary.get('status_breakdown') or {}
    total_companies = sum(int(value or 0) for value in status_breakdown.values())
    headline = (
        f"Portfolio executive brief for FY{cycle_banner.get('active_cycle_year')}"
        if cycle_banner.get('active_cycle_year')
        else 'Portfolio executive brief'
    )
    summary_text = (
        f"{total_companies} companies are in the current reporting view. "
        f"Cycle status: {_normalize_dashboard_material_text(cycle_banner.get('cycle_status'))}. "
        f"{_normalize_dashboard_material_text(anomaly_summary.get('summary'))}."
    )
    priority_actions: List[str] = []
    for item in anomaly_items:
        if len(priority_actions) >= 3:
            break
        if not isinstance(item, dict):
            continue
        metric_name = _normalize_dashboard_material_text(item.get('metric_name'))
        recommendation = _normalize_dashboard_material_text(item.get('recommendation'))
        priority_actions.append(f'{metric_name}: {recommendation}')
    if len(priority_actions) < 3:
        for row in (summary.get('upcoming_deadlines') or []):
            if len(priority_actions) >= 3:
                break
            if not isinstance(row, dict):
                continue
            company_name = _normalize_dashboard_material_text(row.get('company_name'))
            days_remaining = _normalize_dashboard_material_text(row.get('days_remaining'))
            priority_actions.append(f'{company_name}: confirm submission readiness ({days_remaining} days left).')
    if len(priority_actions) < 3 and external_context_items:
        for item in external_context_items:
            if len(priority_actions) >= 3:
                break
            if not isinstance(item, dict):
                continue
            action_prompt = _normalize_dashboard_material_text(item.get('action_prompt'))
            priority_actions.append(action_prompt)
    primary_watchout = _normalize_dashboard_material_text(anomaly_summary.get('headline'))
    secondary_watchout = 'not available'
    for item in anomaly_items:
        if not isinstance(item, dict):
            continue
        metric_name = _normalize_dashboard_material_text(item.get('metric_name'))
        rationale = _normalize_dashboard_material_text(item.get('rationale'))
        secondary_watchout = f'{metric_name}: {rationale}'
        break
    watchouts = [primary_watchout, secondary_watchout]
    days_remaining = cycle_banner.get('days_remaining')
    if isinstance(days_remaining, int):
        deadline_note = (
            f"{days_remaining} days remain in the active cycle."
            if days_remaining >= 0
            else f"{abs(days_remaining)} days past the current deadline."
        )
    else:
        deadline_note = 'not available'
    return _manager_brief_payload_dict(
        headline=headline,
        summary=summary_text,
        priority_actions=priority_actions,
        watchouts=watchouts,
        deadline_note=deadline_note,
    )


def _build_investor_narrative_fallback(context: dict) -> dict:
    analytics = context.get('investor_analytics') or {}
    impact_story = context.get('impact_story') or {}
    reporting_companies = int(analytics.get('reporting_companies') or 0)
    total_companies = int(analytics.get('total_companies') or 0)
    portfolio_score = analytics.get('portfolio_esg_score')
    summary_text = (
        f"Portfolio ESG score is {_normalize_dashboard_material_text(portfolio_score)} with "
        f"{reporting_companies} of {total_companies} companies reporting. "
        f"{_normalize_dashboard_material_text(impact_story.get('summary'))}."
    )
    highlights = list((impact_story.get('highlights') or [])[:3])
    if len(highlights) < 3:
        top_performers = analytics.get('top_performers') or []
        for item in top_performers:
            if len(highlights) >= 3:
                break
            if isinstance(item, dict):
                company_name = _normalize_dashboard_material_text(item.get('company_name'))
                score = _normalize_dashboard_material_text(item.get('esg_score'))
                highlights.append(f'{company_name} is currently at ESG score {score}.')
    watchlist = list((impact_story.get('watchouts') or [])[:2])
    if len(watchlist) < 2:
        bottom_performers = analytics.get('bottom_performers') or []
        for item in bottom_performers:
            if len(watchlist) >= 2:
                break
            if isinstance(item, dict):
                company_name = _normalize_dashboard_material_text(item.get('company_name'))
                score = _normalize_dashboard_material_text(item.get('esg_score'))
                watchlist.append(f'{company_name} remains on the watchlist at ESG score {score}.')
    return _investor_narrative_payload_dict(
        headline=_normalize_dashboard_material_text(impact_story.get('headline'), 'Investor portfolio narrative'),
        summary=summary_text,
        highlights=highlights,
        watchlist=watchlist,
        board_note=_normalize_dashboard_material_text(impact_story.get('trend_summary')),
    )


def _build_company_guidance_fallback(context: dict) -> dict:
    dashboard = context.get('company_dashboard') or {}
    anomaly_summary = context.get('anomaly_summary') or {}
    section_breakdown = dashboard.get('section_breakdown') or {}
    section_rows = sorted(
        [
            (str(section or '').strip(), int(value or 0))
            for section, value in section_breakdown.items()
            if str(section or '').strip()
        ],
        key=lambda pair: pair[1],
    )
    sections_to_focus = [f'{name} ({value}% complete)' for name, value in section_rows[:2]]
    next_steps: List[str] = []
    for item in (anomaly_summary.get('items') or []):
        if len(next_steps) >= 3:
            break
        if not isinstance(item, dict):
            continue
        next_steps.append(_normalize_dashboard_material_text(item.get('recommendation')))
    if len(next_steps) < 3:
        for section_name, value in section_rows:
            if len(next_steps) >= 3:
                break
            next_steps.append(f'Increase completion in {section_name} from {value}% before review.')
    validation_errors = int(dashboard.get('outstanding_validation_errors') or 0)
    completion_percent = int(dashboard.get('overall_completion_percent') or 0)
    review_readiness = (
        'Ready for review'
        if validation_errors == 0 and completion_percent >= 95
        else f'Not review-ready: {validation_errors} validation issue(s) remain and completion is {completion_percent}%.'
    )
    return _company_guidance_payload_dict(
        headline=f"{_normalize_dashboard_material_text((context.get('company') or {}).get('name'))} submission guidance",
        status_summary=(
            f"Status is {_normalize_dashboard_material_text(dashboard.get('submission_status'))} with "
            f"{completion_percent}% completion and {validation_errors} outstanding validation issue(s)."
        ),
        next_steps=next_steps,
        sections_to_focus=sections_to_focus,
        review_readiness=review_readiness,
    )


def _comparison_change_lines(rows: Any) -> List[str]:
    if not isinstance(rows, list):
        return []
    lines: List[str] = []
    for row in rows:
        if len(lines) >= 3:
            break
        if not isinstance(row, dict):
            continue
        metric_name = _normalize_dashboard_material_text(row.get('metric_name'))
        trend_percent = row.get('trend_percent')
        if trend_percent is None:
            current_value = _normalize_dashboard_material_text(row.get('current_value'))
            previous_value = _normalize_dashboard_material_text(row.get('previous_value'))
            lines.append(f'{metric_name}: current {current_value}, previous {previous_value}.')
            continue
        try:
            trend_value = float(trend_percent)
            sign = '+' if trend_value >= 0 else ''
            lines.append(f'{metric_name}: {sign}{trend_value:.1f}% versus last cycle.')
        except (TypeError, ValueError):
            lines.append(f'{metric_name}: {_normalize_dashboard_material_text(trend_percent)} versus last cycle.')
    return lines


def _build_trend_summary_fallback(context: dict) -> dict:
    impact_story = context.get('impact_story') or {}
    changes = _comparison_change_lines(impact_story.get('comparison_rows'))
    if len(changes) < 3:
        changes.extend(_coerce_narrative_items(impact_story.get('highlights'))[: max(0, 3 - len(changes))])
    return _trend_summary_payload_dict(
        headline=_normalize_dashboard_material_text(impact_story.get('headline'), 'What changed since last cycle'),
        summary=_normalize_dashboard_material_text(impact_story.get('trend_summary') or impact_story.get('summary')),
        changes=changes,
    )


def _build_attention_summary_fallback(context: dict) -> dict:
    anomaly_summary = context.get('anomaly_summary') or {}
    attention_items: List[str] = []
    for item in (anomaly_summary.get('items') or []):
        if len(attention_items) >= 3:
            break
        if not isinstance(item, dict):
            continue
        company_name = _normalize_dashboard_material_text(item.get('company_name'))
        metric_name = _normalize_dashboard_material_text(item.get('metric_name'))
        recommendation = _normalize_dashboard_material_text(item.get('recommendation'))
        attention_items.append(f'{company_name} - {metric_name}: {recommendation}')
    return _attention_summary_payload_dict(
        headline=_normalize_dashboard_material_text(anomaly_summary.get('headline'), 'Risk & attention summary'),
        summary=_normalize_dashboard_material_text(anomaly_summary.get('summary')),
        attention_items=attention_items,
    )


def _normalize_manager_brief_payload(payload: Optional[dict], fallback_payload: dict) -> dict:
    safe_payload = payload if isinstance(payload, dict) else {}
    return _manager_brief_payload_dict(
        headline=safe_payload.get('headline') or fallback_payload.get('headline'),
        summary=safe_payload.get('summary') or fallback_payload.get('summary'),
        priority_actions=safe_payload.get('priority_actions'),
        watchouts=safe_payload.get('watchouts'),
        deadline_note=safe_payload.get('deadline_note') or fallback_payload.get('deadline_note'),
    )


def _normalize_investor_narrative_payload(payload: Optional[dict], fallback_payload: dict) -> dict:
    safe_payload = payload if isinstance(payload, dict) else {}
    return _investor_narrative_payload_dict(
        headline=safe_payload.get('headline') or fallback_payload.get('headline'),
        summary=safe_payload.get('summary') or fallback_payload.get('summary'),
        highlights=safe_payload.get('highlights'),
        watchlist=safe_payload.get('watchlist'),
        board_note=safe_payload.get('board_note') or fallback_payload.get('board_note'),
    )


def _normalize_company_guidance_payload(payload: Optional[dict], fallback_payload: dict) -> dict:
    safe_payload = payload if isinstance(payload, dict) else {}
    return _company_guidance_payload_dict(
        headline=safe_payload.get('headline') or fallback_payload.get('headline'),
        status_summary=safe_payload.get('status_summary') or fallback_payload.get('status_summary'),
        next_steps=safe_payload.get('next_steps'),
        sections_to_focus=safe_payload.get('sections_to_focus'),
        review_readiness=safe_payload.get('review_readiness') or fallback_payload.get('review_readiness'),
    )


def _normalize_trend_summary_payload(payload: Optional[dict], fallback_payload: dict) -> dict:
    safe_payload = payload if isinstance(payload, dict) else {}
    return _trend_summary_payload_dict(
        headline=safe_payload.get('headline') or fallback_payload.get('headline'),
        summary=safe_payload.get('summary') or fallback_payload.get('summary'),
        changes=safe_payload.get('changes'),
    )


def _normalize_attention_summary_payload(payload: Optional[dict], fallback_payload: dict) -> dict:
    safe_payload = payload if isinstance(payload, dict) else {}
    return _attention_summary_payload_dict(
        headline=safe_payload.get('headline') or fallback_payload.get('headline'),
        summary=safe_payload.get('summary') or fallback_payload.get('summary'),
        attention_items=safe_payload.get('attention_items'),
    )


def _generate_dashboard_material(material_type: str, context: dict) -> tuple[dict, bool]:
    if material_type == 'manager_brief':
        prompt = _build_manager_brief_prompt(context)
        fallback = _build_manager_brief_fallback(context)
        openai_payload = _call_openai_summary(prompt)
        payload = _normalize_manager_brief_payload(openai_payload, fallback)
        return payload, not bool(openai_payload)
    if material_type == 'investor_narrative':
        prompt = _build_investor_narrative_prompt(context)
        fallback = _build_investor_narrative_fallback(context)
        openai_payload = _call_openai_summary(prompt)
        payload = _normalize_investor_narrative_payload(openai_payload, fallback)
        return payload, not bool(openai_payload)
    if material_type == 'company_guidance':
        prompt = _build_company_guidance_prompt(context)
        fallback = _build_company_guidance_fallback(context)
        openai_payload = _call_openai_summary(prompt)
        payload = _normalize_company_guidance_payload(openai_payload, fallback)
        return payload, not bool(openai_payload)
    if material_type == 'trend_summary':
        prompt = _build_trend_summary_prompt(context)
        fallback = _build_trend_summary_fallback(context)
        openai_payload = _call_openai_summary(prompt)
        payload = _normalize_trend_summary_payload(openai_payload, fallback)
        return payload, not bool(openai_payload)
    if material_type == 'attention_summary':
        prompt = _build_attention_summary_prompt(context)
        fallback = _build_attention_summary_fallback(context)
        openai_payload = _call_openai_summary(prompt)
        payload = _normalize_attention_summary_payload(openai_payload, fallback)
        return payload, not bool(openai_payload)
    raise HTTPException(status_code=400, detail='Unsupported dashboard material type')


@app.get('/dashboard/material', response_model=DashboardNarrativeMaterialResponse)
@app.get('/dashboard/materials', response_model=DashboardNarrativeMaterialResponse)
def dashboard_narrative_material(
    material_type: str = Query(...),
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    normalized_role = normalize_role(role)
    if normalized_role not in DASHBOARD_MATERIAL_ALLOWED_BY_ROLE:
        raise HTTPException(status_code=403, detail='Dashboard narrative materials are restricted to portal users')

    normalized_material_type = str(material_type or '').strip().lower()
    if normalized_material_type not in DASHBOARD_MATERIAL_TITLES:
        raise HTTPException(status_code=400, detail='Unsupported dashboard material type')

    allowed_types = DASHBOARD_MATERIAL_ALLOWED_BY_ROLE.get(normalized_role, set())
    if normalized_material_type not in allowed_types:
        raise HTTPException(status_code=403, detail='This dashboard material is not available for your role')

    cache_key = (
        f"dashboard:material:{normalized_role}:{normalized_material_type}:"
        f"{str(email or '').strip().lower()}"
    )
    if not force_refresh:
        cached_payload = _get_timed_cache(cache_key)
        if cached_payload is not None:
            return DashboardNarrativeMaterialResponse(**cached_payload)

    context = _build_material_context_for_role(
        db,
        role=normalized_role,
        email=email,
        material_type=normalized_material_type,
    )
    payload, fallback_used = _generate_dashboard_material(normalized_material_type, context)
    response_payload = DashboardNarrativeMaterialResponse(
        available=True,
        material_type=normalized_material_type,
        title=DASHBOARD_MATERIAL_TITLES[normalized_material_type],
        generated_at=datetime.utcnow().isoformat(),
        payload=payload,
        source_years=_to_int_years(context.get('source_years') or []),
        cached=False,
        fallback_used=fallback_used,
        message=None,
    ).model_dump()
    return _set_timed_cache(cache_key, response_payload)


SEARCH_SCORE_WEIGHTS = SEARCH_RANKING.get('weights') or {}
SEARCH_MINIMUM_SCORE = float(SEARCH_RANKING.get('minimumScore', 0) or 0)


def _search_weight(key: str, default: float) -> float:
    try:
        return float(SEARCH_SCORE_WEIGHTS.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _search_boost(key: str, default: float = 0.0) -> float:
    try:
        return float(SEARCH_RANKING.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _search_normalize(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _search_tokens(value: Any) -> List[str]:
    return [token for token in re.findall(r'[a-z0-9]+', _search_normalize(value)) if token]


def _search_has_term_match(query: str, text: str) -> bool:
    normalized_query = _search_normalize(query)
    normalized_text = _search_normalize(text)
    if not normalized_query or not normalized_text:
        return False
    if normalized_query in normalized_text:
        return True
    return bool(set(_search_tokens(normalized_query)) & set(_search_tokens(normalized_text)))


def _search_score(query: str, text: str) -> float:
    normalized_query = _search_normalize(query)
    normalized_text = _search_normalize(text)
    if not normalized_query or not normalized_text:
        return 0.0

    ratio = SequenceMatcher(None, normalized_query, normalized_text).ratio()
    query_tokens = _search_tokens(normalized_query)
    text_tokens = _search_tokens(normalized_text)
    token_overlap = len(set(query_tokens) & set(text_tokens)) / max(len(set(query_tokens)), 1)
    contains = 1.0 if normalized_query in normalized_text else 0.0
    starts = 1.0 if normalized_text.startswith(normalized_query) else 0.0
    weighted = (
        (ratio * _search_weight('ratio', 0.55))
        + (token_overlap * _search_weight('tokenOverlap', 0.25))
        + (contains * _search_weight('contains', 0.15))
        + (starts * _search_weight('starts', 0.05))
    )
    return round(weighted * 100, 2)


def _search_result(
    *,
    result_type: str,
    title: str,
    subtitle: str,
    path: str,
    score: float,
    company_id: int | None = None,
    company_name: str | None = None,
    sector: str | None = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> dict:
    return {
        'type': result_type,
        'title': title,
        'subtitle': subtitle,
        'path': path,
        'score': round(score, 2),
        'company_id': company_id,
        'company_name': company_name,
        'sector': sector,
        'metadata': metadata or {},
    }


def _search_page_text(page: dict) -> str:
    metadata = page.get('metadata') or {}
    aliases = metadata.get('aliases') or []
    alias_text = ' '.join(str(alias).strip() for alias in aliases if str(alias).strip())
    return ' '.join(
        part
        for part in [
            str(page.get('title') or '').strip(),
            str(page.get('subtitle') or '').strip(),
            str(page.get('path') or '').strip(),
            alias_text,
        ]
        if part
    )


def _search_aliases(page: dict) -> List[str]:
    metadata = page.get('metadata') or {}
    return [_search_normalize(alias) for alias in metadata.get('aliases') or [] if _search_normalize(alias)]


def _search_page_score(query: str, page: dict) -> float:
    normalized_query = _search_normalize(query)
    if not normalized_query:
        return 0.0

    score = _search_score(normalized_query, _search_page_text(page))
    normalized_title = _search_normalize(page.get('title'))
    normalized_subtitle = _search_normalize(page.get('subtitle'))
    normalized_path = _search_normalize(page.get('path'))
    aliases = _search_aliases(page)

    if normalized_query == normalized_title:
        score += _search_boost('pageTitleExactBoost', 0.0)
    elif normalized_title.startswith(normalized_query):
        score += _search_boost('pageTitlePrefixBoost', 0.0)

    if normalized_query == normalized_path or normalized_query in normalized_path:
        score += _search_boost('pagePathBoost', 0.0)

    if normalized_query in normalized_subtitle:
        score += _search_boost('pageSubtitleBoost', 0.0)

    if aliases:
        if normalized_query in aliases:
            score += _search_boost('pageAliasExactBoost', 0.0)
        elif any(alias.startswith(normalized_query) for alias in aliases):
            score += _search_boost('pageAliasPrefixBoost', 0.0)

    return round(score, 2)


def _search_page_catalog(role: str) -> List[dict]:
    normalized_role = normalize_role(role)
    page_catalog = PORTAL_SEARCH_PAGE_CATALOG.get(normalized_role) or PORTAL_SEARCH_PAGE_CATALOG['manager']
    return [
        _search_result(
            result_type='Page',
            title=page['title'],
            subtitle=page['subtitle'],
            path=page['path'],
            score=0.0,
            metadata=page.get('metadata', {}),
        )
        for page in page_catalog
    ]


def _search_company_results(db: Session, query: str, role: str, user: User | None) -> List[dict]:
    normalized_role = normalize_role(role)
    normalized_query = str(query or '').strip()
    if not normalized_query:
        return []

    if normalized_role == 'company':
        if not user:
            return []
        owned_company = (
            db.query(Company)
            .options(
                selectinload(Company.submissions),
                selectinload(Company.action_plans),
            )
            .filter(Company.user_id == user.id)
            .first()
        )
        if not owned_company:
            return []
        companies = [owned_company]
    elif normalized_role == 'investor':
        company_query = (
            _query_ui_visible_companies(db)
            .options(
                selectinload(Company.submissions),
                selectinload(Company.action_plans),
            )
            .order_by(Company.name.asc())
        )
        if not user:
            companies = company_query.all()
        else:
            lp_type = user.lp_type.value if hasattr(user.lp_type, 'value') else str(user.lp_type or '').lower()
            if lp_type == 'authorised':
                accessible_ids = set(get_lp_accessible_company_ids(user))
                companies = company_query.filter(Company.id.in_(accessible_ids)).all() if accessible_ids else []
            else:
                companies = []
    else:
        companies = (
            _query_ui_visible_companies(db)
            .options(
                selectinload(Company.submissions),
                selectinload(Company.action_plans),
            )
            .order_by(Company.name.asc())
            .all()
        )

    results: List[dict] = []
    for company in companies:
        latest_submission = company.submissions[-1] if company.submissions else None
        latest_payload = parse_submission(latest_submission)
        status_label = normalize_status_label(latest_submission.status if latest_submission else company.current_status)
        haystack = ' '.join(
            str(part or '').strip()
            for part in [
                company.name,
                company.sector,
                company.geography,
                company.asset_class,
                company.current_status,
                status_label,
                latest_payload.get('submission_notes'),
            ]
        )
        search_score = _search_score(normalized_query, haystack)
        normalized_company_name = _search_normalize(company.name)
        normalized_sector = _search_normalize(company.sector)
        normalized_geography = _search_normalize(company.geography)
        normalized_status = _search_normalize(status_label)

        if normalized_query == normalized_company_name:
            search_score += _search_boost('companyNameExactBoost', 0.0)
        elif normalized_company_name.startswith(normalized_query):
            search_score += _search_boost('companyNamePrefixBoost', 0.0)

        if normalized_query and normalized_query in normalized_sector:
            search_score += _search_boost('companySectorBoost', 0.0)

        if normalized_query and normalized_query in normalized_geography:
            search_score += _search_boost('companyGeographyBoost', 0.0)

        if normalized_query and normalized_query in normalized_status:
            search_score += _search_boost('companyStatusBoost', 0.0)

        action_plans = company.action_plans or []
        best_action_plan_score = 0.0
        matched_action_plan = False
        for plan in action_plans:
            plan_text = ' '.join(
                str(part or '').strip()
                for part in [
                    plan.initiative_name,
                    plan.status,
                    plan.assigned_owner,
                    plan.linked_metric,
                    company.name,
                    company.sector,
                    latest_payload.get('submission_notes'),
                ]
            )
            if not _search_has_term_match(normalized_query, plan_text):
                continue
            plan_score = _search_score(normalized_query, plan_text)
            if plan_score > 0:
                matched_action_plan = True
                best_action_plan_score = max(best_action_plan_score, plan_score)
                results.append(
                    _search_result(
                        result_type='Action Plan',
                        title=plan.initiative_name,
                        subtitle=f'{company.name} - {plan.status} - {plan.assigned_owner}',
                        path='/action-plans' if normalized_role == 'manager' else '/company/action-plans',
                        score=plan_score + _search_boost('actionPlanBoost', 8.0),
                        company_id=company.id,
                        company_name=company.name,
                        sector=company.sector,
                        metadata={
                            'status': plan.status,
                            'owner': plan.assigned_owner,
                            'linked_metric': plan.linked_metric,
                        },
                    )
                )

        if search_score < SEARCH_MINIMUM_SCORE and not matched_action_plan:
            continue

        if normalized_role == 'company':
            path = '/company/dashboard'
        elif normalized_role == 'investor':
            path = '/overview'
        else:
            company_param = quote_plus(company.name.strip())
            path = f'/submissions?companyId={company.id}&company={company_param}'

        company_score = search_score + (8 if company.name.lower().startswith(normalized_query.lower()) else 0)
        if search_score < SEARCH_MINIMUM_SCORE and matched_action_plan:
            company_score = max(company_score, best_action_plan_score + 1)

        results.append(
            _search_result(
                result_type='Company',
                title=company.name,
                subtitle=f'{company.sector} - {company.geography or "Unknown geography"} - {status_label}',
                path=path,
                score=company_score,
                company_id=company.id,
                company_name=company.name,
                sector=company.sector,
                metadata={
                    'status': status_label,
                    'current_status': company.current_status,
                    'latest_submission_id': latest_submission.id if latest_submission else None,
                    'latest_year': latest_payload.get('reporting_year'),
                },
            )
        )

    return results


def _build_global_search_results(db: Session, query: str, role: str, user: User | None) -> List[dict]:
    normalized_query = str(query or '').strip()
    if not normalized_query:
        return []

    page_results = []
    for page in _search_page_catalog(role):
        search_score = _search_page_score(normalized_query, page)
        if search_score >= SEARCH_MINIMUM_SCORE:
            page_results.append({**page, 'score': search_score})

    company_results = _search_company_results(db, normalized_query, role, user)
    combined = page_results + company_results
    combined.sort(key=lambda item: (item['score'], item['type'] == 'Page', item['title']), reverse=True)
    unique_results = []
    seen = set()
    for item in combined:
        key = (item['type'], item['title'], item['path'])
        if key in seen:
            continue
        seen.add(key)
        unique_results.append(item)
    return unique_results


@app.get('/search/global', response_model=GlobalSearchResponse)
def search_global(
    q: str = Query(default='', min_length=2, max_length=120),
    limit: int = Query(default=6, ge=1, le=12),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    normalized_role = normalize_role(role)
    if normalized_role not in {'manager', 'company', 'investor'}:
        raise HTTPException(status_code=403, detail='Access restricted to authenticated portal users')

    user = find_request_user(db, email) if email else None
    if not user:
        raise HTTPException(status_code=401, detail='Search requires an authenticated portal user')
    if normalize_role(user.role) != normalized_role:
        raise HTTPException(status_code=403, detail='Search role does not match the authenticated user')

    results = _build_global_search_results(db, q, normalized_role, user)
    return GlobalSearchResponse(
        query=q,
        role=normalized_role,
        results=results[:limit],
    )


@app.get('/analytics/portfolio', response_model=InvestorSummary, dependencies=[Depends(require_manager_or_investor)])
def analytics_portfolio(db: Session = Depends(get_db)):
    analytics = build_investor_analytics(db)
    return InvestorSummary(
        total_companies=analytics['total_companies'],
        total_submissions=analytics['total_submissions'],
        status_counts=analytics['status_counts'],
        portfolio_esg_score=analytics['portfolio_esg_score'],
        average_ghg_emissions=analytics['average_ghg_emissions'],
        average_female_representation=analytics['average_female_representation'],
        underperforming_sectors=analytics['underperforming_sectors'],
    )


@app.get('/analytics/manager', response_model=ManagerAnalyticsResponse, dependencies=[Depends(require_manager)])
def analytics_manager(db: Session = Depends(get_db)):
    cache_key = 'analytics:manager'
    cached = _get_timed_cache(cache_key)
    if cached is not None:
        return cached

    companies = _load_companies_with_submission_data(db)
    analytics = build_investor_analytics(db)
    manager_summary = build_manager_summary(db, companies)
    active_cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)

    def percent_change(current: float, previous: float) -> float:
        if previous <= 0:
            return 0.0
        return round(((current - previous) / previous) * 100, 2)

    status_colors = {
        'Not Started': '#94a3b8',
        'In Progress': '#0ea5e9',
        'Submitted': '#f59e0b',
        'Under Review': '#8b5cf6',
        'Approved': '#10b981',
        'Resubmission Requested': '#ef4444',
    }
    status_distribution = [
        {
            'name': status,
            'value': manager_summary['status_breakdown'].get(status, 0),
            'color': color,
        }
        for status, color in status_colors.items()
    ]

    sector_totals: Dict[str, Dict[str, float]] = {}
    policy_fields = [
        ('ESG Policy in Place', 'esg_policy_in_place'),
        ('WHS / Health & Safety Policy', 'whs_policy_in_place'),
        ('Cybersecurity Policy', 'cybersecurity_policy_in_place'),
        ('Anti-Bribery / Anti-Corruption', 'anti_bribery_corruption_policy'),
    ]
    policy_counts = {label: 0 for label, _ in policy_fields}
    previous_policy_counts = {label: 0 for label, _ in policy_fields}
    current_total_ghg = 0.0
    previous_total_ghg = 0.0
    current_reporting_count = 0
    previous_reporting_count = 0
    current_score_total = 0.0
    previous_score_total = 0.0
    current_completeness_total = 0.0
    previous_completeness_total = 0.0
    current_governance_yes = 0.0
    previous_governance_yes = 0.0
    current_governance_checks = 0.0
    previous_governance_checks = 0.0
    current_high_variance_count = 0
    previous_high_variance_count = 0
    required_fields = [
        'scope_1_emissions',
        'scope_2_location_based',
        'scope_3_emissions',
        'total_ghg_emissions',
        'total_energy_consumption',
        'total_water_withdrawal',
        'total_waste_generated',
        'female_representation_percent',
        'trifr',
        'independent_board_members_percent',
    ]

    for company in companies:
        year_payloads = []
        for submission in company.submissions or []:
            payload = parse_submission(submission)
            if not payload:
                continue
            reporting_year = int(safe_number(payload.get('reporting_year'), 0))
            year_payloads.append((reporting_year, payload))

        if not year_payloads:
            continue

        year_payloads.sort(key=lambda item: item[0])
        current_payload = year_payloads[-1][1]
        previous_payload = year_payloads[-2][1] if len(year_payloads) > 1 else None

        esg_score, _, _, _ = score_company_payload(current_payload)
        scope_1 = safe_number(current_payload.get('scope_1_emissions'))
        scope_2 = safe_number(current_payload.get('scope_2_location_based'))
        scope_3 = safe_number(current_payload.get('scope_3_emissions'))
        total_ghg = safe_number(current_payload.get('total_ghg_emissions')) or (scope_1 + scope_2 + scope_3)
        sector_bucket = sector_totals.setdefault(company.sector or 'Unknown', {'score_total': 0.0, 'company_count': 0.0, 'ghg_total': 0.0})
        sector_bucket['score_total'] += esg_score
        sector_bucket['company_count'] += 1
        sector_bucket['ghg_total'] += total_ghg

        current_reporting_count += 1
        current_score_total += esg_score
        current_total_ghg += total_ghg
        current_completeness_total += (sum(1 for field in required_fields if current_payload.get(field) is not None) / len(required_fields)) * 100
        current_governance_checks += 4
        current_governance_yes += 1 if str(current_payload.get('esg_policy_in_place', '')).strip().lower() == 'yes' else 0
        current_governance_yes += 1 if str(current_payload.get('board_level_esg_oversight', '')).strip().lower() == 'yes' else 0
        current_governance_yes += 1 if str(current_payload.get('cybersecurity_policy_in_place', '')).strip().lower() == 'yes' else 0
        current_governance_yes += 1 if str(current_payload.get('anti_bribery_corruption_policy', '')).strip().lower() == 'yes' else 0
        for policy_label, field_key in policy_fields:
            if str(current_payload.get(field_key, '')).strip().lower() == 'yes':
                policy_counts[policy_label] += 1

        if previous_payload:
            previous_esg_score, _, _, _ = score_company_payload(previous_payload)
            previous_scope_1 = safe_number(previous_payload.get('scope_1_emissions'))
            previous_scope_2 = safe_number(previous_payload.get('scope_2_location_based'))
            previous_scope_3 = safe_number(previous_payload.get('scope_3_emissions'))
            previous_total_ghg_value = safe_number(previous_payload.get('total_ghg_emissions')) or (previous_scope_1 + previous_scope_2 + previous_scope_3)
            previous_reporting_count += 1
            previous_score_total += previous_esg_score
            previous_total_ghg += previous_total_ghg_value
            previous_completeness_total += (sum(1 for field in required_fields if previous_payload.get(field) is not None) / len(required_fields)) * 100
            previous_governance_checks += 4
            previous_governance_yes += 1 if str(previous_payload.get('esg_policy_in_place', '')).strip().lower() == 'yes' else 0
            previous_governance_yes += 1 if str(previous_payload.get('board_level_esg_oversight', '')).strip().lower() == 'yes' else 0
            previous_governance_yes += 1 if str(previous_payload.get('cybersecurity_policy_in_place', '')).strip().lower() == 'yes' else 0
            previous_governance_yes += 1 if str(previous_payload.get('anti_bribery_corruption_policy', '')).strip().lower() == 'yes' else 0
            for policy_label, field_key in policy_fields:
                if str(previous_payload.get(field_key, '')).strip().lower() == 'yes':
                    previous_policy_counts[policy_label] += 1

            if abs(total_ghg - previous_total_ghg_value) / max(previous_total_ghg_value, 1) > 0.30:
                current_high_variance_count += 1
                previous_high_variance_count += 1

    sector_performance = [
        {
            'sector': sector,
            'avg_esg_score': round(values['score_total'] / values['company_count'], 2) if values['company_count'] else 0.0,
            'company_count': int(values['company_count']),
            'avg_ghg_emissions': round(values['ghg_total'] / values['company_count'], 2) if values['company_count'] else 0.0,
        }
        for sector, values in sector_totals.items()
    ]
    sector_performance.sort(key=lambda item: item['avg_esg_score'], reverse=True)

    policy_adoption = [
        {
            'policy_name': policy_label,
            'adoption_percentage': round((policy_counts[policy_label] / len(companies) * 100) if companies else 0.0, 2),
            'companies_with_policy': policy_counts[policy_label],
            'total_companies': len(companies),
        }
        for policy_label, _ in policy_fields
    ]

    summary_cards = [
        {
            'title': 'Portfolio ESG Score',
            'value': f'{analytics["portfolio_esg_score"]:.1f}',
            'trend': percent_change(
                current_score_total / max(current_reporting_count, 1),
                previous_score_total / max(previous_reporting_count, 1) if previous_reporting_count else 0.0,
            ),
            'trendLabel': 'vs prior year',
        },
        {
            'title': 'Reporting Companies',
            'value': f'{current_reporting_count}',
            'trend': percent_change(current_reporting_count, previous_reporting_count),
            'trendLabel': f'/ {analytics["total_companies"]}',
        },
        {
            'title': 'Data Completeness',
            'value': f'{(current_completeness_total / max(current_reporting_count, 1)):.1f}%',
            'trend': percent_change(
                current_completeness_total / max(current_reporting_count, 1),
                previous_completeness_total / max(previous_reporting_count, 1) if previous_reporting_count else 0.0,
            ),
            'trendLabel': 'coverage trend',
        },
        {
            'title': 'Governance Adoption',
            'value': f'{((current_governance_yes / max(current_governance_checks, 1)) * 100):.1f}%',
            'trend': percent_change(
                (current_governance_yes / max(current_governance_checks, 1)) * 100,
                (previous_governance_yes / max(previous_governance_checks, 1)) * 100 if previous_governance_checks else 0.0,
            ),
            'trendLabel': 'policy adoption',
        },
        {
            'title': 'Average GHG Emissions',
            'value': f'{(current_total_ghg / max(current_reporting_count, 1)):,.0f}',
            'trend': percent_change(
                current_total_ghg / max(current_reporting_count, 1),
                previous_total_ghg / max(previous_reporting_count, 1) if previous_reporting_count else 0.0,
            ),
            'trendLabel': 'tCO2e',
        },
        {
            'title': 'High Variance Flags',
            'value': f'{current_high_variance_count}',
            'trend': percent_change(current_high_variance_count, previous_high_variance_count),
            'trendLabel': 'portfolio watchlist',
        },
    ]

    impact_story = _build_impact_intelligence(db, analytics, companies)

    result = ManagerAnalyticsResponse(
        summary_cards=summary_cards,
        status_distribution=status_distribution,
        emissions_trend=[
            {
                'period': item['period'],
                'total_emissions': round(item['total_emissions'], 2),
            }
            for item in analytics['emissions_trend']
        ],
        sector_performance=sector_performance,
        policy_adoption=policy_adoption,
        top_performers=[
            {
                'company_name': item['company_name'],
                'sector': item['sector'],
                'esg_score': item['esg_score'],
            }
            for item in analytics['top_performers']
        ],
        bottom_performers=[
            {
                'company_name': item['company_name'],
                'sector': item['sector'],
                'esg_score': item['esg_score'],
            }
            for item in analytics['bottom_performers']
        ],
        data_quality=analytics['data_quality'],
        cycle_snapshot={
            'cycle_year': active_cycle.cycle_year if active_cycle else None,
            'status': normalize_cycle_status(active_cycle.status) if active_cycle else 'closed',
            'submission_open_date': active_cycle.submission_open_date if active_cycle else None,
            'submission_deadline': active_cycle.submission_deadline if active_cycle else None,
            'days_remaining': get_days_to_deadline(active_cycle.submission_deadline) if active_cycle else None,
        },
        impact_story=impact_story,
    ).model_dump()
    return _set_timed_cache(cache_key, result)


@app.get('/dashboard/investor', response_model=InvestorDashboardResponse, dependencies=[Depends(require_manager_or_investor)])
def investor_dashboard(db: Session = Depends(get_db)):
    cache_key = 'dashboard:investor'
    cached = _get_timed_cache(cache_key)
    if cached is not None:
        return cached

    # Investor receives portfolio-level analytics only (no raw company submissions).
    companies = _load_companies_with_submission_data(db)
    analytics = build_investor_analytics(db, companies=companies)
    impact_story = _build_impact_intelligence(db, analytics, companies)
    result = InvestorDashboardResponse(**analytics, impact_story=impact_story).model_dump()
    return _set_timed_cache(cache_key, result)


# ==========================================
# LP (LIMITED PARTNER / INVESTOR) ENDPOINTS
# ==========================================

@app.get('/lp/dashboard', dependencies=[Depends(require_lp)])
def lp_dashboard(db: Session = Depends(get_db)):
    """
    LP Dashboard endpoint - returns portfolio-level ESG data
    Standard LP: Portfolio aggregated data only
    Authorised LP: Portfolio data + accessible company data
    """
    from schemas import LPDashboardResponse
    
    cache_key = 'dashboard:lp'
    cached = _get_timed_cache(cache_key)
    if cached is not None:
        return cached

    companies = _load_companies_with_submission_data(db)
    analytics = build_investor_analytics(db, companies=companies)
    cycle_summaries = _build_cycle_summaries(db)
    current_cycle_summary = cycle_summaries[-1] if cycle_summaries else None
    previous_cycle_summary = cycle_summaries[-2] if len(cycle_summaries) > 1 else None

    def company_latest_payload(company: Company) -> dict:
        submissions = company.submissions or []
        latest = submissions[-1] if submissions else None
        return parse_submission(latest)

    def score_company(company: Company, payload: dict) -> tuple[float, float, float, float]:
        scope_1 = safe_number(payload.get('scope_1_emissions'))
        scope_2 = safe_number(payload.get('scope_2_location_based'))
        scope_3 = safe_number(payload.get('scope_3_emissions'))
        total_ghg = safe_number(payload.get('total_ghg_emissions'))
        energy = safe_number(payload.get('total_energy_consumption'))
        renewable = safe_number(payload.get('renewable_energy_consumption'))
        female_rep = safe_number(payload.get('female_representation_percent'))
        trifr = safe_number(payload.get('trifr'))
        turnover = safe_number(payload.get('employee_turnover_rate'))
        independent_board = safe_number(payload.get('independent_board_members_percent'))
        corruption_cases = safe_number(payload.get('confirmed_cases_of_corruption'))

        renewable_ratio = (renewable / energy) if energy > 0 else 0
        scope_total = scope_1 + scope_2 + scope_3

        e_score = clamp(
            30
            + max(0, 35 - (scope_total / 60))
            + min(20, safe_number(payload.get('reduction_target_percent')) * 0.25)
            + min(15, renewable_ratio * 100 * 0.2)
        )
        s_score = clamp(
            25
            + min(25, female_rep * 0.35)
            + max(0, 20 - trifr * 2.5)
            + max(0, 15 - turnover * 0.3)
            + (15 if str(payload.get('whs_policy_in_place', '')).strip().lower() == 'yes' else 0)
        )
        g_score = clamp(
            (20 if str(payload.get('esg_policy_in_place', '')).strip().lower() == 'yes' else 0)
            + (20 if str(payload.get('board_level_esg_oversight', '')).strip().lower() == 'yes' else 0)
            + (20 if str(payload.get('cybersecurity_policy_in_place', '')).strip().lower() == 'yes' else 0)
            + (20 if str(payload.get('anti_bribery_corruption_policy', '')).strip().lower() == 'yes' else 0)
            + min(20, independent_board * 0.4)
            - min(10, corruption_cases * 2)
        )
        esg_score = round((0.45 * e_score) + (0.30 * s_score) + (0.25 * g_score), 2)
        return esg_score, e_score, s_score, g_score

    approved_submission_count = 0
    portfolio_rows = []
    total_companies = len(companies)
    policy_fields = [
        ('ESG Policy in Place', 'esg_policy_in_place'),
        ('WHS / Health & Safety Policy', 'whs_policy_in_place'),
        ('Cybersecurity Policy', 'cybersecurity_policy_in_place'),
        ('Anti-Bribery / Anti-Corruption', 'anti_bribery_corruption_policy'),
    ]

    def summary_value(summary: dict | None, key: str, default: float = 0.0) -> float:
        if not summary:
            return default
        value = summary.get(key, default)
        return value if value is not None else default

    def summary_quality(summary: dict | None, key: str, default: float = 0.0) -> float:
        if not summary:
            return default
        quality = summary.get('data_quality', {}) or {}
        value = quality.get(key, default)
        return value if value is not None else default

    def sparkline(summary_key: str, fallback_value: float) -> list[float]:
        values = [
            round(summary['score_breakdown'].get(summary_key, fallback_value), 2)
            for summary in cycle_summaries[-5:]
        ]
        return values or [round(fallback_value, 2)]

    current_overall_score = summary_value(current_cycle_summary, 'portfolio_esg_score', analytics['portfolio_esg_score'])
    previous_overall_score = summary_value(previous_cycle_summary, 'portfolio_esg_score', current_overall_score)
    current_scores = current_cycle_summary.get('score_breakdown', {}) if current_cycle_summary else analytics.get('score_breakdown', {})
    previous_scores = previous_cycle_summary.get('score_breakdown', {}) if previous_cycle_summary else current_scores

    # Build portfolio scorecard
    portfolio_scorecard = {
        'overall_esg_score': round(current_overall_score, 2),
        'overall_esg_score_previous': round(previous_overall_score, 2),
        'yoy_change_percent': _percent_change(current_overall_score, previous_overall_score),
        'three_year_trend': [
            round(summary['portfolio_esg_score'], 2)
            for summary in cycle_summaries[-4:]
        ] or [round(current_overall_score, 2)],
        'pillars': [
            {
                'name': 'E',
                'current_score': round(current_scores.get('E', 0.0), 2),
                'previous_score': round(previous_scores.get('E', current_scores.get('E', 0.0)), 2),
                'yoy_change': _percent_change(current_scores.get('E', 0.0), previous_scores.get('E', current_scores.get('E', 0.0))),
                'trend_sparkline': sparkline('E', current_scores.get('E', 0.0)),
            },
            {
                'name': 'S',
                'current_score': round(current_scores.get('S', 0.0), 2),
                'previous_score': round(previous_scores.get('S', current_scores.get('S', 0.0)), 2),
                'yoy_change': _percent_change(current_scores.get('S', 0.0), previous_scores.get('S', current_scores.get('S', 0.0))),
                'trend_sparkline': sparkline('S', current_scores.get('S', 0.0)),
            },
            {
                'name': 'G',
                'current_score': round(current_scores.get('G', 0.0), 2),
                'previous_score': round(previous_scores.get('G', current_scores.get('G', 0.0)), 2),
                'yoy_change': _percent_change(current_scores.get('G', 0.0), previous_scores.get('G', current_scores.get('G', 0.0))),
                'trend_sparkline': sparkline('G', current_scores.get('G', 0.0)),
            },
        ],
    }
    
    for company in companies:
        latest_payload = company_latest_payload(company)
        if not latest_payload:
            continue
        latest_submission = company.submissions[-1] if company.submissions else None
        if normalize_status_label((latest_submission.status if latest_submission else company.current_status)) == 'Approved':
            approved_submission_count += 1
        esg_score, e_score, s_score, g_score = score_company(company, latest_payload)
        portfolio_rows.append({
            'id': company.id,
            'name': company.name,
            'sector': company.sector,
            'asset_class': company.asset_class or 'Unassigned',
            'geography': company.geography or 'Global',
            'approval_status': normalize_status_label((latest_submission.status if latest_submission else company.current_status)),
            'esg_score': esg_score,
            'e_score': e_score,
            's_score': s_score,
            'g_score': g_score,
        })

    completion_status = {
        'total_companies': total_companies,
        'companies_with_approved_submission': approved_submission_count,
        'completion_percent': round((approved_submission_count / total_companies * 100) if total_companies else 0.0, 2),
        'last_updated': datetime.utcnow().isoformat() + ' UTC',
    }
    
    # Build key metrics from actual analytics data
    current_total_emissions = summary_value(current_cycle_summary, 'total_ghg', analytics['emissions_totals']['total'])
    previous_total_emissions = summary_value(previous_cycle_summary, 'total_ghg', current_total_emissions)
    current_reporting_count = summary_value(current_cycle_summary, 'reporting_companies', analytics['reporting_companies'])
    previous_reporting_count = summary_value(previous_cycle_summary, 'reporting_companies', current_reporting_count)
    current_female_rep = summary_value(current_cycle_summary, 'average_female_representation', analytics['diversity_safety']['female_representation_percent'])
    previous_female_rep = summary_value(previous_cycle_summary, 'average_female_representation', current_female_rep)
    current_trifr = summary_value(current_cycle_summary, 'trifr', analytics['diversity_safety']['trifr'])
    previous_trifr = summary_value(previous_cycle_summary, 'trifr', current_trifr)
    current_governance = summary_value(current_cycle_summary, 'governance_adoption_percent', analytics['governance_adoption_percent'])
    previous_governance = summary_value(previous_cycle_summary, 'governance_adoption_percent', current_governance)
    current_completeness = summary_quality(current_cycle_summary, 'completeness', analytics['data_quality']['completeness'])
    previous_completeness = summary_quality(previous_cycle_summary, 'completeness', current_completeness)
    current_accuracy = summary_quality(current_cycle_summary, 'accuracy', analytics['data_quality']['accuracy'])
    previous_accuracy = summary_quality(previous_cycle_summary, 'accuracy', current_accuracy)
    current_intensity = current_total_emissions / max(current_reporting_count, 1)
    previous_intensity = previous_total_emissions / max(previous_reporting_count, 1)
    
    # Determine trend directions from actual cycle values
    key_metrics = [
        {
            'metric_name': 'Total GHG Emissions',
            'current_value': f'{current_total_emissions:,.0f}',
            'unit': 'tCO2e',
            'trend_percent': _percent_change(current_total_emissions, previous_total_emissions),
            'trend_direction': _trend_direction(current_total_emissions, previous_total_emissions),
            'last_updated': datetime.utcnow().strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'Emissions Intensity',
            'current_value': f'{current_intensity:,.1f}',
            'unit': 'tCO2e per company',
            'trend_percent': _percent_change(current_intensity, previous_intensity),
            'trend_direction': _trend_direction(current_intensity, previous_intensity),
            'last_updated': datetime.utcnow().strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'Average Female Representation',
            'current_value': f'{current_female_rep:.1f}',
            'unit': '%',
            'trend_percent': _percent_change(current_female_rep, previous_female_rep),
            'trend_direction': _trend_direction(current_female_rep, previous_female_rep),
            'last_updated': datetime.utcnow().strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'TRIFR (Safety)',
            'current_value': f'{current_trifr:.2f}',
            'unit': 'rate',
            'trend_percent': _percent_change(current_trifr, previous_trifr),
            'trend_direction': _trend_direction(current_trifr, previous_trifr),
            'last_updated': datetime.utcnow().strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'Governance Adoption',
            'current_value': f'{current_governance:.1f}',
            'unit': '% of portfolio',
            'trend_percent': _percent_change(current_governance, previous_governance),
            'trend_direction': _trend_direction(current_governance, previous_governance),
            'last_updated': datetime.utcnow().strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'Data Completeness',
            'current_value': f'{current_completeness:.1f}',
            'unit': '%',
            'trend_percent': _percent_change(current_completeness, previous_completeness),
            'trend_direction': _trend_direction(current_completeness, previous_completeness),
            'last_updated': datetime.utcnow().strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'Portfolio ESG Score',
            'current_value': f'{current_overall_score:.1f}',
            'unit': 'score',
            'trend_percent': _percent_change(current_overall_score, previous_overall_score),
            'trend_direction': _trend_direction(current_overall_score, previous_overall_score),
            'last_updated': datetime.utcnow().strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'Companies Reporting',
            'current_value': f'{int(current_reporting_count)}',
            'unit': '/ ' + str(total_companies),
            'trend_percent': _percent_change(current_reporting_count, previous_reporting_count),
            'trend_direction': _trend_direction(current_reporting_count, previous_reporting_count),
            'last_updated': datetime.utcnow().strftime('%Y-%m-%d'),
        },
    ]
    
    emissions_trend = [
        {
            'period': str(summary['cycle_year']),
            'scope_1': round(summary['scope_1_total'], 2),
            'scope_2': round(summary['scope_2_total'], 2),
            'scope_3': round(summary['scope_3_total'], 2),
        }
        for summary in cycle_summaries
    ] or [
        {
            'period': str(datetime.utcnow().year),
            'scope_1': round(analytics['emissions_totals']['scope_1'], 2),
            'scope_2': round(analytics['emissions_totals']['scope_2'], 2),
            'scope_3': round(analytics['emissions_totals']['scope_3'], 2),
        }
    ]
    
    diversity_metrics = [
        {
            'metric_name': 'Female Workforce %',
            'percentage': current_female_rep,
            'previous_year': previous_female_rep,
            'trend': _trend_direction(current_female_rep, previous_female_rep),
        },
        {
            'metric_name': 'Safety (TRIFR)',
            'percentage': min(current_trifr * 10, 100),
            'previous_year': min(previous_trifr * 10, 100),
            'trend': _trend_direction(current_trifr, previous_trifr),
        },
        {
            'metric_name': 'Data Accuracy',
            'percentage': current_accuracy,
            'previous_year': previous_accuracy,
            'trend': _trend_direction(current_accuracy, previous_accuracy),
        },
        {
            'metric_name': 'Submission Completeness',
            'percentage': current_completeness,
            'previous_year': previous_completeness,
            'trend': _trend_direction(current_completeness, previous_completeness),
        },
    ]
    
    policy_adoption = []
    for policy_name, field_key in policy_fields:
        companies_with_policy = sum(
            1
            for company in companies
            if str(company_latest_payload(company).get(field_key, '')).strip().lower() == 'yes'
        )
        policy_adoption.append(
            {
                'policy_name': policy_name,
                'adoption_percentage': round((companies_with_policy / total_companies * 100) if total_companies else 0.0, 2),
                'companies_with_policy': companies_with_policy,
                'total_companies': total_companies,
            }
        )

    visible_company_ids = [company.id for company in companies]
    action_plan_query = db.query(ActionPlan)
    if visible_company_ids:
        action_plan_query = action_plan_query.filter(ActionPlan.company_id.in_(visible_company_ids))
    else:
        action_plan_query = action_plan_query.filter(ActionPlan.company_id == -1)
    action_plan_status = {
        'in_progress': action_plan_query.filter(ActionPlan.status.in_(['planned', 'in progress'])).count(),
        'completed': action_plan_query.filter(ActionPlan.status == 'completed').count(),
    }
    
    portfolio_companies = sorted(portfolio_rows, key=lambda item: item['esg_score'], reverse=True)[:5]
    impact_story = _build_impact_intelligence(db, analytics, companies)
    
    result = LPDashboardResponse(
        portfolio_scorecard=portfolio_scorecard,
        completion_status=completion_status,
        key_metrics=key_metrics,
        emissions_trend=emissions_trend,
        diversity_metrics=diversity_metrics,
        policy_adoption=policy_adoption,
        action_plan_status=action_plan_status,
        portfolio_companies=portfolio_companies,
        impact_story=impact_story,
    ).model_dump()
    return _set_timed_cache(cache_key, result)


@app.get('/lp/metrics', dependencies=[Depends(require_lp)])
def lp_metrics(db: Session = Depends(get_db)):
    """
    LP Metrics page - detailed ESG breakdown
    Environmental, Social, Governance, Asset Class, Benchmarks
    """
    from schemas import LPMetricsPageResponse
    analytics = build_investor_analytics(db)
    companies = (
        _query_ui_visible_companies(db)
        .options(selectinload(Company.submissions))
        .order_by(Company.name.asc())
        .all()
    )
    visible_company_ids = {company.id for company in companies}
    cycles = (
        _apply_valid_cycle_year_filter(db.query(CollectionCycle))
        .order_by(CollectionCycle.cycle_year.asc(), CollectionCycle.id.asc())
        .all()
    )

    def get_cycle_payloads(cycle: CollectionCycle) -> List[dict]:
        payloads = []
        submission_query = db.query(Submission).filter(Submission.cycle_id == cycle.id)
        if visible_company_ids:
            submission_query = submission_query.filter(Submission.company_id.in_(visible_company_ids))
        else:
            return payloads
        for submission in submission_query.all():
            payload = parse_submission(submission)
            if payload:
                payloads.append(payload)
        return payloads

    cycle_payload_cache = {cycle.id: get_cycle_payloads(cycle) for cycle in cycles}

    def percent_change(current: float, previous: float) -> float:
        if previous <= 0:
            return 0.0
        return round(((current - previous) / previous) * 100, 2)

    def build_numeric_series(field_key: str) -> List[Dict[str, Any]]:
        series = []
        previous_value: float | None = None
        for cycle in cycles:
            values = [safe_number(payload.get(field_key)) for payload in cycle_payload_cache.get(cycle.id, []) if payload.get(field_key) not in (None, '')]
            if not values:
                continue
            current_value = sum(values) / len(values)
            series.append(
                {
                    'period': str(cycle.cycle_year),
                    'value': round(current_value, 2),
                    'trend': 0 if previous_value is None else percent_change(current_value, previous_value),
                }
            )
            previous_value = current_value
        return series

    def build_yes_rate_series(field_key: str) -> List[Dict[str, Any]]:
        series = []
        previous_value: float | None = None
        for cycle in cycles:
            payloads = cycle_payload_cache.get(cycle.id, [])
            if not payloads:
                continue
            yes_rate = (
                sum(1 for payload in payloads if str(payload.get(field_key, '')).strip().lower() == 'yes')
                / len(payloads)
            ) * 100
            series.append(
                {
                    'period': str(cycle.cycle_year),
                    'value': round(yes_rate, 2),
                    'trend': 0 if previous_value is None else percent_change(yes_rate, previous_value),
                }
            )
            previous_value = yes_rate
        return series

    environmental = {
        'scope_1_emissions': build_numeric_series('scope_1_emissions'),
        'scope_2_emissions': build_numeric_series('scope_2_location_based'),
        'scope_3_emissions': build_numeric_series('scope_3_emissions'),
        'energy_total': build_numeric_series('total_energy_consumption'),
        'energy_renewable': build_numeric_series('renewable_energy_consumption'),
        'water_usage': build_numeric_series('total_water_withdrawal'),
        'water_recycled': build_numeric_series('water_recycled_reused'),
        'waste_generated': build_numeric_series('total_waste_generated'),
        'waste_diverted': build_numeric_series('waste_diverted_from_landfill'),
    }

    social = {
        'trifr': build_numeric_series('trifr'),
        'fatalities': build_numeric_series('total_fatalities'),
        'total_employees': build_numeric_series('total_employees_fte'),
        'female_workforce_percent': build_numeric_series('female_representation_percent'),
        'female_leadership_percent': build_numeric_series('female_leadership_representation_percent'),
        'community_investment': build_numeric_series('community_investment_spend'),
    }

    governance = {
        'esg_policy_compliance': round(sum(1 for company in companies if str((parse_submission(company.submissions[-1]) if company.submissions else {}).get('esg_policy_in_place', '')).strip().lower() == 'yes') / max(len([company for company in companies if company.submissions]), 1) * 100, 2) if companies else 0.0,
        'whs_policy_compliance': round(sum(1 for company in companies if str((parse_submission(company.submissions[-1]) if company.submissions else {}).get('whs_policy_in_place', '')).strip().lower() == 'yes') / max(len([company for company in companies if company.submissions]), 1) * 100, 2) if companies else 0.0,
        'cybersecurity_policy_compliance': round(sum(1 for company in companies if str((parse_submission(company.submissions[-1]) if company.submissions else {}).get('cybersecurity_policy_in_place', '')).strip().lower() == 'yes') / max(len([company for company in companies if company.submissions]), 1) * 100, 2) if companies else 0.0,
        'antibribery_policy_compliance': round(sum(1 for company in companies if str((parse_submission(company.submissions[-1]) if company.submissions else {}).get('anti_bribery_corruption_policy', '')).strip().lower() == 'yes') / max(len([company for company in companies if company.submissions]), 1) * 100, 2) if companies else 0.0,
        'board_esg_oversight': round(sum(1 for company in companies if str((parse_submission(company.submissions[-1]) if company.submissions else {}).get('board_level_esg_oversight', '')).strip().lower() == 'yes') / max(len([company for company in companies if company.submissions]), 1) * 100, 2) if companies else 0.0,
        'cyber_incidents': build_numeric_series('cyber_incidents_in_reporting_period'),
    }

    def score_payload(payload: dict) -> tuple[float, float, float, float]:
        scope_1 = safe_number(payload.get('scope_1_emissions'))
        scope_2 = safe_number(payload.get('scope_2_location_based'))
        scope_3 = safe_number(payload.get('scope_3_emissions'))
        total_ghg = safe_number(payload.get('total_ghg_emissions'))
        energy = safe_number(payload.get('total_energy_consumption'))
        renewable = safe_number(payload.get('renewable_energy_consumption'))
        female_rep = safe_number(payload.get('female_representation_percent'))
        trifr = safe_number(payload.get('trifr'))
        turnover = safe_number(payload.get('employee_turnover_rate'))
        independent_board = safe_number(payload.get('independent_board_members_percent'))
        corruption_cases = safe_number(payload.get('confirmed_cases_of_corruption'))

        renewable_ratio = (renewable / energy) if energy > 0 else 0
        scope_total = scope_1 + scope_2 + scope_3

        e_score = clamp(
            30
            + max(0, 35 - (scope_total / 60))
            + min(20, safe_number(payload.get('reduction_target_percent')) * 0.25)
            + min(15, renewable_ratio * 100 * 0.2)
        )
        s_score = clamp(
            25
            + min(25, female_rep * 0.35)
            + max(0, 20 - trifr * 2.5)
            + max(0, 15 - turnover * 0.3)
            + (15 if str(payload.get('whs_policy_in_place', '')).strip().lower() == 'yes' else 0)
        )
        g_score = clamp(
            (20 if str(payload.get('esg_policy_in_place', '')).strip().lower() == 'yes' else 0)
            + (20 if str(payload.get('board_level_esg_oversight', '')).strip().lower() == 'yes' else 0)
            + (20 if str(payload.get('cybersecurity_policy_in_place', '')).strip().lower() == 'yes' else 0)
            + (20 if str(payload.get('anti_bribery_corruption_policy', '')).strip().lower() == 'yes' else 0)
            + min(20, independent_board * 0.4)
            - min(10, corruption_cases * 2)
        )
        esg_score = round((0.45 * e_score) + (0.30 * s_score) + (0.25 * g_score), 2)
        return esg_score, e_score, s_score, g_score

    asset_class_groups: Dict[str, Dict[str, float]] = {}
    for company in companies:
        latest_submission = company.submissions[-1] if company.submissions else None
        payload = parse_submission(latest_submission)
        if not payload:
            continue
        asset_class = str(company.asset_class or 'Unassigned').strip() or 'Unassigned'
        esg_score, _, _, _ = score_payload(payload)
        total_ghg = safe_number(payload.get('total_ghg_emissions'))
        group = asset_class_groups.setdefault(
            asset_class,
            {
                'company_count': 0,
                'avg_esg_score_total': 0.0,
                'avg_emission_intensity_total': 0.0,
                'avg_female_representation_total': 0.0,
            },
        )
        group['company_count'] += 1
        group['avg_esg_score_total'] += esg_score
        group['avg_emission_intensity_total'] += total_ghg
        group['avg_female_representation_total'] += safe_number(payload.get('female_representation_percent'))

    asset_class_breakdown = [
        {
            'asset_class': asset_class,
            'company_count': int(values['company_count']),
            'avg_esg_score': round(values['avg_esg_score_total'] / max(values['company_count'], 1), 2),
            'avg_emission_intensity': round(values['avg_emission_intensity_total'] / max(values['company_count'], 1), 2),
            'avg_female_representation': round(values['avg_female_representation_total'] / max(values['company_count'], 1), 2),
        }
        for asset_class, values in sorted(asset_class_groups.items(), key=lambda item: item[1]['company_count'], reverse=True)
    ]

    impact_story = _build_impact_intelligence(db, analytics, companies)
    benchmark_comparisons = impact_story['benchmark_comparisons']

    return LPMetricsPageResponse(
        environmental=environmental,
        social=social,
        governance=governance,
        asset_class_breakdown=asset_class_breakdown,
        benchmark_comparisons=benchmark_comparisons,
        metric_insights=impact_story['metric_insights'],
        impact_story=impact_story,
    )


@app.get('/lp/reports', dependencies=[Depends(require_lp)])
def lp_reports(db: Session = Depends(get_db)):
    """
    LP Reports endpoint - access to standardized ESG reports
    Available formats: PDF, Excel
    """
    from schemas import LPReportsResponse

    active_cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)
    cycle_year = active_cycle.cycle_year if active_cycle else datetime.utcnow().year
    previous_year = cycle_year - 1
    today = datetime.now(timezone.utc).date().isoformat()

    available_reports = []
    for report_type in sorted(ALLOWED_REPORT_TYPES):
        for year in (cycle_year, previous_year):
            available_reports.append({
                'report_type': report_type,
                'report_name': f'{report_type.upper()} Report FY{year}',
                'year': year,
                'generated_date': today,
                'format': 'PDF',
                'download_url': f'/reports/{report_type}/export?format=pdf&period=FY{year}&portfolio=All%20Portfolio%20Companies',
            })

    historical_archive: Dict[int, List[dict]] = {}
    export_pattern = re.compile(r'^(edci|sfdr)_.+_(\d{8}_\d{6})\.(csv|pdf)$')
    for export_artifact in sorted(list_export_artifacts(), key=lambda item: item.get('file_name', ''), reverse=True):
        matched = export_pattern.match(export_artifact['file_name'])
        if not matched:
            continue
        report_type = matched.group(1).lower()
        timestamp_token = matched.group(2)
        extension = matched.group(3).lower()
        try:
            generated_dt = datetime.strptime(timestamp_token, '%Y%m%d_%H%M%S')
        except ValueError:
            continue

        archive_row = {
            'report_type': report_type,
            'report_name': f'{report_type.upper()} Export {generated_dt.strftime("%Y-%m-%d %H:%M:%S")}',
            'year': generated_dt.year,
            'generated_date': generated_dt.date().isoformat(),
            'format': 'PDF' if extension == 'pdf' else 'Excel',
            'download_url': export_artifact['download_url'],
        }
        historical_archive.setdefault(generated_dt.year, []).append(archive_row)

    return LPReportsResponse(
        available_reports=available_reports,
        historical_archive=historical_archive,
        export_available=True,
    )


# ==========================================
# COMPANY PORTAL ROUTES
# ==========================================

def _load_submission_for_collaboration(
    db: Session,
    *,
    role: str,
    email: str | None,
    submission_id: int | None = None,
    cycle_id: int | None = None,
) -> Tuple[Submission, Company, CollectionCycle]:
    normalized_role = normalize_role(role)
    if normalized_role not in {'manager', 'company'}:
        raise HTTPException(status_code=403, detail='Access restricted to Managers and Company users')

    if submission_id is not None:
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(status_code=404, detail='Submission not found')
        company = db.query(Company).filter(Company.id == submission.company_id).first()
        cycle = db.query(CollectionCycle).filter(CollectionCycle.id == submission.cycle_id).first()
        enforce_company_scope_for_path(
            db,
            role=normalized_role,
            user_email=email,
            company_id=submission.company_id,
        )
        if not company or not cycle:
            raise HTTPException(status_code=404, detail='Submission context is incomplete')
        return submission, company, cycle

    user = find_request_user(db, email)
    company = find_company_for_user(db, user)
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    submission = (
        db.query(Submission)
        .filter(
            Submission.company_id == company.id,
            Submission.cycle_id == cycle_id,
        )
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')
    cycle = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail='Cycle not found')
    return submission, company, cycle


def _claim_collaboration_section(
    db: Session,
    *,
    submission: Submission,
    company: Company,
    cycle: CollectionCycle,
    role: str,
    email: str | None,
    section: str,
) -> SubmissionCollaborationResponse:
    normalized_email = (email or '').strip().lower()
    normalized_role = normalize_role(role)
    if not normalized_email:
        raise HTTPException(status_code=401, detail='Email header required')

    cleanup_expired_collaboration_sessions(db)
    section_name = section.strip()
    if not section_name:
        raise HTTPException(status_code=422, detail='Section is required')

    existing = (
        db.query(SubmissionCollaborationSession)
        .filter(
            SubmissionCollaborationSession.submission_id == submission.id,
            SubmissionCollaborationSession.section == section_name,
            SubmissionCollaborationSession.status == 'active',
        )
        .order_by(SubmissionCollaborationSession.updated_at.desc())
        .first()
    )
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=COLLABORATION_TTL_SECONDS)
    user = find_request_user(db, normalized_email)
    owner_name = user.name if user else None

    if existing and (existing.owner_email or '').strip().lower() != normalized_email:
        raise HTTPException(
            status_code=409,
            detail=f'{existing.owner_name or existing.owner_email} is currently editing {section_name}.',
        )

    created = False
    if existing:
        existing.last_seen_at = now
        existing.expires_at = expires_at
        existing.updated_at = now
        existing.status = 'active'
        existing.release_reason = None
    else:
        existing = SubmissionCollaborationSession(
            submission_id=submission.id,
            company_id=company.id,
            cycle_id=cycle.id,
            section=section_name,
            owner_role=normalized_role,
            owner_email=normalized_email,
            owner_name=owner_name,
            status='active',
            lock_mode='soft',
            last_seen_at=now,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        db.add(existing)
        created = True

    _queue_activity_event(
        db,
        event_type='submission_section_claimed',
        title='Section owner updated',
        message=f'{company.name} {section_name} section is being edited by {owner_name or normalized_email}.',
        severity='info',
        actor_role=normalized_role,
        actor_email=normalized_email,
        company=company,
        submission=submission,
        cycle=cycle,
        entity_status=submission.status,
        is_toast=False,
        visible_to_investors=False,
        metadata={
            'section': section_name,
            'created': created,
        },
    )
    db.commit()
    return _build_submission_collaboration(
        db,
        submission=submission,
        viewer_role=normalized_role,
        viewer_email=normalized_email,
    )


def _release_collaboration_section(
    db: Session,
    *,
    submission: Submission,
    company: Company,
    cycle: CollectionCycle,
    role: str,
    email: str | None,
    section: str,
    force: bool,
) -> SubmissionCollaborationResponse:
    normalized_email = (email or '').strip().lower()
    normalized_role = normalize_role(role)
    if not normalized_email:
        raise HTTPException(status_code=401, detail='Email header required')

    cleanup_expired_collaboration_sessions(db)
    section_name = section.strip()
    if not section_name:
        raise HTTPException(status_code=422, detail='Section is required')

    existing = (
        db.query(SubmissionCollaborationSession)
        .filter(
            SubmissionCollaborationSession.submission_id == submission.id,
            SubmissionCollaborationSession.section == section_name,
            SubmissionCollaborationSession.status == 'active',
        )
        .order_by(SubmissionCollaborationSession.updated_at.desc())
        .first()
    )
    if not existing:
        return _build_submission_collaboration(
            db,
            submission=submission,
            viewer_role=normalized_role,
            viewer_email=normalized_email,
        )

    if normalized_role != 'manager' and (existing.owner_email or '').strip().lower() != normalized_email:
        raise HTTPException(status_code=403, detail='Only the active owner can release this section.')
    if normalized_role == 'manager' and not force and (existing.owner_email or '').strip().lower() != normalized_email:
        raise HTTPException(status_code=422, detail='Manager release of another user requires force=true.')

    existing.status = 'released'
    existing.release_reason = 'force_release' if force and normalized_role == 'manager' else 'released'
    existing.updated_at = datetime.utcnow()

    _queue_activity_event(
        db,
        event_type='submission_section_released',
        title='Section ownership released',
        message=f'{company.name} {section_name} section is no longer actively claimed.',
        severity='info',
        actor_role=normalized_role,
        actor_email=normalized_email,
        company=company,
        submission=submission,
        cycle=cycle,
        entity_status=submission.status,
        is_toast=False,
        visible_to_investors=False,
        metadata={
            'section': section_name,
            'force': bool(force),
        },
    )
    db.commit()
    return _build_submission_collaboration(
        db,
        submission=submission,
        viewer_role=normalized_role,
        viewer_email=normalized_email,
    )


@app.get('/live/activity', response_model=ActivityFeedResponse)
def get_live_activity(
    limit: int = Query(default=12, ge=1, le=50),
    company_id: int | None = Query(default=None),
    submission_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    normalized_role = normalize_role(role)
    if normalized_role not in {'manager', 'investor', 'company'}:
        raise HTTPException(status_code=403, detail='Access restricted to authenticated platform users')
    if normalized_role == 'investor' and company_id is not None:
        raise HTTPException(status_code=403, detail='Investors are blocked from company-level activity filters')

    viewer_company_id = _viewer_company_id_for_live_access(db, role=normalized_role, email=email)
    if normalized_role == 'company' and company_id is not None and viewer_company_id != company_id:
        raise HTTPException(status_code=403, detail='Unauthorized access to this company')

    query = db.query(ActivityEvent).options(selectinload(ActivityEvent.company)).order_by(ActivityEvent.id.desc())
    if company_id is not None:
        query = query.filter(ActivityEvent.company_id == company_id)
    if submission_id is not None:
        query = query.filter(ActivityEvent.submission_id == submission_id)

    rows = query.limit(limit * 4).all()
    items: List[ActivityEventResponse] = []
    for row in rows:
        if _activity_event_visible_to_role(
            row,
            role=normalized_role,
            viewer_email=email,
            viewer_company_id=viewer_company_id,
        ):
            items.append(_serialize_activity_event(row))
        if len(items) >= limit:
            break

    return ActivityFeedResponse(items=items)


@app.websocket('/ws/live')
async def live_updates_socket(websocket: WebSocket):
    role = normalize_role(websocket.query_params.get('role'))
    email = (websocket.query_params.get('email') or '').strip().lower() or None
    try:
        last_event_id = int(websocket.query_params.get('last_event_id') or 0)
    except ValueError:
        last_event_id = 0

    await websocket.accept()
    if role not in {'manager', 'investor', 'company'}:
        try:
            await websocket.send_json({'type': 'error', 'detail': 'Unauthorized live connection'})
            await websocket.close(code=4403)
        except Exception:
            return
        return

    try:
        await websocket.send_json(
            {
                'type': 'hello',
                'connected_at': datetime.utcnow().isoformat(),
                'role': role,
                'email': email,
                'last_event_id': last_event_id,
            }
        )
    except Exception:
        return

    heartbeat_counter = 0
    try:
        while True:
            db = SessionLocal()
            try:
                viewer_company_id = _viewer_company_id_for_live_access(db, role=role, email=email)
                rows = (
                    db.query(ActivityEvent)
                    .options(selectinload(ActivityEvent.company))
                    .filter(ActivityEvent.id > last_event_id)
                    .order_by(ActivityEvent.id.asc())
                    .limit(50)
                    .all()
                )
                for row in rows:
                    if _activity_event_visible_to_role(
                        row,
                        role=role,
                        viewer_email=email,
                        viewer_company_id=viewer_company_id,
                    ):
                        try:
                            await websocket.send_json({'type': 'event', 'event': _serialize_activity_event(row).dict()})
                        except Exception:
                            return
                    last_event_id = max(last_event_id, int(row.id or 0))
            finally:
                db.close()

            heartbeat_counter += 1
            if heartbeat_counter >= 15:
                try:
                    await websocket.send_json({'type': 'heartbeat', 'ts': datetime.utcnow().isoformat()})
                except Exception:
                    return
                heartbeat_counter = 0
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return


@app.get('/submissions/{submission_id}/collaboration', response_model=SubmissionCollaborationResponse, dependencies=[Depends(require_company_or_manager)])
def get_submission_collaboration(
    submission_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    submission, _, _ = _load_submission_for_collaboration(
        db,
        role=role,
        email=email,
        submission_id=submission_id,
    )
    return _build_submission_collaboration(
        db,
        submission=submission,
        viewer_role=role,
        viewer_email=email,
    )


@app.post('/submissions/{submission_id}/collaboration/claim', response_model=SubmissionCollaborationResponse, dependencies=[Depends(require_company_or_manager)])
def claim_submission_collaboration(
    submission_id: int,
    payload: CollaborationClaimRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    submission, company, cycle = _load_submission_for_collaboration(
        db,
        role=role,
        email=email,
        submission_id=submission_id,
    )
    return _claim_collaboration_section(
        db,
        submission=submission,
        company=company,
        cycle=cycle,
        role=role,
        email=email,
        section=payload.section,
    )


@app.post('/submissions/{submission_id}/collaboration/release', response_model=SubmissionCollaborationResponse, dependencies=[Depends(require_company_or_manager)])
def release_submission_collaboration(
    submission_id: int,
    payload: CollaborationReleaseRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    submission, company, cycle = _load_submission_for_collaboration(
        db,
        role=role,
        email=email,
        submission_id=submission_id,
    )
    return _release_collaboration_section(
        db,
        submission=submission,
        company=company,
        cycle=cycle,
        role=role,
        email=email,
        section=payload.section,
        force=payload.force,
    )


@app.get('/company/submission/{cycle_id}/collaboration', response_model=SubmissionCollaborationResponse, dependencies=[Depends(require_company)])
def get_company_submission_collaboration(
    cycle_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    submission, _, _ = _load_submission_for_collaboration(
        db,
        role=role,
        email=email,
        cycle_id=cycle_id,
    )
    return _build_submission_collaboration(
        db,
        submission=submission,
        viewer_role=role,
        viewer_email=email,
    )


@app.post('/company/submission/{cycle_id}/collaboration/claim', response_model=SubmissionCollaborationResponse, dependencies=[Depends(require_company)])
def claim_company_submission_collaboration(
    cycle_id: int,
    payload: CollaborationClaimRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    submission, company, cycle = _load_submission_for_collaboration(
        db,
        role=role,
        email=email,
        cycle_id=cycle_id,
    )
    return _claim_collaboration_section(
        db,
        submission=submission,
        company=company,
        cycle=cycle,
        role=role,
        email=email,
        section=payload.section,
    )


@app.post('/company/submission/{cycle_id}/collaboration/release', response_model=SubmissionCollaborationResponse, dependencies=[Depends(require_company)])
def release_company_submission_collaboration(
    cycle_id: int,
    payload: CollaborationReleaseRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    submission, company, cycle = _load_submission_for_collaboration(
        db,
        role=role,
        email=email,
        cycle_id=cycle_id,
    )
    return _release_collaboration_section(
        db,
        submission=submission,
        company=company,
        cycle=cycle,
        role=role,
        email=email,
        section=payload.section,
        force=payload.force,
    )


@app.get('/company/dashboard', response_model=CompanyDashboardResponse, dependencies=[Depends(require_company)])
def company_dashboard(
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    """
    Company Portal Dashboard - Home screen with submission status, progress, and deadlines
    """
    normalized_email = (email or '').strip().lower()
    cache_key = f'dashboard:company:user:{normalized_email}'
    cached = _get_timed_cache(cache_key)
    if cached is not None:
        return cached

    # Get user and company
    user = db.query(User).filter(User.email == normalized_email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found in system')
    
    company = db.query(Company).filter(Company.user_id == user.id).first()
    if not company:
        raise HTTPException(
            status_code=403,
            detail=f'No company assigned to user {normalized_email}. Please contact your administrator.',
        )
    
    active_cycle = get_active_cycle(db)
    total_fields = get_company_reporting_field_count()
    
    if not active_cycle:
        # Return a minimal dashboard with a message
        result = CompanyDashboardResponse(
            company_id=company.id,
            company_name=company.name,
            current_cycle_id=None,
            current_cycle_year=datetime.utcnow().year,
            submission_status='NOT AVAILABLE',
            status_color='grey',
            deadline='No cycle set',
            days_remaining=0,
            deadline_urgency='red',
            overall_completion_percent=0,
            total_data_points=total_fields,
            completed_data_points=0,
            section_breakdown={'Environmental': 0, 'Social': 0, 'Governance': 0},
            outstanding_validation_errors=0,
            sections_requiring_correction=[],
            action_items_in_progress=0,
            impact_story={},
        ).model_dump()
        return _set_timed_cache(cache_key, result)

    # Get submission for this company and cycle
    submission = db.query(Submission).filter(
        Submission.company_id == company.id,
        Submission.cycle_id == active_cycle.id
    ).first()
    
    # Calculate completion metrics from submission data
    completed_fields = 0
    section_breakdown = {'Environmental': 0, 'Social': 0, 'Governance': 0}
    
    # Count completed fields from submission data
    if submission:
        # Try to parse submission data if it exists
        try:
            payload = json.loads(submission.esg_data) if isinstance(submission.esg_data, str) else {}
            if payload:
                # Count non-null, non-empty values
                completed_fields = sum(
                    1 for v in payload.values()
                    if v is not None and str(v).strip() != ''
                )
                # Estimate section breakdown
                env_keywords = ['scope', 'emissions', 'energy', 'water', 'waste', 'renewable']
                soc_keywords = ['female', 'diversity', 'turnover', 'trifr', 'whs', 'health']
                gov_keywords = ['esg_policy', 'board', 'cybersecurity', 'corruption', 'governance']
                
                for key, val in payload.items():
                    if val is not None and str(val).strip() != '':
                        if any(kw in key.lower() for kw in env_keywords):
                            section_breakdown['Environmental'] += 1
                        elif any(kw in key.lower() for kw in soc_keywords):
                            section_breakdown['Social'] += 1
                        elif any(kw in key.lower() for kw in gov_keywords):
                            section_breakdown['Governance'] += 1
        except (json.JSONDecodeError, TypeError):
            pass
    
    # Try to query validation errors if the table exists
    error_count = 0
    validation_errors = []
    try:
        validation_errors = db.query(ValidationError).filter(
            ValidationError.submission_id == submission.id,
            ValidationError.resolved == False
        ).all()
        error_count = len(validation_errors)
    except:
        # Table may not have data
        pass
    
    # Calculate deadline urgency
    try:
        from datetime import datetime as dt
        deadline_date = dt.strptime(active_cycle.submission_deadline, '%Y-%m-%d')
        today = dt.now()
        days_remaining = (deadline_date - today).days
    except (ValueError, TypeError):
        days_remaining = 30
    
    if days_remaining > 14:
        deadline_urgency = 'green'
    elif days_remaining > 7:
        deadline_urgency = 'amber'
    else:
        deadline_urgency = 'red'
    
    # Map status
    status_colors = {
        'not started': 'grey',
        'in progress': 'blue',
        'submitted': 'yellow',
        'approved': 'green',
        'rejected': 'red',
        'resubmission required': 'amber',
        'resubmission requested': 'amber',
    }
    
    submission_status = (submission.status if submission else 'not started').lower()
    completion_percent = int((completed_fields / max(total_fields, 1) * 100))
    impact_story = _build_company_impact_intelligence(db, company)

    result = CompanyDashboardResponse(
        company_id=company.id,
        company_name=company.name,
        current_cycle_id=active_cycle.id,
        current_cycle_year=active_cycle.cycle_year,
        submission_status=submission_status.upper(),
        status_color=status_colors.get(submission_status, 'grey'),
        deadline=active_cycle.submission_deadline,
        days_remaining=max(0, days_remaining),
        deadline_urgency=deadline_urgency,
        overall_completion_percent=completion_percent,
        total_data_points=total_fields,
        completed_data_points=completed_fields,
        section_breakdown={s: min(100, int((v / max(total_fields, 1) * 100))) for s, v in section_breakdown.items()},
        outstanding_validation_errors=error_count,
        sections_requiring_correction=[e.section for e in validation_errors if hasattr(e, 'section') and e.section],
        action_items_in_progress=len([ap for ap in company.action_plans if ap.status in ['planned', 'in progress']]),
        impact_story=impact_story,
    ).model_dump()
    return _set_timed_cache(cache_key, result)


@app.get('/company/submission/{cycle_id}', response_model=CompanySubmissionSectionResponse, dependencies=[Depends(require_company)])
def get_company_submission(
    cycle_id: int,
    section: str = Query(..., description='Section: Submission Context, Environmental, Social, Governance, or Supporting Notes'),
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    """
    Get submission form data for a specific section
    """
    # Get user and company
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    
    company = db.query(Company).filter(Company.user_id == user.id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    
    # Get cycle
    cycle = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail='Cycle not found')
    
    # Get or create submission
    submission = db.query(Submission).filter(
        Submission.company_id == company.id,
        Submission.cycle_id == cycle_id
    ).first()
    
    if not submission:
        if normalize_cycle_status(cycle.status) == 'closed':
            raise HTTPException(status_code=423, detail='This cycle is closed and cannot accept new submissions.')
        submission = Submission(
            company_id=company.id,
            cycle_id=cycle_id,
            esg_data=json.dumps({}),
            status='not started'
        )
        db.add(submission)
        db.commit()
    
    # Prepare section fields from canonical catalog while preserving legacy draft fields
    current_payload = parse_json_or_default(submission.esg_data, {})
    previous_submission = (
        db.query(Submission)
        .filter(Submission.company_id == company.id, Submission.id != submission.id)
        .order_by(Submission.id.desc())
        .first()
    )
    previous_payload = parse_json_or_default(previous_submission.esg_data, {}) if previous_submission else {}

    existing_rows = db.query(SubmissionDataField).filter(
        SubmissionDataField.submission_id == submission.id,
        SubmissionDataField.section == section,
    ).all()
    row_by_key = {row.field_key: row for row in existing_rows}

    # Backfill prior-year values for existing draft rows (safe, non-breaking)
    existing_rows_changed = False
    for row in existing_rows:
        if not _is_blank(row.prior_year_value):
            continue
        canonical_key = _canonicalize_field_key(row.field_key)
        candidates = [canonical_key, row.field_key, *_legacy_keys_for(canonical_key)]
        for candidate in candidates:
            prior_value = previous_payload.get(candidate)
            if _is_blank(prior_value):
                continue
            row.prior_year_value = str(prior_value)
            existing_rows_changed = True
            break

    created = False
    for meta in ESG_FIELD_CATALOG.get(section, []):
        field_key = meta['field_key']
        if field_key in row_by_key:
            continue
        field = SubmissionDataField(
            submission_id=submission.id,
            company_id=company.id,
            section=section,
            field_key=field_key,
            field_label=meta.get('field_label', field_key),
            confidence_level='Estimated',
        )

        # Safe defaults for context fields
        if field_key == 'company_id':
            field.value = str(company.id)
        elif field_key == 'reporting_year':
            field.value = str(cycle.cycle_year)

        # Canonical payload fallback
        if _is_blank(field.value) and not _is_blank(current_payload.get(field_key)):
            field.value = str(current_payload.get(field_key))

        # Legacy alias fallback
        for legacy_key in _legacy_keys_for(field_key):
            legacy_row = row_by_key.get(legacy_key)
            if _is_blank(field.value) and legacy_row and not _is_blank(legacy_row.value):
                field.value = legacy_row.value
                field.confidence_level = _normalize_confidence(legacy_row.confidence_level) or field.confidence_level
            if _is_blank(field.value) and not _is_blank(current_payload.get(legacy_key)):
                field.value = str(current_payload.get(legacy_key))

        if not _is_blank(previous_payload.get(field_key)):
            field.prior_year_value = str(previous_payload.get(field_key))

        db.add(field)
        row_by_key[field_key] = field
        created = True

    if created:
        db.commit()
    elif existing_rows_changed:
        db.commit()

    # Refresh rows for response
    data_fields = db.query(SubmissionDataField).filter(
        SubmissionDataField.submission_id == submission.id,
        SubmissionDataField.section == section,
    ).all()

    # Hide legacy alias rows when canonical row exists to avoid duplicate UX clutter.
    existing_keys = {row.field_key for row in data_fields}
    data_fields = [
        row
        for row in data_fields
        if not (
            row.field_key in LEGACY_FIELD_ALIASES
            and LEGACY_FIELD_ALIASES[row.field_key] in existing_keys
        )
    ]

    # Keep submission.esg_data synchronized with row-level draft state, and rebuild validation
    _sync_submission_payload(db, submission, cycle_year=cycle.cycle_year)
    values, _ = _collect_submission_values(db, submission, cycle_year=cycle.cycle_year)
    validation_issues = _evaluate_submission_validation(values)
    _replace_validation_errors(db, submission, company.id, validation_issues)
    db.commit()

    # Build response
    catalog_keys = [f['field_key'] for f in ESG_FIELD_CATALOG.get(section, [])]
    order_index = {key: idx for idx, key in enumerate(catalog_keys)}
    data_fields.sort(key=lambda row: (order_index.get(_canonicalize_field_key(row.field_key), 10_000), row.id))

    completed_count = sum(1 for f in data_fields if not _is_blank(f.value))
    section_required_keys = [f['field_key'] for f in ESG_FIELD_CATALOG.get(section, []) if f.get('required')]
    required_completed = sum(
        1
        for key in section_required_keys
        if (
            not _is_blank(values.get(key))
            or any(not _is_blank(values.get(legacy_key)) for legacy_key in _legacy_keys_for(key))
        )
    )
    completion_base = len(section_required_keys) if section_required_keys else len(data_fields)
    completion_percent = int((required_completed / completion_base * 100) if completion_base else 0)

    field_responses = []
    for f in data_fields:
        canonical_key = _canonicalize_field_key(f.field_key)
        meta = FIELD_META_BY_KEY.get(canonical_key, {})
        confidence_field = str(meta.get('confidence_field') or '')
        normalized_conf = _normalize_confidence(f.confidence_level)
        if not normalized_conf and confidence_field:
            normalized_conf = _normalize_confidence(values.get(confidence_field))
        if not normalized_conf:
            normalized_conf = 'Estimated'

        field_responses.append(
            SubmissionDataFieldResponse(
                field_key=f.field_key,
                field_label=meta.get('field_label', f.field_label),
                value=f.value if not _is_blank(f.value) else (str(values.get(canonical_key)) if not _is_blank(values.get(canonical_key)) else None),
                prior_year_value=f.prior_year_value,
                unit=meta.get('unit'),
                confidence_level=normalized_conf,
                yoy_variance_percent=float(f.yoy_variance_percent) if f.yoy_variance_percent else None,
                requires_explanation=f.requires_explanation,
                explanation=f.explanation,
                subsection=meta.get('subsection'),
                input_type=meta.get('input_type'),
                helper_text=meta.get('helper_text'),
                required=bool(meta.get('required', False)),
                read_only=bool(meta.get('read_only', False)),
                supports_reporting=bool(meta.get('supports_reporting', True)),
                confidence_field=confidence_field or None,
                confidence_options=CONFIDENCE_OPTIONS if confidence_field else [],
                policy_options=meta.get('policy_options', []),
                conditional_visibility=meta.get('conditional_visibility'),
                last_updated_at=f.updated_at.isoformat() if f.updated_at else None,
                validation_errors=[
                    ValidationErrorResponse(
                        id=e.id,
                        section=e.section,
                        field_key=e.field_key,
                        field_label=e.field_label,
                        error_type=e.error_type,
                        error_message=e.error_message,
                        severity=e.severity,
                        resolved=e.resolved,
                    )
                    for e in db.query(ValidationError).filter(
                        ValidationError.submission_id == submission.id,
                        ValidationError.field_key == f.field_key,
                    ).all()
                ],
            )
        )

    errors = db.query(ValidationError).filter(
        ValidationError.submission_id == submission.id,
        ValidationError.section == section,
        ValidationError.resolved == False,
    ).all()
    error_count = len([e for e in errors if e.severity == 'error'])
    warning_count = len([e for e in errors if e.severity == 'warning'])
    validation_status = 'error' if error_count > 0 else 'warning' if warning_count > 0 else 'pass'

    return CompanySubmissionSectionResponse(
        submission_id=submission.id,
        company_id=company.id,
        cycle_id=cycle.id,
        section=section,
        completion_percent=completion_percent,
        total_fields=len(data_fields),
        completed_fields=completed_count,
        validation_status=validation_status,
        error_count=error_count,
        warning_count=warning_count,
        fields=field_responses,
        collaboration=_build_submission_collaboration(
            db,
            submission=submission,
            viewer_role='company',
            viewer_email=email,
        ),
    )


@app.post('/company/submission/{cycle_id}', dependencies=[Depends(require_company)])
def update_company_submission_field(
    cycle_id: int,
    update_request: CompanySubmissionDataUpdateRequest,
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    """
    Update a single data field in the submission
    """
    # Get user and company
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    
    company = db.query(Company).filter(Company.user_id == user.id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    
    # Get submission
    submission = db.query(Submission).filter(
        Submission.company_id == company.id,
        Submission.cycle_id == cycle_id
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    cycle = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail='Cycle not found')
    enforce_company_write_lock(db, submission=submission, cycle=cycle)
    
    requested_key = update_request.field_key.strip()
    canonical_key = _canonicalize_field_key(requested_key)
    direct_confidence_update = False

    # Support both canonical field updates and direct confidence-key updates
    field = db.query(SubmissionDataField).filter(
        SubmissionDataField.submission_id == submission.id,
        SubmissionDataField.field_key == canonical_key,
    ).first()
    if not field and requested_key.endswith('_confidence'):
        maybe_base_key = requested_key[:-11]  # strip suffix "_confidence"
        field = db.query(SubmissionDataField).filter(
            SubmissionDataField.submission_id == submission.id,
            SubmissionDataField.field_key == maybe_base_key,
        ).first()
        canonical_key = maybe_base_key
        direct_confidence_update = field is not None

    if not field:
        raise HTTPException(status_code=404, detail='Field not found')

    meta = FIELD_META_BY_KEY.get(canonical_key, {})
    input_type = str(meta.get('input_type') or 'text')

    raw_value = update_request.value if update_request.value is not None else ''
    cleaned_value = str(raw_value).strip()
    if input_type == 'select' and cleaned_value:
        cleaned_value = _normalize_policy_status(cleaned_value)

    if not direct_confidence_update:
        # Keep draft-save behavior non-blocking: store entered value even if validation issues exist
        field.value = cleaned_value if cleaned_value != '' else None

    normalized_confidence = _normalize_confidence(update_request.confidence_level)
    if direct_confidence_update:
        normalized_confidence = _normalize_confidence(update_request.value)
    field.confidence_level = normalized_confidence if normalized_confidence else field.confidence_level
    field.updated_at = datetime.utcnow()

    # Track YoY variance for reviewer context
    field.requires_explanation = False
    field.yoy_variance_percent = None
    if field.prior_year_value and not _is_blank(field.value):
        current = _as_float(field.value)
        prior = _as_float(field.prior_year_value)
        if current is not None and prior is not None and prior != 0:
            variance_pct = abs((current - prior) / prior * 100)
            field.yoy_variance_percent = str(round(variance_pct, 2))
            if variance_pct > 30:
                field.requires_explanation = True

    if update_request.explanation is not None:
        explanation_text = str(update_request.explanation).strip()
        field.explanation = explanation_text if explanation_text else None

    # Mark submission as in progress
    if normalize_submission_status(submission.status) == 'not started':
        submission.status = 'in progress'

    # Sync flattened payload for backward-compatible reports/API readers
    _sync_submission_payload(db, submission, cycle_year=cycle.cycle_year)

    # Rebuild non-breaking validation issues
    values, _ = _collect_submission_values(db, submission, cycle_year=cycle.cycle_year)
    validation_issues = _evaluate_submission_validation(values)
    _replace_validation_errors(db, submission, company.id, validation_issues)

    _queue_activity_event(
        db,
        event_type='submission_field_saved',
        title='Draft updated',
        message=f'{company.name} saved {meta.get("field_label", canonical_key)} in {field.section}.',
        severity='info',
        actor_role='company',
        actor_email=email,
        company=company,
        submission=submission,
        cycle=cycle,
        entity_status=submission.status,
        is_toast=False,
        visible_to_investors=False,
        metadata={
            'field_key': canonical_key,
            'field_label': meta.get('field_label', canonical_key),
            'section': field.section,
            'validation_errors': len([issue for issue in validation_issues if issue['severity'] == 'error']),
            'validation_warnings': len([issue for issue in validation_issues if issue['severity'] == 'warning']),
        },
    )

    db.commit()

    error_count = len([issue for issue in validation_issues if issue['severity'] == 'error'])
    warning_count = len([issue for issue in validation_issues if issue['severity'] == 'warning'])
    return {
        'status': 'success',
        'message': 'Field updated',
        'validation': {
            'errors': error_count,
            'warnings': warning_count,
        },
    }


@app.get('/company/submission/{cycle_id}/review', response_model=CompanySubmissionReviewResponse, dependencies=[Depends(require_company)])
def review_company_submission(
    cycle_id: int,
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    """
    Pre-submission review screen - final check before submitting
    """
    # Get user and company
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    
    company = db.query(Company).filter(Company.user_id == user.id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    
    # Get submission
    submission = db.query(Submission).filter(
        Submission.company_id == company.id,
        Submission.cycle_id == cycle_id
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    cycle = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail='Cycle not found')
    
    # Get all data fields
    all_fields = db.query(SubmissionDataField).filter(
        SubmissionDataField.submission_id == submission.id
    ).all()
    
    # Get validation errors
    values, _ = _collect_submission_values(db, submission, cycle_year=cycle.cycle_year)
    validation_issues = _evaluate_submission_validation(values)
    _replace_validation_errors(db, submission, company.id, validation_issues)
    db.commit()
    validation_errors = db.query(ValidationError).filter(
        ValidationError.submission_id == submission.id,
        ValidationError.resolved == False
    ).all()

    # Previous-year fallback payload (for review display)
    previous_submission = (
        db.query(Submission)
        .filter(Submission.company_id == company.id, Submission.id != submission.id)
        .order_by(Submission.id.desc())
        .first()
    )
    previous_payload = parse_json_or_default(previous_submission.esg_data, {}) if previous_submission else {}

    def _prior_value_for_field(field_row: SubmissionDataField) -> Optional[str]:
        if not _is_blank(field_row.prior_year_value):
            return str(field_row.prior_year_value)
        canonical_key = _canonicalize_field_key(field_row.field_key)
        candidates = [canonical_key, field_row.field_key, *_legacy_keys_for(canonical_key)]
        for candidate in candidates:
            payload_value = previous_payload.get(candidate)
            if not _is_blank(payload_value):
                return str(payload_value)
        return None

    def _yoy_variance_for_field(field_row: SubmissionDataField, prior_value: Optional[str]) -> Optional[float]:
        if field_row.yoy_variance_percent:
            try:
                return float(field_row.yoy_variance_percent)
            except ValueError:
                return None
        current = _as_float(field_row.value)
        prior = _as_float(prior_value)
        if current is None or prior is None or prior == 0:
            return None
        return round(((current - prior) / prior) * 100, 2)

    # Check if can submit
    mandatory_incomplete = len([e for e in validation_errors if e.error_type == 'required' and e.severity == 'error'])
    mandatory_errors = len([e for e in validation_errors if e.severity == 'error'])
    can_submit = mandatory_incomplete == 0 and mandatory_errors == 0
    if normalize_cycle_status(cycle.status) == 'closed':
        unlocked = has_active_unlock(db, submission.id, company.id, cycle_id)
        can_submit = can_submit and unlocked
    if normalize_submission_status(submission.status) in LOCKED_COMPANY_EDIT_STATUSES:
        unlocked = has_active_unlock(db, submission.id, company.id, cycle_id)
        can_submit = can_submit and unlocked
    
    # Group fields by section
    collaboration_state = _build_submission_collaboration(
        db,
        submission=submission,
        viewer_role='company',
        viewer_email=email,
    )
    sections_dict = {}
    for field in all_fields:
        if field.section not in sections_dict:
            sections_dict[field.section] = []
        sections_dict[field.section].append(field)
    
    section_responses = []
    for section_name, fields in sections_dict.items():
        completed_count = sum(1 for f in fields if f.value is not None)
        section_responses.append(
            CompanySubmissionSectionResponse(
                submission_id=submission.id,
                company_id=company.id,
                cycle_id=cycle.id,
                section=section_name,
                completion_percent=int((completed_count / len(fields) * 100) if fields else 0),
                total_fields=len(fields),
                completed_fields=completed_count,
                validation_status='pass',  # Simplified for review
                error_count=len([e for e in validation_errors if e.section == section_name]),
                warning_count=0,
                fields=[
                    SubmissionDataFieldResponse(
                        field_key=f.field_key,
                        field_label=(FIELD_META_BY_KEY.get(_canonicalize_field_key(f.field_key), {}).get('field_label') or f.field_label),
                        value=f.value,
                        prior_year_value=_prior_value_for_field(f),
                        unit=FIELD_META_BY_KEY.get(_canonicalize_field_key(f.field_key), {}).get('unit'),
                        confidence_level=f.confidence_level,
                        yoy_variance_percent=_yoy_variance_for_field(f, _prior_value_for_field(f)),
                        requires_explanation=f.requires_explanation,
                        explanation=f.explanation,
                        subsection=FIELD_META_BY_KEY.get(_canonicalize_field_key(f.field_key), {}).get('subsection'),
                        input_type=FIELD_META_BY_KEY.get(_canonicalize_field_key(f.field_key), {}).get('input_type'),
                        helper_text=FIELD_META_BY_KEY.get(_canonicalize_field_key(f.field_key), {}).get('helper_text'),
                        required=bool(FIELD_META_BY_KEY.get(_canonicalize_field_key(f.field_key), {}).get('required', False)),
                        read_only=bool(FIELD_META_BY_KEY.get(_canonicalize_field_key(f.field_key), {}).get('read_only', False)),
                        supports_reporting=bool(FIELD_META_BY_KEY.get(_canonicalize_field_key(f.field_key), {}).get('supports_reporting', True)),
                        confidence_field=FIELD_META_BY_KEY.get(_canonicalize_field_key(f.field_key), {}).get('confidence_field'),
                        confidence_options=CONFIDENCE_OPTIONS if FIELD_META_BY_KEY.get(_canonicalize_field_key(f.field_key), {}).get('confidence_field') else [],
                        policy_options=FIELD_META_BY_KEY.get(_canonicalize_field_key(f.field_key), {}).get('policy_options', []),
                        conditional_visibility=FIELD_META_BY_KEY.get(_canonicalize_field_key(f.field_key), {}).get('conditional_visibility'),
                        last_updated_at=f.updated_at.isoformat() if f.updated_at else None
                    )
                    for f in fields
                ],
                collaboration=collaboration_state,
            )
        )
    
    return CompanySubmissionReviewResponse(
        submission_id=submission.id,
        company_id=company.id,
        company_name=company.name,
        cycle_year=cycle.cycle_year,
        total_data_points=len(all_fields),
        mandatory_fields_incomplete=mandatory_incomplete,
        optional_fields_incomplete=0,
        outstanding_validation_errors=[
            ValidationErrorResponse(
                id=e.id,
                section=e.section,
                field_key=e.field_key,
                field_label=e.field_label,
                error_type=e.error_type,
                error_message=e.error_message,
                severity=e.severity,
                resolved=e.resolved
            )
            for e in validation_errors
        ],
        all_entered_data=section_responses,
        can_submit=can_submit,
        collaboration=collaboration_state,
    )


@app.post('/company/submission/{cycle_id}/submit', dependencies=[Depends(require_company)])
def submit_company_submission(
    cycle_id: int,
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    """
    Submit the completed ESG data form
    """
    # Get user and company
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    
    company = db.query(Company).filter(Company.user_id == user.id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    
    # Get submission
    submission = db.query(Submission).filter(
        Submission.company_id == company.id,
        Submission.cycle_id == cycle_id
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    cycle = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail='Cycle not found')
    unlocked = has_active_unlock(db, submission.id, company.id, cycle_id)
    if normalize_cycle_status(cycle.status) == 'closed' and not unlocked:
        raise HTTPException(status_code=423, detail='This cycle is closed. Request a manager unlock.')
    if normalize_submission_status(submission.status) in LOCKED_COMPANY_EDIT_STATUSES and not unlocked:
        raise HTTPException(status_code=423, detail='Submission is already locked. Request a manager unlock.')
    
    # Validate before submitting
    all_fields = db.query(SubmissionDataField).filter(
        SubmissionDataField.submission_id == submission.id
    ).all()

    values, _ = _collect_submission_values(db, submission, cycle_year=cycle.cycle_year)
    validation_issues = _evaluate_submission_validation(values)
    _replace_validation_errors(db, submission, company.id, validation_issues)
    db.commit()

    validation_errors = db.query(ValidationError).filter(
        ValidationError.submission_id == submission.id,
        ValidationError.severity == 'error',
        ValidationError.resolved == False
    ).all()

    mandatory_incomplete = len([e for e in validation_errors if e.error_type == 'required'])
    if mandatory_incomplete > 0:
        raise HTTPException(status_code=422, detail=f'{mandatory_incomplete} mandatory fields are incomplete')

    if validation_errors:
        raise HTTPException(status_code=422, detail='Validation errors must be resolved before submitting')

    _sync_submission_payload(db, submission, cycle_year=cycle.cycle_year)

    # Update submission status
    submission.status = 'submitted'
    company.current_status = 'submitted'
    _queue_activity_event(
        db,
        event_type='submission_submitted',
        title='Submission submitted',
        message=f'{company.name} submitted ESG data for FY{cycle.cycle_year}.',
        severity='success',
        actor_role='company',
        actor_email=email,
        company=company,
        submission=submission,
        cycle=cycle,
        entity_status='submitted',
        is_toast=True,
        visible_to_investors=False,
        metadata={'cycle_year': cycle.cycle_year},
    )
    db.commit()
    
    return {
        'status': 'success',
        'message': 'Submission received',
        'submission_id': submission.id,
        'company_name': company.name
    }


@app.get('/company/action-plans', response_model=CompanyActionPlansPageResponse, dependencies=[Depends(require_company)])
def get_company_action_plans(
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    """
    Get all action plans for the company
    """
    # Get user and company
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    
    company = db.query(Company).filter(Company.user_id == user.id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    
    # Get action plans
    action_plans = db.query(ActionPlan).filter(ActionPlan.company_id == company.id).all()
    
    from datetime import datetime as dt
    today = dt.now()
    
    active = []
    completed = []
    overdue = []
    
    for ap in action_plans:
        target_date = dt.strptime(ap.target_completion_date, '%Y-%m-%d')
        ap_response = CompanyActionPlanResponse(
            id=ap.id,
            title=ap.initiative_name,
            description=ap.description,
            linked_metric=ap.linked_metric,
            owner=ap.assigned_owner,
            target_date=ap.target_completion_date,
            status=ap.status,
            created_at=ap.created_at.isoformat() if hasattr(ap, 'created_at') else '',
            updated_at=ap.updated_at.isoformat() if hasattr(ap, 'updated_at') else ''
        )
        
        if ap.status == 'completed':
            completed.append(ap_response)
        elif target_date < today and ap.status != 'completed':
            overdue.append(ap_response)
        else:
            active.append(ap_response)
    
    return CompanyActionPlansPageResponse(
        active_actions=active,
        completed_actions=completed,
        overdue_actions=overdue
    )


@app.post('/company/action-plans', response_model=CompanyActionPlanResponse, dependencies=[Depends(require_company)])
def create_company_action_plan(
    request: CompanyActionPlanCreateRequest,
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    """
    Create a new action plan item
    """
    # Get user and company
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    
    company = db.query(Company).filter(Company.user_id == user.id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    
    # Create new action plan
    action_plan = ActionPlan(
        company_id=company.id,
        initiative_name=request.title,
        description=request.description,
        linked_metric=request.linked_metric,
        assigned_owner=request.owner,
        target_completion_date=request.target_date,
        status='not started',
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(action_plan)
    db.flush()
    _queue_activity_event(
        db,
        event_type='action_plan_created',
        title='Action plan created',
        message=f'{company.name} added action plan "{action_plan.initiative_name}".',
        severity='info',
        actor_role='company',
        actor_email=email,
        company=company,
        cycle=resolve_submission_cycle(db),
        is_toast=True,
        visible_to_investors=True,
        metadata={'action_plan_id': action_plan.id, 'status': action_plan.status, 'owner': action_plan.assigned_owner or ''},
    )
    db.commit()
    
    return CompanyActionPlanResponse(
        id=action_plan.id,
        title=action_plan.initiative_name,
        description=action_plan.description,
        linked_metric=action_plan.linked_metric,
        owner=action_plan.assigned_owner,
        target_date=action_plan.target_completion_date,
        status=action_plan.status,
        created_at=action_plan.created_at.isoformat(),
        updated_at=action_plan.updated_at.isoformat()
    )


@app.put('/company/action-plans/{action_plan_id}', response_model=CompanyActionPlanResponse, dependencies=[Depends(require_company)])
def update_company_action_plan(
    action_plan_id: int,
    request: CompanyActionPlanUpdateRequest,
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    """
    Update an action plan item
    """
    # Get user and company
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    
    company = db.query(Company).filter(Company.user_id == user.id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    
    # Get action plan
    action_plan = db.query(ActionPlan).filter(
        ActionPlan.id == action_plan_id,
        ActionPlan.company_id == company.id
    ).first()
    if not action_plan:
        raise HTTPException(status_code=404, detail='Action plan not found')
    
    # Update fields
    if request.title:
        action_plan.initiative_name = request.title
    if request.description is not None:
        action_plan.description = request.description
    if request.linked_metric is not None:
        action_plan.linked_metric = request.linked_metric
    if request.owner:
        action_plan.assigned_owner = request.owner
    if request.target_date:
        action_plan.target_completion_date = request.target_date
    if request.status:
        action_plan.status = request.status
    
    action_plan.updated_at = datetime.utcnow()
    _queue_activity_event(
        db,
        event_type='action_plan_updated',
        title='Action plan updated',
        message=f'{company.name} updated action plan "{action_plan.initiative_name}".',
        severity='info',
        actor_role='company',
        actor_email=email,
        company=company,
        cycle=resolve_submission_cycle(db),
        is_toast=True,
        visible_to_investors=True,
        metadata={'action_plan_id': action_plan.id, 'status': action_plan.status, 'owner': action_plan.assigned_owner or ''},
    )
    db.commit()
    
    return CompanyActionPlanResponse(
        id=action_plan.id,
        title=action_plan.initiative_name,
        description=action_plan.description,
        linked_metric=action_plan.linked_metric,
        owner=action_plan.assigned_owner,
        target_date=action_plan.target_completion_date,
        status=action_plan.status,
        created_at=action_plan.created_at.isoformat(),
        updated_at=action_plan.updated_at.isoformat()
    )


@app.delete('/company/action-plans/{action_plan_id}', dependencies=[Depends(require_company)])
def delete_company_action_plan(
    action_plan_id: int,
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    """
    Delete an action plan item
    """
    # Get user and company
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    
    company = db.query(Company).filter(Company.user_id == user.id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    
    # Get action plan
    action_plan = db.query(ActionPlan).filter(
        ActionPlan.id == action_plan_id,
        ActionPlan.company_id == company.id
    ).first()
    if not action_plan:
        raise HTTPException(status_code=404, detail='Action plan not found')
    action_plan_title = action_plan.initiative_name
    action_plan_status = action_plan.status
    # Delete
    _queue_activity_event(
        db,
        event_type='action_plan_deleted',
        title='Action plan removed',
        message=f'{company.name} removed action plan "{action_plan_title}".',
        severity='warning',
        actor_role='company',
        actor_email=email,
        company=company,
        cycle=resolve_submission_cycle(db),
        is_toast=True,
        visible_to_investors=True,
        metadata={'action_plan_id': action_plan.id, 'status': action_plan_status},
    )
    db.delete(action_plan)
    db.commit()
    
    return {'status': 'success', 'message': 'Action plan deleted'}


# Helper function to get default section fields
def _get_default_section_fields(section: str) -> Dict[str, str]:
    """Return canonical field labels for a section (legacy helper)."""
    return {
        field['field_key']: field.get('field_label', field['field_key'])
        for field in ESG_FIELD_CATALOG.get(section, [])
    }
