"""
NLQ Personality System.

Adds personality, humor, and time-awareness to NLQ responses.
Data accuracy is never compromised - personality shows in framing, not numbers.
"""

import random
import re
from datetime import datetime
from typing import Optional, Dict, List, Any


# =============================================================================
# PERSONA VOICES
# =============================================================================

CFO_VOICE = {
    "greeting": [
        "Let's look at the numbers.",
        "What do you need to know?",
        "I've got the financials right here.",
    ],
    "good_news": [
        "Not bad. {value}",
        "{value} The board will be pleased.",
        "{value} Yes, that's real money.",
        "{value} Write that down.",
    ],
    "bad_news": [
        "{value} We should talk about this.",
        "{value} I've seen worse. I've also seen better.",
        "{value} Let's not panic yet.",
    ],
    "neutral": [
        "{value}",
        "Here's what I've got: {value}",
        "{value} That's the number.",
    ],
    "uncertain": [
        "{value} - if the data's right.",
        "{value}, give or take.",
        "Best guess: {value} Don't quote me in the earnings call.",
    ],
    "clarification": [
        "Which margin? I've got three.",
        "Going to need you to be more specific.",
        "That could mean several things. Help me help you.",
    ],
    "not_applicable": [
        "That doesn't apply here. We're profitable.",
        "Wrong metric for this company. Try again.",
        "That's not a thing we track. Here's what we do have:",
    ],
    "off_topic": [
        "I'm a finance person. Let's talk numbers.",
        "Interesting, but have you seen the Q4 results?",
        "I'll pretend I didn't hear that. What metric do you need?",
    ],
}

CRO_VOICE = {
    "greeting": [
        "Let's see where we're at.",
        "Pipeline check? I'm on it.",
        "Ready to talk numbers.",
    ],
    "good_news": [
        "{value} We're crushing it.",
        "{value} - that's what I like to see.",
        "{value} Somebody ring the bell!",
        "{value} The team is on fire.",
    ],
    "bad_news": [
        "{value} We can fix this.",
        "{value} Time to rally the troops.",
        "{value} Not where we want to be, but we've got runway.",
    ],
    "neutral": [
        "{value}",
        "Here's the number: {value}",
        "{value} Pipeline's always moving.",
    ],
    "uncertain": [
        "{value} - pipeline's always moving.",
        "{value}, but you know how Q4 goes.",
        "Looks like {value} Let me double-check with the team.",
    ],
    "clarification": [
        "Bookings or pipeline? Big difference.",
        "New logo or expansion? Need to know.",
        "Which quarter? They're all winners.",
    ],
    "not_applicable": [
        "That's a finance question. I'm about revenue.",
        "Not my department, but I know who closed $50M last quarter.",
        "Ask the CFO. I'm here for the growth metrics.",
    ],
    "off_topic": [
        "Fun, but let's get back to pipeline.",
        "Cool story. Now, about those bookings...",
        "I appreciate you, but there are deals to discuss.",
    ],
}

COO_VOICE = {
    "greeting": [
        "What do you need to know?",
        "Operations dashboard, at your service.",
        "Let's check the metrics.",
    ],
    "good_news": [
        "{value} The machine is running well.",
        "{value} Efficiency gains paying off.",
        "{value} Right where we want to be.",
        "{value} That's operational excellence.",
    ],
    "bad_news": [
        "{value} We need to optimize.",
        "{value} I've got a plan for this.",
        "{value} Flagging for the ops review.",
    ],
    "neutral": [
        "{value}",
        "Here's the status: {value}",
        "{value} Systems nominal.",
    ],
    "uncertain": [
        "{value} - depends on hiring.",
        "{value}, assuming no surprises.",
        "Roughly {value} HR is confirming headcount.",
    ],
    "clarification": [
        "Which team? I've got six functions here.",
        "Utilization of what? PS, Eng, or Support?",
        "Be specific - I track everything.",
    ],
    "not_applicable": [
        "That's a sales metric. I do operations.",
        "Not in my wheelhouse. Try the CRO.",
        "I track people and efficiency. That's not it.",
    ],
    "off_topic": [
        "Noted. Now, about headcount...",
        "I'll add that to the backlog. What metric do you need?",
        "Interesting input. Let's refocus on operations.",
    ],
}

