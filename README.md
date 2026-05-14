# Doubt Window Engine

A prototype of the load-bearing component in the Zeutara BD pipeline.

Pulls recent SEC Form D filings, scores each one against the Zeutara ICP,
and generates a one-page execution brief for the qualifying ones. The brief
is what gets attached to the outreach email so the founder sees that we did
the homework before reaching out.

Built as part of the Zeutara analyst screening.

## What this is

Every US company raising venture money has to file a Form D with the SEC
within 15 days of the first sale (Regulation D). The filing is public the day
it's submitted. That makes it the cleanest free signal for "this founder just
raised, the capital is sitting in their account, and they're about to spend
the next 90 days deciding how to deploy it."

This script reads that feed, filters for the Zeutara ICP (pre-seed / seed /
Series A founders running operating companies, not investment funds), and
produces a one-page brief per company that lays out what we think they're
solving for in the next 90 days and where the execution gap probably is.

The brief is the thing. Not the email. The email is short and just points to
the brief.

## How to run it

You need Python 3.9 or later. No other dependencies. No API keys.

```
git clone <repo-url>
cd doubt-window-engine
python run.py --offline
```

That runs against a small bundled sample of 8 mock filings. Output goes to
`output/` as one markdown brief and one email draft per qualifying company,
plus a `queue.json` summary.

To run against live SEC EDGAR data:

```
python run.py --live --count 30
```

The live mode pulls the most recent 30 Form D filings and runs them through
the same pipeline. SEC EDGAR is a free public API, no signup. The script
sends a User-Agent header per the SEC's access rules.

To run the tests:

```
python tests/test_pipeline.py
```

## What's in here

```
prototype/
├── run.py                    # the orchestrator
├── src/
│   ├── fetch_filings.py      # SEC EDGAR client
│   ├── icp_filter.py         # scoring against Zeutara ICP
│   └── brief_generator.py    # turns a scored filing into a brief + email
├── tests/
│   └── test_pipeline.py      # 15 tests, all pass
├── sample_data/
│   └── sample_filings.json   # fixture for offline runs
└── output/                   # briefs and emails land here
```

## What it does (and doesn't) do

Does:
- Pulls Form D filings from SEC EDGAR's atom feed
- Parses the XML to extract: issuer name, location, industry, raise size,
  amount sold, year of incorporation, named executives
- Scores each filing 0-100 against an ICP rubric with reasons attached
- Maps raise size to funding stage using 2025 Carta benchmarks
- Generates a stage-specific brief that names the first three execution
  priorities and the load-bearing gap
- Generates a short cold email that points to the brief

Doesn't (yet):
- Enrich the contact with email/phone (Form D gives a phone number but it's
  usually the company's main line; for a real pipeline I'd waterfall through
  Apollo + Clay)
- Send the email (a real pipeline would push qualified rows into Smartlead;
  see the architecture spec for why I chose Smartlead over Instantly)
- Score against a second-derivative signal layer (hiring velocity, job posts,
  GitHub activity); the architecture spec describes this as the v2 layer.
- Handle international filings (Form D is US-only; that's a feature for
  Zeutara since the network is US-centric)

## How the scoring works

A filing scores points for:
- Raise size in the pre-seed / seed / Series A band (40 points)
- Operating company in a target industry (20)
- Located in a top-5 startup metro state (10)
- Round is still actively open (the "doubt window" signal) (15)
- Company is 0-3 years old (10), or 4-6 years old (5)
- A named founder/exec is on the filing (5)

And it's disqualified entirely (0 points) for:
- Investment fund, oil and gas, tobacco, banking
- Raise under $250k or over $25M
- Located outside the US

The reasoning is attached to every score so a human reviewer can sort the
queue and decide whether to override. See the `_zeutara.reasons` field in
`output/queue.json`.

## Sample output

Running the offline mode produces six qualifying briefs out of eight sample
filings. The top-ranked one (Northwind Robotics, a Palo Alto seed-stage tech
company) gets a brief that opens with:

> Seed: pick the one acquisition channel that survives the next round.
>
> 1. Identify the one channel where CAC payback is under 12 months. Not three
>    channels. One. The Series A pitch lives or dies on this number.
> 2. Replace founder-led sales with a repeatable motion (or commit to
>    founder-led for 12 more months and staff around it). Half-measures kill
>    seeds.
> ...

That's the kind of output you can put in front of a founder and they'll
either disagree (useful) or nod (better).

## If I had two more days

In rough priority order:

1. **Contact enrichment.** Form D gives company main lines, not founder
   direct emails. Add an Apollo or Hunter waterfall to find the founder's
   work email. This is the biggest gap.

2. **Hiring-velocity signal as a second filter.** A founder who filed a Form
   D and is also posting 5+ new roles on LinkedIn is in deeper "execution
   gap" territory than one who hasn't started hiring. The script could pull
   the LinkedIn jobs page.

3. **Better stage-specific copy.** The three current stage theses
   (pre-seed / seed / Series A) are based on what I've read about founder
   behavior. With access to Zeutara's actual client engagements I'd rewrite
   each one to reference the specific patterns Joseph has seen.

4. **Push to CRM.** Right now the output is files on disk. Add a small
   adapter that writes qualifying rows directly to Attio (or whichever CRM
   Zeutara picks). The data structure in `queue.json` is already shaped for
   it.

5. **Backtest the scoring.** Run the scoring against a known historical set
   (say, all Form Ds from Q1 2025 where Zeutara already has data on which
   companies became real prospects) and see whether the rubric actually
   predicts conversion. The current weights are a defensible starting point,
   not validated.

6. **Brief quality scoring.** Sample 20 generated briefs, have Joseph rate
   them 1-5 for "would I send this," then use his ratings to tune the stage
   theses.

## Notes for the reviewer

The whole thing is ~500 lines of Python with zero external dependencies. I
deliberately kept it boring. The architecture spec argues that the
load-bearing component is the brief itself, not the plumbing around it. The
plumbing should be as plain as possible so the brief gets the attention.

If you want to see this run against real, live data right now, run
`python run.py --live --count 20`. It will hit sec.gov directly. The first
run takes about a minute (mostly the SEC's rate-limit-friendly delays).

Joseph: if anything in here is wrong or unclear, the README is yours to
mark up. I'll fix it.

- [Candidate]
