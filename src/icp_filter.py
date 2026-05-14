"""
Score each filing against the Zeutara ICP.

Zeutara wants founders who are:
  - raising pre-seed, seed, or Series A (so: total_offering between around $250,000 and $15,000,000)
  - operating companies, not investment funds
  - US based since Zeutara's network is here
  - inside a "doubt window" where they have new capital and an execution gap

The output isn't yes or no. It's a 0-100 score with the reasoning attached, so a
human reviewer can sort the queue and read the why behind it.
"""

from typing import Dict, List, Optional


# Industries Zeutara has no edge in and where the founder buying behavior is
# different and slower. I would exclude these.
HARD_EXCLUDE_INDUSTRIES = {
    "Pooled Investment Fund Interests",
    "Hedge Fund",
    "Private Equity Fund",
    "Venture Capital Fund",
    "Real Estate Fund",
    "Other Investment Fund",
    "Oil and Gas",
    "Coal Mining",
    "Tobacco",
    "Commercial Banking",
}

# Industries where founders are most likely to need GTM/AI/capital raise help

PREFERRED_INDUSTRIES = {
    "Technology",
    "Computers",
    "Other Technology",
    "Business Services",
    "Health Technology",
    "Biotechnology",
    "Other Health Care",
    "Retailing",
    "Restaurants",
    "Other Consumer",
    "Other Real Estate",
    "Manufacturing",
}


def _parse_amount(amount_str: Optional[str]) -> Optional[float]:
    if not amount_str:
        return None
    try:
        return float(amount_str)
    except (ValueError, TypeError):
        return None


def stage_from_raise(amount: Optional[float]) -> Optional[str]:
    """
    Map raise size to funding stage. These bands are based on Carta's State of
    Private Markets Q4 2025 medians: pre-seed around $1,000,000, seed $3,000,000, Series A $12,000,000.
    Citation: https://valueaddvc.com/blog/startup-funding-rounds-in-2025
    """
    if amount is None:
        return None
    if amount < 250_000:
        return "friends_and_family"  # too early for Zeutara
    if amount < 2_000_000:
        return "pre_seed"
    if amount < 8_000_000:
        return "seed"
    if amount < 20_000_000:
        return "series_a"
    return "growth"  # Series B+, out of scope


def score_filing(filing: Dict) -> Dict:
    """
    Return a dict with score of 0-100, stage, reasons (list of strings), and
    disqualifiers (list of strings).
    """
    score = 0
    reasons = []
    disqualifiers = []

    industry = filing.get("industry") or ""
    issuer_state = filing.get("issuer_state") or ""
    total_offering = _parse_amount(filing.get("total_offering"))
    total_sold = _parse_amount(filing.get("total_sold"))
    year_of_inc = filing.get("year_of_inc")

    # ---- Hard disqualifiers ----
    if industry in HARD_EXCLUDE_INDUSTRIES:
        disqualifiers.append(f"Industry '{industry}' is out of scope (investment fund or low fit sector)")

    if not total_offering or total_offering < 250_000:
        disqualifiers.append("Raise too small (under $250,000,000) or unreported")

    if total_offering and total_offering > 25_000_000:
        disqualifiers.append("Raise too large (>$25,000,000) for Zeutara's stage focus")

    # Non-US: Zeutara's network is US-centric. Strict for now; could relax later.
    if issuer_state and not _is_us_state(issuer_state):
        disqualifiers.append(f"Issuer location '{issuer_state}' is outside of the US")

    if disqualifiers:
        return {
            "score": 0,
            "stage": stage_from_raise(total_offering),
            "reasons": reasons,
            "disqualifiers": disqualifiers,
        }

    # ---- Positive signals ----
    stage = stage_from_raise(total_offering)
    if stage in ("pre_seed", "seed", "series_a"):
        score += 40
        reasons.append(f"Raise of ${total_offering:,.0f} maps to {stage.replace('_', ' ')} (main Zeutara stage)")

    if industry in PREFERRED_INDUSTRIES:
        score += 20
        reasons.append(f"Industry '{industry}' is one where Zeutara has GTM or AI leverage")

    if issuer_state in ("CA", "NY", "MA", "TX", "WA"):
        score += 10
        reasons.append(f"In a top 5 startup metro state ({issuer_state})")

    # "Doubt window" signal: capital is deployed but offering isn't done yet.
    # When total_sold < total_offering by a meaningful margin, the founder is
    # still actively raising. This is the highest-leverage moment to reach them.
    if total_offering and total_sold and total_sold < total_offering * 0.9:
        gap_pct = (1 - total_sold / total_offering) * 100
        score += 15
        reasons.append(f"Round still open: only {100-gap_pct:.0f}% of ${total_offering:,.0f} closed (active raise = doubt window)")

    # Recently incorporated companies = more likely to have an execution gap
    # (no senior GTM hires yet, founder doing everything).
    if year_of_inc:
        try:
            year = int(year_of_inc)
            current_year = 2026
            age = current_year - year
            if age <= 3:
                score += 10
                reasons.append(f"Incorporated {year} ({age}yr old): green field execution arch opportunity")
            elif age <= 6:
                score += 5
                reasons.append(f"Incorporated {year} ({age}yr old): likely scaling pain points")
        except (ValueError, TypeError):
            pass

    # Founder is named in related persons (vs corporate trustees etc.)
    related = filing.get("related_persons") or []
    has_founder_role = any(
        any("Executive" in r or "Director" in r or "President" in r for r in p.get("relationships", []))
        for p in related
    )
    if has_founder_role:
        score += 5
        reasons.append("Founder level decision maker named in filing (direct contact path)")

    return {
        "score": min(score, 100),
        "stage": stage,
        "reasons": reasons,
        "disqualifiers": disqualifiers,
    }


def _is_us_state(state_code: str) -> bool:
    """Form D uses two letter codes for US states, longer for countries."""
    return len(state_code) == 2 and state_code.isalpha()


def rank_filings(filings: List[Dict]) -> List[Dict]:
    """Attach scoring to each filing, sort by score desc, return all."""
    scored = []
    for f in filings:
        f["_zeutara"] = score_filing(f)
        scored.append(f)
    scored.sort(key=lambda x: x["_zeutara"]["score"], reverse=True)
    return scored
