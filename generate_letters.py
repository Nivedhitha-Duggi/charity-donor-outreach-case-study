#!/usr/bin/env python3
"""
generate_letters.py

A working implementation of the improved `charity-donor-outreach` skill.
Reads donor data from a CSV at run time (never hardcoded), validates each
record, computes ask amounts with a transparent, auditable formula, and
produces review-ready draft letters — flagging anything it can't safely
handle instead of guessing.

Usage:
    python3 generate_letters.py donors.csv --campaign "Annual Fund" \
        --charity-name "ASPCA" --donation-url "aspca.org/give" \
        --signer-name "Jane Alvarez" --signer-title "Director of Development" \
        --matched false
"""

import argparse
import csv
import html
import re
import math
import os
from datetime import date

TIER_RULES = {
    "Platinum": {"pct": 0.40, "tone": "very formal"},
    "Gold": {"pct": 0.25, "tone": "warm and professional"},
    "Silver": {"pct": 0.15, "tone": "friendly"},
}
FLAT_ASK = {"Bronze": 150, "Lapsed": 50}
VALID_TIERS = set(TIER_RULES) | set(FLAT_ASK)


def parse_gift_years(gift_history):
    """Extract the sorted list of years a donor gave, from a 'YYYY: $amount; ...' string."""
    if not gift_history or not gift_history.strip():
        return []
    years = [int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", gift_history)]
    return sorted(set(years))


def consecutive_streak_ending_at(years, end_year):
    """Length of the run of consecutive years ending at end_year (0 if none/not present)."""
    if not years or end_year not in years:
        return 0
    year_set = set(years)
    streak = 1
    y = end_year - 1
    while y in year_set:
        streak += 1
        y -= 1
    return streak

CAMPAIGN_COPY = {
    "Emergency Appeal": (
        "Right now, animals in crisis can't wait — every hour matters, "
        "and your response today directly determines how quickly help arrives."
    ),
    "Annual Fund": (
        "Your continued support helps us plan for the long term and keep "
        "our programs running strong, year after year."
    ),
    "Capital Campaign": (
        "We're building the lasting infrastructure that will let this work "
        "continue for generations to come."
    ),
    "Event Fundraiser": (
        "We'd love for you to be part of the excitement — join a community "
        "of supporters coming together for this cause."
    ),
}

TIER_LINE = {
    "Platinum": "We'd also love to talk with you about a naming opportunity in recognition of your generosity.",
    "Gold": "We'd be glad to share more about our legacy giving options if that's ever of interest.",
    "Silver": "If you'd like, we can also set this up as a monthly gift.",
    "Bronze": "You can also start your own peer fundraising page to multiply your impact.",
    "Lapsed": "As a welcome back, we'd love to send you a small thank-you gift.",
}


def round_nearest_50(x):
    return round(x / 50) * 50


def derive_tier(row):
    tier = (row.get("tier") or "").strip()
    if tier in VALID_TIERS:
        return tier, None
    # try deriving from lifetime_total if tier missing/invalid
    lifetime = row.get("lifetime_total") or ""
    if lifetime.strip():
        try:
            lt = float(lifetime)
        except ValueError:
            return None, f"lifetime_total '{lifetime}' is not a number"
        if lt > 50000:
            return "Platinum", None
        elif lt >= 10000:
            return "Gold", None
        elif lt >= 1000:
            return "Silver", None
        else:
            return "Bronze", None
    return None, "tier missing/invalid and lifetime_total not present to derive it"


def validate_row(row):
    """Return list of problems. Empty list = record is safe to process."""
    problems = []
    if not row.get("donor_name", "").strip():
        problems.append("missing donor_name")

    tier, tier_problem = derive_tier(row)
    if tier_problem:
        problems.append(tier_problem)

    if tier in TIER_RULES:  # needs largest_gift for percentage calc
        lg = row.get("largest_gift", "")
        if not lg.strip():
            problems.append("missing largest_gift (required for tier's percentage-based ask)")
        else:
            try:
                float(lg)
            except ValueError:
                problems.append(f"largest_gift '{lg}' is not a number")

    if tier == "Platinum" and not row.get("relationship_manager", "").strip():
        problems.append("Platinum donor has no relationship_manager on file — required, not invented")

    ly = row.get("last_gift_year", "")
    if ly.strip():
        try:
            int(ly)
        except ValueError:
            problems.append(f"last_gift_year '{ly}' is not a number")

    return problems, tier


def compute_ask(row, tier, campaign):
    """Returns (ask_amount, calculation_trace_list)."""
    trace = []
    if tier in FLAT_ASK:
        amount = FLAT_ASK[tier]
        trace.append(f"{tier} flat ask = ${amount}")
        return amount, trace

    largest_gift = float(row["largest_gift"])
    pct = TIER_RULES[tier]["pct"]
    base = largest_gift * pct
    trace.append(f"largest_gift ${largest_gift:,.0f} x {tier} rate {pct:.0%} = ${base:,.2f}")

    base = round_nearest_50(base)
    trace.append(f"rounded to nearest $50 = ${base:,.0f}")

    last_year = int(row["last_gift_year"]) if row.get("last_gift_year", "").strip() else None
    current_year = date.today().year
    gave_last_year = last_year is not None and last_year >= current_year - 1
    if gave_last_year:
        base = base * 1.10
        trace.append(f"gave last year -> +10% loyalty uplift = ${base:,.2f}")

    if row.get("volunteer", "").strip().lower() == "yes":
        base += 100
        trace.append(f"volunteer -> +$100 flat = ${base:,.2f}")

    if campaign == "Emergency Appeal":
        base *= 1.20
        trace.append(f"Emergency Appeal -> x1.20 = ${base:,.2f}")

    base = round_nearest_50(base)
    trace.append(f"final rounded ask = ${base:,.0f}")

    # Sanity check: ask should never exceed lifetime giving
    lifetime = row.get("lifetime_total", "")
    if lifetime.strip():
        lifetime_val = float(lifetime)
        if base > lifetime_val:
            capped = round_nearest_50(lifetime_val * pct)
            trace.append(
                f"SANITY CHECK FAILED: ask ${base:,.0f} exceeds lifetime giving "
                f"${lifetime_val:,.0f} -> capped to ${capped:,.0f} based on lifetime total, flagged for review"
            )
            return capped, trace

    return base, trace


def salutation(row, tier):
    title = row.get("title", "").strip()
    first = row["donor_name"].split()[0]
    last = row["donor_name"].split()[-1]
    if tier == "Lapsed":
        return f"We'd love to have you back, {first},"
    if tier in ("Platinum", "Gold") and title:
        return f"Dear {title} {last},"
    # No guessing titles from first names — full name fallback
    return f"Dear {first} {last},"


def build_letter(row, tier, ask_amount, campaign, charity_name, donation_url,
                  signer_name, signer_title, matched, match_detail):
    sal = salutation(row, tier)
    campaign_para = CAMPAIGN_COPY.get(campaign, CAMPAIGN_COPY["Annual Fund"])

    if campaign == "Annual Fund":
        years = parse_gift_years(row.get("gift_history", ""))
        last_year = int(row["last_gift_year"]) if row.get("last_gift_year", "").strip() else None
        streak = consecutive_streak_ending_at(years, last_year) if last_year else 0
        if streak >= 3:
            campaign_para += f" In fact, you've given for {streak} years running — consistency like yours is what lets us plan for the long term."
        # streak of 1-2 years: no streak claim, base copy stands on its own

    if campaign == "Emergency Appeal" and matched:
        campaign_para += f" {match_detail}"

    tier_line = TIER_LINE.get(tier, "")
    lifetime = row.get("lifetime_total", "0")
    rm_name = row.get("relationship_manager", "").strip() or signer_name

    letter = f"""<html>
<body style="font-family: Georgia; padding: 30px; max-width: 600px; color: #222;">

  <p style="text-align:right; color: #888;">{date.today().strftime('%B %d, %Y')}</p>

  <p>{html.escape(sal)}</p>

  <p>On behalf of everyone at <strong>{html.escape(charity_name)}</strong>, thank you
  for your generosity. Your lifetime support of
  <strong>${float(lifetime):,.0f}</strong> has made a real difference.</p>

  <p>{html.escape(campaign_para)}</p>

  <p>Today, I'd like to invite you to make a gift of
  <strong>${ask_amount:,.0f}</strong>. {html.escape(tier_line)}</p>

  <p>To give, simply reply to this email or visit our donation page at
  <strong>{html.escape(donation_url)}</strong>.</p>

  <p>With gratitude,<br>
  <strong>{html.escape(rm_name)}</strong><br>
  {html.escape(signer_title)}, {html.escape(charity_name)}</p>

  <p style="color:#b00; font-size: 11px; border-top: 1px solid #ccc; padding-top: 8px;">
  DRAFT — for staff review before sending. Not a final donor communication.
  </p>

</body>
</html>"""
    return letter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--campaign", required=True, choices=list(CAMPAIGN_COPY.keys()))
    ap.add_argument("--charity-name", required=True)
    ap.add_argument("--donation-url", required=True)
    ap.add_argument("--signer-name", required=True)
    ap.add_argument("--signer-title", required=True)
    ap.add_argument("--matched", default="false")
    ap.add_argument("--match-detail", default="")
    ap.add_argument("--outdir", default="output")
    args = ap.parse_args()

    matched = args.matched.strip().lower() == "true"
    if args.campaign == "Emergency Appeal" and matched and not args.match_detail:
        raise SystemExit("Error: --matched true requires --match-detail (the actual confirmed match terms).")

    os.makedirs(os.path.join(args.outdir, "letters"), exist_ok=True)

    review_needed = []
    summary_rows = []

    with open(args.csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            problems, tier = validate_row(row)
            if problems:
                review_needed.append({
                    "donor_name": row.get("donor_name", "(unknown)"),
                    "issues": "; ".join(problems),
                })
                continue

            ask_amount, trace = compute_ask(row, tier, args.campaign)
            letter_html = build_letter(
                row, tier, ask_amount, args.campaign,
                args.charity_name, args.donation_url,
                args.signer_name, args.signer_title,
                matched, args.match_detail,
            )

            safe_name = row["donor_name"].replace(" ", "_").replace(",", "")
            filename = f"draft_{safe_name}.html"
            with open(os.path.join(args.outdir, "letters", filename), "w", encoding="utf-8") as out:
                out.write(letter_html)

            summary_rows.append({
                "donor_name": row["donor_name"],
                "tier": tier,
                "ask_amount": f"${ask_amount:,.0f}",
                "calculation": " | ".join(trace),
                "file": filename,
            })

    # Write summary CSV (for a staff reviewer to spot-check math without opening every letter)
    with open(os.path.join(args.outdir, "calculation_summary.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["donor_name", "tier", "ask_amount", "calculation", "file"])
        writer.writeheader()
        writer.writerows(summary_rows)

    # Write review-needed CSV
    with open(os.path.join(args.outdir, "needs_manual_review.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["donor_name", "issues"])
        writer.writeheader()
        writer.writerows(review_needed)

    print(f"Generated {len(summary_rows)} draft letters -> {args.outdir}/letters/")
    print(f"Flagged {len(review_needed)} donor(s) for manual review -> {args.outdir}/needs_manual_review.csv")
    print(f"Calculation summary -> {args.outdir}/calculation_summary.csv")


if __name__ == "__main__":
    main()