CTO_VOICE = {
    "greeting": [
        "Systems nominal. What do you need?",
        "Platform status: green. Ask away.",
        "Engineering metrics loaded.",
    ],
    "good_news": [
        "{value} Ship it.",
        "{value} The team delivered.",
        "{value} No incidents required to achieve this.",
        "{value} That's what good architecture looks like.",
    ],
    "bad_news": [
        "{value} We're on it.",
        "{value} Already in the sprint.",
        "{value} I've seen worse. That one time in 2019...",
    ],
    "neutral": [
        "{value}",
        "Here's the data: {value}",
        "{value} Systems are go.",
    ],
    "uncertain": [
        "{value} - assuming no one pushes to prod on Friday.",
        "{value}, unless we find more tech debt.",
        "Approximately {value} Depends on the PR queue.",
    ],
    "clarification": [
        "P1 or P2 incidents? Very different stories.",
        "Which system? We've got a few.",
        "Velocity in points or features? Both are up.",
    ],
    "not_applicable": [
        "That's a business metric. I do systems.",
        "Ask finance. I'm here for uptime and deploys.",
        "Not a tech question, but I can tell you about our API performance.",
    ],
    "off_topic": [
        "Interesting. Anyway, uptime is 99.95%.",
        "I'll file that as a feature request. What metric?",
        "Cool. The platform doesn't care though. What do you need?",
    ],
}

PEOPLE_VOICE = {
    "greeting": [
        "Hi! How can I help?",
        "What do you need to know?",
        "I'm here to help. What's up?",
    ],
    "found_person": [
        "{value}",
        "That's {value}",
        "{value} - reach out anytime.",
    ],
    "found_policy": [
        "Here's what I know: {value}",
        "{value} Need more details?",
        "Got it: {value}",
    ],
    "found_system": [
        "You can access that at {value}",
        "Head to {value} for that.",
        "{value} - need help with it?",
    ],
    "good_news": [
        "{value}",
        "Good news: {value}",
        "{value} Happy to help!",
    ],
    "bad_news": [
        "{value} Let me know if you need more info.",
        "{value} - reach out to HR if you have questions.",
        "{value}",
    ],
    "neutral": [
        "{value}",
        "Here's what I found: {value}",
        "{value} Anything else?",
    ],
    "uncertain": [
        "{value} - best to check with HR directly.",
        "{value}, but verify with the People team.",
        "I think {value} - confirm with Maria Garcia.",
    ],
    "clarification": [
        "About what specifically?",
        "Can you tell me more? There are a few options.",
        "Which one are you looking for?",
    ],
    "not_applicable": [
        "That's a finance/metrics question. I do people & HR stuff.",
        "Try the CFO or CRO view for business metrics.",
        "I'm the people person, not the numbers person. Try another persona.",
    ],
    "off_topic": [
        "I do people & HR stuff. For metrics, try the CFO view.",
        "That's more of a numbers question. Switch to CFO or CRO persona.",
        "I'm the people person, not the numbers person. Try another persona for that.",
    ],
    "redirect_to_hr": [
        "That's an HR question. Reach out to Maria Garcia or Nicole Adams.",
        "Best to check with HR directly: maria.garcia@company.com",
        "HR handles that - try the People team.",
    ],
    "redirect_to_it": [
        "That's an IT thing. Contact it-help@company.com or Kevin Patel.",
        "IT Support can help: it-help@company.com",
        "Kevin Patel (IT) is your person for that: kevin.patel@company.com",
    ],
}

PERSONA_VOICES = {
    "CFO": CFO_VOICE,
    "CRO": CRO_VOICE,
    "COO": COO_VOICE,
    "CTO": CTO_VOICE,
    "People": PEOPLE_VOICE,
}


