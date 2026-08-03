# Charity Donor Outreach Case Study

## Overview

This repository contains my submission for the **AI Product Lead Case Study**.

The objective was to review the provided **Charity Donor Outreach** AI skill, identify design and implementation issues, and propose a more reliable, scalable, and production-ready solution for generating personalized donor letters.

---

## Improvements Implemented

Compared to the original skill, this solution introduces several enhancements:

- Reads donor information from a structured CSV file instead of embedding donor records in the prompt.
- Performs deterministic calculations (donation totals, suggested ask amounts, donor tier validation) using Python.
- Validates input data before generating letters.
- Routes incomplete or inconsistent donor records to a manual review workflow.
- Avoids generating unsupported or fabricated claims.
- Produces personalized donor letters using validated inputs.
- Generates processing summaries for transparency and review.

---

## Repository Contents

```
generate_letters.py          # Main processing script
donors.csv                   # Sample donor dataset
explanation.pdf              # Assessment of the original skill and proposed improvements
skill.md.pdf                 # Rewritten production-ready AI skill
calculation_summary.csv      # Processing summary
needs_manual_review.csv      # Records requiring manual review
```

---

## Workflow

1. Load donor data from `donors.csv`
2. Validate required fields
3. Calculate donation metrics and suggested ask amounts
4. Flag records requiring manual review
5. Generate personalized donor letters
6. Produce summary reports

---

## Design Principles

This implementation focuses on:

- Reliability
- Deterministic business logic
- Scalability
- Transparency
- Human oversight
- Production readiness

---

## Notes

This repository was developed solely as part of the JLL AI Product Lead case study. The charity referenced (ASPCA) is real, while the donor data provided in the exercise is mocked and used only for demonstration purposes.
