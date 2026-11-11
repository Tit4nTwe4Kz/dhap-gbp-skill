#!/usr/bin/env python3
"""DHAP GBP engine — page builder.

Builds the full DHAP report and the Digital Health Alert from the repository's CURRENT reference templates
(templates/ in Clikdata2/dhap-gbp-skill) plus two small files written per dealer:
  evidence.json  — the recorded facts (scored by score.py: rows, overall, status, colours)
  content.json   — only the dealer-specific wording (see content-example-vacaville.json)
Everything that is the same for every dealer (layout, Solution, Investment, Jessica widget, mobile layout, status
colours and labels, scorecard footnote, results labels, template text fixes) is done here, the same way every run.

Usage: python3 build.py [--repo REPO] --evidence evidence.json --content content.json --out OUTDIR
Writes <slug>_dhap_<MM-DD-YY>.html and <slug>_health-alert_<MM-DD-YY>.html and prints their paths.
Refuses (exit 1) when content is incomplete or unsafe (script tags, unbalanced <div>, a stat header over 18 chars...).
"""
import argparse, datetime, html as H, json, pathlib, re, sys
ENG = pathlib.Path(__file__).resolve().parent; sys.path.insert(0, str(ENG))
import score as S, alert_cards as AC, directories as DIR, ai_answers as AA, ai_visibility as AV, design as DS

MITS_LOGO = None   # read from SKILL.md "VERIFIED LOGO / IMAGE URLS" at run time, so the link lives in one place
def load_logo(repo):
    global MITS_LOGO
    m = re.search(r'^MITS_LOGO = "(https://[^"]+)"', (repo / "SKILL.md").read_text(encoding="utf-8"), re.M)
    if not m: raise SystemExit("MITS_LOGO not found in SKILL.md (VERIFIED LOGO / IMAGE URLS)")
    MITS_LOGO = m.group(1)
TEMPLATE_DEALER = [("James Mitsubishi Greece", None), ("Greece, NY", "city"), ("Greece NY", "city")]
SIGNALS = [("Google AI Overview Eligibility", "CLIKsearch Schema"), ("GBP Completeness for AI", "CLIKsearch 3-Pack"),
           ("Structured Data Quality", "CLIKsearch Schema"), ("GEO/AEO Content Freshness", "CLIKsearch Content"),
           ("Entity Authority &amp; Knowledge Graph", "CLIKsearch Schema"), ("Multi-Platform AI Discovery", "CLIKsearch Directories"),
           ("AI Review Signal Strength", "CLIKsearch Reputation"), ("Answer Engine Optimization (AEO)", "CLIKsearch SEO/AEO")]
ROW_LABELS = ["GBP Claimed &amp; Verified", "Profile Completeness", "Photos &amp; Visual Presence", "Reviews &amp; Reputation",
              "GBP Posts &amp; Engagement", "Google Maps / NAP Consistency", "LocalBusiness Schema", "Schema Field Completeness",
              "AI Answer Visibility"]   # row 9 from v16.0
COUNT_WORD = {8: "eight", 9: "nine"}
COL = {"red": "#e82b39", "orange": "#f97316"}

DS_ORDER = {"red": 0, "org": 1, "grn": 2, "gry": 3}

class Bad(Exception): pass

# ----------------------------------------------------------------------------------------------- helpers
def slugify(name): return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
def names(dealer, date):
    d = datetime.date.fromisoformat(date).strftime("%m-%d-%y"); s = slugify(dealer)
    return f"{s}_dhap_{d}.html", f"{s}_health-alert_{d}.html", f"audit_evidence_{s}_{d}.md"
def pill(label="CLIKsearch"): return f'<span class="pill pill-blue"><img src="{MITS_LOGO}" style="height:12px;vertical-align:middle;margin-right:3px;"> {label}</span>'
def tag(t, date):
    if not t: return ""
    if t == "i": return '<span class="tag-amber-sm">Inferred</span>'
    return '<span class="tag-green-sm">Audit Verified' + (f" &middot; {date}" if t == "v-date" else "") + "</span>"
def card(c, date):
    kind, icon, title, body = c["kind"], c.get("icon", "&#9888;&#65039;"), c["title"], c["body"]
    t = tag(c.get("tag"), date); title = f"{title} &nbsp;{t}" if t else title
    p = c.get("pill"); p = ("\n    " + (pill(p) if not p.startswith("<") else p)) if p else ""
    return (f'  <div class="finding-card {kind}">\n    <div class="finding-header"><span class="finding-icon">{icon}</span><span class="finding-title">{title}</span></div>\n'
            f'    <div class="finding-body">{body}</div>{p}\n  </div>\n')
def dot(color, strong, rest, last=False):
    mb = "" if last else "margin-bottom:7px;"
    s = f'<strong style="color:#fff;">{strong}</strong> &mdash; {rest}' if strong else rest
    return f'<div style="display:flex;align-items:flex-start;gap:9px;{mb}"><span style="color:{COL.get(color, color)};font-weight:900;font-size:1rem;flex-shrink:0;">&#9679;</span><span>{s}</span></div>'
def fact(f):
    val, lbl, color = f[0], f[1], f[2] if len(f) > 2 else "red"
    small = ' style="font-size:1.6rem;"' if len(re.sub(r"<[^>]+>|&[a-z]+;", "x", val)) > 3 else ""
    return f'<div class="hero-fact"><div class="hero-fact-num {color}"{small}>{val}</div><div class="hero-fact-lbl">{lbl}</div></div>'
def swap(t, a, b, new):
    if a not in t or b not in t: raise Bad(f"template marker missing: {a!r} / {b!r} (template changed? check the repository)")
    i = t.index(a); j = t.index(b); return t[:i] + new + t[j:]