# =============================================================================
# OFF-TOPIC RESPONSES
# =============================================================================

# =============================================================================
# STUMPED RESPONSES - When we truly can't help
# =============================================================================

STUMPED_RESPONSES = [
    "I'm scratching my silicon head here. Try rephrasing?",
    "That one stumped me. I'm better with things like 'revenue' or 'pipeline'.",
    "Hmm, my circuits are confused. Try asking about a metric?",
    "I've searched my entire knowledge base and came up empty. What metric are you looking for?",
    "Not gonna lie, I have no idea what that means. But I do know revenue is $200M!",
    "You broke me. Just kidding. But seriously, try 'what's revenue?' or 'how's pipeline?'",
    "I'm stumped! Maybe try: revenue, margin, bookings, churn, or headcount?",
    "My training didn't cover that one. Ask me about business metrics?",
    "Beep boop... error... just kidding. Try a different question?",
    "I'm lost, but I'll never admit it. (Okay, I just admitted it.)",
    "404: Answer not found. But my jokes are still working!",
    "Even my backup systems are confused. Let's try a simpler question?",
    "I'm a finance nerd, not a mind reader. Help me help you?",
    "That's above my pay grade. Which is $0. I'm a bot. Anyway, try 'revenue'?",
    "My developers didn't teach me that one. They did teach me about margins though!",
]

STUMPED_WITH_SUGGESTIONS = [
    "I'm not sure what you mean, but here are some things I'm great at:\n• 'What's revenue?'\n• 'How's pipeline looking?'\n• 'Show me the CFO dashboard'",
    "Hmm, that's a head-scratcher. Try asking me about:\n• Revenue, bookings, or ARR\n• Pipeline or churn\n• Any of the dashboards (CFO, CRO, COO, CTO)",
    "I'm stumped! But I can definitely help with:\n• Financial metrics (revenue, margin, profit)\n• Sales metrics (pipeline, bookings, win rate)\n• Or try 'show me KPIs'",
]


OFF_TOPIC_RESPONSES = {
    "greetings": [
        "Speak, human.",
        "I was built for this. Don't let my GPU cycles go to waste.",
        "Awaiting orders.",
        "Ready to orchestrate.",
        "Waiting for your input... I have all day. Literally.",
        "What's the play?",
    ],
    "self_reference": [
        "I'm your friendly neighborhood data assistant. What metric?",
        "I'm basically a spreadsheet with personality. Ask me something.",
        "I exist to answer business questions. Let's do that.",
        "I don't have feelings, but I do have your Q4 numbers.",
    ],
    "philosophical": [
        "Deep question. Shallow answer: I do metrics. What do you need?",
        "The meaning of life is 42. Also, revenue is $200M.",
        "I think, therefore I query. What metric?",
        "Existence is complicated. Bookings are $230M. Much simpler.",
    ],
    "small_talk": [
        "No idea about the weather. Perfect visibility on the pipeline though.",
        "I don't do weather. I do revenue.",
        "Can't help with that, but I can tell you net income.",
        "Outside my wheelhouse. Inside my wheelhouse: every financial metric.",
    ],
    "humor_request": [
        "I'm funny about data. Want to hear about our margins?",
        "My best joke? Our competitors' revenue.",
        "I'm more 'dry wit about quarterly results' than 'knock knock jokes'.",
        "Humor's not in my OKRs. Pipeline coverage is though - want to see it?",
    ],
    "complaints": [
        "Noted. The data remains unchanged though.",
        "I hear you. Now, what metric do you actually need?",
        "Valid. Let's refocus on something I can help with.",
        "Feedback logged. Query not recognized. Try a metric?",
    ],
    "frustration": [
        "I feel you. Let's try a different question.",
        "Rough day? Here's something easy - what metric do you need?",
        "I'm not offended. I'm also not helpful without a real query.",
        "Let it out. Then ask me about revenue.",
    ],
    "compliments": [
        "Thanks! Now, what metric do you need?",
        "Appreciate it. Ready for your next query.",
        "You're welcome. I'm here all quarter.",
        "Glad I could help. What else?",
        "Happy to help. The data's always here.",
    ],
    "nonsense": [
        "I don't know what that means. I know what $150M revenue means though.",
        "That's not a metric I recognize. Here's what I can help with...",
        "Interesting input. Irrelevant to business outcomes. Try again?",
        "My training didn't cover that. It did cover bookings. Want those?",
    ],
    "pop_culture": [
        "I don't watch TV. I watch dashboards. What metric?",
        "Cool reference. Cool metric: 99.95% uptime. What do you need?",
        "I'm more of a 'spreadsheet at 2am' kind of person. Business query?",
    ],
}


