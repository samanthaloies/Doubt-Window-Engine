"""
Run the whole pipeline

Two modes:
  --offline   reads sample_data/sample_filings.json (works without network)
  --live      pulls from SEC EDGAR (needs network, the sandbox you may be in
              right now might not have outbound network access)

Usage:
  python run.py --offline
  python run.py --live --count 30
"""

import argparse
import json
import sys
from pathlib import Path

# Make sure src/ is importable when running from the repo root
SRC = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC))

from icp_filter import rank_filings
from brief_generator import generate_brief, generate_outreach_email


def load_offline():
    sample = Path(__file__).parent / "sample_data" / "sample_filings.json"
    with open(sample) as f:
        return json.load(f)


def load_live(count):
    # Importing inside the function so the script still loads even if the
    # fetcher fails (e.g. no network in an air-gapped review machine).
    from fetch_filings import fetch_recent_form_d, fetch_filing_detail
    import time

    raw = fetch_recent_form_d(count=count)
    enriched = []
    for i, filing in enumerate(raw):
        print(f"  [{i+1}/{len(raw)}] {filing['title'][:60]}")
        if filing.get("link"):
            detail = fetch_filing_detail(filing["link"])
            filing.update(detail)
            enriched.append(filing)
            time.sleep(0.3)
    return enriched


def main():
    parser = argparse.ArgumentParser(description="Zeutara Doubt Window Engine")
    parser.add_argument("--offline", action="store_true",
                        help="Use bundled sample data (default)")
    parser.add_argument("--live", action="store_true",
                        help="Pull fresh filings from SEC EDGAR")
    parser.add_argument("--count", type=int, default=20,
                        help="How many filings to pull in live mode")
    parser.add_argument("--min-score", type=int, default=40,
                        help="Skip filings with fit score below this")
    args = parser.parse_args()

    if args.live:
        print("Pulling live filings from SEC EDGAR...")
        try:
            filings = load_live(args.count)
        except Exception as e:
            print(f"Live fetch failed ({e}). Falling back to offline sample.")
            filings = load_offline()
    else:
        print("Running in offline mode with bundled sample data.")
        filings = load_offline()

    print(f"\nScoring {len(filings)} filings against Zeutara ICP...")
    ranked = rank_filings(filings)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    # Summary table
    print(f"\n{'='*72}")
    print(f"{'Score':>6}  {'Stage':<12}  {'State':<6}  Company")
    print(f"{'-'*72}")
    qualified = []
    for f in ranked:
        z = f["_zeutara"]
        score = z["score"]
        stage = (z.get("stage") or "-").replace("_", " ")
        state = f.get("issuer_state") or "-"
        name = (f.get("issuer_name") or "?")[:40]
        disq = " [DISQUALIFIED]" if z.get("disqualifiers") else ""
        print(f"{score:>6}  {stage:<12}  {state:<6}  {name}{disq}")
        if score >= args.min_score and not z.get("disqualifiers"):
            qualified.append(f)
    print(f"{'='*72}")
    print(f"\n{len(qualified)} of {len(ranked)} filings qualified (score >= {args.min_score})")

    # Generate briefs for everyone who qualified
    print(f"\nGenerating briefs to {output_dir}/")
    for f in qualified:
        name = f.get("issuer_name", "unknown")
        safe = "".join(c if c.isalnum() else "_" for c in name)[:60]

        brief = generate_brief(f)
        brief_path = output_dir / f"{safe}_brief.md"
        with open(brief_path, "w") as fp:
            fp.write(brief)

        email = generate_outreach_email(f)
        email_path = output_dir / f"{safe}_email.txt"
        with open(email_path, "w") as fp:
            fp.write(email)

        print(f"  - {name}: brief + email")

    # Write a summary JSON for the CRM import / human reviewer
    summary_path = output_dir / "queue.json"
    with open(summary_path, "w") as f:
        json.dump([
            {
                "issuer_name": r.get("issuer_name"),
                "state": r.get("issuer_state"),
                "stage": r["_zeutara"].get("stage"),
                "score": r["_zeutara"].get("score"),
                "reasons": r["_zeutara"].get("reasons", []),
                "disqualifiers": r["_zeutara"].get("disqualifiers", []),
                "total_offering": r.get("total_offering"),
                "total_sold": r.get("total_sold"),
            }
            for r in ranked
        ], f, indent=2)
    print(f"\nWrote summary queue to {summary_path}")
    print("Done.")


if __name__ == "__main__":
    main()