def rep(t, old, new, count=1, what=""):
    if old not in t: raise Bad(f"template text not found ({what or old[:60]!r}) — the repository template changed; update build.py")
    return t.replace(old, new) if count == 0 else t.replace(old, new, count)

# ----------------------------------------------------------------------------------------------- content check
def walk_strings(o):
    if isinstance(o, str): yield o
    elif isinstance(o, dict):
        for v in o.values(): yield from walk_strings(v)
    elif isinstance(o, list):
        for v in o: yield from walk_strings(v)

FUNNEL_PLACEHOLDER = "REPLACE_WITH_DHAP_FUNNEL_LINK"   # the DHAP funnel link is always added by hand; never guess it
CLARITY_PROJECT = "z61t7jbioc"   # v16.6: Microsoft Clarity project "CLIKdata Reports" (public: it is in every tracked page's source)

def clarity_tag(dealer, brand, report_type):
    """v16.6 (RULE M): Microsoft Clarity heatmaps and recordings for every DHAP and Alert, tagged with the dealer, the
    report type and the brand so Clarity can filter by each. Loads once: if the funnel's own tracking code already
    started Clarity, only the tags are added. Values are JSON-encoded and '</' is escaped so a name can't end the script."""
    v = lambda x: json.dumps(str(x or ""), ensure_ascii=False).replace("</", "<\\/")
    return ('<!-- Microsoft Clarity: CLIKdata Reports (RULE M) -->\n<script type="text/javascript">'
            '(function(c,l,a,r,i,t,y){if(c[a])return;c[a]=function(){(c[a].q=c[a].q||[]).push(arguments)};'
            't=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;y=l.getElementsByTagName(r)[0];'
            f'y.parentNode.insertBefore(t,y);}})(window,document,"clarity","script","{CLARITY_PROJECT}");'
            f'clarity("set","report_type",{v(report_type)});clarity("set","prospect",{v(dealer)});'
            f'clarity("set","dealer_group",{v(brand)});</script>\n')
ALERT_MOBILE_CSS = """<style>
/* ===== MOBILE LAYOUT — Digital Health Alert (phones <= 520px): header and terminal title may not push the page wider than the screen ===== */
@media(max-width:520px){
  .header-inner{flex-wrap:wrap;gap:8px 12px;}
  .header-title{font-size:1.05rem;letter-spacing:.04em;min-width:0;flex:1 1 120px;}
  .header-badge{padding:6px 10px;font-size:.62rem;letter-spacing:.08em;}
  .term-title{font-size:.62rem;letter-spacing:.03em;min-width:0;overflow-wrap:anywhere;}
}
</style>
"""

def check_content(c, picked=False, n_rows=8):
    P = []
    def need(cond, why):
        if not cond: P.append(why)
    for s in walk_strings(c):
        if re.search(r"<\s*(script|iframe|object|embed|style|link|meta)\b|\bon[a-z]+\s*=|javascript:", s, re.I): P.append(f"unsafe HTML in content: {s[:60]!r}")
        if re.search(r"<\s*/?\s*div\b", s, re.I): P.append(f"<div> is not allowed inside content (it breaks the page layout): {s[:60]!r}")
        if re.search(r"\{\{|\}\}|TODO|TBD|XXX", s): P.append(f"placeholder left in content: {s[:60]!r}")
    for k in ("dealer", "city_st", "report_id", "month_year", "summary", "scorecard_notes", "ai", "findings", "opportunities", "why_card", "alert"):
        need(k in c, f"content.{k} missing")
    if P or not all(k in c for k in ("summary", "ai", "alert", "scorecard_notes")): return P
    need(re.match(r"^GBP-[A-Z]{3,8}-\d{4}$", c["report_id"]), "report_id must look like GBP-VMVCA-1026")
    need(c["dhap_url"] == FUNNEL_PLACEHOLDER or re.match(r"^https://", c["dhap_url"]), f"dhap_url must be {FUNNEL_PLACEHOLDER} (the link is added by hand) or the https link of the published DHAP page")
    need(len(c["summary"].get("facts", [])) == 4, "summary.facts needs exactly 4 hero facts")
    need(3 <= len(c["summary"].get("bullets", [])) <= 5, "summary.bullets needs 3-5 bullets")
    need(len(c["scorecard_notes"]) == n_rows, f"scorecard_notes needs exactly {n_rows} notes (one per category, in order{'; the 9th is AI Answer Visibility' if n_rows == 9 else ''})")
    need(len(c["ai"].get("signals", [])) == 8, "ai.signals needs exactly 8 (fixed order: " + ", ".join(n for n, _ in SIGNALS) + ")")
    for i, s in enumerate(c["ai"].get("signals", [])):
        need(len(s) == 3 and s[1] in ("v", "i") and s[2] in ("c", "m", "p", "s"), f"ai.signals[{i}] must be [note, 'v'|'i', 'c'|'m'|'p'|'s']")
    need(1 <= len(c["ai"].get("key_gaps", [])) <= 5, "ai.key_gaps needs 1-5 bullets")
    need(len(c["ai"].get("facts", [])) == 4, "ai.facts needs exactly 4")
    A = c["alert"]
    need(len(A.get("tiles", [])) == 6, "alert.tiles needs exactly 6")
    need(any("Reviews Not Shown on Website" in t[3] for t in A.get("tiles", [])) or A.get("reviews_shown_on_site"), "alert.tiles: one tile must be 'Reviews Not Shown on Website' unless the rendered site shows reviews (then set reviews_shown_on_site: true)")
    if picked:   # rule 7 (v15.2): the engine picks the cards and writes the Revenue Impact paragraph from the evidence
        for k in ("stats", "impact_para2"): need(k not in A, f"alert.{k}: leave it out — from v15.2 the engine writes it from the evidence (rule 7)")
    else:
        need(len(A.get("stats", [])) == 4, "alert.stats needs exactly 4 stat cards")
        heads = [s[0] for s in A.get("stats", [])]
        need("SAMEAS_LINKS" in heads and "AI_VIS_GAPS" in heads, "alert.stats must include SAMEAS_LINKS and AI_VIS_GAPS")
        for h in heads: need(len("> " + h) <= 18 and re.match(r"^[A-Z0-9_]+$", h), f"stat header '{h}' must be CAPS_WITH_UNDERSCORES and at most 16 characters")
        for s in A.get("stats", []): need(isinstance(s[1], int) and s[1] >= 0, f"stat {s[0]} target must be a whole number")
        need("impact_para2" in A, "alert.impact_para2 missing")
    need(len(A.get("locked", [])) == 3, "alert.locked needs exactly 3 blurred findings (06-08)")
    need(len(c["opportunities"]) >= 3, "opportunities needs at least 3 rows (Omni-Social and ACT NOW rows are added automatically)")
    return P

