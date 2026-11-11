# Building the two pages (DHAP + health alert)

Source of truth for structure, wording and locked rules = the repository's SKILL.md ("CANONICAL DHAP SPEC", RULES A–J, hot sheet spec) and the reference templates in `templates/` of the same repository (James Mitsubishi Greece, current version named in SKILL.md line 2). Read the full SKILL.md every run; the worked example `run/scripts/example_build_vacaville.py` shows the mechanics.

## Mechanics (what worked)
1. Load the templates from the freshly fetched repo. Never from memory, never from a previous dealer's output.
2. DHAP: replace everything between `<!-- SUMMARY TAB -->` and `<!-- SOLUTION TAB -->` with newly written Summary, Scorecard, AI Visibility, Findings, Opportunities panels (use `lib_dhap.swap/card/dot/mits_pill/score_bar`). Replace only the first Why Act Now dealer card; keep the MiDS card, omni-social card and banner. Keep Solution and Investment panels. Then global-replace the template dealer name/city (`James Mitsubishi Greece`, `Greece, NY`, `Greece NY`).
3. Health alert: replace the header/identity strings, the Report ID, the score (`.score-big`, `.score-fill` width), the verdict label, the teaser and the `.score-method` caption, the six KPI tiles, the revenue-impact paragraph and the stat cards (v15.2: take both from `python3 REPO/engine/alert_cards.py evidence.json` — rule 7; never pick them by hand), the three locked findings, and the funnel link.
4. Scores come from `lib_dhap.score_rows(evidence)`; the status label/colour from `status_from_lowest`. Update every occurrence: DHAP `score-num`, OVERALL row + bar width, health alert `score-big`, teaser, slider fill, captions.
5. Report ID: `GBP-<initials of dealership><ST>-<MMYY>` (James = GBP-JMGNY-1026; Vacaville = GBP-VMVCA-1026). It appears on the health alert only.
6. The funnel link on "ACCESS THE FULL REPORT" must point at the DHAP page and must be VERIFIED, never guessed: open the dealer's DHAP funnel/page in the signed-in Chrome (GHL funnel builder or the live page), read the real published URL, and use it. If the page does not exist yet or Chrome cannot show the URL, say the link is unverified and leave it flagged.

## Status other than Critical (v14 status rule)
The templates are drawn for Critical. For any other status change, consistently: verdict text (`[MAJOR ISSUES]` etc.), teaser, scale caption, score colour, banner border and slider fill gradient (Major = orange `#ea580c`, Needs Improvement = `#ca8a04`, Fully Optimized = `#15803d`), the OVERALL icon (🔴 🟠 🟡 🟢), "Major" (not "Critical") in the stat-card status words (the count-up JS reads `data-status`). The fixed phrases the spec locks stay as written ("01 · Critical Alert" breadcrumb, "C:\> Critical Alerts Identified"); the eyebrow can be made neutral ("Digital Health Alert — Attention Required"). Tell the user about this.

## When a locked element's premise is false for this dealer
The spec is written around James's gaps. Never write a false claim to satisfy it:
- Stat cards (audits before Oct 25 2026 only; from v15.2 the engine picks them, rule 7): `DEPTS_MISSING` when a combined (or separate) listing exists → use another verified alert, explain; `GBP_INACTIVITY` when the dealer posted recently → use `POSTS_30D`, explain.
- sameAs/areaServed findings and the assertion strings `'Google Link in'` and `'No areaServed in Site Schema'` when the schema already has them → drop those findings; run assertions with `--skip-cond` and list each skip for the user.
- Locked health-alert findings 06–08 → replace with this dealer's verified findings.
Every such departure goes in the final message to the user.

## Template text to correct (do this, and say so)
- "Averages from active active CLIKsearch…" → single "active" (typo).
- "MiDS reimbursement can bring net dealer cost to $0. Get optimized and syndicated in 72 hours." in the Investment banner contradicts "up to 100%, no guarantees" (KB: "up to 100% reimbursement based on available funds"). Replace those two sentences with "Up to 100% MiDS reimbursement, based on available funds. Go-live in 72 hours after onboarding." and keep the template's own "Results in 90 days." that follows them, so the banner ends "… Go-live in 72 hours after onboarding. Results in 90 days." with that sentence once, never twice. The repo assertion needs "Results in 90 days" in the Investment tab.
- The ACT NOW impact cell is "Department Revenue Gains" (title case — the repo assertion uses that exact string).

## Wording rules to re-check before saving (repo has the full list)
Never "SGE"; "MiDS" not "MIDS"; no "review gate" (review campaign = automated emails and text messages to past customers); no review-markup finding of any kind; results labels exactly as sourced (+62.4% = Google Maps views, mobile …); no dollar amounts outside the Investment tab; no guarantees; competitor claims carry the "(Competitor … not directly audited — industry pattern.)" note; photo/post cadence is "a standard we set, not a Google requirement"; no KB id, location id or other internal identifier on any page.

## Deliverables and names (owned by THIS skill, not the repo)
`lib_dhap.file_names("<Dealership Name>", "<YYYY-MM-DD report date>")` →
- `<dealership-name>_dhap_<MM-DD-YY>.html`
- `<dealership-name>_health-alert_<MM-DD-YY>.html`
- `audit_evidence_<dealership-name>_<MM-DD-YY>.md`
e.g. `vacaville-mitsubishi_dhap_10-20-26.html`, `vacaville-mitsubishi_health-alert_10-20-26.html`, `audit_evidence_vacaville-mitsubishi_10-20-26.md`. Dealership name = the name as the user gave it, lowercased, non-alphanumerics → hyphens (city only if it is part of the name). The date is the report/audit date. Send the three files to the user with the SendUserFile tool.

## Checks before delivery (all required)
`run_assertions.py` (repository suite read at run time + health alert list + consistency), `probe_mobile.py` (Playwright 360/390/430, all 8 tabs, 3 screens, count-up), `spellcheck.py`, visual look at the screenshots (slider labels must not overlap; tables stack on phone). Nothing is published unless the user asks.
