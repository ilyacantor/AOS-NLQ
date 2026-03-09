"""
Maestra type definitions — Contour Map, session state, messages, intel brief.

Ported from dcl-onboarding-agent TypeScript types, extended for Convergence
(dual-entity M&A). These are the canonical types — no other module defines them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================

class Provenance(str, Enum):
    PUBLIC_FILING = "PUBLIC_FILING"
    SYSTEM_EXTRACTED = "SYSTEM_EXTRACTED"
    STAKEHOLDER_CONFIRMED = "STAKEHOLDER_CONFIRMED"
    STAKEHOLDER_FILE = "STAKEHOLDER_FILE"
    INFERRED = "INFERRED"
    UNVERIFIED = "UNVERIFIED"


class NodeType(str, Enum):
    LEGAL_ENTITY = "LEGAL_ENTITY"
    DIVISION = "DIVISION"
    DEPARTMENT = "DEPARTMENT"
    COST_CENTER = "COST_CENTER"
    PROFIT_CENTER = "PROFIT_CENTER"
    REGION = "REGION"
    SEGMENT = "SEGMENT"


class ConflictStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    PARKED = "PARKED"


class SectionId(str, Enum):
    S0A = "0A"
    S0B = "0B"
    S1 = "1"
    S2 = "2"
    S3 = "3"
    S4 = "4"
    S5 = "5"
    S6 = "6"   # Convergence: Reconciliation Object Scoping
    S7 = "7"   # Convergence: Cross-Entity Conflict Review
    # Pre-Deal sections
    PDC = "PDC"   # Deal Context
    PDA = "PDA"   # Acquirer Profile
    PDT = "PDT"   # Target Profile
    PDS = "PDS"   # DD Scope Configuration
    PDR = "PDR"   # Run Analysis (automatic)
    PDF = "PDF"   # Findings Presentation


class SectionStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    PARKED = "PARKED"


class SessionStatus(str, Enum):
    INTEL_GATHERING = "INTEL_GATHERING"
    PREMEET_SENT = "PREMEET_SENT"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETE = "COMPLETE"


class EngagementPhase(str, Enum):
    PREWORK_RUNNING = "prework_running"
    PREWORK_COMPLETE = "prework_complete"
    SCOPING = "scoping"
    ANALYSIS_RUNNING = "analysis_running"
    ANALYSIS_COMPLETE = "analysis_complete"
    FINDINGS = "findings"
    EXECUTION = "execution"
    ONGOING = "ongoing_management"


class EngagementMode(str, Enum):
    PRE_DEAL = "pre_deal"
    CLASSIC = "classic"


class DemoPhase(str, Enum):
    PHASE_1_CONTEXT = "PHASE_1_CONTEXT"
    PHASE_2_DISCOVERY = "PHASE_2_DISCOVERY"
    PHASE_3_CONNECTION = "PHASE_3_CONNECTION"
    PHASE_4_ONBOARDING = "PHASE_4_ONBOARDING"
    PHASE_5_COFA = "PHASE_5_COFA"
    PHASE_6_CROSS_SELL = "PHASE_6_CROSS_SELL"
    PHASE_7_QOE = "PHASE_7_QOE"
    PHASE_8_WHAT_IF = "PHASE_8_WHAT_IF"
    PHASE_9_NEXT_STEPS = "PHASE_9_NEXT_STEPS"
    DEMO_COMPLETE = "DEMO_COMPLETE"


# =============================================================================
# CONTOUR MAP COMPONENTS
# =============================================================================

class HierarchyNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    type: NodeType = NodeType.DIVISION
    level: int = 0
    parent_id: str | None = None
    children: list[HierarchyNode] = Field(default_factory=list)
    source_system: str = ""
    source_field: str = ""
    confidence: float = 0.8
    provenance: Provenance = Provenance.UNVERIFIED
    notes: str = ""


class SOREntry(BaseModel):
    dimension: str
    system: str
    confidence: float = 0.8
    confirmed_by: str | None = None
    conflicts: list[str] = Field(default_factory=list)
    notes: str = ""


class Conflict(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    dimension: str
    systems: list[dict[str, str]] = Field(default_factory=list)  # [{system, value}]
    resolution: str | None = None
    resolved_by: str | None = None
    status: ConflictStatus = ConflictStatus.OPEN


class VocabularyEntry(BaseModel):
    term: str
    meaning: str
    context: str = ""
    system_equivalent: str | None = None


class PriorityQuery(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    question: str
    business_context: str = ""
    frequency: str = ""
    current_pain: str = ""
    priority: int = 5


class FollowUpTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str
    assigned_to: str | None = None
    section: str = ""
    status: str = "OPEN"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class UploadedArtifact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    filename: str
    type: str = ""
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    section: str = ""
    uploaded_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ContourMetadata(BaseModel):
    version: str = "1.0"
    created: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    last_updated: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    completeness_score: float = 0.0


# =============================================================================
# ENTERPRISE CONTOUR MAP — the crown jewel
# =============================================================================

class ContourMap(BaseModel):
    """
    Maestra's structured memory of what she learned about an entity.
    One per entity per engagement.
    """
    organizational_hierarchy: list[HierarchyNode] = Field(default_factory=list)
    sor_authority_map: list[SOREntry] = Field(default_factory=list)
    conflict_register: list[Conflict] = Field(default_factory=list)
    management_overlay: list[HierarchyNode] = Field(default_factory=list)
    vocabulary_map: list[VocabularyEntry] = Field(default_factory=list)
    priority_queries: list[PriorityQuery] = Field(default_factory=list)
    follow_up_tasks: list[FollowUpTask] = Field(default_factory=list)
    uploaded_artifacts: list[UploadedArtifact] = Field(default_factory=list)
    metadata: ContourMetadata = Field(default_factory=ContourMetadata)


# =============================================================================
# INTEL BRIEF
# =============================================================================

class IntelSource(BaseModel):
    url: str = ""
    type: str = ""  # SEC_FILING, WEBSITE, NEWS, LINKEDIN, CRUNCHBASE
    extracted_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class IntelBrief(BaseModel):
    company_overview: str = ""
    industry: str = ""
    public_structure: list[str] = Field(default_factory=list)
    known_systems: list[str] = Field(default_factory=list)
    recent_events: list[str] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    sources: list[IntelSource] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# =============================================================================
# RICH CONTENT (chat message attachments)
# =============================================================================

class TableContent(BaseModel):
    type: str = "table"
    title: str | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class HierarchyContent(BaseModel):
    type: str = "hierarchy"
    title: str | None = None
    root: dict[str, Any] = Field(default_factory=dict)


class ComparisonContent(BaseModel):
    type: str = "comparison"
    dimension: str = ""
    systems: list[dict[str, Any]] = Field(default_factory=list)


RichContent = TableContent | HierarchyContent | ComparisonContent


# =============================================================================
# SESSION & MESSAGE
# =============================================================================

class ConversationState(BaseModel):
    """Deterministic state for the interview state machine."""
    status: SessionStatus = SessionStatus.READY
    current_section: SectionId = SectionId.S1
    section_statuses: dict[str, str] = Field(default_factory=lambda: {
        "0A": SectionStatus.NOT_STARTED.value,
        "0B": SectionStatus.NOT_STARTED.value,
        "1": SectionStatus.NOT_STARTED.value,
        "2": SectionStatus.NOT_STARTED.value,
        "3": SectionStatus.NOT_STARTED.value,
        "4": SectionStatus.NOT_STARTED.value,
        "5": SectionStatus.NOT_STARTED.value,
    })


class MaestraSession(BaseModel):
    """Full session state persisted to Supabase."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    engagement_id: str = ""
    entity_id: str = ""  # which entity this scoping session is for
    status: SessionStatus = SessionStatus.READY
    current_section: SectionId = SectionId.S1
    section_statuses: dict[str, str] = Field(default_factory=lambda: {
        "0A": SectionStatus.NOT_STARTED.value,
        "0B": SectionStatus.NOT_STARTED.value,
        "1": SectionStatus.NOT_STARTED.value,
        "2": SectionStatus.NOT_STARTED.value,
        "3": SectionStatus.NOT_STARTED.value,
        "4": SectionStatus.NOT_STARTED.value,
        "5": SectionStatus.NOT_STARTED.value,
    })
    contour_map: ContourMap = Field(default_factory=ContourMap)
    intel_brief: IntelBrief | None = None
    demo_phase: DemoPhase | None = None
    customer_name: str = ""
    stakeholder_name: str = ""
    stakeholder_role: str = ""
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class MaestraMessage(BaseModel):
    """Single chat message."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: str  # "agent", "stakeholder", "system"
    content: str
    rich_content: list[dict[str, Any]] = Field(default_factory=list)
    section: str = ""
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# =============================================================================
# ENGAGEMENT (top-level container for M&A deal)
# =============================================================================

class DDDeliverable(BaseModel):
    """A due diligence deliverable that can be toggled on/off."""
    id: str
    name: str
    description: str
    selected: bool = True


class DDScope(BaseModel):
    """DD scope configuration — deliverables + synergy targets."""
    deliverables: list[DDDeliverable] = Field(default_factory=lambda: [
        DDDeliverable(id="crm_integration", name="CRM Integration Analysis",
                      description="Territory overlap, shared prospects, coverage gaps"),
        DDDeliverable(id="cross_sell", name="Cross-Sell Pipeline",
                      description="Named accounts, propensity scores, estimated ACV"),
        DDDeliverable(id="customer_migration", name="Customer Migration Planning",
                      description="Concentration risk, at-risk accounts, retention priorities"),
        DDDeliverable(id="portfolio_rationalization", name="Portfolio Rationalization",
                      description="Combined offering mapping", selected=False),
        DDDeliverable(id="tech_integration", name="Technology Integration Roadmap",
                      description="Systems inventory, SOR conflicts, migration specs"),
        DDDeliverable(id="ebitda_bridge", name="EBITDA Bridge + What-If",
                      description="Full bridge with sensitivity levers"),
    ])
    reconciliation_objects: list[str] = Field(default_factory=lambda: [
        "Financial Statements", "Customers", "Vendors", "People", "IT Landscape",
    ])
    synergy_targets: dict[str, Any] = Field(default_factory=lambda: {
        "revenue_synergy": 215_000_000,
        "cost_synergy": 180_000_000,
        "integration_budget": 100_000_000,
    })
    confirmed: bool = False


class DealContext(BaseModel):
    """Deal-level context captured during Section 1."""
    deal_type: str = "acquisition"
    deal_stage: str = ""
    timeline: str = ""
    key_concerns: list[str] = Field(default_factory=list)
    synergy_targets: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class PreDealContext(BaseModel):
    """
    Everything Maestra knows after prework — loaded before first message.
    Stored on the engagement, not on individual sessions.
    """
    acquirer_intel: IntelBrief = Field(default_factory=IntelBrief)
    target_intel: IntelBrief = Field(default_factory=IntelBrief)
    acquirer_systems: list[dict[str, str]] = Field(default_factory=list)
    target_systems: list[dict[str, str]] = Field(default_factory=list)
    system_connections: list[dict[str, str]] = Field(default_factory=list)
    deal_context: DealContext = Field(default_factory=DealContext)
    dd_scope: DDScope = Field(default_factory=DDScope)
    analysis_results: dict[str, Any] = Field(default_factory=dict)
    prework_complete: bool = False


class MaestraEngagement(BaseModel):
    """
    Top-level engagement — one per deal.
    Contains references to entity-specific scoping sessions and
    tracks cross-entity status.
    """
    engagement_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deal_name: str = ""
    mode: EngagementMode = EngagementMode.PRE_DEAL
    phase: EngagementPhase = EngagementPhase.SCOPING
    entities: list[dict[str, str]] = Field(default_factory=list)  # [{id, name}]
    objects_in_scope: list[str] = Field(default_factory=lambda: [
        "Financial Statements", "Customers", "Vendors", "People", "IT"
    ])
    session_ids: list[str] = Field(default_factory=list)  # per-entity session IDs
    stakeholder_map: dict[str, str] = Field(default_factory=dict)
    timeline: dict[str, str] = Field(default_factory=dict)
    pre_deal_context: PreDealContext | None = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# =============================================================================
# COMPLETENESS SCORING (Convergence extension)
# =============================================================================

class EngagementCompleteness(BaseModel):
    """Combined engagement completeness score."""
    entity_scores: dict[str, float] = Field(default_factory=dict)  # entity_id -> 0-100
    cofa_unification_pct: float = 0.0
    entity_resolution_pct: float = 0.0
    cross_sell_scored: bool = False
    ebitda_bridge_built: bool = False
    conflict_register_reviewed: bool = False
    qoe_baseline_established: bool = False
    combined_score: float = 0.0
