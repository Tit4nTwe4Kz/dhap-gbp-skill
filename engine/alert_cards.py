#!/usr/bin/env python3
"""DHAP GBP engine — Alert stat cards follow the dealer (rule 7, v15.2; audits dated on or after Oct 25 2026).

The four stat cards on Alert screen 3 are the dealer's four weakest areas, not a fixed set. The areas are the eight
scored categories plus AI answers (from the AI answer check). Each area has a short menu of cards; a card shows only
when its number is a real problem, and the number comes straight from the evidence (never rounded up).
  rank    area score minus its customer weight, lowest first: get found (Claimed, Profile Completeness, NAP, AI
          answers) 1.0 · get chosen (Reviews, Posts, Photos) 0.5 · website schema 0. Ties: the order in AREAS.
  pick    the first card in each area's menu that shows a real problem; an area with no such card is skipped;
          one card per area; up to four. Every area at 10 -> no cards -> no Digital Health Alert.
  status  each card's status comes from its own area score: 5.0 or below Critical, below 7.0 Major, else Needs Improvement.
  text    the Revenue Impact paragraph ("With ..., ... and ...") is written from the first three cards.
Audits dated before Oct 25 2026 keep the cards written in the content file.
Usage: python3 alert_cards.py evidence.json   -> the cards and the paragraph (JSON)
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import score as S, ai_visibility as AV

START = "2026-10-25"
AREAS = ["Profile Completeness", "GBP Claimed & Verified", "Google Maps / NAP Consistency", "AI Answers",
         "Reviews & Reputation", "GBP Posts & Engagement", "Photos & Visual Presence",
         "Schema Field Completeness", "LocalBusiness Schema"]
WEIGHT = {"Profile Completeness": 1.0, "GBP Claimed & Verified": 1.0, "Google Maps / NAP Consistency": 1.0, "AI Answers": 1.0,
          "Reviews & Reputation": .5, "GBP Posts & Engagement": .5, "Photos & Visual Presence": .5,
          "Schema Field Completeness": 0, "LocalBusiness Schema": 0}
DEPT = {"sales": "Sales", "service": "Service", "parts": "Parts", "combined": "Service &amp; Parts"}
WORDS = "no one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()

def applies(ev): return str(ev.get("audit_date", "")) >= START
def w(n): return WORDS[n] if 0 <= n < len(WORDS) else f"{n:,}"
def w_of(n): return "none" if n == 0 else w(n)   # before "of": "none of 125", never "no of 125" (v16.4)
def s(n, one="", many="s"): return one if n == 1 else many
def card(head, n, cap, phrase, suffix=""): return {"head": head, "target": n, "suffix": suffix, "cap": cap, "phrase": phrase}
def status(x): return "Critical" if x <= 5.0 else "Major" if x < 7.0 else "Needs Improvement"

def ai_area(ev):
    """AI answers as a 0-10 area: the share of answers that name the dealer and show no wrong phone. None before the check existed."""
    A = [a for a in (ev.get("ai_answers") or {}).get("answers", []) if a.get("status") == "answered"]
    if not A: return None
    good = sum(1 for a in A if (a["prompt"] == "card" or a.get("named")) and not (a.get("phone") and a.get("phone_matches_site") is False))
    return S.r1d(10 * good / len(A))

def menus(ev):
    """area -> the cards that show a real problem, in menu order."""
    L = ev["listings"]; roles = S._roles(L)
    order = [k for k in ("sales", "service", "parts", "combined") if L.get(k)]
    M = {a: [] for a in AREAS}
    # 1 Claimed
    if not order: M["GBP Claimed & Verified"].append(card("GBP_LISTINGS", 0, "Google Business<br/>Profile Listings", "no Google Business Profile listing"))
    elif ev["claimed"]["main_claim_link"]:
        M["GBP Claimed & Verified"].append(card("UNCLAIMED_MAIN", 1, "Main Listing Shows<br/>&ldquo;Claim This Business&rdquo;", "a main Google listing that still shows &ldquo;Claim this business&rdquo;"))
    # 2 Profile Completeness
    miss = sum(1 for r in ("sales", "service", "parts") if r not in roles)
    if miss: M["Profile Completeness"].append(card("DEPTS_MISSING", miss, "Revenue Depts.<br/>Not on Google", f"{w(miss)} revenue department{s(miss)} missing from Google"))
    gaps = sum(L[k]["checklist_total"] - L[k]["checklist_done"] for k in order)
    if gaps: M["Profile Completeness"].append(card("PROFILE_GAPS", gaps, "Profile Items Left<br/>Blank on Google", f"{w(gaps)} profile item{s(gaps)} left blank on Google"))
    # 3 Photos
    for k in order:
        n = L[k]["photos_30d"]
        if n < 4: M["Photos & Visual Presence"].append(card("PHOTOS_30D", n, f"New {DEPT[k]} Photos in<br/>30 Days (Std. 4)", f"{w(n)} new {DEPT[k]} photo{s(n)} in the last 30 days against a standard of four", " / 4")); break
    pg = sum((not L[k]["logo"]) + (not L[k]["cover"]) + sum(not v for v in L[k]["coverage"].values()) for k in order)
    if pg: M["Photos & Visual Presence"].append(card("PHOTO_GAPS", pg, "Logo, Cover &amp; Photo<br/>Types Missing", f"{w(pg)} missing logo, cover or photo type{s(pg)}"))
    # 4 Reviews (only what CLIKsearch's review answering and review campaign act on)
    R = ev["reviews"]; un = 10 - R["owner_replies_of_10_newest"]
    if un: M["Reviews & Reputation"].append(card("UNANSWERED_REVS", un, "Newest Reviews With<br/>No Owner Reply", f"{w_of(un)} of the ten newest reviews with no owner reply", " / 10"))
    for k in order:
        r = "service" if k == "combined" else k; d = L[k]["newest_review_days"]; win = S.REVIEW_WINDOW[r][0]
        if d is not None and d > win:
            M["Reviews & Reputation"].append(card("LAST_REVIEW_DAYS", d, f"Days Since the Newest<br/>{DEPT[k]} Review", f"no new {DEPT[k]} review in {d} days")); break
    # 5 Posts
    for k in order:
        l = L[k]; bench = S.BENCH_POSTS["service" if k == "combined" else k]
        if l["last_post_days"] is None:
            M["GBP Posts & Engagement"].append(card("POSTS_ON_LISTING", 0, f"Owner Posts on the<br/>{DEPT[k]} Listing", f"no owner posts on the {DEPT[k]} listing")); break
        if l["last_post_days"] > 30:
            mo = l["last_post_days"] // 30
            M["GBP Posts & Engagement"].append(card("GBP_INACTIVITY", mo, f"Months Since the<br/>Last {DEPT[k]} Post", f"{w(mo)} month{s(mo)} since the last {DEPT[k]} post", " Mo.")); break
        if l["posts_30d"] < bench:
            n = l["posts_30d"]
            M["GBP Posts & Engagement"].append(card("POSTS_30D", n, f"{DEPT[k]} Posts in 30<br/>Days (Std. {bench})", f"{w(n)} {DEPT[k]} post{s(n)} in the last 30 days against a standard of {w(bench)}", f" / {bench}")); break
    for k in order:
        n = sum(not v for v in L[k]["variety"].values())
        if L[k]["posts_30d"] and n:
            M["GBP Posts & Engagement"].append(card("POST_TYPE_GAPS", n, f"{DEPT[k]} Post Types Not Used<br/>(Offers, Events, Calls)", f"{w(n)} {DEPT[k]} post type{s(n)} (offers, events, calls to action) not used")); break
    # 6 NAP
    N = ev["nap"]
    dmm = sum(1 for r in N["_directory_results"] if r["status"] == "found" and not r["agree"]) if "_directory_results" in N else 5 - sum(N["directories_agree"])
    mm = (3 - N["google_vs_site_fields_matching"]) + dmm + (0 if N["map_pin_ok"] else 1) \
        + sum(1 for x in (N["dept_phones"] or []) if S._digits(x["gbp"]) != S._digits(x["site"]) and not (applies(ev) and (S.directories.toll_free(x["gbp"]) or S.directories.toll_free(x["site"]))))
    if mm: M["Google Maps / NAP Consistency"].append(card("NAP_MISMATCHES", mm, "Name, Address &amp; Phone<br/>Mismatches Found", f"{w(mm)} name, address or phone mismatch{s(mm, '', 'es')} across Google and the directories"))
    # 7 LocalBusiness Schema
    Sc = ev["schema"]
    if Sc["pages_with_jsonld"] < 5:
        n = 5 - Sc["pages_with_jsonld"]; M["LocalBusiness Schema"].append(card("PAGES_NO_SCHEMA", n, "Key Pages With No<br/>Business Schema", f"{w(n)} key website page{s(n)} with no business schema"))
    if Sc["department_entities"] < 3:
        n = 3 - Sc["department_entities"]; M["LocalBusiness Schema"].append(card("DEPT_SCHEMA_GAPS", n, "Departments Missing<br/>From Site Schema", f"{w(n)} department{s(n)} missing from the website schema"))
    n = 2 * Sc["department_entities"] - Sc["dept_own_page_address"] - Sc["dept_own_phone"]
    if n > 0: M["LocalBusiness Schema"].append(card("DEPT_LINK_GAPS", n, "Dept. Pages &amp; Phones<br/>Not in Schema", f"{w(n)} department page or phone link{s(n)} missing from the website schema"))
    n = (not Sc["parses_cleanly"]) + (not Sc["business_type_ok"])
    if n: M["LocalBusiness Schema"].append(card("SCHEMA_ERRORS", n, "Errors in the<br/>Business Schema", f"{w(n)} error{s(n)} in the website&rsquo;s business schema"))
    # 8 Schema fields
    if not Sc["sameas_google"]: M["Schema Field Completeness"].append(card("SAMEAS_LINKS", 0, "Google Profile Links<br/>in sameAs Schema", "no Google Business Profile link in the website&rsquo;s sameAs schema"))
    A = Sc["areaserved"]
    if A["delivery_offered"]:
        code = {x.casefold() for x in A["code_places"]}; n = sum(1 for p in A["page_places"] if p.casefold() not in code)
        if n: M["Schema Field Completeness"].append(card("AREAS_UNSTATED", n, "Served Towns Not<br/>Stated in Schema", f"{w(n)} served town{s(n)} not stated in the website schema"))
    n = (6 - Sc["core_fields"]) + (not Sc["logo_or_image"]) + (not Sc["sameas_other"]) + (not Sc["hasmap_or_map"]) + (not Sc["services_or_offers"])
    if n: M["Schema Field Completeness"].append(card("MISSING_FIELDS", n, "Business Details<br/>Missing From Schema", f"{w(n)} business detail{s(n)} missing from the website schema"))
    # 9 AI answers (v16.0: the AI visibility check — how often AI names the dealer, out of all answers given)
    if AV.applies(ev):
        V = AV.scores(ev)
        if V["answered"] and V["named"] < V["answered"]:
            M["AI Answers"].append(card("AI_ANSWERS_NAMED", V["named"], f"Times AI Named This Dealership<br/>Out of {V['answered']:,} AI Answers" if AV.v171(ev) else "AI Answers Naming<br/>This Dealership", f"the dealership named {AV.ONLY(V['named'])}{V['named']} {'time' if V['named'] == 1 else 'times'} out of {V['answered']:,} AI answers" + (f" while {AV.rival_line(R)}" if (R := AV.top_rival(ev) if AV.v171(ev) else None) else ""), "" if AV.v171(ev) else f" / {V['answered']}"))
        return M
    ans = [a for a in (ev.get("ai_answers") or {}).get("answers", []) if a.get("status") == "answered"]
    best = [a for a in ans if a["prompt"] == "best"]; n = sum(1 for a in best if a.get("named") is False)
    if n: M["AI Answers"].append(card("AI_TOOLS_MISSED", n, "AI Tools That Left Out<br/>This Dealership", f"{w_of(n)} of {w(len(best))} AI tools leaving the dealership out when asked for the best dealer nearby", f" / {len(best)}"))
    n = sum(1 for a in ans if a.get("phone") and a.get("phone_matches_site") is False)
    if n: M["AI Answers"].append(card("AI_WRONG_PHONES", n, "AI Answers Showing<br/>a Wrong Phone", f"{w(n)} AI answer{s(n)} giving a wrong phone number"))
    return M

def pick(ev, rows):
    """The cards for this dealer (0 to 4) and the Revenue Impact paragraph."""
    score = dict(zip(S.row_names(rows), rows)); a = ai_area(ev)
    if S.AI_ROW in score: score["AI Answers"] = score.pop(S.AI_ROW)   # v16.0: scorecard row 9 is the AI answers area
    elif a is not None: score["AI Answers"] = a
    M = menus(ev)
    ranked = sorted((x for x in AREAS if x in score and score[x] < 10 and M[x]), key=lambda x: (score[x] - WEIGHT[x], AREAS.index(x)))
    cards = [dict(M[x][0], area=x, area_score=score[x], status=status(score[x])) for x in ranked[:4]]
    p = [c["phrase"] for c in cards[:3]]
    para = "" if not p else "With " + (p[0] if len(p) == 1 else " and ".join(p) if len(p) == 2 else f"{p[0]}, {p[1]}, and {p[2]}")
    return cards, para

if __name__ == "__main__":
    if len(sys.argv) != 2: print(__doc__); sys.exit(2)
    ev = S.resolve_ages(json.load(open(sys.argv[1]))); p = S.check(ev)
    if p: sys.exit("NOT PICKED — evidence incomplete:\n  - " + "\n  - ".join(p))
    cards, para = pick(ev, S.score_rows(ev)[1])
    print(json.dumps({"cards": cards, "impact_paragraph": para, "alert": bool(cards)}, indent=2, ensure_ascii=False))
