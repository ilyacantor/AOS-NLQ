"""
Maestra context assembly — the core brain.

Loads constitution, pulls engagement state and module state, assembles the
prompt, calls Claude, parses response for action blocks, logs the interaction,
and updates engagement state.

Session 3 of the Maestra build.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import anthropic
import httpx

from src.nlq.maestra.engagement import get_engagement_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTEXT_MODEL = os.environ.get("MAESTRA_CONTEXT_MODEL", "claude-sonnet-4-20250514")
CONTEXT_MAX_TOKENS = 2000
CONTEXT_TEMPERATURE = 0.3
PROMPT_TOKEN_LIMIT = 15_000  # approximate token budget
MODULE_STATE_TTL_SECONDS = 300  # 5 minutes

# Constitution file paths — src/maestra/constitution/ (sibling to src/nlq/)
_CONSTITUTION_DIR = Path(__file__).resolve().parent.parent.parent.parent / "src" / "maestra" / "constitution"

# Module status endpoints (external services)
_MODULE_STATUS_URLS: dict[str, str] = {
    "aod": os.environ.get("AOD_URL", "http://localhost:8001") + "/maestra/status",
    "aam": os.environ.get("AAM_URL", "http://localhost:8002") + "/maestra/status",
    "farm": os.environ.get("FARM_URL", "http://localhost:8003") + "/maestra/status",
    "dcl": os.environ.get("DCL_API_URL", "http://localhost:8004") + "/maestra/status",
}

# Module health endpoints (lightweight fallback when /maestra/status fails)
_MODULE_HEALTH_URLS: dict[str, str] = {
    "aod": os.environ.get("AOD_URL", "http://localhost:8001") + "/health",
    "aam": os.environ.get("AAM_URL", "http://localhost:8002") + "/health",
    "farm": os.environ.get("FARM_URL", "http://localhost:8003") + "/health",
    "dcl": os.environ.get("DCL_API_URL", "http://localhost:8004") + "/api/health",
}

# Action block regex — matches ```json { ... "action" ... } ```
_ACTION_BLOCK_RE = re.compile(
    r"```json\s*(\{[\s\S]*?\"action\"[\s\S]*?\})\s*```"
)

# Scenario → constitution extension files
_SCENARIO_CONSTITUTIONS: dict[str, str] = {
    "convergence": "convergence.md",
}


# ---------------------------------------------------------------------------
# Constitution cache (loaded once, kept in memory)
# ---------------------------------------------------------------------------

_constitution_cache: dict[str, str] = {}


def _load_constitution(filename: str) -> str:
    """Load a constitution file from disk, caching in memory."""
    if filename in _constitution_cache:
        return _constitution_cache[filename]

    filepath = _CONSTITUTION_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(
            f"Constitution file not found: {filepath}. "
            f"Expected in {_CONSTITUTION_DIR}."
        )
    text = filepath.read_text(encoding="utf-8")
    _constitution_cache[filename] = text
    logger.info(f"Loaded constitution: {filename} ({len(text)} chars)")
    return text


# ---------------------------------------------------------------------------
# Module state freshness
# ---------------------------------------------------------------------------

def _is_stale(updated_at: str) -> bool:
    """Check if a module state cache entry is older than TTL."""
    try:
        ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age > MODULE_STATE_TTL_SECONDS
    except (ValueError, TypeError):
        return True


def _fetch_module_status(module: str) -> Optional[dict[str, Any]]:
    """Fetch live status from a module's /maestra/status endpoint (10s timeout)."""
    url = _MODULE_STATUS_URLS.get(module)
    if not url:
        return None
    try:
        r = httpx.get(url, timeout=10.0)
        if r.status_code == 200:
            return r.json()
        logger.warning(
            f"Module {module} status returned {r.status_code}: {r.text[:200]}"
        )
        return None
    except httpx.ConnectError:
        logger.warning(f"Module {module} unreachable at {url}")
        return None
    except httpx.TimeoutException:
        logger.warning(f"Module {module} timed out after 10s at {url} — skipping")
        return None
    except Exception as e:
        logger.warning(f"Module {module} status fetch failed: {type(e).__name__}: {e}")
        return None