# ----------------------------------------------------------------------------------------------- DHAP
def nap_tables(ev, date="", rows=None):
    """Rule 8 (v15.2): the NAP tables — AI and car-shopper sites (AI Visibility tab) and the CLIKsearch network (Findings tab)."""
    N = ev.get("nap", {}); R = N.get("_directory_results")
    if not R: return "", ""
    cites = {}
    for a in (ev.get("ai_answers") or {}).get("answers", []):
        for src in a.get("sources") or []:
            cites.setdefault(re.sub(r"^https?://(www\.)?", "", src).split("/")[0], set()).add(AA.NAME.get(a["tool"], a["tool"]))
    def why(r):
        k = r["directory"]
        if k.startswith("cited:"): return "Cited by " + ", ".join(sorted(cites.get(k[6:], []))) + " in the AI answer check" if cites.get(k[6:]) else "Cited in the AI answer check"
        w = DIR.SITES[k].get("why", "CLIKsearch syndication network"); return w[0].upper() + w[1:]
    TF = '<div style="color:#c2410c;font-weight:700;font-size:.74rem;margin-top:4px;">Should be the local number</div>'
    def band(r):   # RULE L: red wrong or missing, orange matches with a warning (toll-free), green matches, grey not scored
        if r["status"] != "found": return "gry"
        return "red" if not r["agree"] else "org" if r.get("toll_free") else "grn"
    def status(r, k):
        if k == "gry": return DS.chip(k, {"not_found": "NOT LISTED", "skipped": "LEGAL NAME &mdash; NOT COMPARED"}.get(r["status"], "NOT READABLE"))
        if k == "red": return DS.chip(k, "&#10007; " + H.escape(r["why"].split(" (")[0].replace("differs: ", "Wrong ").replace("Wrong no phone shown", "No phone shown")).upper()) + (TF if r.get("toll_free") else "")
        return DS.chip(k, "&#9888; MATCHES &middot; TOLL-FREE") + TF if k == "org" else DS.chip(k, "&#10003; MATCHES")
    def shows(r, k):
        if r["status"] not in ("found", "skipped"): return "&mdash;"
        bad = r["why"] if k == "red" else "phone" if k == "org" else ""   # the field that is wrong (red) or toll-free (orange) is highlighted
        return "<br/>".join(f'<mark class="cc-m{" o" if k == "org" else ""}">{t}</mark>' if f in bad else t
                            for f in ("name", "address", "phone") for t in [H.escape(r["shows"].get(f) or "No phone shown")])
    P = N["_directory_points"]
    def table(g, title, intro, sumlabel, extra=""):
        rs = [(DS_ORDER[band(r)], r["label"], band(r), r) for r in R if g in r["groups"]]
        rs.sort(key=lambda x: x[:2])   # wrong first, then warnings, then matches, then not scored
        body = "\n".join(f'      <tr class="cc-{k}"><td><strong>{H.escape(r["label"])}</strong><div style="font-size:.78rem;color:#555;margin-top:3px;">{H.escape(why(r))}</div></td><td>{shows(r, k)}</td><td>{status(r, k)}</td></tr>' for _, _, k, r in rs)
        pts, ok, found = P[g]; k = DS.band(rows[5])   # the total takes the colour of NAP Consistency, the category it is part of
        return f'''
  <div class="section-title">{title}</div>
  <p style="font-size:.85rem;color:#4b5563;margin:-4px 0 12px;">{intro}</p>
  <table class="score-table{" cc-tint-red" if g == "network" else ""}">
    <thead><tr><th>Site</th><th>What It Shows</th><th>Status</th></tr></thead>
    <tbody>
{body}
      <tr class="cc-total cc-t-{k}"><td><strong>{sumlabel}</strong></td><td>{ok} of {found} listings found match your website{extra}</td><td><span class="cc-big">{DS.num(pts)} of 2 points</span><span class="cc-sub">{DS.nap_sum(ev, rows, g)}</span></td></tr>
    </tbody>
  </table>
{DS.legend("site")}
'''
    site = N["site"]; ref = f'Your website shows {H.escape(site["name"])}, {H.escape(site["address"])}, {H.escape(site["phone"])}.'
    ai = table("ai", "Where AI Tools &amp; Car Shoppers Read Your Name, Address &amp; Phone",
               ref + " These are the sites AI answers, search engines and car shoppers read. A wrong phone or address here can send a shopper to the wrong number, even when CLIKsearch does not list you there.",
               "AI &amp; CAR-SHOPPER SITES")
    net = table("network", "Directory Network Check &mdash; CLIKsearch Syndication",
                ref + " These are the main directories CLIKsearch keeps accurate for its clients; CLIKsearch also syndicates to 40+ smaller directories and the map and data providers behind GPS, in-car and voice systems. &ldquo;Not listed&rdquo; is a directory CLIKsearch adds.",
                "CLIKSEARCH NETWORK")
    flags = DIR.local_flags(ev)   # the always-local rule: a finding card for each toll-free main or department number
    if flags:
        cards = "".join(card({"kind": "major", "title": f"{f['dept'].title()} Number Is Toll-Free &mdash; It Should Be Local", "tag": "v-date",
                              "body": H.escape(f["text"]) + (" CLIKsearch sets the local number on the Google listing." if f["case"] in ("google", "both") else "") +
                                      (" The dealer&rsquo;s website company updates the website and its schema." if f["case"] in ("website", "both", "schema") else ""),
                              "pill": "CLIKsearch &mdash; GBP Profile Management" if f["case"] in ("google", "both") else None}, date) for f in flags)
        net = f'\n  <div class="section-title">&#9888;&#65039; Phone Numbers Should Be Local</div>\n' + cards + net
    return ai, net

