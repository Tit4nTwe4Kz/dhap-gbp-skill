#!/usr/bin/env python3
"""DHAP GBP engine — evidence checker + scorer.

The RULES live only in SKILL.md of the Clikdata2/dhap-gbp-skill repository. This file turns recorded evidence into
the eight rubric rows (nine from v16: row 9 is AI Answer Visibility) the way that SKILL.md describes them, so the arithmetic is identical every run.
Three safety gates:
  1. RULES GUARD  — fingerprints the "OVERALL SCORE METHOD" and "CATEGORY RUBRICS" sections of the repository's
                    SKILL.md. If the text changed since this file was checked, it STOPS: a person must re-check the
                    arithmetic against the new text and update KNOWN_RULES (a repository rule change is a pull request).
  2. EVIDENCE CHECK — refuses to score when a field is missing, has the wrong type, is impossible, or has no source
                    ("anything not recorded = audit incomplete: do not publish a score").
  3. PROOF LEDGER — every evidence group must say how and when it was observed (method + date), so each score can
                    be traced back without redoing the audit.
Usage:
  python3 score.py score evidence.json [--repo PATH]      -> rows, overall, status (JSON) or the list of problems
  python3 score.py check evidence.json                     -> only the evidence check
  python3 score.py rules [--repo PATH]                     -> show the rules fingerprint
"""
import calendar, datetime, hashlib, json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import areas, ai_answers, ai_visibility, directories

def default_repo():
    """The rules folder: the repository this engine/ folder sits in, else a local copy at ~/.cache/dhap-gbp-skill."""
    here = pathlib.Path(__file__).resolve().parent.parent
    return here if (here / "SKILL.md").exists() else pathlib.Path.home() / ".cache" / "dhap-gbp-skill"
from decimal import Decimal, ROUND_HALF_UP