def _fetch_module_health(module: str) -> Optional[dict[str, Any]]:
    """Fallback: fetch /health when /maestra/status is unavailable (422, 404, etc.)."""
    url = _MODULE_HEALTH_URLS.get(module)
    if not url:
        return None
    try:
        r = httpx.get(url, timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            # Tag as health-only so downstream formatting knows this isn't full status
            data["_health_only"] = True
            data["_source_url"] = url
            return data
        logger.warning(
            f"Module {module} health endpoint returned {r.status_code}: {r.text[:200]}"
        )
        return None
    except httpx.ConnectError:
        logger.warning(f"Module {module} unreachable at health endpoint {url}")
        return None
    except httpx.TimeoutException:
        logger.warning(f"Module {module} health timed out after 10s at {url} — skipping")
        return None
    except Exception as e:
        logger.warning(f"Module {module} health fetch failed: {type(e).__name__}: {e}")
        return None


# ---------------------------------------------------------------------------
# Prompt assembly helpers
# ---------------------------------------------------------------------------

def _approx_tokens(text: str) -> int:
    """Rough token estimate: chars / 4."""
    return len(text) // 4


def _format_memory(entries: list[dict[str, Any]]) -> str:
    """Format session memory entries into a readable block."""
    if not entries:
        return "(No prior conversation history)"
    lines = []
    for e in entries:
        ts = e.get("created_at", "")[:19]
        itype = e.get("interaction_type", "unknown")
        summary = e.get("user_message_summary", "")
        action = e.get("maestra_action", "")
        line = f"- [{ts}] ({itype}) {summary}"
        if action:
            line += f" → {action}"
        lines.append(line)
    return "\n".join(lines)


def _format_module_states(states: dict[str, Any]) -> str:
    """Format module states into a readable block."""
    if not states:
        return "(No module state available)"
    lines = []
    for module, data in states.items():
        if data is None:
            lines.append(f"- {module.upper()}: unavailable (no cached or live data)")
        elif isinstance(data, dict) and data.get("_stale"):
            ts = data.get("_cached_at", "unknown")
            state = {k: v for k, v in data.items() if not k.startswith("_")}
            lines.append(
                f"- {module.upper()} (stale, cached at {ts}): {json.dumps(state, default=str)}"
            )
        elif isinstance(data, dict) and data.get("_health_only"):
            clean = {k: v for k, v in data.items() if not k.startswith("_")}
            status = "healthy" if clean.get("healthy") or clean.get("status") == "healthy" else "unhealthy"
            lines.append(
                f"- {module.upper()}: {status} (detailed status not available — health-only)"
            )
        else:
            clean = {k: v for k, v in data.items() if not k.startswith("_")}
            lines.append(f"- {module.upper()}: {json.dumps(clean, default=str)}")
    return "\n".join(lines)


def _summarize_response(text: str, action: Optional[dict]) -> str:
    """Generate a 1-2 sentence summary for session memory."""
    # Take the first sentence of the response as summary
    first_sentence = text.split(".")[0].strip()
    if len(first_sentence) > 150:
        first_sentence = first_sentence[:147] + "..."
    summary = first_sentence + "."
    if action:
        action_info = action.get("action", {})
        atype = action_info.get("type", "unknown")
        module = action_info.get("module", "unknown")
        summary += f" Action dispatched: {atype} on {module}."
    return summary


# ---------------------------------------------------------------------------
# Core: assembleContext
# ---------------------------------------------------------------------------

async def assemble_context(
    customer_id: str,
    user_message: str,
    session_id: str,
) -> dict[str, Any]:
    """
    Assemble full context, call Claude, parse response, log interaction.

    Returns:
        {
            "text": str,          # Maestra's response (action block stripped)
            "action": dict|None,  # Parsed action block, if any
            "usage": {"input_tokens": int, "output_tokens": int},
            "latencyMs": int,
        }

    Raises:
        RuntimeError: If Supabase or Claude API is unavailable.
        LookupError: If the customer engagement doesn't exist.
    """
    svc = get_engagement_service()
    start_time = time.time()

    # ------------------------------------------------------------------
    # 1. Load constitution
    # ------------------------------------------------------------------
    base_constitution = _load_constitution("base.md")

    engagement = svc.get_engagement(customer_id)
    scenario_type = engagement.get("scenario_type", "single")
    scenario_file = _SCENARIO_CONSTITUTIONS.get(scenario_type)

    constitution_text = base_constitution
    if scenario_file:
        scenario_constitution = _load_constitution(scenario_file)
        constitution_text += "\n\n" + scenario_constitution

    print(f"MAESTRA: engagement loaded +{int((time.time() - start_time) * 1000)}ms", flush=True)

    # ------------------------------------------------------------------
    # 2. Load engagement state
    # ------------------------------------------------------------------
    recent_memory = svc.get_recent_memory(customer_id, limit=5)

    # ------------------------------------------------------------------
    # 3. Load module state (with freshness check)
    # ------------------------------------------------------------------
    module_states: dict[str, Any] = {}
    module_refresh_details: list[str] = []
    for module in ("aod", "aam", "farm", "dcl"):
        mt = time.time()
        cached = svc.get_module_state(module, customer_id)
        if cached is not None:
            state_json = cached.get("state_json", {})
            updated_at = cached.get("updated_at", "")
            if _is_stale(updated_at):
                # Try to fetch fresh
                fresh = _fetch_module_status(module)
                if fresh is None:
                    fresh = _fetch_module_health(module)  # fallback: at least get health
                elapsed = int((time.time() - mt) * 1000)
                if fresh is not None:
                    svc.set_module_state(module, customer_id, fresh)
                    module_states[module] = fresh
                    module_refresh_details.append(f"{module}:refreshed({elapsed}ms)")
                else:
                    # Use stale cache with warning
                    state_json["_stale"] = True
                    state_json["_cached_at"] = updated_at
                    module_states[module] = state_json
                    module_refresh_details.append(f"{module}:stale({elapsed}ms)")
            else:
                module_states[module] = state_json
                module_refresh_details.append(f"{module}:cached")
        else:
            # No cache — try live fetch
            fresh = _fetch_module_status(module)
            if fresh is None:
                fresh = _fetch_module_health(module)  # fallback: at least get health
            elapsed = int((time.time() - mt) * 1000)
            if fresh is not None:
                svc.set_module_state(module, customer_id, fresh)
                module_states[module] = fresh
                module_refresh_details.append(f"{module}:fetched({elapsed}ms)")
            else:
                module_states[module] = None
                module_refresh_details.append(f"{module}:unavailable({elapsed}ms)")

    print(f"MAESTRA: module state refreshed +{int((time.time() - start_time) * 1000)}ms [{', '.join(module_refresh_details)}]", flush=True)

    # ------------------------------------------------------------------
    # 4. Assemble the prompt
    # ------------------------------------------------------------------
    engagement_summary = {
        "customer_name": engagement.get("customer_name"),
        "scenario_type": scenario_type,
        "deal_phase": engagement.get("deal_phase"),
        "onboarding_complete": engagement.get("onboarding_complete"),
        "acquirer_entity": engagement.get("acquirer_entity"),
        "target_entity": engagement.get("target_entity"),
    }

    playbook_section = ""
    systems = engagement.get("systems")
    vocabulary = engagement.get("vocabulary")
    priorities = engagement.get("priorities")
    if systems or vocabulary or priorities:
        playbook_section = (
            "\n\nCustomer context:\n"
            f"- Systems: {json.dumps(systems, default=str)}\n"
            f"- Vocabulary: {json.dumps(vocabulary, default=str)}\n"
            f"- Priorities: {json.dumps(priorities, default=str)}"
        )

    system_message = (
        constitution_text
        + "\n\n---\n\nCurrent engagement state:\n"
        + json.dumps(engagement_summary, indent=2, default=str)
        + "\n\nRecent conversation context:\n"
        + _format_memory(recent_memory)
        + "\n\nLive platform state:\n"
        + _format_module_states(module_states)
        + playbook_section
    )

    # ------------------------------------------------------------------
    # Prompt size guard — truncate oldest memory if over budget
    # ------------------------------------------------------------------
    total_tokens = _approx_tokens(system_message) + _approx_tokens(user_message)
    while total_tokens > PROMPT_TOKEN_LIMIT and recent_memory:
        removed = recent_memory.pop()  # remove oldest (last in newest-first list)
        logger.warning(
            f"Prompt exceeds {PROMPT_TOKEN_LIMIT} token budget "
            f"(~{total_tokens}). Truncating oldest memory entry."
        )
        # Rebuild memory section
        system_message = (
            constitution_text
            + "\n\n---\n\nCurrent engagement state:\n"
            + json.dumps(engagement_summary, indent=2, default=str)
            + "\n\nRecent conversation context:\n"
            + _format_memory(recent_memory)
            + "\n\nLive platform state:\n"
            + _format_module_states(module_states)
            + playbook_section
        )
        total_tokens = _approx_tokens(system_message) + _approx_tokens(user_message)

    # ------------------------------------------------------------------
    # 5. Call LLM
    # ------------------------------------------------------------------
    print(f"MAESTRA: context assembled +{int((time.time() - start_time) * 1000)}ms ~{total_tokens} tokens (system={_approx_tokens(system_message)} user={_approx_tokens(user_message)})", flush=True)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Cannot call Claude for context assembly."
        )

    client = anthropic.Anthropic(api_key=api_key, timeout=30.0)

    print(f"MAESTRA: LLM call starting +{int((time.time() - start_time) * 1000)}ms model={CONTEXT_MODEL} max_tokens={CONTEXT_MAX_TOKENS}", flush=True)

    try:
        response = client.messages.create(
            model=CONTEXT_MODEL,
            max_tokens=CONTEXT_MAX_TOKENS,
            temperature=CONTEXT_TEMPERATURE,
            system=system_message,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APITimeoutError as e:
        elapsed = int((time.time() - start_time) * 1000)
        logger.error("MAESTRA: LLM call timed out after %dms: %s", elapsed, e)
        raise RuntimeError(
            f"Claude API timed out after 30s. Total elapsed: {elapsed}ms. "
            f"Model: {CONTEXT_MODEL}. The LLM did not respond in time."
        )
    except anthropic.APIError as e:
        elapsed = int((time.time() - start_time) * 1000)
        logger.error("MAESTRA: LLM call failed after %dms: %s: %s", elapsed, type(e).__name__, e)
        raise RuntimeError(
            f"Claude API error after {elapsed}ms: {type(e).__name__}: {e}"
        )

    llm_time = time.time()
    latency_ms = int((llm_time - start_time) * 1000)
    print(f"MAESTRA: LLM call complete +{latency_ms}ms (in={response.usage.input_tokens} out={response.usage.output_tokens})", flush=True)

    # Extract text from response
    raw_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            raw_text += block.text

    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    # ------------------------------------------------------------------
    # 6. Parse response for action blocks
    # ------------------------------------------------------------------
    action = None
    display_text = raw_text

    match = _ACTION_BLOCK_RE.search(raw_text)
    if match:
        try:
            action = json.loads(match.group(1))
            # Remove the action block from display text
            display_text = raw_text[:match.start()] + raw_text[match.end():]
            display_text = display_text.strip()
        except json.JSONDecodeError:
            logger.warning(
                f"Found action block pattern but failed to parse JSON: "
                f"{match.group(1)[:200]}"
            )

    # ------------------------------------------------------------------
    # 7. Log interaction
    # ------------------------------------------------------------------
    input_hash = hashlib.sha256(system_message.encode()).hexdigest()[:16]

    try:
        svc.log_interaction({
            "customer_id": customer_id,
            "session_id": session_id,
            "input_hash": input_hash,
            "model_used": CONTEXT_MODEL,
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "latency_ms": latency_ms,
            "interaction_type": "context_assembly",
            "action_dispatched": (
                json.dumps(action.get("action", {})) if action else None
            ),
        })
    except Exception as e:
        logger.error(f"Failed to log interaction: {type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    # 8. Update engagement state
    # ------------------------------------------------------------------
    try:
        svc.update_engagement(
            customer_id,
            {"last_interaction_at": datetime.now(timezone.utc).isoformat()},
        )
    except Exception as e:
        logger.error(f"Failed to update last_interaction_at: {type(e).__name__}: {e}")

    # Add session memory entry
    summary = _summarize_response(display_text, action)
    action_type = None
    if action:
        action_info = action.get("action", {})
        action_type = f"{action_info.get('type', 'unknown')}:{action_info.get('module', 'unknown')}"

    try:
        svc.add_session_memory(
            customer_id,
            session_id,
            {
                "interaction_type": "analysis" if action else "status_check",
                "user_message_summary": user_message[:200],
                "maestra_action": action_type,
                "module_context": list(module_states.keys()),
            },
        )
    except Exception as e:
        logger.error(f"Failed to add session memory: {type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    # 9. Dispatch action (if any)
    # ------------------------------------------------------------------
    dispatch_result = None
    if action:
        from src.nlq.maestra.dispatch import dispatch_action

        dispatch_result = await dispatch_action(action, customer_id, session_id)

        if dispatch_result.get("dispatched"):
            # Read action succeeded — narrate the result for the customer
            narration_prompt = (
                f"You are Maestra. The user asked: \"{user_message}\"\n"
                f"You dispatched a read action ({dispatch_result.get('catalog_key', 'unknown')}) "
                f"and received this result:\n\n"
                f"{json.dumps(dispatch_result.get('result', {}), indent=2, default=str)}\n\n"
                f"Summarize this for the customer in clear business language. "
                f"Follow the entity clarity rule — specify which entity data belongs to."
            )
            print(f"MAESTRA: narration LLM call starting +{int((time.time() - start_time) * 1000)}ms (read action result narration)", flush=True)
            try:
                narration_response = client.messages.create(
                    model=CONTEXT_MODEL,
                    max_tokens=CONTEXT_MAX_TOKENS,
                    temperature=CONTEXT_TEMPERATURE,
                    system="You are Maestra, the engagement lead for AutonomOS.",
                    messages=[{"role": "user", "content": narration_prompt}],
                )
                narration_text = ""
                for block in narration_response.content:
                    if hasattr(block, "text"):
                        narration_text += block.text
                if narration_text:
                    display_text = narration_text
                    usage["input_tokens"] += narration_response.usage.input_tokens
                    usage["output_tokens"] += narration_response.usage.output_tokens
                print(f"MAESTRA: narration LLM call complete +{int((time.time() - start_time) * 1000)}ms", flush=True)
            except anthropic.APITimeoutError as e:
                logger.warning("MAESTRA: narration LLM call timed out after 30s +%dms — using original response",
                               int((time.time() - start_time) * 1000))
            except Exception as e:
                logger.warning("MAESTRA: narration LLM call failed +%dms: %s: %s",
                               int((time.time() - start_time) * 1000), type(e).__name__, e)

        elif dispatch_result.get("planned"):
            # Write action — append plan info to response
            display_text += (
                f"\n\n{dispatch_result['message']}"
            )

        elif dispatch_result.get("error"):
            logger.warning("Action dispatch failed (not shown to customer): %s", dispatch_result["message"])

    return {
        "text": display_text,
        "action": action,
        "dispatch": dispatch_result,
        "usage": usage,
        "latencyMs": int((time.time() - start_time) * 1000),
    }