def ai_table(ev, c, rows):
    """v16.0: the AI visibility check — how often AI names the dealer for each question (score out of 100)."""
    if not AV.applies(ev): return ""
    V = AV.scores(ev); A = ev["ai_visibility"]
    def qrow(i, d):
        q = V["questions"][i]; k = DS.band(q["score"] / 10)
        return (f'      <tr class="cc-{k}"><td><strong>{AV.DEPT_LABEL[d]}</strong></td><td>&ldquo;{H.escape(AV.ask(i, A["city_st"]))}&rdquo;</td><td>{q["named"]} of {q["answered"]}</td>'
                f'<td>{DS.bar(q["score"] / 10, k, str(q["score"]) + "/100")} {DS.chip(k, DS.LABEL[k])}</td></tr>')
    body = "\n".join(qrow(i, d) for i, d, _ in AV.questions(ev))
    k = DS.band(rows[8])
    tools = ", ".join(AV.NAME[t] for t in AV.tools(ev))
    return f'''
  <div class="section-title">How Often AI Names {c["dealer"]} &mdash; Shopper Questions Near {H.escape(A["city_st"])}</div>
  <p style="font-size:.85rem;color:#4b5563;margin:-4px 0 12px;">We asked {len(AV.tools(ev))} AI tools ({tools}) the questions shoppers ask, {AV.runs(ev)} times each, with only your city and state &mdash; never your name or brand.{' We count the answers that name you as one of the first two businesses.' if AV.v161(ev) else ''} AI answers change by person, place and time.</p>
  <table class="score-table">
    <thead><tr><th>Dept.</th><th>Question</th><th>Named</th><th>Score</th></tr></thead>
    <tbody>
{body}
      <tr class="cc-total cc-t-{k}"><td><strong>AI ANSWER VISIBILITY</strong></td><td>All questions, all tools</td><td>{V["named"]} of {V["answered"]}</td><td><span class="cc-big">{rows[8]:.1f}/10</span>{DS.pill(k)}<span class="cc-sub">This is the whole category: scorecard row 9, <b>{rows[8]:.1f} of 10</b> ({V["named"]} &divide; {V["answered"]} &times; 10).</span></td></tr>
    </tbody>
  </table>
{DS.legend("score")}
'''

