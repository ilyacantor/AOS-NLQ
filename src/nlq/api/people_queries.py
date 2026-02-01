"""
People/HR query handling for AOS-NLQ.

This module handles queries related to:
- Employee lookups (who is, who reports to)
- Contact information (email, phone)
- Office locations
- PTO/Leave policies
- Benefits (401k, insurance, etc.)
- Company holidays
- HR systems (Workday, Concur)
- Company policies
"""

import json
from pathlib import Path
from typing import Optional

from src.nlq.models.response import NLQResponse


# Terms that indicate a People/HR query
PEOPLE_TERMS = [
    # People lookup
    "who is", "who's", "who runs", "who handles", "who manages",
    "reports to", "org chart", "directory", "team lead",

    # HR/Benefits
    "pto", "vacation", "time off", "leave", "parental", "maternity",
    "paternity", "sabbatical", "holiday", "holidays", "benefits",
    "health insurance", "dental", "vision", "401k", "hsa",
    "payroll", "pay stub", "w2", "w-2",

    # Policies
    "policy", "handbook", "travel policy", "expense policy",
    "remote work", "work from home", "wfh",

    # Systems (HR-related)
    "workday", "lattice", "greenhouse", "concur", "expenses",
    "how do i access", "where do i submit",

    # Office/Location
    "office address", "headquarters", "hq address", "where is the office",
    "nyc office", "austin office", "sf office",

    # General HR
    "hr question", "human resources", "people team", "recruiting",
    "onboarding", "new hire", "training budget", "learning budget",

    # Assets
    "logo", "brand guidelines", "templates", "letterhead",

    # Contact info
    "email", "phone extension", "contact for", "it help", "help desk",
]

# Title lookup mapping
TITLE_MAP = {
    "ceo": "CEO",
    "cfo": "CFO",
    "cro": "CRO",
    "coo": "COO",
    "cto": "CTO",
    "vp of engineering": "VP Engineering",
    "vp engineering": "VP Engineering",
    "vp of sales": "VP Sales",
    "vp sales": "VP Sales",
    "vp of product": "VP Product",
    "vp product": "VP Product",
    "vp of people": "VP People",
    "vp people": "VP People",
    "vp of finance": "VP Finance",
    "vp finance": "VP Finance",
    "vp of marketing": "VP Marketing",
    "vp marketing": "VP Marketing",
    "vp of customer success": "VP Customer Success",
    "vp customer success": "VP Customer Success",
    "director of recruiting": "Director of Recruiting",
    "director of it": "Director of IT",
    "hr business partner": "HR Business Partner",
    "it contact": "Director of IT",
    "hr": "VP People",
    "recruiting": "Director of Recruiting",
    "sales": "CRO",
    "engineering": "CTO",
}

# Domain contact mapping
DOMAIN_CONTACTS = {
    "hr": ("Maria Garcia", "VP People", "maria.garcia@company.com"),
    "recruiting": ("Amanda Foster", "Director of Recruiting", "amanda.foster@company.com"),
    "it": ("Kevin Patel", "Director of IT", "kevin.patel@company.com"),
    "benefits": ("Nicole Adams", "HR Business Partner", "nicole.adams@company.com"),
    "finance": ("Michael Torres", "CFO", "michael.torres@company.com"),
    "sales": ("Jennifer Park", "CRO", "jennifer.park@company.com"),
    "engineering": ("Rachel Martinez", "CTO", "rachel.martinez@company.com"),
    "operations": ("David Kim", "COO", "david.kim@company.com"),
}


def is_people_query(question: str) -> bool:
    """Detect if this is a People/HR query."""
    q = question.lower()
    return any(term in q for term in PEOPLE_TERMS)


def _load_people_data() -> dict:
    """Load people data from fact_base.json."""
    # Try multiple paths for flexibility
    paths = [
        Path('data/fact_base.json'),
        Path('/home/user/AOS-NLQ/data/fact_base.json'),
        Path('./data/fact_base.json'),
    ]

    for path in paths:
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            return data.get('people', {})

    return {}


def _create_response(
    answer: str,
    intent: str,
    metric: str,
    value=None,
    unit: str = None,
    period: str = None,
    confidence: float = 0.95
) -> NLQResponse:
    """Create a standard NLQResponse for people queries."""
    return NLQResponse(
        success=True,
        answer=answer,
        value=value,
        unit=unit,
        confidence=confidence,
        parsed_intent=intent,
        resolved_metric=metric,
        resolved_period=period
    )


