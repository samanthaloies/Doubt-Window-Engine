"""
Turn a scored filing into a one-page execution brief.

This is the load-bearing component. Cold email gets ignored because it reads
like a template. The brief is what we attach (or paste) when we reach out:
a single page that says "we already looked at your situation, here's what we
think the next-90-days execution priorities are."

It doesn't ask for a meeting. It shows up with the work already done.
"""

from typing import Dict


def _fmt_amount(amount_str):
    if not amount_str:
        return "undisclosed"
    try:
        a = float(amount_str)
        if a >= 1_000_000:
            return f"${a/1_000_000:.1f}M"
        return f"${a/1_000:.0f}K"
    except (ValueError, TypeError):
        return amount_str


def _primary_contact(filing: Dict):
    related = filing.get("related_persons") or []
    if not related:
        return None
    # Prefer someone with an exec title
    for p in related:
        rels = p.get("relationships") or []
        if any("Executive" in r or "President" in r for r in rels):
            return p
    return related[0]


def _stage_thesis(stage: str) -> Dict[str, str]:
    """
    What we believe each stage needs. These come from how founders actually
    spend the first 90 days of a fresh raise. Not a generic checklist;
    specific positions.
    """
    if stage == "pre_seed":
        return {
            "headline": "Pre-seed: prove the wedge before headcount grows past 4",
            "priority_1": "Lock the ICP to one industry-and-stage cell. Most pre-seeds die spending the raise on a TAM they assumed and never sharpened.",
            "priority_2": "Build a first-pipeline that doesn't depend on the founder's personal network running out. By month 6 the warm list is exhausted; the engine has to be running by then.",
            "priority_3": "Get the AI-leverage baseline in by hire #5. Pre-seeds that pick up AI tooling early ship 2-3x more by seed.",
            "load_bearing_gap": "An honest pipeline math sheet that the founder can actually defend to the seed investor in 6-9 months.",
        }
    if stage == "seed":
        return {
            "headline": "Seed: pick the one acquisition channel that survives the next round",
            "priority_1": "Identify the one channel where CAC payback is under 12 months. Not three channels. One. The Series A pitch lives or dies on this number.",
            "priority_2": "Replace founder-led sales with a repeatable motion (or commit to founder-led for 12 more months and staff around it). Half-measures kill seeds.",
            "priority_3": "Capital raise architecture: who's on the lead list, what's the data room, what's the milestone for the term sheet conversation? Most seeds wait too long.",
            "load_bearing_gap": "A defensible CAC/LTV table from real data, not modeled assumptions. Investors at Series A will pressure-test this in week one.",
        }
    if stage == "series_a":
        return {
            "headline": "Series A: rebuild the GTM machine before Series B diligence starts",
            "priority_1": "Audit the seed-era growth assumptions. The Series A pitch was 'we found the channel.' The reality usually needs a second channel by month 18.",
            "priority_2": "Senior GTM hire architecture: VP Sales, Head of Growth, or fractional CRO depends on motion. Wrong call here burns 4-6 months and a year of runway.",
            "priority_3": "Operational layer: revops, forecasting, board reporting. The Series B investor wants to see numbers they trust, not a founder who 'has it in their head.'",
            "load_bearing_gap": "A board-ready GTM scorecard with the next-quarter commits the team is willing to sign their name to.",
        }
    return {
        "headline": "Stage unclear from filing",
        "priority_1": "Insufficient data to recommend.",
        "priority_2": "",
        "priority_3": "",
        "load_bearing_gap": "",
    }