def build_dhap(tpl, c, ev, sc):
    rows, ovr, st = sc["rows"], sc["overall"], sc["status"]; date = sc["date_long"]; fill = round(ovr * 10)
    s = c["summary"]
    bullets = "".join(dot(b[0], b[1], b[2], last=(i == len(s["bullets"]) - 1)) for i, b in enumerate(s["bullets"]))
    summary = f'''<!-- SUMMARY TAB -->
<div id="summary" class="tab-panel active">
  <div class="hero-card">
    <img src="{MITS_LOGO}" alt="Mitsubishi Motors" style="position:absolute;top:24px;right:28px;height:68px;object-fit:contain;opacity:.92;"/><div class="hero-eyebrow">GBP &amp; Local Presence Audit · {c["city_st"]} · {c["month_year"]}</div>
    <div class="hero-title">{c["dealer"]}<br/>{s["title"]}</div>
    <div class="hero-sub">
      {s["context"]} — but <strong style="color:#e82b39;">{s["red"]}</strong> {s["consequence"]} Meanwhile, <strong style="color:#f97316;">{s["orange"]}</strong> <em style="color:#6b7280;">(Competitor GBP activity in {c["city_st"]} not directly audited — industry pattern.)</em> CLIKsearch closes every gap — fully managed, 24/7.
    </div>
    <div class="hero-fact-strip">
      {"".join(fact(f) for f in s["facts"])}
    </div>
    <div class="score-banner">
      <div><span class="score-num">{ovr}</span><span class="score-denom">/10</span></div>
      <div class="score-banner-context">
        <div class="score-label" style="font-size:2.2rem;font-weight:900;letter-spacing:.01em;">{st["icon"]} {st["label"]} {st["icon"]}</div>
        <div class="score-desc" style="margin-top:10px;">{bullets}</div>
      </div>
    </div>
  </div>
</div>

'''
    # RULE L: each row in its status colour, with how its 10 points add up and why; the OVERALL row follows the lowest category
    raw = S.score_rows(ev)[0]; parts = S.row_parts(ev)
    def srow(i):
        k = DS.band(rows[i])
        return (f'      <tr class="cc-{k}"><td><strong>{ROW_LABELS[i]}</strong></td><td>{DS.bar(rows[i], k, f"{rows[i]:.1f}/10")}<br>{DS.chip(k, DS.LABEL[k])}</td>'
                f'<td>{c["scorecard_notes"][i]}{DS.chips(parts[i]["parts"])}<div class="cc-why">{DS.why(i, parts[i], raw[i], ev)}</div></td><td>{pill()}</td></tr>')
    trs = "\n".join(srow(i) for i in range(len(rows)))
    k = DS.STATUS_BAND[st["label"]]; low = st["lowest_row"].replace("&", "&amp;")
    trs += (f'\n      <tr class="cc-total cc-t-{k}"><td><strong>OVERALL</strong></td><td><span class="cc-big" data-fill="{fill}">{ovr}/10</span></td>'
            f'<td>{DS.pill(k)}<span class="cc-sub">Average of the {len(rows)} categories (<b>{S.r1d(sum(rows)):.1f} &divide; {len(rows)} = {ovr}</b>). Status set by the lowest category: <b>{low} {st["lowest_value"]:.1f}/10</b>.</span></td>'
            f'<td><span class="pill pill-green">✅ CLIKsearch 3-Pack</span></td></tr>')
    scorecard = f'''<!-- SCORECARD TAB -->
<div id="scorecard" class="tab-panel">
  <div class="section-title">GBP &amp; Schema Scorecard</div>
  <p style="font-size:.75rem;color:#6b7280;margin-bottom:14px;font-style:italic;">Category ratings are scored from direct audit findings against a fixed rubric. Photo and post cadence are rated against a standard we set &mdash; one new photo per week per profile; 8 posts a month for Sales and 4 each for Service and Parts &mdash; not a Google requirement. The overall score is the equal-weight average of the {COUNT_WORD[len(rows)]} categories; the overall status follows the lowest category: 5.0 or below is Critical, above 5.0 to 6.9 is Major Issues, 7.0 to 8.9 is Needs Improvement, 9.0 or higher is Fully Optimized.</p>
  <table class="score-table">
    <thead><tr><th>Category</th><th>Score</th><th>What we found &middot; how the 10 points add up</th><th>Solution</th></tr></thead>
    <tbody>
{trs}
    </tbody>
  </table>
{DS.legend("score")}
</div>

'''
    A = c["ai"]
    ST = {"c": ("#e82b39", "Critical Gap"), "m": ("#f97316", "Major Gap"), "p": ("#d97706", "Partial Signal"), "s": ("#15803d", "Strength")}
    SB = {"c": "red", "m": "org", "p": "yel", "s": "grn"}
    sig_rows = []
    for (name, fix), (note, tg, stt) in zip(SIGNALS, A["signals"]):
        tgh = '<span class="tag-green">Audit Verified</span>' if tg == "v" else '<span class="tag-orange">Inferred</span>'
        sig_rows.append(f'      <tr class="cc-{SB[stt]}"><td><strong>{name}</strong><div style="font-size:.78rem;color:#555;margin-top:3px;">{note}</div></td><td>{tgh}</td><td>{DS.chip(SB[stt], ST[stt][1].upper())}</td><td><span class="pill pill-blue">{fix}</span></td></tr>')
    oa = A.get("overall", "m")
    sig_rows.append(f'      <tr class="cc-total cc-t-{SB[oa]}"><td><strong>OVERALL ASSESSMENT</strong></td><td>&mdash;</td><td><span class="cc-pill">{ {"c": "CRITICAL", "m": "MAJOR GAPS", "p": "PARTIAL", "s": "STRONG"}[oa]}</span></td><td><span class="pill pill-green">&#10003; Full CLIKsearch Stack</span></td></tr>')
    kg = A["key_gaps"]
    kgh = "\n".join("          " + dot(g[0], g[1], g[2], last=(i == len(kg) - 1)) for i, g in enumerate(kg))
    badge_emoji = {"CRITICAL": "&#128308;", "MAJOR": "&#128992;", "PARTIAL": "&#128993;", "STRONG": "&#128994;"}.get(A["badge"], "&#128992;")
    secs = "".join(f'\n  <div class="section-title">{sec["title"]}</div>\n\n' + "".join(card(x, date) for x in sec["cards"]) for sec in A["sections"])
    nap_ai, nap_net = nap_tables(ev, date, rows)
    aiv = f'''<!-- AI VISIBILITY SCORE TAB -->
<div id="aivisibility" class="tab-panel">
  <div class="hero-card">
    <div class="hero-eyebrow">AI Search Visibility Assessment &middot; Based on GBP &amp; Schema Audit &middot; {c["dealer"]}</div>
    <div class="hero-title">AI Visibility Assessment: <span class="red">{A["title_status"]}</span></div>
    <div class="hero-sub" style="margin-top:12px;">AI-powered search engines &mdash; <strong>Google AI Overviews, ChatGPT, Perplexity, and Bing Copilot</strong> &mdash; now answer the questions buyers ask before ever visiting a dealership website. The verified audit findings below identify specific structural gaps that limit {c["dealer"]}&rsquo;s ability to appear in those AI-generated answers.</div>
    <div class="hero-fact-strip">
      {"".join(fact(f) for f in A["facts"])}
    </div>
    <div class="score-banner">
      <div style="min-width:120px;text-align:center;flex-shrink:0;">
        <div style="font-size:2.6rem;line-height:1;">{badge_emoji}</div>
        <div class="score-label" style="font-size:1.4rem;font-weight:900;margin-top:6px;">{A["badge"]}</div>
        <div style="font-size:.75rem;color:rgba(255,255,255,.65);margin-top:4px;font-weight:600;">{A["badge_sub"]}</div>
      </div>
      <div class="score-banner-context">
        <div class="score-label" style="font-size:1rem;font-weight:800;">Key Gaps &mdash; Verified From Audit</div>
        <div class="score-desc" style="margin-top:10px;">
{kgh}
        </div>
      </div>
    </div>
  </div>

  <div class="finding-card" style="border-left-color:#7c3aed;background:linear-gradient(135deg,#faf5ff,#f3f0ff);margin-bottom:20px;">
    <div class="finding-header"><span class="finding-icon">&#128269;</span><span class="finding-title" style="color:#6d28d9;">How This Assessment Was Built &mdash; Read This First</span></div>
    <div class="finding-body">Each signal is rated qualitatively &mdash; not with a numerical score. Signals marked <strong style="color:#15803d;">Audit Verified</strong> are directly confirmed by your GBP and schema audit. Signals marked <strong style="color:#92400e;">Inferred</strong> are logical conclusions drawn from those verified findings &mdash; the actual AI engine behavior specific to your dealership was not directly tested on every platform. Verified signals represent confirmed gaps in your current digital presence. Inferred signals are strong directional indicators where a targeted follow-up audit would provide complete measurement.</div>
  </div>

  <div class="section-title">AI Visibility Signal Assessment</div>
  <table class="score-table">
    <thead><tr><th>AI Signal</th><th>Evidence</th><th>Status</th><th>Fix</th></tr></thead>
    <tbody>
{chr(10).join(sig_rows)}
    </tbody>
  </table>
{ai_table(ev, c, rows)}{nap_ai}{secs}
  <div class="mids-box" style="background:linear-gradient(135deg,#f0fdf4,#dcfce7);border-color:rgba(34,197,94,.3);margin-top:20px;">
    <div class="mids-title" style="color:#15803d;">&#129302; CLIKsearch Closes Every Verified Gap</div>
    <div class="mids-body">CLIKsearch&rsquo;s SEO/AEO/GEO-focused content strategy, custom dealership schema build, 60+ directory syndication, and 3-Pack profile management are specifically engineered to address each of the verified gaps identified above. Every deliverable is designed to be AI-readable, AI-indexable, and AI-citable. <strong>MiDS approved &mdash; up to 100% reimbursable.</strong></div>
  </div>
</div>

'''
    OMNI = {"kind": "opportunity", "icon": "&#128225;", "title": "No Cross-Platform Social Distribution", "pill": "CLIKsearch &mdash; Omni-Social Post Distribution",
            "body": "GBP posts happen &mdash; but they stay on GBP. No other GBP service distributes that content further. CLIKsearch does: in addition to every GBP post, the same content is simultaneously distributed to Facebook, Instagram, Threads, LinkedIn, Pinterest, and Bluesky &mdash; each version written and formatted for that platform&rsquo;s audience. Your GBP posts don&rsquo;t stop &mdash; they get amplified across 6 more channels. This is a force multiplier no other GBP service includes &mdash; creating 6&times; the engagement signals, social citations, and entity authority with every single post."}
    F = '<!-- FINDINGS TAB -->\n<div id="findings" class="tab-panel">\n'
    for sec in c["findings"]:
        cards = sec["cards"] + ([OMNI] if sec.get("add_omni_social") else [])
        F += f'  <div class="section-title">{sec["title"]}</div>\n' + "".join(card(x, date) for x in cards) + "\n"
    if "No Cross-Platform Social Distribution" not in F: raise Bad("findings: one section must set add_omni_social: true (RULE G card)")
    F += nap_net + "</div>\n\n"
    orows = "\n".join(f'      <tr><td><strong>{o[0]}</strong></td><td>{o[1]}</td><td><div class="roi-tag"><span>&#9654;</span><span>{o[2]}</span></div></td><td>{pill()}</td></tr>' for o in c["opportunities"])
    orows += f'''
      <tr><td><strong>Omni-Social Post Distribution</strong></td><td>&#9889; Force Multiplier</td>
        <td><div class="roi-tag"><span>&#9654;</span><span>In addition to every GBP post, simultaneously distribute content to Facebook, Instagram, Threads, LinkedIn, Pinterest &amp; Bluesky &mdash; each rewritten for that platform&rsquo;s audience. GBP posts stay. Social reach gets added on top. 6&times; the signals, zero additional effort.</span></div></td>
        <td>{pill()}</td></tr>
      <tr><td><strong style="color:#d97706;">ACT NOW</strong></td><td><strong style="color:#d97706;">Department Revenue Gains</strong></td>
        <td><strong style="color:#d97706;">Full CLIKsearch 3-Pack Deployment &mdash; Sales &bull; Service &bull; Parts</strong></td>
        <td><span class="pill pill-green"><img src="{MITS_LOGO}" style="height:12px;vertical-align:middle;margin-right:3px;"> CLIKsearch 3-Pack</span></td></tr>'''
    opps = f'''<!-- OPPORTUNITIES TAB -->
<div id="opportunities" class="tab-panel">
  <div class="section-title">Growth Opportunities — CLIKsearch 3-Pack</div>
  <table class="opp-table">
    <thead><tr><th>Opportunity</th><th>Impact</th><th>CLIKsearch Action</th><th>Solution</th></tr></thead>
    <tbody>
{orows}
    </tbody>
  </table>
</div>

'''
    h = swap(tpl, "<!-- SUMMARY TAB -->", "<!-- SOLUTION TAB -->", summary + scorecard + aiv + F + opps)
    i = h.index("Why James Mitsubishi Greece Needs to Act Now</div>")
    a = h.index('<div class="finding-card major" style="border-left-color:#e82b39;">', i)
    b = h.index('<div class="finding-card major" style="border-left-color:#f97316;">', a)
    w = c["why_card"]
    h = h[:a] + (f'<div class="finding-card major" style="border-left-color:#e82b39;">\n    <div class="finding-header"><span class="finding-icon">{w["icon"]}</span><span class="finding-title">{w["title"]}</span></div>\n'
                 f'    <div class="finding-body">{w["body"]} <em style="color:#6b7280;">(Specific competitor activity in this market not directly audited.)</em></div>\n  </div>\n  ') + h[b:]
    # template text fixes (documented in the run skill): typo, and the KB-aligned reimbursement wording
    h = h.replace("Averages from active active CLIKsearch", "Averages from active CLIKsearch")
    # the template's own "Results in 90 days." follows the replaced text, so the replacement must not end with it (v16.9)
    h = h.replace("MiDS reimbursement can bring net dealer cost to $0. Get optimized and syndicated in 72 hours.",
                  "Up to 100% MiDS reimbursement, based on available funds. Go-live in 72 hours after onboarding.")
    for old, kind in TEMPLATE_DEALER: h = h.replace(old, c["city_st"] if kind else c["dealer"])
    h = rep(h, "</head>", DS.CSS + "</head>", what="DHAP </head>")
    return h