def handle_people_query(question: str, fact_base=None) -> Optional[NLQResponse]:
    """
    Handle People/HR queries by looking up from fact base.

    Args:
        question: The user's question
        fact_base: Optional fact base (not used, loads from JSON)

    Returns:
        NLQResponse if handled, None otherwise
    """
    people = _load_people_data()
    if not people:
        return None

    employees = people.get('employees', [])
    offices = people.get('offices', [])
    policies = people.get('policies', [])
    systems = people.get('systems', [])
    benefits = people.get('benefits', {})
    pto_policies = people.get('pto_policies', {})
    contacts = people.get('contacts', {})
    dept_headcount = people.get('department_headcount', {})

    q = question.lower()

    # ===== PERSON LOOKUP =====
    if "who is" in q or "who's" in q:
        for term, title in TITLE_MAP.items():
            if term in q:
                emp = next((e for e in employees if e['title'] == title), None)
                if emp:
                    answer = f"{emp['name']} ({emp['title']})"
                    return _create_response(answer, "PEOPLE_LOOKUP", "employee")

    # "Who reports to X?"
    if "reports to" in q or "report to" in q:
        for emp in employees:
            if emp['name'].lower() in q or emp['title'].lower() in q:
                reports = [e for e in employees if e.get('manager') == emp['name']]
                if reports:
                    names = ", ".join([f"{r['name']} ({r['title']})" for r in reports])
                    answer = f"Reports to {emp['name']}: {names}"
                    return _create_response(answer, "PEOPLE_LOOKUP", "reports", len(reports), "people")

    # "Who does X report to?"
    if "who does" in q and "report to" in q:
        for emp in employees:
            if emp['name'].lower() in q:
                manager = emp.get('manager')
                answer = f"{emp['name']} reports to {manager}" if manager else f"{emp['name']} is the CEO (no manager)"
                return _create_response(answer, "PEOPLE_LOOKUP", "manager")

    # "Who handles X?"
    if "who handles" in q or "who's in charge" in q or "in charge of" in q:
        for domain, (name, title, email) in DOMAIN_CONTACTS.items():
            if domain in q:
                answer = f"{name} ({title}) - {email}"
                return _create_response(answer, "PEOPLE_LOOKUP", "contact")

    # ===== CONTACT INFO =====
    if "email" in q:
        for emp in employees:
            if emp['name'].lower().split()[0] in q or emp['name'].lower().split()[-1] in q:
                return _create_response(emp['email'], "PEOPLE_CONTACT", "email")

    if "phone" in q or "extension" in q:
        for emp in employees:
            if emp['title'].lower() in q or emp['name'].lower().split()[-1] in q:
                answer = f"{emp['name']}: {emp['phone']}"
                return _create_response(answer, "PEOPLE_CONTACT", "phone")

    if "where is" in q and "located" in q:
        for emp in employees:
            if emp['name'].lower().split()[-1] in q:
                answer = f"{emp['name']} is located in {emp['location']}"
                return _create_response(answer, "PEOPLE_LOCATION", "location")

    # ===== ORG STRUCTURE =====
    if "org chart" in q:
        lines = ["Sarah Chen (CEO)"]
        for e in employees:
            if e.get('manager') == 'Sarah Chen':
                lines.append(f"  └── {e['name']} ({e['title']})")
        answer = "\n".join(lines[:6])
        return _create_response(answer, "PEOPLE_ORG", "org_chart", 5, "executives")

    if "vps" in q or ("vp" in q and ("who" in q or "how many" in q)):
        vps = [e for e in employees if "VP" in e['title']]
        names = ", ".join([f"{e['name']} ({e['title']})" for e in vps])
        answer = f"VPs: {names}"
        return _create_response(answer, "PEOPLE_ORG", "vps", len(vps), "VPs")

    # ===== HEADCOUNT =====
    if "how many" in q and ("engineering" in q or "engineers" in q):
        hc = dept_headcount.get('2025', {}).get('Engineering', 115)
        hc_26 = dept_headcount.get('2026', {}).get('Engineering', 150)
        answer = f"Engineering: {hc} (2025), {hc_26} (2026F)"
        return _create_response(answer, "PEOPLE_HEADCOUNT", "engineering_headcount", hc, "people", "2025")

    if "how many" in q and "sales" in q:
        hc = dept_headcount.get('2025', {}).get('Sales', 60)
        hc_26 = dept_headcount.get('2026', {}).get('Sales', 80)
        answer = f"Sales: {hc} (2025), {hc_26} (2026F)"
        return _create_response(answer, "PEOPLE_HEADCOUNT", "sales_headcount", hc, "people", "2025")

    if "how many" in q and ("hr" in q or "people team" in q):
        hc = dept_headcount.get('2025', {}).get('People', 20)
        answer = f"People/HR: {hc} (2025)"
        return _create_response(answer, "PEOPLE_HEADCOUNT", "hr_headcount", hc, "people", "2025")

    if "total" in q and ("headcount" in q or "company" in q):
        hc = dept_headcount.get('2025', {}).get('Total', 350)
        hc_26 = dept_headcount.get('2026', {}).get('Total', 450)
        answer = f"Total headcount: {hc} (2025), {hc_26} (2026F)"
        return _create_response(answer, "PEOPLE_HEADCOUNT", "total_headcount", hc, "people", "2025")

    # ===== OFFICE / LOCATION =====
    if "headquarters" in q or "hq" in q or ("where is" in q and "office" in q):
        office = offices[0] if offices else None
        if office:
            answer = f"HQ: {office['address']}"
            return _create_response(answer, "PEOPLE_OFFICE", "hq_address")

    if "nyc" in q and ("office" in q or "address" in q):
        office = next((o for o in offices if o['name'] == 'NYC'), None)
        if office:
            answer = f"NYC: {office['address']}"
            return _create_response(answer, "PEOPLE_OFFICE", "nyc_address")

    if "austin" in q and ("office" in q or "address" in q):
        office = next((o for o in offices if o['name'] == 'Austin'), None)
        if office:
            answer = f"Austin: {office['address']}"
            return _create_response(answer, "PEOPLE_OFFICE", "austin_address")

    if "how many offices" in q:
        answer = f"{len(offices)} offices (SF, NYC, Austin)"
        return _create_response(answer, "PEOPLE_OFFICE", "office_count", len(offices), "offices")

    # ===== PTO / LEAVE =====
    if "pto" in q or ("how many" in q and ("vacation" in q or "days" in q)):
        answer = pto_policies.get('pto_days', '20 days/year (unlimited for L6+)')
        return _create_response(answer, "PEOPLE_PTO", "pto_days", 20, "days")

    if "parental" in q or "maternity" in q or "paternity" in q:
        answer = pto_policies.get('parental_leave', '16 weeks paid (all parents)')
        return _create_response(answer, "PEOPLE_PTO", "parental_leave", 16, "weeks")

    if "bereavement" in q:
        answer = pto_policies.get('bereavement', '5 days immediate family, 3 days extended')
        return _create_response(answer, "PEOPLE_PTO", "bereavement", 5, "days")

    if "sabbatical" in q:
        answer = pto_policies.get('sabbatical', '4 weeks after 5 years')
        return _create_response(answer, "PEOPLE_PTO", "sabbatical", 4, "weeks")

    if "how many holidays" in q:
        answer = f"{pto_policies.get('holidays', 11)} company holidays"
        return _create_response(answer, "PEOPLE_HOLIDAY", "holidays", 11, "holidays")

    # ===== HOLIDAYS =====
    if "thanksgiving" in q:
        return _create_response("Thanksgiving: Nov 26-27, 2026 (Thursday-Friday)", "PEOPLE_HOLIDAY", "thanksgiving", period="2026")

    if "christmas" in q:
        return _create_response("Christmas: Dec 24-25, 2026 (Christmas Eve & Christmas Day)", "PEOPLE_HOLIDAY", "christmas", period="2026")

    if "memorial day" in q:
        return _create_response("Memorial Day: May 25, 2026 (Monday)", "PEOPLE_HOLIDAY", "memorial_day", period="2026")

    if ("year end" in q or "year-end" in q) and "holiday" in q:
        return _create_response("Year-end holidays: Dec 24 (Christmas Eve), Dec 25 (Christmas), Dec 31 (New Year's Eve)", "PEOPLE_HOLIDAY", "year_end_holidays", 3, "days", "2026")

    # ===== BENEFITS =====
    if "health insurance" in q or ("what" in q and "insurance" in q):
        answer = benefits.get('health_insurance', 'Anthem Blue Cross (Bronze, Silver, Gold plans)')
        return _create_response(answer, "PEOPLE_BENEFITS", "health_insurance")

    if "401k" in q or "401(k)" in q:
        answer = benefits.get('401k', '4% company match, immediate vesting')
        return _create_response(answer, "PEOPLE_BENEFITS", "401k", 4, "%")

    if "hsa" in q:
        answer = benefits.get('hsa', 'Company contributes $1,000/year')
        return _create_response(answer, "PEOPLE_BENEFITS", "hsa", 1000, "$")

    if "learning" in q or "education" in q or "training" in q:
        answer = benefits.get('learning_budget', '$2,000/year')
        return _create_response(answer, "PEOPLE_BENEFITS", "learning_budget", 2000, "$")

    if "wellness" in q:
        answer = benefits.get('wellness_stipend', '$100/month')
        return _create_response(answer, "PEOPLE_BENEFITS", "wellness", 100, "$/month")

    if "benefits" in q and "what" in q:
        answer = f"Health ({benefits.get('health_insurance', 'Anthem')}), 401k ({benefits.get('401k', '4% match')}), HSA ({benefits.get('hsa', '$1K/yr')}), Learning ({benefits.get('learning_budget', '$2K/yr')})"
        return _create_response(answer, "PEOPLE_BENEFITS", "benefits_summary", confidence=0.9)

    # ===== SYSTEMS =====
    if "workday" in q or ("time off" in q and "request" in q):
        system = next((s for s in systems if s['name'] == 'Workday'), None)
        if system:
            answer = f"Workday: {system['url']} ({system['purpose']})"
            return _create_response(answer, "PEOPLE_SYSTEM", "workday")

    if "expenses" in q or "concur" in q:
        system = next((s for s in systems if s['name'] == 'Concur'), None)
        if system:
            answer = f"Concur: {system['url']} ({system['purpose']})"
            return _create_response(answer, "PEOPLE_SYSTEM", "concur")

    if "handbook" in q:
        policy = next((p for p in policies if p['name'] == 'Employee Handbook'), None)
        if policy:
            answer = f"Employee Handbook: {policy['url']}"
            return _create_response(answer, "PEOPLE_POLICY", "handbook")

    # ===== POLICIES =====
    if "travel policy" in q:
        policy = next((p for p in policies if p['name'] == 'Travel Policy'), None)
        if policy:
            answer = f"Travel Policy: {policy['url']}"
            return _create_response(answer, "PEOPLE_POLICY", "travel_policy")

    if "expense policy" in q:
        policy = next((p for p in policies if p['name'] == 'Expense Policy'), None)
        if policy:
            answer = f"Expense Policy: {policy['url']}"
            return _create_response(answer, "PEOPLE_POLICY", "expense_policy")

    if "remote" in q and ("work" in q or "policy" in q):
        policy = next((p for p in policies if p['name'] == 'Remote Work Policy'), None)
        if policy:
            answer = f"Remote Work Policy: {policy['url']}"
            return _create_response(answer, "PEOPLE_POLICY", "remote_policy")

    if "brand" in q and ("guidelines" in q or "guide" in q):
        policy = next((p for p in policies if p['name'] == 'Brand Guidelines'), None)
        if policy:
            answer = f"Brand Guidelines: {policy['url']}"
            return _create_response(answer, "PEOPLE_POLICY", "brand_guidelines")

    if "logo" in q:
        policy = next((p for p in policies if p['name'] == 'Logo & Assets'), None)
        if policy:
            answer = f"Logo & Assets: {policy['url']}"
            return _create_response(answer, "PEOPLE_ASSETS", "logo")

    # ===== IT / HELP DESK =====
    if "it help" in q or "help desk" in q or "it support" in q:
        answer = f"IT Help: {contacts['it_help_desk']['email']} or Kevin Patel ({contacts['it_support']['email']})"
        return _create_response(answer, "PEOPLE_CONTACT", "it_help")

    return None  # Not a People query we can handle
