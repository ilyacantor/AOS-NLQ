"""
Maestra state machine — pure reducer pattern.

Deterministic state transitions with no side effects.
Ported from dcl-onboarding-agent state.service.ts.
"""

from __future__ import annotations

import copy
import logging
from enum import Enum
from typing import Optional

from src.nlq.maestra.types import (
    ConversationState,
    SectionId,
    SectionStatus,
    SessionStatus,
)

logger = logging.getLogger(__name__)


# Section ordering: 0A/0B are automated, 1-5 are interview, 6-7 are Convergence
SECTION_ORDER: list[str] = ["0A", "0B", "1", "2", "3", "4", "5", "6", "7"]

# Pre-deal section ordering
PRE_DEAL_SECTION_ORDER: list[str] = ["PDI", "PDC", "PDA", "PDT", "PDS", "PDR", "PDF"]

# Only interview sections count toward completion percentage
INTERVIEW_SECTIONS: list[str] = ["1", "2", "3", "4", "5"]

# Pre-deal interview sections (PDR is automatic, PDF is presentation)
PRE_DEAL_INTERVIEW_SECTIONS: list[str] = ["PDC", "PDA", "PDT", "PDS"]


class ActionType(str, Enum):
    ADVANCE = "ADVANCE"
    JUMP = "JUMP"
    PARK = "PARK"
    RESUME = "RESUME"
    PAUSE = "PAUSE"
    COMPLETE = "COMPLETE"


class StateAction:
    def __init__(
        self,
        action_type: ActionType,
        target_section: Optional[str] = None,
        summary: str = "",
    ):
        self.type = action_type
        self.target_section = target_section
        self.summary = summary


def reduce_state(state: ConversationState, action: StateAction) -> ConversationState:
    """
    Pure reducer: returns a new ConversationState without mutating the input.

    Actions:
        ADVANCE — Mark current section COMPLETE, move to next NOT_STARTED/IN_PROGRESS
        JUMP    — Jump to target section without marking current as COMPLETE
        PARK    — Mark current section PARKED, move to next
        RESUME  — Move back to a PARKED section, set to IN_PROGRESS
        PAUSE   — Set session status to PAUSED
        COMPLETE — Mark current section COMPLETE, set session status COMPLETE
    """
    new_state = ConversationState(**copy.deepcopy(state.model_dump()))

    current = state.current_section.value

    if action.type == ActionType.ADVANCE:
        new_state.section_statuses[current] = SectionStatus.COMPLETE.value
        next_section = _find_next_section(new_state.section_statuses, current)
        if next_section:
            new_state.current_section = SectionId(next_section)
            new_state.section_statuses[next_section] = SectionStatus.IN_PROGRESS.value
            new_state.status = SessionStatus.IN_PROGRESS
        else:
            # All sections done
            new_state.status = SessionStatus.COMPLETE

    elif action.type == ActionType.JUMP:
        if action.target_section and action.target_section in new_state.section_statuses:
            new_state.current_section = SectionId(action.target_section)
            if new_state.section_statuses[action.target_section] == SectionStatus.NOT_STARTED.value:
                new_state.section_statuses[action.target_section] = SectionStatus.IN_PROGRESS.value

    elif action.type == ActionType.PARK:
        new_state.section_statuses[current] = SectionStatus.PARKED.value
        next_section = _find_next_section(new_state.section_statuses, current)
        if next_section:
            new_state.current_section = SectionId(next_section)
            new_state.section_statuses[next_section] = SectionStatus.IN_PROGRESS.value
        else:
            new_state.status = SessionStatus.COMPLETE

    elif action.type == ActionType.RESUME:
        if action.target_section and action.target_section in new_state.section_statuses:
            if new_state.section_statuses[action.target_section] == SectionStatus.PARKED.value:
                new_state.current_section = SectionId(action.target_section)
                new_state.section_statuses[action.target_section] = SectionStatus.IN_PROGRESS.value

    elif action.type == ActionType.PAUSE:
        new_state.status = SessionStatus.PAUSED

    elif action.type == ActionType.COMPLETE:
        new_state.section_statuses[current] = SectionStatus.COMPLETE.value
        new_state.status = SessionStatus.COMPLETE

    return new_state


def calculate_completion_pct(section_statuses: dict[str, str]) -> int:
    """Calculate interview completion as percentage."""
    # Detect pre-deal mode by checking for PDC section
    if "PDC" in section_statuses:
        sections = PRE_DEAL_INTERVIEW_SECTIONS
    else:
        sections = INTERVIEW_SECTIONS

    completed = sum(
        1 for s in sections
        if section_statuses.get(s) == SectionStatus.COMPLETE.value
    )
    return round((completed / len(sections)) * 100) if sections else 0


def _find_next_section(
    section_statuses: dict[str, str],
    current: str,
) -> str | None:
    """Find next NOT_STARTED or IN_PROGRESS section after current."""
    # Determine which section order to use
    order = PRE_DEAL_SECTION_ORDER if current in PRE_DEAL_SECTION_ORDER else SECTION_ORDER

    try:
        idx = order.index(current)
    except ValueError:
        return None

    for i in range(idx + 1, len(order)):
        section = order[i]
        status = section_statuses.get(section)
        if status in (SectionStatus.NOT_STARTED.value, SectionStatus.IN_PROGRESS.value):
            return section

    return None