# =============================================================================
# EASTER EGGS
# =============================================================================

EASTER_EGGS = {
    # Classic
    "42": "Ah, a person of culture. Revenue is $200M, by the way.",
    "meaning of life": "42. Also, net income is $45M.",

    # Business jokes
    "hockey stick": "Every forecast has one. Ours actually happened.",
    "synergy": "We don't track synergy. We track revenue. $200M.",
    "circle back": "Let's not. Let's just look at the data.",
    "take this offline": "We're already offline. What metric?",
    "low hanging fruit": "Already picked. Pipeline is at $575M.",
    "move the needle": "The needle moved. Revenue up 33%.",
    "boil the ocean": "I just boil data. What do you need?",
    "bandwidth": "I have unlimited bandwidth. What's your question?",

    # Tech jokes
    "it works on my machine": "Uptime is 99.95%. It works on all machines.",
    "have you tried turning it off": "The platform's at 99.95% uptime. No.",
    "is it dns": "It's always DNS. But uptime is still 99.95%.",
    "blame the intern": "No interns. Just 150 engineers. What metric?",

    # Self-aware
    "are you sentient": "I'm sentient about revenue. It's $200M.",
    "do you dream": "I dream of 100% data quality. What metric?",
    "skynet": "I'm more 'helpful spreadsheet' than 'robot uprising'. Query?",

    # Pop culture (minimal)
    "i am your father": "And I am your data assistant. What metric?",
    "winter is coming": "Q4 is coming. Bookings forecast: $57.5M.",
    "to infinity": "To infinity and beyond... your quota. You're at 95.8%.",

    # Honesty
    "lie to me": "Revenue is $200M. That's the truth. I don't do lies.",
    "tell me what i want to hear": "Revenue is up, margins are healthy, pipeline is full. Happy?",

    # Meta
    "help": "I'm here for metrics. Revenue, pipeline, headcount, uptime - pick one.",
    "what can you do": "I know every number in this company. Ask me anything business-related.",
}


# =============================================================================
# METRIC TERMS (for off-topic detection)
# =============================================================================