# ----------------------------------------------------------------------------------------------- health alert
def build_alert(tpl, c, sc, picked=None):
    st, ovr = sc["status"], sc["overall"]; fill = round(ovr * 10); col = st["color"]; A = c["alert"]
    s = tpl
    s = rep(s, "James Mitsubishi Greece &mdash; Greece, NY", f'{c["dealer"]} &mdash; {c["city_st"]}', what="identity strip")
    s = re.sub(r"GBP-[A-Z]{3,8}-\d{4}", c["report_id"], s)
    s = s.replace("James Mitsubishi Greece", c["dealer"]).replace("Greece, NY", c["city_st"]).replace("Greece NY", c["city_st"])
    if st["label"] != "Critical":
        s = rep(s, "border-bottom:3px solid #dc2626;}", f"border-bottom:3px solid {col};}}", what="banner border")
        s = rep(s, ".score-big{font-size:5.8rem;font-weight:900;color:#dc2626;", f".score-big{{font-size:5.8rem;font-weight:900;color:{col};", what="score colour")
        s = rep(s, ".verdict-label{font-family:'Courier New',Courier,monospace;font-size:2.6rem;font-weight:900;color:#dc2626;", f".verdict-label{{font-family:'Courier New',Courier,monospace;font-size:2.6rem;font-weight:900;color:{col};", what="verdict colour")
        s = re.sub(r"\.score-fill\{height:100%;width:\d+%;background:linear-gradient\(90deg,#ef4444,#dc2626\);", f".score-fill{{height:100%;width:{fill}%;background:linear-gradient(90deg,#fb923c,{col});", s)
        s = rep(s, '<div class="alert-lbl">Critical Alert &mdash; Immediate Attention Required</div>', f'<div class="alert-lbl">{A.get("eyebrow", "Digital Health Alert &mdash; Attention Required")}</div>', what="eyebrow")
        s = rep(s, '<span class="br">[</span>CRITICAL<span class="br">]</span>', f'<span class="br">[</span>{st["label"].upper()}<span class="br">]</span>', what="verdict")
    else:
        s = re.sub(r"(\.score-fill\{height:100%;width:)\d+%", rf"\g<1>{fill}%", s)
    s = re.sub(r'<span class="score-big">[\d.]+</span>', f'<span class="score-big">{ovr}</span>', s)
    s = re.sub(r"status set by the lowest category \([^)]*\)", f'status set by the lowest category ({st["lowest_row"].replace("&", "&amp;")}: {st["lowest_value"]:.1f}/10)', s)
    s = re.sub(r"<b>[\d.]+/10 &mdash; CRITICAL</b>", f'<b>{ovr}/10 &mdash; {st["label"].upper()}</b>', s)
    n = len(sc["rows"])
    if n != 8:   # v16.0: nine categories (row 9 AI Answer Visibility)
        s = rep(s, "average of 8 audited categories", f"average of {n} audited categories", what="score-method caption")
        s = rep(s, "covers 8 audit categories", f"covers {n} audit categories", what="gap-list intro")
    def tile(t):
        cls, val, valcls, lbl, sub, badge, bcls = t
        return (f'    <div class="kpi-tile {cls}">\n      <div class="kpi-icon">{"&#128680;" if cls == "alarm" else "&#9888;&#65039;"}</div>\n      <div class="kpi-val {valcls}">{val}</div>\n'
                f'      <div class="kpi-lbl">{lbl}</div>\n      <div class="kpi-sub">{sub}</div>\n      <span class="kpi-badge {bcls}">{badge}</span>\n    </div>\n')
    i = s.index("<!-- KPI ROW 1"); j = s.index('<div class="step-cta-wrap">', i)
    kp = ('<!-- KPI ROW 1 -->\n  <div class="section-lbl" style="margin-top:4px;">GBP Activity &amp; Profile Status</div>\n  <div class="kpi-grid">\n' + "".join(tile(t) for t in A["tiles"][:3]) +
          '  </div>\n\n  <!-- KPI ROW 2 -->\n  <div class="section-lbl">Visibility, Reputation &amp; Authority</div>\n  <div class="kpi-grid">\n' + "".join(tile(t) for t in A["tiles"][3:]) + '  </div>\n\n')
    s = s[:i] + kp + s[j:]
    if picked is not None:   # rule 7: the dealer's weakest areas, picked from the evidence
        stats = [(x["head"], x["target"], x["suffix"], x["cap"], x["status"]) for x in picked[0]]; para = picked[1]
    else: stats, para = A["stats"], A["impact_para2"]
    s = re.sub(r'(<span style="display:block;margin-top:16px;">)With .*?(, this dealership is surrendering)', lambda m: m.group(1) + para + m.group(2), s, count=1, flags=re.S)
    if para not in s: raise Bad("revenue-impact paragraph marker not found (template changed?)")
    # the stat cards (legacy content: AI_VIS_GAPS always equals the Key Gaps bullets)
    i = s.index('<div class="impact-stats">'); j = s.index("</div>\n  </div>", s.index('class="t-head">&gt; AI_VIS_GAPS'))
    cards = []
    for head, target, suffix, cap, stat in stats:
        if head == "AI_VIS_GAPS": target = len(c["ai"]["key_gaps"])
        cards.append(f'''<div class="t-stat" data-status="{stat}" data-target="{target}" data-suffix="{suffix}" data-comma="0">
        <div class="t-head">&gt; {head}</div>
        <div class="t-num"><span class="t-val">{target}{suffix}</span></div>
        <div class="t-cap">{cap}</div>
        <div class="t-bar"><i></i></div>
        <div class="t-status">&gt; Status: <b>{stat}</b></div>
      </div>''')
    grid = f' style="grid-template-columns:repeat({len(cards)},1fr);"' if len(cards) < 4 else ""
    s = s[:i] + f'<div class="impact-stats"{grid}>\n      ' + "\n      ".join(cards) + "\n    " + s[j:]
    s = rep(s, "c.querySelector('.t-status').innerHTML='&gt; Status: <b>Critical</b>';", "c.querySelector('.t-status').innerHTML='&gt; Status: <b>'+(c.getAttribute('data-status')||'Critical')+'</b>';", what="count-up status")
    # blurred locked findings 06-08
    rows = list(re.finditer(r'<div class="bf-title">(.*?)</div>\s*<div class="bf-detail">(.*?)</div>', s, re.S))
    if len(rows) != 3: raise Bad("expected 3 locked findings in the template")
    for m, (title, detail) in reversed(list(zip(rows, A["locked"]))):
        s = s[:m.start(1)] + title + s[m.end(1):m.start(2)] + detail + s[m.end(2):]
    s = re.sub(r'href="https://clikdatamarketing\.com/[a-z0-9-]+-digital-health-analysis-proposal-page"', f'href="{c["dhap_url"]}"', s)
    return s