def r1d(x):
    """Round to 1 decimal the way people do (5.85 -> 5.9), not the way binary floats do (5.85 -> 5.8)."""
    return float(Decimal(repr(round(x, 9))).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


# fingerprints of the rules text this scorer was checked against (repository version -> section hashes)
KNOWN_RULES = {
    "15.0": {"OVERALL SCORE METHOD": "d7da08a51ea2ddb5", "CATEGORY RUBRICS": "f5a8ea6d0450b93b"},
    "15.1": {"OVERALL SCORE METHOD": "d7da08a51ea2ddb5", "CATEGORY RUBRICS": "f5a8ea6d0450b93b"},   # AI answer check added; scoring text unchanged
    "15.2": {"OVERALL SCORE METHOD": "d7da08a51ea2ddb5", "CATEGORY RUBRICS": "d28d2e9830d751cc"},   # rule 8: NAP sites in two groups from saved readings (audits from Oct 25 2026; earlier audits unchanged)
    "15.3": {"OVERALL SCORE METHOD": "d7da08a51ea2ddb5", "CATEGORY RUBRICS": "cf0f56718ea5276f"},   # v15.3: NAP site-list wording matches the trimmed run; arithmetic unchanged
    "16.0": {"OVERALL SCORE METHOD": "bcc8496ad38bfcfd", "CATEGORY RUBRICS": "6ae54a3ea960afe0"},   # v16.0: row 9 AI Answer Visibility; listing sites: no phone = not agreeing, legal name skipped (audits from Oct 27 2026)
    "16.1": {"OVERALL SCORE METHOD": "bcc8496ad38bfcfd", "CATEGORY RUBRICS": "d046303f9cd684f4"},   # v16.1: row 9 = 5 questions x 5 runs x 5 tools through their APIs (audits from Oct 28 2026)
    "16.2": {"OVERALL SCORE METHOD": "bcc8496ad38bfcfd", "CATEGORY RUBRICS": "d046303f9cd684f4"},   # v16.2: JEV decides which names are businesses; scoring text unchanged
    "16.3": {"OVERALL SCORE METHOD": "bcc8496ad38bfcfd", "CATEGORY RUBRICS": "d046303f9cd684f4"},   # v16.3: RULE L colour codes and point breakdowns; scoring text unchanged
    "16.4": {"OVERALL SCORE METHOD": "bcc8496ad38bfcfd", "CATEGORY RUBRICS": "3e2fbe4d39551d48"},   # v16.4: owner photos only; Facebook with no rating dropped and rescaled
    "16.5": {"OVERALL SCORE METHOD": "bcc8496ad38bfcfd", "CATEGORY RUBRICS": "3e2fbe4d39551d48"},   # v16.5: Markdown copies of the DHAP and Alert; scoring text unchanged
    "16.6": {"OVERALL SCORE METHOD": "bcc8496ad38bfcfd", "CATEGORY RUBRICS": "3e2fbe4d39551d48"},   # v16.6: RULE M Clarity tracking on every DHAP and Alert; scoring text unchanged
    "17.1": {"OVERALL SCORE METHOD": "bcc8496ad38bfcfd", "CATEGORY RUBRICS": "8aea2252d5b195ca"},   # v17.1: row 9 counts an answer only when its number one suggestion is the dealer (audits from Nov 16 2026); arithmetic unchanged
}
ROW_NAMES = ["GBP Claimed & Verified", "Profile Completeness", "Photos & Visual Presence", "Reviews & Reputation",
             "GBP Posts & Engagement", "Google Maps / NAP Consistency", "LocalBusiness Schema", "Schema Field Completeness"]
AI_ROW = "AI Answer Visibility"                       # row 9 (v16.0, audits dated on or after Oct 27 2026)
def row_names(rows): return ROW_NAMES + [AI_ROW] if len(rows) == 9 else ROW_NAMES
BENCH_POSTS = {"sales": 8, "service": 4, "parts": 4}
WEIGHT = {"sales": 50, "service": 25, "parts": 25}
REVIEW_WINDOW = {"sales": (15, 1.5), "service": (30, .75), "parts": (90, .75)}
LEDGER_GROUPS = ["website_schema", "google_listings", "reviews", "posts", "photos", "facebook", "directories"]
SCHEMA_NUM = (("pages_with_jsonld", 0, 5), ("department_entities", 0, 3), ("dept_own_page_address", 0, 3), ("dept_own_phone", 0, 3), ("core_fields", 0, 6))
SCHEMA_BOOL = ("business_type_ok", "parses_cleanly", "logo_or_image", "sameas_google", "sameas_other", "hasmap_or_map", "services_or_offers")

# ----------------------------------------------------------------------------------------------- Google's age labels (rule 2)
def _months_back(d, n):
    y, m = divmod(d.month - 1 - n, 12); y += d.year; m += 1
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

def age_range(label, audit_date):
    """Google's rounded label -> (fewest days, most days) it can mean. 'a month ago' = 1 month up to just under 2 months.
    An exact date ('Apr 30, 2026' or '2026-04-30') gives one number. Unknown wording -> None (the evidence check refuses it)."""
    t = re.sub(r"^\s*edited\s+", "", str(label).strip().lower()); a = datetime.date.fromisoformat(audit_date)
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try: d = (a - datetime.datetime.strptime(str(label).strip(), fmt).date()).days; return (d, d) if d >= 0 else None
        except ValueError: pass
    m = re.fullmatch(r"(a|an|\d+) (minute|hour|day|week|month|year)s? ago", t)
    if not m: return None
    n = 1 if m.group(1) in ("a", "an") else int(m.group(1)); u = m.group(2)
    if u in ("minute", "hour"): return (0, 1)
    if u == "day": return (n, n)
    if u == "week": return (7 * n, 7 * n + 6)
    if u == "month": return ((a - _months_back(a, n)).days, (a - _months_back(a, n + 1)).days - 1)
    return ((a - _months_back(a, 12 * n)).days, (a - _months_back(a, 12 * (n + 1))).days - 1)

def resolve_ages(ev):
    """Fill newest_review_days / last_post_days from Google's labels, using the MOST days the label can mean, so a label
    that crosses a scoring line earns the lower credit (rule 2). Exact day counts are kept as given."""
    for k, l in (ev.get("listings") or {}).items():
        if not isinstance(l, dict): continue
        for f in ("newest_review", "last_post"):
            if l.get(f + "_label") is not None and l.get(f + "_days") is None:
                r = age_range(l[f + "_label"], ev.get("audit_date", "1970-01-01"))
                if r: l[f + "_days"] = r[1]; l.setdefault("_ranges", {})[f] = r
    return directories.resolve(ev)                         # rule 8 (v15.2): directory matches decided from the saved readings

def _digits(t): return re.sub(r"\D", "", str(t or "")).removeprefix("1")[-10:]

# ----------------------------------------------------------------------------------------------- rules guard
def rules_fingerprint(repo):
    repo = pathlib.Path(repo).expanduser()
    s = (repo / "SKILL.md").read_text(encoding="utf-8"); v = (repo / "VERSION").read_text().strip()
    out = {}
    for title in ("OVERALL SCORE METHOD", "CATEGORY RUBRICS"):
        i = s.index("### " + title); j = s.index("\n### ", i + 5)
        out[title] = hashlib.sha256(s[i:j].encode()).hexdigest()[:16]
    return v, out

def fb_dropped(ev):
    """Facebook point dropped and Reviews rescaled: a recommend %, or (v16.4, audits from Oct 29 2026) no rating at all."""
    m = ev["reviews"]["facebook"]["mode"]
    return m == "percent" or (m == "none" and str(ev.get("audit_date", "")) >= "2026-10-29")

def rules_guard(repo):
    v, fp = rules_fingerprint(repo)
    for kv, known in KNOWN_RULES.items():
        if known == fp:
            return v, kv
    raise SystemExit(f"RULES GUARD STOP: the scoring rules in SKILL.md v{v} differ from the text this scorer was checked against "
                     f"({fp}). Re-read OVERALL SCORE METHOD and CATEGORY RUBRICS, update score.py, add the new fingerprint to "
                     f"KNOWN_RULES, run the tests, then score.")

# ----------------------------------------------------------------------------------------------- evidence check
def _num(x, lo=None, hi=None, integer=False):
    if isinstance(x, bool) or not isinstance(x, (int, float)): return False
    if integer and int(x) != x: return False
    return (lo is None or x >= lo) and (hi is None or x <= hi)

def check(ev):
    """Return a list of problems. Empty list = OK to score."""
    resolve_ages(ev)
    P = []
    def need(path, ok, why):
        if not ok: P.append(f"{path}: {why}")
    need("dealer", isinstance(ev.get("dealer"), str) and ev["dealer"].strip(), "dealer name missing")
    need("audit_date", isinstance(ev.get("audit_date"), str) and re.match(r"^\d{4}-\d{2}-\d{2}$", ev.get("audit_date", "")), "audit_date must be YYYY-MM-DD")
    L = ev.get("listings")
    if not isinstance(L, dict): return P + ["listings: missing"]
    if L.get("combined") and (L.get("service") or L.get("parts")):
        P.append("listings: a combined Service & Parts listing and a separate Service/Parts listing were both given — record which is which")
    any_listing = False
    for k in ("sales", "service", "parts", "combined"):
        l = L.get(k)
        if l is None: continue
        any_listing = True; p = f"listings.{k}"
        if not isinstance(l, dict): P.append(f"{p}: must be an object or null"); continue
        tot = 8 if k in ("service", "combined") else 7
        need(p + ".checklist_total", l.get("checklist_total") == tot, f"must be {tot} for a {k} listing")
        need(p + ".checklist_done", _num(l.get("checklist_done"), 0, tot, True), f"whole number 0..{tot}")
        for f in ("photos_30d", "posts_30d"): need(f"{p}.{f}", _num(l.get(f), 0, 500, True), "whole number >= 0")
        need(p + ".last_post_days", l.get("last_post_days") is None or _num(l.get("last_post_days"), 0, 9999, True), "days >= 0, or null when there are no posts")
        if l.get("last_post_days") is None and l.get("posts_30d", 0) > 0: P.append(f"{p}: posts_30d > 0 but last_post_days is null")
        if _num(l.get("last_post_days"), 0) and l.get("posts_30d", 0) > 0 and l["last_post_days"] > 30:
            P.append(f"{p}: posts_30d > 0 but the newest post is older than 30 days")
        for f in ("newest_review", "last_post"):
            if l.get(f + "_label") is not None and age_range(l[f + "_label"], ev.get("audit_date", "1970-01-01")) is None:
                P.append(f"{p}.{f}_label: Google's label not understood ({l[f + '_label']!r}); save it word for word, e.g. 'a month ago', '2 weeks ago', 'Apr 30, 2026'")
        need(p + ".newest_review_days", l.get("newest_review_days") is None or _num(l.get("newest_review_days"), 0, 99999, True), "days >= 0, or null when the listing has no reviews")
        for f in ("logo", "cover"): need(f"{p}.{f}", isinstance(l.get(f), bool), "true/false (was it SEEN in the audit)")
        cov = l.get("coverage", {}); need(p + ".coverage", isinstance(cov, dict) and all(isinstance(cov.get(x), bool) for x in ("exterior", "interior_or_team", "department")), "exterior / interior_or_team / department true/false")
        var = l.get("variety", {}); need(p + ".variety", isinstance(var, dict) and all(isinstance(var.get(x), bool) for x in ("offers", "events", "cta")), "offers / events / cta true/false")
        if l.get("posts_30d") == 0 and isinstance(var, dict) and any(var.get(x) for x in ("offers", "events", "cta")):
            P.append(f"{p}.variety: variety is judged on posts from the last 30 days, but posts_30d is 0")
    need("listings", any_listing, "no Google listing recorded (row 2 is then 0; record that explicitly with listings_none: true)" ) if not ev.get("listings_none") else None
    C = ev.get("claimed", {})
    need("claimed.main_claim_link", isinstance(C.get("main_claim_link"), bool), "true/false: does the MAIN listing show 'Claim this business' on Google Maps (rule 3)")
    need("claimed.lookalikes", isinstance(C.get("lookalikes"), list), "list of look-alike listings for the rep brief (empty list when none; rule 3 add-on)")
    R = ev.get("reviews", {})
    need("reviews.google_rating", R.get("google_rating") is None or _num(R.get("google_rating"), 1, 5), "1.0..5.0, or null when there are no Google reviews")
    need("reviews.owner_replies_of_10_newest", _num(R.get("owner_replies_of_10_newest"), 0, 10, True), "whole number 0..10")
    fb = R.get("facebook", {}); need("reviews.facebook.mode", fb.get("mode") in ("stars", "percent", "none"), "stars | percent | none")
    if fb.get("mode") == "stars": need("reviews.facebook.within_half", isinstance(fb.get("within_half"), bool), "true/false when Facebook shows stars")
    y = R.get("yelp", "missing")
    need("reviews.yelp", y is None or (isinstance(y, dict) and (y.get("rating") is None or _num(y.get("rating"), 1, 5))),
         "null when no Yelp listing exists, else {rating, count, claimed}: Apple Maps, Bing and Perplexity show this rating (finding only, not scored)")
    need("reviews.real_reviews_visible_on_site", isinstance(R.get("real_reviews_visible_on_site"), bool), "true/false (rendered-site check)")
    N = ev.get("nap", {})
    need("nap.google_vs_site_fields_matching", _num(N.get("google_vs_site_fields_matching"), 0, 3, True), "0..3 (name, address, phone)")
    if directories.applies(ev): P += directories.check(ev)
    else: d = N.get("directories_agree"); need("nap.directories_agree", isinstance(d, list) and len(d) == 5 and all(isinstance(x, bool) for x in d), "exactly 5 true/false: Apple Maps, Bing, Yelp, Facebook, Mitsubishi locator")
    dp = N.get("dept_phones")
    need("nap.dept_phones", dp is None or (isinstance(dp, list) and dp and all(isinstance(x, dict) and x.get("dept") and _digits(x.get("gbp")) and _digits(x.get("site")) for x in dp)),
         "null when there is no department listing, else one {dept, gbp, site} per department listing: its Google phone and the website's phone for that department (rule 1)")
    need("nap.map_pin_ok", isinstance(N.get("map_pin_ok"), bool), "true/false")
    for key in ("schema", "schema_rendered"):          # raw page = scored (what ChatGPT, Claude, Perplexity read); rendered = Google's view
        S = ev.get(key)
        if not isinstance(S, dict): P.append(f"{key}: missing — the JavaScript check reads every key page twice (raw and after JavaScript) and records both"); continue
        for f, lo, hi in SCHEMA_NUM: need(f"{key}.{f}", _num(S.get(f), lo, hi, True), f"whole number {lo}..{hi}")
        for f in ("dept_own_page_address", "dept_own_phone"):
            if _num(S.get(f)) and _num(S.get("department_entities")) and S[f] > S["department_entities"]:
                P.append(f"{key}.{f}: cannot be more than department_entities")
        for f in SCHEMA_BOOL: need(f"{key}.{f}", isinstance(S.get(f), bool), "true/false")
    A = (ev.get("schema") or {}).get("areaserved")
    need("schema.areaserved", isinstance(A, dict) and isinstance(A.get("delivery_offered"), bool) and all(isinstance(A.get(x), list) for x in ("code_places", "page_places", "code_on_page")),
         "{delivery_offered, code_places, page_places, code_on_page} (rule 4: areaServed both ways, only when the dealer offers any delivery)")
    if isinstance(A, dict) and isinstance(A.get("code_on_page"), list) and isinstance(A.get("code_places"), list):
        extra = {areas.fold(x) for x in A["code_on_page"]} - {areas.fold(x) for x in A["code_places"]}
        if extra: P.append(f"schema.areaserved.code_on_page: {sorted(extra)} are not in code_places")
    J = ev.get("jev")
    need("jev", isinstance(J, dict) and J.get("status") in ("ok", "skipped") and isinstance(J.get("items"), list) and (J["status"] == "ok" or J.get("reason")),
         "the decide.py ledger: JEV decides every yes/no text judgment first (post offers/events, delivery, serving towns, site reviews, look-alikes)")
    led = ev.get("ledger", {})
    for g in LEDGER_GROUPS:
        e = led.get(g)
        need("ledger." + g, isinstance(e, dict) and str(e.get("method", "")).strip() and re.match(r"^\d{4}-\d{2}-\d{2}", str(e.get("when", ""))),
             "say HOW it was observed (method) and WHEN (YYYY-MM-DD) — proof ledger")
    P += ai_answers.check(ev)                                  # v15.1: the AI answer check (audits Oct 24 to Oct 26 2026)
    P += ai_visibility.check(ev)                               # v16.0: the AI visibility check replaces it (audits from Oct 27 2026)
    return [p for p in P if p]

# ----------------------------------------------------------------------------------------------- scoring
def _roles(L):
    roles = {}
    if L.get("sales"): roles["sales"] = L["sales"]
    if L.get("service"): roles["service"] = L["service"]
    if L.get("parts"): roles["parts"] = L["parts"]
    if L.get("combined"): roles["service"] = L["combined"]; roles["parts"] = L["combined"]
    return roles

def score_rows(ev):
    resolve_ages(ev)                                       # Google's labels -> days (rule 2), whoever calls the scorer
    L = ev["listings"]; roles = _roles(L)
    tot = sum(WEIGHT[r] for r in roles) or 1; w = {r: WEIGHT[r] / tot for r in roles}
    def wavg(f): return sum(w[r] * f(roles[r], r) for r in roles)
    uniq = list({id(v): v for v in roles.values()}.values())
    # 1 Claimed & Verified
    # (rule 3: the main listing and every listing on its Departments line are claimed; look-alikes cost nothing)
    r1 = 0 if not uniq else 2 if ev["claimed"]["main_claim_link"] else 10
    # 2 Profile Completeness: structure 4 + information 6 (combined counts as BOTH Service and Parts)
    struct = (2 if L.get("sales") else 0) + (1 if (L.get("service") or L.get("combined")) else 0) + (1 if (L.get("parts") or L.get("combined")) else 0)
    pct = lambda l: l["checklist_done"] / l["checklist_total"]
    info = (2 * pct(L["sales"]) if L.get("sales") else 0)
    if L.get("combined"): info += 4 * pct(L["combined"])
    else: info += (2 * pct(L["service"]) if L.get("service") else 0) + (2 * pct(L["parts"]) if L.get("parts") else 0)
    r2 = struct + info if roles else 0
    # 3 Photos: 6 cadence (one new photo a week) + 2 logo/cover (1 each, as seen) + 2 coverage
    r3 = 6 * wavg(lambda l, r: min(l["photos_30d"] / 4, 1)) + wavg(lambda l, r: int(l["logo"]) + int(l["cover"])) \
        + wavg(lambda l, r: 2 * sum(1 for k in ("exterior", "interior_or_team", "department") if l["coverage"][k]) / 3)
    # 4 Reviews: 3 rating + 3 recent flow + 2 owner replies (10 newest) + 1 Facebook within 0.5 (stars only) + 1 visible on site
    R = ev["reviews"]; rt = R["google_rating"] or 0
    rating = 3 if rt >= 4.5 else 2 if rt >= 4.0 else 1 if rt >= 3.5 else 0
    earned = mx = 0
    for r in roles:
        days, pts = REVIEW_WINDOW[r]; d = roles[r]["newest_review_days"]; mx += pts
        earned += 0 if d is None else pts if d <= days else pts / 2 if d <= 2 * days else 0
    flow = 3 * earned / mx if mx else 0
    owner = 2 * R["owner_replies_of_10_newest"] / 10
    fb = R["facebook"]; fbpt = 1 if (fb["mode"] == "stars" and fb.get("within_half")) else 0
    r4 = rating + flow + owner + fbpt + (1 if R["real_reviews_visible_on_site"] else 0)
    if fb_dropped(ev): r4 = (r4 - fbpt) / 9 * 10                   # no star rating: point dropped, row rescaled to 10
    # 5 Posts: 6 cadence (8/4/4) + 2 recency (<=7d 2, <=14d 1) + 2 variety (offers, events, calls to action)
    rec = lambda l: 0 if l["last_post_days"] is None else 2 if l["last_post_days"] <= 7 else 1 if l["last_post_days"] <= 14 else 0
    r5 = 6 * wavg(lambda l, r: min(l["posts_30d"] / BENCH_POSTS[r], 1)) + wavg(lambda l, r: rec(l)) \
        + wavg(lambda l, r: 2 * sum(1 for k in ("offers", "events", "cta") if l["variety"][k]) / 3)
    # 6 NAP: 4 Google vs site + 4 five-directory sample + 1 department phones + 1 map pin
    N = ev["nap"]
    dirs = N["_directory_points"]["network"][0] + N["_directory_points"]["ai"][0] if "_directory_points" in N else 4 * sum(N["directories_agree"]) / 5   # v15.2 rule 8: two groups of 2
    r6 = 4 * N["google_vs_site_fields_matching"] / 3 + dirs + (1 if _dept_phones_ok(ev) else 0) + (1 if N["map_pin_ok"] else 0)
    # 7 Schema structure: 3 page coverage + 1 type + 3 department entities + 1 parses + 2 (own page address, own phone)
    S = ev["schema"]
    r7 = 3 * S["pages_with_jsonld"] / 5 + int(S["business_type_ok"]) + S["department_entities"] + int(S["parses_cleanly"]) \
        + S["dept_own_page_address"] / 3 + S["dept_own_phone"] / 3
    # 8 Schema fields: 3 core + 1 logo/image + 2 sameAs (Google, other) + 2 areaServed + 1 hasMap/map + 1 services/offers
    #   areaServed (rule 4) counts only when the dealer offers any delivery; otherwise the other 8 points are scaled to 10
    base = 3 * S["core_fields"] / 6 + int(S["logo_or_image"]) + int(S["sameas_google"]) + int(S["sameas_other"]) \
        + int(S["hasmap_or_map"]) + int(S["services_or_offers"])
    A = S["areaserved"]
    r8 = base + areas.score(A["code_places"], A["page_places"], A["code_on_page"])[0] if A["delivery_offered"] else base / 8 * 10
    raw = [r1, r2, r3, r4, r5, r6, r7, r8]
    # 9 AI Answer Visibility (v16.0): answers naming the dealer / all answers given x 10
    if ai_visibility.applies(ev): raw.append(ai_visibility.scores(ev)["row"])
    return raw, [r1d(x) for x in raw]

def _dept_phones_ok(ev):
    """Row 6, department phones: every department listing's phone matches the website's (toll-free never compared, rule 8)."""
    D = ev["nap"]["dept_phones"]
    return not D or all(_digits(x["gbp"]) == _digits(x["site"]) or (directories.applies(ev) and (directories.toll_free(x["gbp"]) or directories.toll_free(x["site"]))) for x in D)

AI_PART_171 = "Times named"   # v17.1: its chip reads "Times named only X out of 125" (no "only" before 0) (design.chips)

def row_parts(ev):
    """RULE L (v16.3): how each row's 10 points add up, for the scorecard. One entry per row:
    {"parts": [(label, earned, most) or (label, "not scored")], "note": why a part is not scored, or None}.
    Row score = sum(earned) / sum(most) x 10 — the same arithmetic as score_rows() (tests and check_all compare them). Labels are plain text."""
    resolve_ages(ev)
    L = ev["listings"]; roles = _roles(L)
    tot = sum(WEIGHT[r] for r in roles) or 1; w = {r: WEIGHT[r] / tot for r in roles}
    def wavg(f): return sum(w[r] * f(roles[r], r) for r in roles)
    out = []
    # 1 Claimed & Verified
    p = [("Google listing found", 0, 10)] if not roles else [("\u201cClaim this business\u201d link showing", 2, 10)] if ev["claimed"]["main_claim_link"] else [("No \u201cClaim this business\u201d link", 10, 10)]
    out.append({"parts": p, "note": None})
    # 2 Profile Completeness: structure 4 + information 6
    pct = lambda l: l["checklist_done"] / l["checklist_total"]
    info = lambda name, l, most: (f"{name} info ({l['checklist_done']} of {l['checklist_total']})", most * pct(l), most) if l else (f"{name} info", 0, most)
    p = [("Sales listing", 2 if L.get("sales") else 0, 2)]
    if L.get("combined"): p += [("Service & Parts listing (combined)", 2, 2), info("Sales", L.get("sales"), 2), info("Service & Parts", L["combined"], 4)]
    else: p += [("Service listing", 1 if L.get("service") else 0, 1), ("Parts listing", 1 if L.get("parts") else 0, 1),
                info("Sales", L.get("sales"), 2), info("Service", L.get("service"), 2), info("Parts", L.get("parts"), 2)]
    if not roles: p = [(x[0], 0, x[2]) for x in p]
    out.append({"parts": p, "note": None})
    # 3 Photos
    out.append({"parts": [("New photos, last 30 days", 6 * wavg(lambda l, r: min(l["photos_30d"] / 4, 1)), 6),
                          ("Logo + cover", wavg(lambda l, r: int(l["logo"]) + int(l["cover"])), 2),
                          ("Coverage", wavg(lambda l, r: 2 * sum(1 for k in ("exterior", "interior_or_team", "department") if l["coverage"][k]) / 3), 2)], "note": None})
    # 4 Reviews
    R = ev["reviews"]; rt = R["google_rating"] or 0
    rating = 3 if rt >= 4.5 else 2 if rt >= 4.0 else 1 if rt >= 3.5 else 0
    earned = mx = 0
    for r in roles:
        days, pts = REVIEW_WINDOW[r]; d = roles[r]["newest_review_days"]; mx += pts
        earned += 0 if d is None else pts if d <= days else pts / 2 if d <= 2 * days else 0
    fb = R["facebook"]
    p = [("Google rating 4.5+" if rating == 3 else f"Google rating {rt:g}", rating, 3), ("Recent reviews", 3 * earned / mx if mx else 0, 3),
         (f"Owner replies ({R['owner_replies_of_10_newest']} of 10)", 2 * R["owner_replies_of_10_newest"] / 10, 2),
         ("Reviews on website", 1 if R["real_reviews_visible_on_site"] else 0, 1)]
    if fb_dropped(ev): p.append(("Facebook vs Google", "not scored")); note = ("Facebook shows a recommend %, not stars" if fb["mode"] == "percent" else "Facebook shows no rating") + ", so that point is dropped."
    else: p.append(("Facebook within 0.5 stars", 1 if fb.get("within_half") else 0, 1)); note = None
    out.append({"parts": p, "note": note})
    # 5 Posts
    rec = lambda l: 0 if l["last_post_days"] is None else 2 if l["last_post_days"] <= 7 else 1 if l["last_post_days"] <= 14 else 0
    out.append({"parts": [("Posts, last 30 days", 6 * wavg(lambda l, r: min(l["posts_30d"] / BENCH_POSTS[r], 1)), 6),
                          ("Post within 7 days", wavg(lambda l, r: rec(l)), 2),
                          ("Offers, events, calls to action", wavg(lambda l, r: 2 * sum(1 for k in ("offers", "events", "cta") if l["variety"][k]) / 3), 2)], "note": None})
    # 6 NAP
    N = ev["nap"]; p = [("Google vs website", 4 * N["google_vs_site_fields_matching"] / 3, 4)]
    if "_directory_points" in N:
        (n_pts, n_ok, n_f), (a_pts, a_ok, a_f) = N["_directory_points"]["network"], N["_directory_points"]["ai"]
        p += [(f"CLIKsearch network sites ({n_ok} of {n_f})", n_pts, 2), (f"AI & car-shopper sites ({a_ok} of {a_f})", a_pts, 2)]
    else: p.append(("Five-directory sample", 4 * sum(N["directories_agree"]) / 5, 4))
    p += [("Department phones", 1 if _dept_phones_ok(ev) else 0, 1), ("Map pin", 1 if N["map_pin_ok"] else 0, 1)]
    out.append({"parts": p, "note": None})
    # 7 Schema structure
    S = ev["schema"]
    out.append({"parts": [(f"Key pages with schema ({S['pages_with_jsonld']} of 5)", 3 * S["pages_with_jsonld"] / 5, 3), ("Business type", int(S["business_type_ok"]), 1),
                          (f"Department entities ({S['department_entities']} of 3)", S["department_entities"], 3), ("Parses cleanly", int(S["parses_cleanly"]), 1),
                          ("Own page + phone per dept.", S["dept_own_page_address"] / 3 + S["dept_own_phone"] / 3, 2)], "note": None})
    # 8 Schema fields
    sa = "sameAs (Google + other profiles)" if S["sameas_google"] and S["sameas_other"] else "sameAs (Google link missing)" if not S["sameas_google"] else "sameAs (other profiles missing)"
    p = [(f"Core fields ({S['core_fields']} of 6)", 3 * S["core_fields"] / 6, 3), ("Logo or image", int(S["logo_or_image"]), 1), (sa, int(S["sameas_google"]) + int(S["sameas_other"]), 2)]
    A = S["areaserved"]
    if A["delivery_offered"]: p.append(("areaServed", areas.score(A["code_places"], A["page_places"], A["code_on_page"])[0], 2)); note = None
    else: p.append(("areaServed", "not scored")); note = "The dealer offers no delivery, so areaServed is not scored (rule 4)."
    p += [("Map link", int(S["hasmap_or_map"]), 1), ("Services", int(S["services_or_offers"]), 1)]
    out.append({"parts": p, "note": note})
    # 9 AI Answer Visibility
    if ai_visibility.applies(ev):
        V = ai_visibility.scores(ev)
        out.append({"parts": [(AI_PART_171 if ai_visibility.v171(ev) else "AI answers naming the dealer", V["named"], V["answered"] or 1)], "note": None})
    return out

def parts_total(entry):
    """The row score a breakdown adds up to: sum(earned) / sum(most) x 10."""
    P = [x for x in entry["parts"] if len(x) == 3]
    return 10 * sum(x[1] for x in P) / sum(x[2] for x in P)

def overall(rows): return r1d(sum(rows) / len(rows))

def status(rows):
    low = min(rows); name = row_names(rows)[rows.index(low)]
    if low <= 5.0: lab, icon, col = "Critical", "🔴", "#dc2626"
    elif low < 7.0: lab, icon, col = "Major Issues", "🟠", "#ea580c"
    elif low < 9.0: lab, icon, col = "Needs Improvement", "🟡", "#ca8a04"
    else: lab, icon, col = "Fully Optimized", "🟢", "#15803d"
    return {"label": lab, "icon": icon, "color": col, "lowest_row": name, "lowest_value": low}

def edge_warnings(raw, rows):
    """Flag scores sitting on a band edge, where one small fact flips the status."""
    W = []
    for n, r, x in zip(row_names(rows), raw, rows):
        for edge in (5.0, 7.0, 9.0):
            if abs(r - edge) <= 0.2 + 1e-9: W.append(f"{n} is {r:.2f} (shown {x:.1f}), within 0.2 of the {edge} status edge")
    return W

def main():
    a = sys.argv[1:]
    repo = a[a.index("--repo") + 1] if "--repo" in a else default_repo()
    if not a: print(__doc__); return
    if a[0] == "rules":
        print(json.dumps(dict(zip(("version", "fingerprint"), rules_fingerprint(repo))), indent=2)); return
    ev = resolve_ages(json.load(open(a[1])))
    probs = check(ev)
    if a[0] == "check":
        print("EVIDENCE OK" if not probs else "EVIDENCE INCOMPLETE:\n  - " + "\n  - ".join(probs)); sys.exit(1 if probs else 0)
    if a[0] == "score":
        v, kv = rules_guard(repo)
        if probs: print("NOT SCORED — evidence incomplete:\n  - " + "\n  - ".join(probs)); sys.exit(1)
        raw, rows = score_rows(ev)
        print(json.dumps({"rules_version": v, "rows": dict(zip(row_names(rows), rows)), "overall": overall(rows), "status": status(rows),
                          "edge_warnings": edge_warnings(raw, rows), "raw": [round(x, 3) for x in raw]}, indent=2, ensure_ascii=False))

if __name__ == "__main__": main()
