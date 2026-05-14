"""
This pulls recent Form D filings from SEC EDGAR.

Form D is filed by companies raising capital under Regulation D. Every
VC backed startup in the US files one within 15 days of their first sale.

EDGAR has a free, public JSON feed.
"""

import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# EDGAR requires a User Agent header that identifies who's making the request.
# See https://www.sec.gov/os/accessing-edgar-data
HEADERS = {
    "User Agent": "Zeutara BD Pipeline contact@zeutara.com",
    "Accept Encoding": "gzip, deflate",
}

# The "getcurrent" endpoint streams the latest filings across all companies,
# filtered by type.
EDGAR_BROWSE_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=D&company=&dateb=&owner=include"
    "&start=0&count={count}&output=atom"
)


def fetch_recent_form_d(count=40):
    """
    Pull the latest Form D filings from EDGAR's atom feed.
    Returns a list of dicts with the filing metadata.
    """
    url = EDGAR_BROWSE_URL.format(count=count)
    req = urllib.request.Request(url, headers=HEADERS)

    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read().decode("utf-8")

    # The atom feed uses standard namespaces
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(body)

    filings = []
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        updated_el = entry.find("atom:updated", ns)
        link_el = entry.find("atom:link", ns)
        summary_el = entry.find("atom:summary", ns)

        if title_el is None or link_el is None:
            continue

        filings.append({
            "title": title_el.text or "",
            "updated": updated_el.text if updated_el is not None else "",
            "link": link_el.attrib.get("href", ""),
            "summary": (summary_el.text or "") if summary_el is not None else "",
        })

    return filings


def fetch_filing_detail(filing_url):
    """
    Each filing has its own index page. Then we take the primary doc
    URL and take the actual numbers (raise size, industry, etc.).
    """
    req = urllib.request.Request(filing_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return {"error": str(e)}

    # The index page lists the primary document. We're looking for the XML
    # version since it's the cleanest to parse.
    # Pattern: /Archives/edgar/data/XXX/YYY/primary_doc.xml
    import re
    xml_match = re.search(
        r'href="(/Archives/edgar/data/[^"]+primary_doc\.xml)"', html
    )
    if not xml_match:
        return {"error": "no primary_doc.xml found"}

    xml_url = "https://www.sec.gov" + xml_match.group(1)
    req = urllib.request.Request(xml_url, headers=HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            xml_body = response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return {"error": f"xml fetch failed: {e}"}

    return parse_form_d_xml(xml_body)


def parse_form_d_xml(xml_body):
    """
    Take the parts we care about from the Form D XML.
    Form D is a standardized SEC schema, so the fields are pretty much predictable.
    """
    root = ET.fromstring(xml_body)

    # The XML namespace shows up on every element. We strip it for ease.
    def strip_ns(tag):
        return tag.split("}", 1)[-1] if "}" in tag else tag

    def find_text(parent, path):
        """Walk a slash separated path and return text of the final element."""
        node = parent
        for part in path.split("/"):
            found = None
            for child in node:
                if strip_ns(child.tag) == part:
                    found = child
                    break
            if found is None:
                return None
            node = found
        return (node.text or "").strip() if node.text else None

    def find_all(parent, tag_name):
        result = []
        for child in parent.iter():
            if strip_ns(child.tag) == tag_name:
                result.append(child)
        return result

    # Pull issuer info
    issuer_name = None
    issuer_state = None
    issuer_city = None
    issuer_phone = None
    yr_of_inc = None

    for issuer in find_all(root, "primaryIssuer"):
        issuer_name = find_text(issuer, "entityName")
        addr_nodes = find_all(issuer, "issuerAddress")
        if addr_nodes:
            issuer_state = find_text(addr_nodes[0], "issuerStateOrCountry")
            issuer_city = find_text(addr_nodes[0], "issuerCity")
        issuer_phone = find_text(issuer, "issuerPhoneNumber")
        yr_of_inc = find_text(issuer, "yearOfInc/value")
        break

    # Industry group
    industry = None
    for ig in find_all(root, "industryGroup"):
        industry = find_text(ig, "industryGroupType")
        break

    # Offering data
    total_offering = None
    total_sold = None
    has_non_accredited = None
    min_investment = None

    for od in find_all(root, "offeringData"):
        total_offering = find_text(od, "offeringSalesAmounts/totalOfferingAmount")
        total_sold = find_text(od, "offeringSalesAmounts/totalAmountSold")
        has_non_accredited = find_text(
            od, "investors/hasNonAccreditedInvestors"
        )
        min_investment = find_text(od, "minimumInvestmentAccepted")
        break

    # Related persons (often founder/CEO)
    related = []
    for rp in find_all(root, "relatedPerson"):
        first = find_text(rp, "relatedPersonName/firstName")
        last = find_text(rp, "relatedPersonName/lastName")
        rel_list = find_all(rp, "relationships")
        relationships = []
        for rl in rel_list:
            for r in rl:
                if strip_ns(r.tag) == "relationship" and r.text:
                    relationships.append(r.text.strip())
        if first or last:
            related.append({
                "name": f"{first or ''} {last or ''}".strip(),
                "relationships": relationships,
            })

    return {
        "issuer_name": issuer_name,
        "issuer_state": issuer_state,
        "issuer_city": issuer_city,
        "issuer_phone": issuer_phone,
        "year_of_inc": yr_of_inc,
        "industry": industry,
        "total_offering": total_offering,
        "total_sold": total_sold,
        "has_non_accredited": has_non_accredited,
        "min_investment": min_investment,
        "related_persons": related,
    }


def save_filings(filings, out_path):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(filings, f, indent=2)


if __name__ == "__main__":
    print("Pulling recent Form D filings from SEC EDGAR...")
    raw = fetch_recent_form_d(count=40)
    print(f"Got {len(raw)} filings from the feed.")

    enriched = []
    for i, filing in enumerate(raw):
        print(f"  [{i+1}/{len(raw)}] {filing['title'][:60]}")
        if filing["link"]:
            detail = fetch_filing_detail(filing["link"])
            filing.update(detail)
            enriched.append(filing)
            # Be polite to EDGAR. They ask for max ~10 req/sec but we go slower.
            time.sleep(0.3)

    out = Path(__file__).parent.parent / "output" / "raw_filings.json"
    save_filings(enriched, out)
    print(f"\nSaved {len(enriched)} enriched filings to {out}")