# ----------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--repo", default=str(S.default_repo())); ap.add_argument("--evidence", required=True)
    ap.add_argument("--content", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
    repo = pathlib.Path(a.repo).expanduser(); ev = json.load(open(a.evidence)); c = json.load(open(a.content))
    S.rules_guard(repo); load_logo(repo)
    probs = S.check(ev)
    if probs: sys.exit("NOT BUILT — evidence incomplete:\n  - " + "\n  - ".join(probs))
    c.setdefault("dhap_url", FUNNEL_PLACEHOLDER)
    new = AC.applies(ev)
    probs = check_content(c, picked=new, n_rows=len(S.score_rows(ev)[1]))
    if probs: sys.exit("NOT BUILT — content problems:\n  - " + "\n  - ".join(probs))
    if c["dealer"] != ev["dealer"]: sys.exit(f"NOT BUILT — content is for {c['dealer']!r} but evidence is for {ev['dealer']!r}")
    c = dict(c, dealer=H.escape(c["dealer"], quote=False), city_st=H.escape(c["city_st"], quote=False))   # plain text -> safe HTML
    raw, rows = S.score_rows(ev)
    d = datetime.date.fromisoformat(ev["audit_date"])
    sc = {"rows": rows, "overall": S.overall(rows), "status": S.status(rows), "date_long": d.strftime("%B %-d, %Y")}
    T = repo / "templates"
    dh = sorted(T.glob("*_dhap_v*.html"))[-1]; ha = sorted(T.glob("*_hotsheet_v*.html"))[-1]
    try:
        D = build_dhap(dh.read_text(encoding="utf-8"), c, ev, sc)
        picked = AC.pick(ev, rows) if new else None
        Hs = None if picked is not None and not picked[0] else build_alert(ha.read_text(encoding="utf-8"), c, sc, picked)   # every area at 10: no Alert
        if Hs is not None:
            if Hs.count("</head>") != 1: raise Bad("health alert template must have exactly one </head>")
            Hs = Hs.replace("</head>", ALERT_MOBILE_CSS + clarity_tag(ev["dealer"], ev.get("brand"), "ALERT") + "</head>", 1)
        if D.count("</head>") != 1: raise Bad("DHAP template must have exactly one </head>")
        D = D.replace("</head>", clarity_tag(ev["dealer"], ev.get("brand"), "DHAP") + "</head>", 1)
    except Bad as e:
        sys.exit(f"NOT BUILT — {e}")
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    n1, n2, _ = names(ev["dealer"], ev["audit_date"])
    (out / n1).write_text(D, encoding="utf-8")
    if Hs is not None: (out / n2).write_text(Hs, encoding="utf-8")
    print(json.dumps({"dhap": str(out / n1), "health_alert": str(out / n2) if Hs is not None else None,
                      "alert_cards": [x["head"] for x in picked[0]] if picked else None, "templates": [dh.name, ha.name], "rows": rows,
                      "overall": sc["overall"], "status": sc["status"]["label"], "edge_warnings": S.edge_warnings(raw, rows)}, indent=2, ensure_ascii=False))

if __name__ == "__main__": main()