def generate_brief(filing: Dict) -> str:
    """Return the brief as a single markdown string."""
    z = filing.get("_zeutara", {})
    stage = z.get("stage")
    thesis = _stage_thesis(stage)
    contact = _primary_contact(filing)

    issuer_name = filing.get("issuer_name") or "Unknown Issuer"
    industry = filing.get("industry") or "Unspecified industry"
    state = filing.get("issuer_state") or ""
    city = filing.get("issuer_city") or ""
    location = f"{city}, {state}" if city and state else (state or "US")
    raised = _fmt_amount(filing.get("total_sold"))
    target = _fmt_amount(filing.get("total_offering"))

    contact_line = ""
    if contact:
        name = contact.get("name", "").strip()
        rels = ", ".join(contact.get("relationships") or [])
        contact_line = f"**Primary contact (per filing):** {name}" + (f" ({rels})" if rels else "")

    score = z.get("score", 0)
    reasons = z.get("reasons") or []
    reasons_md = "\n".join(f"- {r}" for r in reasons) or "- (no positive signals scored)"

    lines = [
        f"# Execution brief: {issuer_name}",
        "",
        f"**Stage signal:** {(stage or 'unknown').replace('_', ' ').title()}  ",
        f"**Round:** {raised} closed of {target} target  ",
        f"**Industry:** {industry}  ",
        f"**Location:** {location}  ",
        f"**Fit score:** {score}/100",
        "",
        contact_line,
        "",
        "---",
        "",
        f"## What we think you're solving for in the next 90 days",
        "",
        f"**{thesis['headline']}.**",
        "",
        f"1. {thesis['priority_1']}",
        f"2. {thesis['priority_2']}",
        f"3. {thesis['priority_3']}",
        "",
        "## The load-bearing gap",
        "",
        thesis["load_bearing_gap"],
        "",
        "## Why this brief exists",
        "",
        "Your Form D filing is public the day the SEC receives it. We saw yours, did the homework above before reaching out, and figured the cheapest thing we can do for you is be specific. If any of the above is wrong, that itself is useful information for you to test against. If it's directionally right, we should talk.",
        "",
        "## Why we (Zeutara) are reaching out",
        "",
        "We build the execution architecture that founders running lean don't have time to build themselves. Pipeline, AI automation, GTM, capital raise. We are industry-agnostic but we are highly stage-specific. The above is what we'd want to dig into in a 30-minute call.",
        "",
        "---",
        "",
        f"*This brief was generated automatically from the company's SEC Form D filing. We flagged it because it scored {score}/100 against our ICP. Signals: {len(reasons)} positive.*",
        "",
        "### Underlying scoring (transparency)",
        "",
        reasons_md,
        "",
    ]
    return "\n".join(lines)


def generate_outreach_email(filing: Dict) -> str:
    """
    Companion to the brief. The email itself is short and references the brief.
    Timeline-based hook (highest-converting per Belkins 2025: 10% reply rate
    vs 4.4% for problem-based hooks).
    Citation: https://thedigitalbloom.com/learn/cold-outbound-reply-rate-benchmarks/
    """
    z = filing.get("_zeutara", {})
    stage = (z.get("stage") or "").replace("_", " ")
    contact = _primary_contact(filing)
    first_name = ""
    if contact:
        first_name = contact.get("name", "").split(" ")[0] or ""

    issuer_name = filing.get("issuer_name") or "your company"
    raised = _fmt_amount(filing.get("total_sold"))

    salutation = f"Hi {first_name}," if first_name else "Hi,"

    # Stage-specific timeline hook
    if "pre_seed" in (z.get("stage") or ""):
        hook = "From what I've seen across pre-seed rounds, the next 90 days usually decide whether the raise lasts 18 months or 12."
    elif "seed" in (z.get("stage") or ""):
        hook = "Seed teams I've worked with typically need to pick their one channel by month 6 of the raise. Most pick it by month 10 and lose 4 months."
    elif "series_a" in (z.get("stage") or ""):
        hook = "Series A teams have a 6-month window before Series B diligence math starts pulling on the GTM scorecard."
    else:
        hook = "The first 90 days after a raise tend to set the pace for the year."

    return f"""Subject: 90-day execution view on {issuer_name}

{salutation}

Saw the {raised} round close. Congrats.

{hook}

I run a small firm called Zeutara. We do execution architecture for founders at your stage: pipeline, AI automation, GTM, capital raise. Before reaching out I put together a one-page brief on what we'd dig into with you in the first 30 days. It's attached. No ask attached to it; just our read of the situation.

If any of it lands, happy to spend 30 minutes pressure-testing it with you. If not, the brief is yours either way.

Joseph
joseph@zeutara.com
"""