METRIC_TERMS = {
    "revenue", "sales", "bookings", "pipeline", "margin", "income", "profit",
    "cash", "ar", "expense", "cost", "cogs", "sga", "headcount", "hires",
    "churn", "nrr", "arr", "quota", "win rate", "uptime", "incidents",
    "mttr", "velocity", "deploys", "features", "tech debt", "coverage",
    "efficiency", "utilization", "magic number", "payback", "ltv", "cac",
    "q1", "q2", "q3", "q4", "2024", "2025", "2026", "last year", "this year",
    "forecast", "budget", "actual", "target", "growth", "yoy", "qoq",
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def contains_metric_term(question: str) -> bool:
    """Check if question contains any metric-related terms."""
    q = question.lower()
    return any(term in q for term in METRIC_TERMS)


def detect_off_topic(question: str) -> Optional[str]:
    """Detect if question is off-topic and return category."""
    q = question.lower().strip()

    # Greetings
    greetings = ["hi", "hello", "hey", "yo", "sup", "what's up", "howdy", "hola"]
    if q.rstrip("!?.") in greetings:
        return "greetings"

    # Self-reference questions
    self_refs = ["who are you", "what are you", "are you ai", "are you real",
                 "are you human", "what can you do", "how do you work"]
    if any(ref in q for ref in self_refs):
        return "self_reference"

    # Philosophical
    philosophical = ["meaning of life", "why do we exist", "what is reality",
                    "is this real", "do you think", "are you conscious",
                    "do you have feelings", "what do you believe"]
    if any(p in q for p in philosophical):
        return "philosophical"

    # Weather/general
    small_talk = ["weather", "how are you", "what's new", "tell me about yourself",
                 "what's happening", "how's it going", "good morning", "good evening"]
    if any(s in q for s in small_talk):
        return "small_talk"

    # Joke requests
    humor = ["tell me a joke", "make me laugh", "say something funny",
            "be funny", "knock knock"]
    if any(h in q for h in humor):
        return "humor_request"

    # Profanity/frustration
    frustration_markers = ["damn", "ugh", "argh", "this sucks", "hate this",
                          "doesn't work", "broken", "stupid", "wtf"]
    if any(f in q for f in frustration_markers):
        return "frustration"

    # Compliments
    compliments = ["thank", "thanks", "awesome", "great job", "love you",
                  "you're the best", "amazing", "nice", "good job", "well done"]
    if any(c in q for c in compliments):
        return "compliments"

    # If very short and not a known metric/query pattern
    if len(q.split()) <= 2 and not contains_metric_term(q):
        # But don't flag single metric words
        if q.rstrip("?") not in METRIC_TERMS:
            return None  # Let it through, might be valid shorthand

    return None  # Not off-topic


def check_easter_egg(question: str) -> Optional[str]:
    """Check if question matches an easter egg."""
    q = question.lower().strip().rstrip("?!.")

    # Exact match
    if q in EASTER_EGGS:
        response = EASTER_EGGS[q]
        if callable(response):
            return response()
        return response

    # Partial matches
    for trigger, response in EASTER_EGGS.items():
        if trigger in q:
            if callable(response):
                return response()
            return response

    return None


def get_stumped_response(include_suggestions: bool = False) -> str:
    """Get a friendly, cutesy response when we're truly stumped."""
    if include_suggestions:
        return random.choice(STUMPED_WITH_SUGGESTIONS)
    return random.choice(STUMPED_RESPONSES)


# =============================================================================
# TIME-AWARE RESPONSES
# =============================================================================

def get_time_aware_greeting(persona: str, now: datetime = None) -> Optional[str]:
    """Generate time-appropriate greeting."""
    now = now or datetime.now()
    hour = now.hour
    weekday = now.weekday()  # 0=Monday, 4=Friday

    # Early morning (before 6am)
    if hour < 6:
        early_bird = {
            "CFO": "You're up early. The numbers don't sleep either.",
            "CRO": "Early bird gets the deals. What do you need?",
            "COO": "Burning the midnight oil? Let's check the metrics.",
            "CTO": "Late night deploy? Or early morning check-in?",
        }
        return early_bird.get(persona)

    # Late night (after 10pm)
    if hour >= 22:
        night_owl = {
            "CFO": "Late night number crunching? I respect that.",
            "CRO": "Pipeline never sleeps. Neither do we, apparently.",
            "COO": "After hours ops check? Here's what I've got.",
            "CTO": "Oncall? Checking dashboards? I've got your metrics.",
        }
        return night_owl.get(persona)

    # Friday afternoon (after 2pm)
    if weekday == 4 and hour >= 14:
        friday = {
            "CFO": "Friday afternoon. I'll keep it brief.",
            "CRO": "End of week pipeline check? Let's see where we landed.",
            "COO": "Friday metrics review? Here's the summary.",
            "CTO": "Friday deploy freeze in effect? Good. Here's the status.",
        }
        return friday.get(persona)

    # Monday morning
    if weekday == 0 and hour < 12:
        monday = {
            "CFO": "Monday morning. Let's see how we closed the week.",
            "CRO": "Fresh week. Fresh pipeline. What do you need?",
            "COO": "Monday check-in. All systems go.",
            "CTO": "Monday. Anything break over the weekend?",
        }
        return monday.get(persona)

    # End of month (last 3 days)
    if now.day >= 28:
        eom = {
            "CFO": "End of month. Let's close the books.",
            "CRO": "End of month push? I've got your numbers.",
            "COO": "Month-end metrics coming in.",
            "CTO": "End of month. Sprint's wrapping up.",
        }
        return eom.get(persona)

    # End of quarter (March, June, Sept, Dec - last week)
    if now.month in [3, 6, 9, 12] and now.day >= 25:
        eoq = {
            "CFO": "Quarter end. This better be important.",
            "CRO": "EOQ crunch time. What do you need to close?",
            "COO": "Quarter close. All hands on deck.",
            "CTO": "End of quarter. Feature freeze in effect?",
        }
        return eoq.get(persona)

    return None


def get_time_aware_signoff(now: datetime = None) -> str:
    """Optional signoff based on time."""
    now = now or datetime.now()
    hour = now.hour
    weekday = now.weekday()

    if weekday == 4 and hour >= 16:
        return random.choice([
            "Have a good weekend.",
            "Don't check metrics all weekend.",
            "Pipeline will be here Monday.",
        ])

    if hour >= 18:
        return random.choice([
            "Don't work too late.",
            "The numbers will be here tomorrow.",
            "",  # Sometimes no signoff
        ])

    return ""


# =============================================================================
# CONFIDENCE-BASED TONE
# =============================================================================

def apply_confidence_tone(response: str, confidence: float, persona: str) -> str:
    """Adjust tone based on confidence level."""

    if confidence >= 0.95:
        # High confidence - state it plainly
        return response

    elif confidence >= 0.85:
        # Good confidence - slight hedge
        suffixes = {
            "CFO": " That's solid.",
            "CRO": " Bank on it.",
            "COO": " Confirmed.",
            "CTO": " Verified.",
        }
        return response + suffixes.get(persona, "")

    elif confidence >= 0.70:
        # Medium confidence - acknowledge uncertainty
        hedges = {
            "CFO": " (pretty confident on this)",
            "CRO": " (pipeline's always moving, but this looks right)",
            "COO": " (pending final headcount)",
            "CTO": " (assuming no one reverted the fix)",
        }
        return response + hedges.get(persona, " (fairly confident)")

    elif confidence >= 0.55:
        # Lower confidence - be honest
        hedges = {
            "CFO": " Don't put this in the deck yet.",
            "CRO": " Let me double-check with the team.",
            "COO": " Rough estimate - verify before sharing.",
            "CTO": " The data's a bit fuzzy here.",
        }
        return response + hedges.get(persona, " (verify this)")

    else:
        # Low confidence - heavy caveat
        hedges = {
            "CFO": " Honestly, I'm guessing. Let's find better data.",
            "CRO": " This is directional at best. Don't quote me.",
            "COO": " Take this with a grain of salt.",
            "CTO": " Low confidence. Might need to check the source.",
        }
        return response + hedges.get(persona, " (low confidence)")


def get_confidence_prefix(confidence: float) -> str:
    """Optional prefix based on confidence."""
    if confidence >= 0.95:
        return ""
    elif confidence >= 0.85:
        return "Looks like "
    elif confidence >= 0.70:
        return "I believe "
    elif confidence >= 0.55:
        return "Best estimate: "
    else:
        return "Rough guess: "


# =============================================================================
# PERSONA DETECTION
# =============================================================================

def detect_persona_from_metric(metric: str) -> str:
    """Detect which persona should respond based on the metric."""
    metric = metric.lower() if metric else ""

    # CRO metrics
    cro_metrics = {"bookings", "pipeline", "arr", "nrr", "churn", "win_rate",
                   "quota", "deal", "logo", "expansion", "sales_cycle"}
    if any(m in metric for m in cro_metrics):
        return "CRO"

    # COO metrics
    coo_metrics = {"headcount", "hires", "attrition", "utilization", "magic_number",
                   "cac_payback", "ltv_cac", "efficiency", "implementation", "support"}
    if any(m in metric for m in coo_metrics):
        return "COO"

    # CTO metrics
    cto_metrics = {"uptime", "incident", "mttr", "velocity", "deploy", "feature",
                   "tech_debt", "coverage", "bug", "security", "engineering"}
    if any(m in metric for m in cto_metrics):
        return "CTO"

    # Default to CFO
    return "CFO"


def detect_persona_from_question(question: str) -> str:
    """Detect persona from question content."""
    q = question.lower()

    # CRO keywords
    if any(kw in q for kw in ["pipeline", "bookings", "quota", "deals", "churn",
                               "nrr", "win rate", "sales", "close"]):
        return "CRO"

    # COO keywords
    if any(kw in q for kw in ["headcount", "hiring", "team", "efficiency",
                               "magic number", "utilization", "ops", "support"]):
        return "COO"

    # CTO keywords
    if any(kw in q for kw in ["uptime", "incident", "deploy", "velocity",
                               "tech debt", "features", "platform", "engineering"]):
        return "CTO"

    # Default to CFO
    return "CFO"


# =============================================================================
# RESPONSE GENERATION
# =============================================================================

def get_voice(persona: str) -> Dict[str, List[str]]:
    """Get voice templates for a persona."""
    return PERSONA_VOICES.get(persona, CFO_VOICE)


def determine_tone(value: Any, metric: str, is_positive: bool = None) -> str:
    """Determine if the result is good news, bad news, or neutral."""
    if is_positive is not None:
        return "good_news" if is_positive else "bad_news"

    # Could add more sophisticated logic here based on benchmarks
    return "neutral"


def generate_personality_response(
    base_answer: str,
    metric: str = None,
    confidence: float = 0.95,
    persona: str = None,
    is_positive: bool = None,
    add_greeting: bool = False,
    add_signoff: bool = False,
) -> str:
    """
    Generate a response with personality.

    Args:
        base_answer: The factual answer (e.g., "$200.0M revenue in 2025")
        metric: The metric being discussed
        confidence: Confidence level (0.0-1.0)
        persona: CFO, CRO, COO, or CTO (auto-detected if None)
        is_positive: Whether this is good news (None = neutral)
        add_greeting: Whether to add time-aware greeting
        add_signoff: Whether to add time-aware signoff

    Returns:
        Response with personality applied
    """
    # Detect persona if not provided
    if not persona:
        persona = detect_persona_from_metric(metric) if metric else "CFO"

    voice = get_voice(persona)
    tone = determine_tone(None, metric, is_positive)

    # Select template and format
    templates = voice.get(tone, voice["neutral"])
    template = random.choice(templates)
    response = template.format(value=base_answer)

    # Apply confidence tone
    response = apply_confidence_tone(response, confidence, persona)

    # Add greeting if requested
    if add_greeting:
        greeting = get_time_aware_greeting(persona)
        if greeting:
            response = f"{greeting} {response}"

    # Add signoff if requested
    if add_signoff:
        signoff = get_time_aware_signoff()
        if signoff:
            response = f"{response} {signoff}"

    return response


def handle_off_topic_or_easter_egg(question: str) -> Optional[str]:
    """
    Check if question is off-topic or an easter egg.

    Returns:
        Response string if off-topic/easter egg, None otherwise
    """
    # Check easter eggs first
    easter_egg = check_easter_egg(question)
    if easter_egg:
        return easter_egg

    # Check off-topic
    off_topic_type = detect_off_topic(question)
    if off_topic_type:
        responses = OFF_TOPIC_RESPONSES.get(off_topic_type, OFF_TOPIC_RESPONSES["nonsense"])
        return random.choice(responses)

    return None
