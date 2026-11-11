"""WORKED EXAMPLE - the build script for the Oct 20 2026 Vacaville Mitsubishi run (repository v14.2, templates DHAP v20 / health alert v27).

Do NOT reuse the wording: every finding, tile, signal note and score line here is Vacaville's. Use it as the pattern for a new run:
  1. read the repo templates; 2. score from your evidence JSON (lib_dhap.score_rows) instead of hand-typed formulas;
  3. rewrite the dealer-specific panels (Summary, Scorecard, AI Visibility, Findings, Opportunities), the first Why Act Now card,
     the health alert KPI tiles / stat cards / locked findings, and the status colours;
  4. leave Solution and Investment panels as the template has them (apart from the documented wording fixes);
  5. write files with lib_dhap.file_names().
Paths come from env vars: DHAP_REPO (cloned rules repo) and DHAP_OUT (output folder).
"""
import os
import re, pathlib
HERE = pathlib.Path(__file__).resolve().parent
T = pathlib.Path(os.environ["DHAP_REPO"]).expanduser() / "templates"
OUT = pathlib.Path(os.environ.get("DHAP_OUT", "dhap_out")); OUT.mkdir(parents=True, exist_ok=True)

MITS_LOGO = "https://storage.googleapis.com/crm-conversations-ai-production/ask-ai-attachments/pD1xrcLAci2kVYlEsUSa/E1a3Kiox27Z6n5KNmx1O/kdKQLwzGTkPvz8og4h4y/c3567bcd-fe66-4a7e-b00d-119bd43fa5cd.png"
DHAP_URL = "https://clikdatamarketing.com/vacaville-mitsubishi-digital-health-analysis-proposal-page"
REPORT_ID = "GBP-VMVCA-1026"
DEALER = "Vacaville Mitsubishi"
AUDIT = "October 20, 2026"
PAGES = "the homepage, About Us (Contact Us), Service, Parts, and Hours &amp; Directions pages"

def mits_pill(label="CLIKsearch"):
    return f'<span class="pill pill-blue"><img src="{MITS_LOGO}" style="height:12px;vertical-align:middle;margin-right:3px;"> {label}</span>'
def ver(d=None): return '<span class="tag-green-sm">Audit Verified' + (f' &middot; {d}' if d else '') + '</span>'
def inf(): return '<span class="tag-amber-sm">Inferred</span>'
def overall(rows): return round(sum(rows) / len(rows), 1)

# =====================================================================
# v13 rubrics scored from recorded evidence (see audit_evidence_vacaville_1026.md); v14 status rule
# =====================================================================
W = {"sales": .5, "combo": .5}   # Sales 50 / Service 25 + Parts 25 (the one combined listing counts as both)
def wsum(d): return sum(W[k] * d[k] for k in W)
r1 = 8 + 2
r2 = 4 + 2 * (7 / 7) + 2 * (4 / 8) * 2
r3 = wsum({"sales": min(4 / 4, 1), "combo": min(1 / 4, 1)}) * 6 + wsum({"sales": 1, "combo": 1}) + wsum({"sales": 2 * 2 / 3, "combo": 2})
r4 = 3 + (1.5 * 1 + .75 * 0 + .75 * .5) + 2 * (10 / 10) + 0 + 0
r5 = wsum({"sales": min(5 / 8, 1), "combo": min(1 / 4, 1)}) * 6 + wsum({"sales": 2, "combo": 1}) + wsum({"sales": 2, "combo": 2 * 2 / 3})
r6 = 4 * (2 / 3) + 4 * (2 / 5) + 0 + 1
r7 = 3 + 1 + 2 + 1 + 2 / 3 + 1 / 3
r8 = 3 + 1 + 1 + 0 + 2 + 0 + 1
rows = [round(x, 1) for x in (r1, r2, r3, r4, r5, r6, r7, r8)]
NAMES = ["GBP Claimed & Verified", "Profile Completeness", "Photos & Visual Presence", "Reviews & Reputation",
         "GBP Posts & Engagement", "Google Maps / NAP Consistency", "LocalBusiness Schema", "Schema Field Completeness"]
SCORE = overall(rows)
LOWV = min(rows); LOWN = NAMES[rows.index(LOWV)].replace("&", "&amp;")
if LOWV <= 5.0: STATUS, ICON, SCOL = "Critical", "🔴", "#dc2626"
elif LOWV < 7.0: STATUS, ICON, SCOL = "Major Issues", "🟠", "#ea580c"
elif LOWV < 9.0: STATUS, ICON, SCOL = "Needs Improvement", "🟡", "#ca8a04"
else: STATUS, ICON, SCOL = "Fully Optimized", "🟢", "#15803d"
FILL = round(SCORE * 10)
print("ROWS", rows, "OVERALL", SCORE, "LOWEST", LOWN, LOWV, "STATUS", STATUS)
assert STATUS == "Major Issues" and LOWN.startswith("Google Maps")

def barcolor(v): return "#22c55e" if v >= 9 else "#f59e0b" if v >= 7 else "#f97316" if v > 5 else "#e82b39"
def bar(v): return f'<div class="bar-wrap"><div class="bar-fill" style="width:{round(v*10)}%;background:{barcolor(v)};"></div></div>{v:.1f}/10'

def swap(text, a, b, new):
    i = text.index(a); j = text.index(b)
    return text[:i] + new + text[j:]
def card(kind, icon, title, body, pill="", tag=""):
    t = f"{title} &nbsp;{tag}" if tag else title
    p = f"\n    {pill}" if pill else ""
    return (f'  <div class="finding-card {kind}">\n    <div class="finding-header"><span class="finding-icon">{icon}</span><span class="finding-title">{t}</span></div>\n'
            f'    <div class="finding-body">{body}</div>{p}\n  </div>\n')
def dot(c, text, last=False):
    mb = "" if last else "margin-bottom:7px;"
    return f'<div style="display:flex;align-items:flex-start;gap:9px;{mb}"><span style="color:{c};font-weight:900;font-size:1rem;flex-shrink:0;">&#9679;</span><span>{text}</span></div>'
def mp(t): return mits_pill(t)

# =====================================================================
# DHAP
# =====================================================================
h = (T / "james-mitsubishi-greece_dhap_v20.html").read_text(encoding="utf-8")

summary = f'''<!-- SUMMARY TAB -->
<div id="summary" class="tab-panel active">
  <div class="hero-card">
    <img src="{MITS_LOGO}" alt="Mitsubishi Motors" style="position:absolute;top:24px;right:28px;height:68px;object-fit:contain;opacity:.92;"/><div class="hero-eyebrow">GBP &amp; Local Presence Audit · Vacaville, CA · October 2026</div>
    <div class="hero-title">Vacaville Mitsubishi<br/>Has Clear Local Search Gaps to Close</div>
    <div class="hero-sub">
      Vacaville Mitsubishi has a strong Google presence and well-built website schema — but <strong style="color:#e82b39;">seven different local phone numbers across the website and listings, Service and Parts sharing one thin Google listing, and none of its Google reviews shown on the website</strong> are limiting local search visibility every single day. Meanwhile, <strong style="color:#f97316;">dealerships that keep their Sales, Service and Parts listings and phone numbers aligned are positioned to gain ground on every department search.</strong> <em style="color:#6b7280;">(Competitor GBP activity in Vacaville, CA not directly audited — industry pattern.)</em> CLIKsearch closes every gap — fully managed, 24/7.
    </div>
    <div class="hero-fact-strip">
      <div class="hero-fact"><div class="hero-fact-num red">7</div><div class="hero-fact-lbl">Different Local<br/>Phone Numbers</div></div>
      <div class="hero-fact"><div class="hero-fact-num red">1</div><div class="hero-fact-lbl">Shared Listing for<br/>Service &amp; Parts</div></div>
      <div class="hero-fact"><div class="hero-fact-num red" style="font-size:1.6rem;">None</div><div class="hero-fact-lbl">Google Reviews Shown<br/>on the Website</div></div>
      <div class="hero-fact"><div class="hero-fact-num orange" style="font-size:1.6rem;">5 of 8</div><div class="hero-fact-lbl">Sales Posts in the<br/>Last 30 Days</div></div>
    </div>
    <div class="score-banner">
      <div><span class="score-num">{SCORE}</span><span class="score-denom">/10</span></div>
      <div class="score-banner-context">
        <div class="score-label" style="font-size:2.2rem;font-weight:900;letter-spacing:.01em;">{ICON} {STATUS} {ICON}</div>
        <div class="score-desc" style="margin-top:10px;">{dot("#e82b39", '<strong style="color:#fff;">7 different local phone numbers</strong> &mdash; the website, Google, Bing, Facebook and the Mitsubishi locator disagree')}{dot("#e82b39", '<strong style="color:#fff;">Service &amp; Parts share one thin listing</strong> &mdash; 1 category, 1 review, no description or scheduling link')}{dot("#e82b39", '<strong style="color:#fff;">172 Google reviews at 4.9&#9733;</strong> &mdash; none are shown on the website')}{dot("#f97316", 'Strong foundation: active Sales posting, fast owner replies, and rich website schema', last=True)}</div>
      </div>
    </div>
  </div>
</div>

'''

sc = [
 ("GBP Claimed &amp; Verified", 0, "✅ Both Google listings show owner posts; no duplicate Google listing found (Apple Maps shows &ldquo;Claim This Place&rdquo;)"),
 ("Profile Completeness", 1, "⚠️ Sales listing complete (7 of 7 items); Service &amp; Parts share one listing with 1 category, no description or scheduling link (4 of 8)"),
 ("Photos &amp; Visual Presence", 2, "⚠️ Sales added 4+ photos in October; the shared Service &amp; Parts listing added 1; no logo seen on either listing"),
 ("Reviews &amp; Reputation", 3, "⚠️ Google 4.9★ / 172 reviews, newest 14 hours old, 10 of 10 newest answered; Facebook shows no star rating; reviews not shown on the website"),
 ("GBP Posts &amp; Engagement", 4, "⚠️ Sales 5 posts in 30 days (standard 8); Service &amp; Parts 1 (standard 4); newest Sales post 16 hours before the audit"),
 ("Google Maps / NAP Consistency", 5, "🟠 Google, Bing, Facebook and the Mitsubishi locator show phone numbers that differ from the website; Apple Maps and Yelp match"),
 ("LocalBusiness Schema", 6, "✅ JSON-LD on all 5 key pages and it parses; Service &amp; Parts entities present; no Sales department entity"),
 ("Schema Field Completeness", 7, "✅ Google link in sameAs, areaServed (6 cities), offers, logo; ⚠️ no other official profiles in sameAs, no hasMap or map"),
]
trs = "\n".join(f'      <tr><td><strong>{n}</strong></td><td>{bar(rows[i])}</td><td>{s}</td><td>{mits_pill()}</td></tr>' for n, i, s in sc)
trs += (f'\n      <tr><td><strong>OVERALL</strong></td><td><div class="bar-wrap"><div class="bar-fill" style="width:{FILL}%;background:{SCOL if STATUS!="Needs Improvement" else "#f59e0b"};"></div></div>{SCORE}/10</td>'
        f'<td>{ICON} {STATUS} <span style="font-size:.7rem;font-weight:600;color:#6b7280;">(status set by the lowest category: {LOWN} is {LOWV:.1f}/10)</span></td><td><span class="pill pill-green">✅ CLIKsearch 3-Pack</span></td></tr>')
scorecard = f'''<!-- SCORECARD TAB -->
<div id="scorecard" class="tab-panel">
  <div class="section-title">GBP &amp; Schema Scorecard</div>
  <p style="font-size:.75rem;color:#6b7280;margin-bottom:14px;font-style:italic;">Category ratings are scored from direct audit findings against a fixed rubric. Photo and post cadence are rated against a standard we set &mdash; one new photo per week per profile; 8 posts a month for Sales and 4 each for Service and Parts &mdash; not a Google requirement. The overall score is the equal-weight average of the eight categories; the overall status follows the lowest category: 5.0 or below is Critical, above 5.0 to 6.9 is Major Issues, 7.0 to 8.9 is Needs Improvement, 9.0 or higher is Fully Optimized.</p>
  <table class="score-table">
    <thead><tr><th>Category</th><th>Score</th><th>Status</th><th>Solution</th></tr></thead>
    <tbody>
{trs}
    </tbody>
  </table>
</div>

'''

def sig(name, note, tag, status, fix):
    tg = '<span class="tag-green">Audit Verified</span>' if tag == "v" else '<span class="tag-orange">Inferred</span>'
    st = {"c": ('#e82b39', '&#128308; Critical Gap'), "m": ('#f97316', '&#9888;&#65039; Major Gap'), "p": ('#d97706', '&#9899; Partial Signal'), "s": ('#15803d', '&#10003; Strength')}[status]
    return f'      <tr><td><strong>{name}</strong><div style="font-size:.78rem;color:#555;margin-top:3px;">{note}</div></td><td>{tg}</td><td style="color:{st[0]};font-weight:700;white-space:nowrap;">{st[1]}</td><td><span class="pill pill-blue">{fix}</span></td></tr>'
sigs = "\n".join([
 sig("Google AI Overview Eligibility", "Well-built site schema: Google link in sameAs, areaServed, offers and FAQ structured data; no hasMap or map (AI impact inferred, not tested)", "i", "p", "CLIKsearch Schema"),
 sig("GBP Completeness for AI", "Complete Sales listing; Service and Parts share one nested listing with 1 category, 1 review, no description or scheduling link", "v", "m", "CLIKsearch 3-Pack"),
 sig("Structured Data Quality", "sameAs lists only the Google profile (no Facebook, Instagram or other official profiles); no Sales department entity; the Parts entity repeats the main phone number", "v", "m", "CLIKsearch Schema"),
 sig("GEO/AEO Content Freshness", "Sales posted 16 hours before the audit and 5 times in 30 days (standard 8); the shared Service &amp; Parts listing posted once (standard 4)", "v", "p", "CLIKsearch Content"),
 sig("Entity Authority &amp; Knowledge Graph", "Active Knowledge Panel with description and a Departments link to the combined listing &mdash; sameAs links to Google only (entity effect inferred)", "v", "p", "CLIKsearch Schema"),
 sig("Multi-Platform AI Discovery", "7 different local phone numbers across the website, Google, Bing, Facebook and the Mitsubishi locator; Apple Maps shows &ldquo;Claim This Place&rdquo;", "v", "m", "CLIKsearch Directories"),
 sig("AI Review Signal Strength", "Google 4.9&#9733; / 172 reviews vs. Yelp 3.3&#9733; / 7; none shown on the website; Facebook shows no star rating (browser checks, " + AUDIT + ")", "v", "m", "CLIKsearch Reputation"),
 sig("Answer Engine Optimization (AEO)", "FAQ structured data is on the homepage and GBP posts answer local &ldquo;near me&rdquo; searches", "v", "s", "CLIKsearch SEO/AEO"),
])
sigs += '\n      <tr style="background:#fff7ed;"><td><strong>OVERALL ASSESSMENT</strong></td><td>&mdash;</td><td style="color:#f97316;font-weight:800;white-space:nowrap;">&#9888;&#65039; Major Gaps</td><td><span class="pill pill-green">&#10003; Full CLIKsearch Stack</span></td></tr>'

KEYGAPS = [
 ("#e82b39", '<strong style="color:#fff;">7 different local phone numbers</strong> &mdash; conflicting contact data across the website and listings'),
 ("#e82b39", '<strong style="color:#fff;">Service &amp; Parts share one thin Google listing</strong> &mdash; 1 category, 1 review, no description'),
 ("#e82b39", '<strong style="color:#fff;">172 Google reviews not shown on the website</strong> &mdash; visitors must leave the site to see them'),
 ("#f97316", '<strong style="color:#fff;">sameAs lists only the Google profile</strong> &mdash; no other official profiles, no hasMap or map'),
]
AI_VIS_GAPS = len(KEYGAPS)
kg = "\n".join(f'          {dot(c, t, last=(i == len(KEYGAPS)-1))}' for i, (c, t) in enumerate(KEYGAPS))
D = AUDIT

aiv = f'''<!-- AI VISIBILITY SCORE TAB -->
<div id="aivisibility" class="tab-panel">
  <div class="hero-card">
    <div class="hero-eyebrow">AI Search Visibility Assessment &middot; Based on GBP &amp; Schema Audit &middot; Vacaville Mitsubishi</div>
    <div class="hero-title">AI Visibility Assessment: <span class="red">Major Gaps Found</span></div>
    <div class="hero-sub" style="margin-top:12px;">AI-powered search engines &mdash; <strong>Google AI Overviews, ChatGPT, Perplexity, and Bing Copilot</strong> &mdash; now answer the questions buyers ask before ever visiting a dealership website. The verified audit findings below identify specific structural gaps that limit Vacaville Mitsubishi&rsquo;s ability to appear in those AI-generated answers.</div>
    <div class="hero-fact-strip">
      <div class="hero-fact"><div class="hero-fact-num red">7</div><div class="hero-fact-lbl">Different Local<br/>Phone Numbers</div></div>
      <div class="hero-fact"><div class="hero-fact-num red">1</div><div class="hero-fact-lbl">Shared Listing for<br/>Service &amp; Parts</div></div>
      <div class="hero-fact"><div class="hero-fact-num red" style="font-size:1.6rem;">None</div><div class="hero-fact-lbl">Google Reviews Shown<br/>on the Website</div></div>
      <div class="hero-fact"><div class="hero-fact-num orange" style="font-size:1.6rem;">Google</div><div class="hero-fact-lbl">Only Profile in<br/>sameAs Schema</div></div>
    </div>
    <div class="score-banner">
      <div style="min-width:120px;text-align:center;flex-shrink:0;">
        <div style="font-size:2.6rem;line-height:1;">&#128992;</div>
        <div class="score-label" style="font-size:1.4rem;font-weight:900;margin-top:6px;">MAJOR</div>
        <div style="font-size:.75rem;color:rgba(255,255,255,.65);margin-top:4px;font-weight:600;">Gaps to Close</div>
      </div>
      <div class="score-banner-context">
        <div class="score-label" style="font-size:1rem;font-weight:800;">Key Gaps &mdash; Verified From Audit</div>
        <div class="score-desc" style="margin-top:10px;">
{kg}
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
{sigs}
    </tbody>
  </table>

  <div class="section-title">&#9888;&#65039; Verified Major Gaps</div>

''' + card("major", "&#9888;&#65039;", "Seven Different Local Phone Numbers", "The website lists 707-532-2052 (Sales), 707-353-4579 (Service) and 707-475-0868 (Parts). Google lists (707) 926-3135 for the dealership and (707) 348-0555 for the shared Service &amp; Parts listing; Bing repeats the first. Facebook lists (707) 452-2500 and the Mitsubishi dealer locator lists 707-513-4935. Apple Maps and Yelp match the website&rsquo;s Sales number. Some may be call-tracking numbers (not verified). AI engines and directories draw on this data, so conflicting numbers weaken confidence.", "<span class=\"pill pill-blue\">CLIKsearch &mdash; 60+ Directory Syndication</span>", ver(D)) + card("major", "&#9888;&#65039;", "Service &amp; Parts Share One Thin, AI-Indexable Entity", "Google Maps shows one &ldquo;Vacaville Mitsubishi Service and Parts&rdquo; listing nested under the main listing: 1 category, 1 review (5.0&#9733;, four months old, unanswered), no description and no scheduling link, with its own website and phone number. <em>Whether a query like &ldquo;Mitsubishi service Vacaville&rdquo; on ChatGPT or Perplexity currently returns Vacaville Mitsubishi was not directly tested.</em>", "<span class=\"pill pill-blue\">CLIKsearch &mdash; 3-Pack Profile Build &amp; Management</span>", ver(D)) + card("major", "&#9888;&#65039;", "Strong Reviews, Invisible on the Website", "Google shows 4.9&#9733; across 172 reviews, but none appear on the rendered homepage or Contact Us page, and the site has no reviews page. Facebook shows no star rating or recommendation figure, and Yelp shows 3.3&#9733; across 7 reviews.", "", ver(D)) + '''
  <div class="section-title">&#9888;&#65039; Inferred Major Gaps</div>

''' + card("major", "&#9888;&#65039;", "sameAs Lists Only the Google Profile", "The AutoDealer schema&rsquo;s sameAs list holds the Google Business Profile link and nothing else &mdash; no Facebook, Instagram, Yelp or other official profiles &mdash; and no <code>hasMap</code> or <code>map</code> property appears on any page checked. (Effect on entity recognition inferred, not tested.)", "<span class=\"pill pill-blue\">CLIKsearch &mdash; Custom Dealership Website Schema</span>", inf()) + '''
  <div class="section-title">&#10003; Verified AI Visibility Strengths</div>

''' + card("working", "&#10003;", "Strong Review Foundation &mdash; Verified AI Signal", "4.9&#9733; across 172 Google reviews, with the newest review 14 hours old and all of the 10 newest reviews answered by the owner. CLIKsearch&rsquo;s Reputation Review Reactivation Builder Campaign extends that momentum to Service and Parts.", "", ver(D)) + card("working", "&#10003;", "Well-Built Schema and Active Posting", "Homepage schema carries a Google link in sameAs, six cities in areaServed, offers, and FAQ structured data; the Sales profile posted five times in the last 30 days. Paired with dedicated 3-Pack profiles and weekly content, this is a strong base. CLIKsearch&rsquo;s omni-social distribution across 6 platforms creates continuous cross-platform entity citations that multiply this authority signal for AI engine indexing.", "", ver(D)) + '''
  <div class="mids-box" style="background:linear-gradient(135deg,#f0fdf4,#dcfce7);border-color:rgba(34,197,94,.3);margin-top:20px;">
    <div class="mids-title" style="color:#15803d;">&#129302; CLIKsearch Closes Every Verified Gap</div>
    <div class="mids-body">CLIKsearch&rsquo;s SEO/AEO/GEO-focused content strategy, custom dealership schema build, 60+ directory syndication, and 3-Pack profile management are specifically engineered to address each of the verified gaps identified above. Every deliverable is designed to be AI-readable, AI-indexable, and AI-citable. <strong>MiDS approved &mdash; up to 100% reimbursable.</strong></div>
  </div>
</div>

'''

F = '<!-- FINDINGS TAB -->\n<div id="findings" class="tab-panel">\n  <div class="section-title">⚠️ Major Gaps</div>\n'
F += card("major", "⚠️", "Seven Different Local Phone Numbers", "Website: 707-532-2052 (Sales), 707-353-4579 (Service), 707-475-0868 (Parts); the Parts schema entity repeats 707-532-2052. Google: (707) 926-3135 for the dealership and (707) 348-0555 for the shared Service &amp; Parts listing. Bing: (707) 926-3135. Facebook: (707) 452-2500. Mitsubishi dealer locator: 707-513-4935. Apple Maps and Yelp show 707-532-2052 and match. Name, address, and phone should match everywhere the business is listed; some of these may be call-tracking numbers (not verified). Of the five directories sampled (Apple Maps, Bing, Yelp, Facebook, the locator) two agree with the website. <span class=\"tag-green-sm\">Audit Verified &middot; " + D + "</span>", mp("CLIKsearch — 60+ Directory Listing Syndication"))
F += card("major", "⚠️", "Mitsubishi Dealer Locator Shows Different Service Hours", "The Mitsubishi locator lists Service hours of 7:30 AM to 5:30 PM Monday to Friday; the website and Google show 8:00 AM to 5:00 PM (checked " + D + "). Sales hours (9:00 AM to 8:00 PM) agree everywhere.", mp("CLIKsearch — Profile Accuracy Monitoring"))
F += card("major", "⚠️", "Service &amp; Parts Share One Thin Google Listing", "Google has a single &ldquo;Vacaville Mitsubishi Service and Parts&rdquo; listing at Suite A, nested under the main listing. It has 1 category (Auto repair shop), 1 review (5.0&#9733;, four months old, no reply), no description and no scheduling link; its phone is (707) 348-0555 and its website is factorypartsstore.com. The website lists separate Service and Parts numbers. <strong>Both views:</strong> the website&rsquo;s schema already describes Service (AutoRepair) and Parts (AutoPartsStore) departments (audited " + D + ") &mdash; neither entity links to the combined Google listing, and Google shows no separate Service or Parts listings.", mp("CLIKsearch — Service &amp; Parts Profile Setup &amp; Management"))
F += card("major", "&#9888;&#65039;", "Google Reviews Aren&rsquo;t Shown on the Website", "None of the dealership&rsquo;s 172 Google reviews (4.9&#9733;) appear on its homepage or its Contact Us page, and no Reviews or Testimonials page was found in the navigation, footer or site map &mdash; checked in a browser on " + D + ". Visitors have to leave the website to see the reputation that lives on the Google Business Profile. Reviews can be shown visibly to visitors &mdash; for example a Google reviews widget or testimonials &mdash; without any review markup in the structured data.")
F += card("major", "⚠️", "Posting Below the Standard on Service &amp; Parts and Sales", "The Sales profile posted 5 times in the 30 days before the audit (newest 16 hours earlier) against a standard of 8 a month. The shared Service &amp; Parts listing posted once (October 6, 2026) against a standard of 4, and its owner-uploaded photos date to April 2026. The posting standard is one we set, not a Google requirement. <em style=\"color:#6b7280;\">(Competitor posting activity in Vacaville, CA not directly audited — industry pattern.)</em>", mp("CLIKsearch — Weekly SEO/GEO Content &amp; Photo Posts"))
F += card("major", "⚠️", "No Logo Seen on Either Google Listing", "Both listings show a cover photo, but no business logo was seen; the profile image on the Sales and the shared listing is a photo or an initial (checked " + D + "). A logo is one of the two profile-image items scored.", mp("CLIKsearch — Full GBP Optimization"))
F += '\n  <div class="section-title">⚡ Missed Opportunities</div>\n'
F += card("opportunity", "⚡", "sameAs Lists Only the Google Profile; No hasMap or map", "The AutoDealer schema&rsquo;s sameAs list contains the Google Business Profile link only &mdash; it does not include Facebook, Instagram, Yelp or the other official profiles. sameAs is how a site&rsquo;s structured data points to a business&rsquo;s other official profiles. No <code>hasMap</code> or legacy <code>map</code> property appears on the top-level entity or on the Service and Parts department entities (parsed from the JSON-LD on " + PAGES + ", " + D + "). <em style=\"color:#6b7280;\">(Effect on entity recognition inferred, not tested.)</em>", mp("CLIKsearch — Custom Dealership Website Schema"))
F += card("opportunity", "⚡", "Department Entities Don&rsquo;t Match the Listings", "The schema has Service (AutoRepair, 707-353-4579) and Parts (AutoPartsStore) entities with their own page addresses, but no separate Sales department entity, and the Parts entity repeats the main phone number while the page shows 707-475-0868. Neither department entity carries a sameAs or map link to the combined Google listing (audited " + D + ").", mp("CLIKsearch — Custom Schema Build"))
F += card("opportunity", "⚡", "Apple Maps Listing Is Unclaimed", "The Apple Maps listing for the dealership shows &ldquo;Claim This Place&rdquo; (checked " + D + "). Its name, address and phone match the website. Yelp shows a claimed page (3.3&#9733;, 7 reviews) with the matching phone.", mp("CLIKsearch — 60+ Directory Listing Syndication"))
F += card("opportunity", "&#128225;", "No Cross-Platform Social Distribution", "GBP posts happen &mdash; but they stay on GBP. No other GBP service distributes that content further. CLIKsearch does: in addition to every GBP post, the same content is simultaneously distributed to Facebook, Instagram, Threads, LinkedIn, Pinterest, and Bluesky &mdash; each version written and formatted for that platform&rsquo;s audience. Your GBP posts don&rsquo;t stop &mdash; they get amplified across 6 more channels. This is a force multiplier no other GBP service includes &mdash; creating 6&times; the engagement signals, social citations, and entity authority with every single post.", mp("CLIKsearch &mdash; Omni-Social Post Distribution"))
F += '\n  <div class="section-title">✅ What\'s Working</div>\n'
F += card("working", "✅", "Excellent Google Review Profile", "4.9★ with 172 Google reviews; the newest review was 14 hours old and the owner answered all of the 10 newest. CLIKsearch's Reputation Review Reactivation Builder Campaign extends this momentum to Service and Parts.")
F += card("working", "✅", "Complete Sales Listing", "The main Google listing has 7 categories, hours, phone, website, an appointment link, offerings, attributes, a business description, and a Departments link to the Service &amp; Parts listing.")
F += card("working", "✅", "Active, Varied Posting on Sales", "Five posts in 30 days &mdash; offers, community events and trade-in content &mdash; with a new post 16 hours before the audit, and at least four new photos in October.")
F += card("working", "✅", "Well-Built Website Schema", "JSON-LD appears on all five key pages and parses cleanly. The AutoDealer entity carries name, address, phone, URL, hours, geo, logo, a Google Business Profile link in sameAs, six cities in areaServed, six service offers, and FAQ structured data is on the homepage.")
F += '</div>\n\n'
findings = F

def opp(name, impact, text):
    return f'      <tr><td><strong>{name}</strong></td><td>{impact}</td><td><div class="roi-tag"><span>&#9654;</span><span>{text}</span></div></td><td>{mits_pill()}</td></tr>'
orows = "\n".join([
 opp("Align Phone Numbers Across the Web", "⚠️ Major", "Choose one correct number per department and keep it identical on the website, schema, Google, Facebook, Bing, Apple Maps, Yelp and the Mitsubishi locator &mdash; replacing seven conflicting numbers"),
 opp("Build Out Dedicated Service &amp; Parts Listings", "⚠️ Major", "Fully optimize and manage the Service and Parts listings &mdash; categories, description, scheduling link, weekly photos and posts, and a Departments link from the main listing"),
 opp("Complete Entity Structured Data", "⚠️ Major", "Build complete dealership structured data &mdash; the Service and Parts department entities already exist in the schema, so connect each department to its own GBP profile, add a Sales department entity, and expand sameAs beyond the Google Business Profile link to the other official profiles"),
 opp("Weekly GBP Posting &amp; Photos", "⚠️ Major", "8 Sales + 4 Service + 4 Parts SEO/GEO-optimized posts and photo posts monthly &mdash; closing the gap on the Service and Parts listing"),
 opp("Reputation Review Builder", "⚡ Opportunity", "Automated emails and text messages to past Sales, Service, and Parts customers to help grow a steady stream of reviews on Google and Facebook &mdash; extending a strong Sales review base to Service and Parts, 24/7"),
 opp("60+ Directory Syndication &amp; Claim Coverage", "⚡ Opportunity", "Keep name, address, and phone consistent across 60+ directories &mdash; including the unclaimed Apple Maps listing &mdash; and align Service hours on the Mitsubishi locator"),
])
orows += f'''
      <tr><td><strong>Omni-Social Post Distribution</strong></td><td>&#9889; Force Multiplier</td>
        <td><div class="roi-tag"><span>&#9654;</span><span>In addition to every GBP post, simultaneously distribute content to Facebook, Instagram, Threads, LinkedIn, Pinterest &amp; Bluesky &mdash; each rewritten for that platform&rsquo;s audience. GBP posts stay. Social reach gets added on top. 6&times; the signals, zero additional effort.</span></div></td>
        <td><span class="pill pill-blue"><img src="{MITS_LOGO}" style="height:12px;vertical-align:middle;margin-right:3px;"> CLIKsearch</span></td></tr>
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
h = swap(h, "<!-- SUMMARY TAB -->", "<!-- SOLUTION TAB -->", summary + scorecard + aiv + findings + opps)

# Why Act Now: dealer card + typo fix
i = h.index("Why James Mitsubishi Greece Needs to Act Now</div>")
a = h.index('<div class="finding-card major" style="border-left-color:#e82b39;">', i)
b = h.index('<div class="finding-card major" style="border-left-color:#f97316;">', a)
h = h[:a] + ('<div class="finding-card major" style="border-left-color:#e82b39;">\n    <div class="finding-header"><span class="finding-icon">📞</span><span class="finding-title">Seven Phone Numbers = Split Calls and Mixed Signals</span></div>\n'
             '    <div class="finding-body">Customers and search engines see seven different local numbers for this dealership across the website, Google, Bing, Facebook and the Mitsubishi locator &mdash; so calls, directions and service requests can land in the wrong place, and every conflicting listing weakens the others. Competitors with one aligned number per department are positioned to compound their Map Pack advantage every single week. <em style="color:#6b7280;">(Specific competitor activity in this market not directly audited.)</em></div>\n  </div>\n  ') + h[b:]
assert "active active" in h
h = h.replace("Averages from active active CLIKsearch", "Averages from active CLIKsearch")
h = h.replace("James Mitsubishi Greece", DEALER).replace("Greece, NY", "Vacaville, CA")
_o1 = "MiDS reimbursement can bring net dealer cost to $0. Get optimized and syndicated in 72 hours."
assert _o1 in h
h = h.replace(_o1, "Up to 100% MiDS reimbursement, based on available funds. Go-live in 72 hours after onboarding.")   # the template's own "Results in 90 days." follows
assert h.count("Go-live in 72 hours after onboarding. Results in 90 days.") == 1 and h.count("Results in 90 days.") == 1
(OUT / "vacaville-mitsubishi_dhap_v20.html").write_text(h, encoding="utf-8")

# =====================================================================
# HOT SHEET (v27)
# =====================================================================
s = (T / "james-mitsubishi-greece_hotsheet_v27.html").read_text(encoding="utf-8")
def rep(old, new, count=1):
    global s
    assert old in s, old[:80]
    s = s.replace(old, new) if count == 0 else s.replace(old, new, count)
rep("James Mitsubishi Greece &mdash; Greece, NY", "Vacaville Mitsubishi &mdash; Vacaville, CA")
rep("GBP-JMGNY-1026", REPORT_ID, 0)
rep("James Mitsubishi Greece", DEALER, 0)
rep("Greece, NY", "Vacaville, CA", 0)
rep("Greece NY", "Vacaville, CA", 0)
# status colour treatment (Major Issues = orange)
rep("border-bottom:3px solid #dc2626;}", f"border-bottom:3px solid {SCOL};}}")
rep(".score-big{font-size:5.8rem;font-weight:900;color:#dc2626;", f".score-big{{font-size:5.8rem;font-weight:900;color:{SCOL};")
rep(".verdict-label{font-family:'Courier New',Courier,monospace;font-size:2.6rem;font-weight:900;color:#dc2626;", f".verdict-label{{font-family:'Courier New',Courier,monospace;font-size:2.6rem;font-weight:900;color:{SCOL};")
rep(".score-fill{height:100%;width:56%;background:linear-gradient(90deg,#ef4444,#dc2626);", f".score-fill{{height:100%;width:{FILL}%;background:linear-gradient(90deg,#fb923c,{SCOL});")
rep('<div class="alert-lbl">Critical Alert &mdash; Immediate Attention Required</div>', '<div class="alert-lbl">Digital Health Alert &mdash; Attention Required</div>')
rep('<span class="br">[</span>CRITICAL<span class="br">]</span>', f'<span class="br">[</span>{STATUS.upper()}<span class="br">]</span>')
rep('<span class="score-big">5.6</span>', f'<span class="score-big">{SCORE}</span>')
rep("status set by the lowest category (GBP Posts: 0/10)", f"status set by the lowest category ({LOWN}: {LOWV:.1f}/10)")
rep("<b>5.6/10 &mdash; CRITICAL</b>", f"<b>{SCORE}/10 &mdash; {STATUS.upper()}</b>")

def tile(cls, val, valcls, lbl, sub, badge, bcls):
    return (f'    <div class="kpi-tile {cls}">\n      <div class="kpi-icon">{"&#128680;" if cls=="alarm" else "&#9888;&#65039;"}</div>\n      <div class="kpi-val {valcls}">{val}</div>\n'
            f'      <div class="kpi-lbl">{lbl}</div>\n      <div class="kpi-sub">{sub}</div>\n      <span class="kpi-badge {bcls}">{badge}</span>\n    </div>\n')
i = s.index('<!-- KPI ROW 1')
j = s.index('<div class="step-cta-wrap">', i)
kp = '<!-- KPI ROW 1 -->\n  <div class="section-lbl" style="margin-top:4px;">GBP Activity &amp; Profile Status</div>\n  <div class="kpi-grid">\n'
kp += tile("warn", "5 of 8", "orange sm", "&#128203; Sales Posts in 30 Days", "Five Sales posts in the last 30 days against a standard of 8 a month; the shared Service &amp; Parts listing has 1 against 4.", "Below Standard", "major")
kp += tile("warn", "1", "orange", "&#128203; Shared Listing for Service &amp; Parts", "One Google listing covers both departments: 1 category, 1 review, no description or scheduling link.", "Thin Listing", "major")
kp += tile("alarm", "7", "red", "&#127759; Different Local Phone Numbers", "The website, Google, Bing, Facebook and the Mitsubishi locator list seven different local numbers for this dealership.", "NAP Mismatch", "crit")
kp += '  </div>\n\n  <!-- KPI ROW 2 -->\n  <div class="section-lbl">Visibility, Reputation &amp; Authority</div>\n  <div class="kpi-grid">\n'
kp += tile("warn", "MAJOR", "orange sm", "&#129302; AI Search Visibility", f"{AI_VIS_GAPS} verified gaps: conflicting phone numbers, a thin shared listing, reviews missing from the site, and a sameAs list limited to Google.", "Gaps Found", "major")
kp += tile("warn", "No Stars", "orange sm", "&#9888;&#65039; Facebook Rating", "Facebook shows no star rating or recommendation figure; Google shows 4.9 stars across 172 reviews and Yelp shows 3.3 stars across 7.", "Not Displayed", "major")
kp += tile("alarm", "None", "red", "&#9940; Reviews Not Shown on Website", "172 Google reviews at 4.9 stars &mdash; none appeared on the dealership&rsquo;s rendered website.", "Not Displayed", "crit")
kp += '  </div>\n\n'
s = s[:i] + kp + s[j:]

rep("Every unanswered search query for Mitsubishi service, parts, or financing in Vacaville, CA is", "Every unanswered search query for Mitsubishi service, parts, or financing in Vacaville, CA is")
rep("With two revenue departments missing from Google, about seven months of content silence, and no Google Business Profile link in the website&rsquo;s sameAs schema",
    "With seven conflicting phone numbers, Service and Parts sharing one thin Google listing, and none of its 172 Google reviews shown on the website")
# stat cards: DEPTS_MISSING / GBP_INACTIVITY premises do not hold for this dealer (combined listing exists; last post 16 hours before audit)
rep('data-target="2" data-suffix="" data-comma="0">\n        <div class="t-head">&gt; DEPTS_MISSING</div>\n        <div class="t-num"><span class="t-val">2</span></div>\n        <div class="t-cap">Revenue Depts.<br/>Not on Google</div>',
    'data-target="7" data-suffix="" data-comma="0">\n        <div class="t-head">&gt; PHONE_NUMBERS</div>\n        <div class="t-num"><span class="t-val">7</span></div>\n        <div class="t-cap">Different Local<br/>Phone Numbers</div>')
rep('data-target="7" data-suffix=" Mo." data-comma="0">\n        <div class="t-head">&gt; GBP_INACTIVITY</div>\n        <div class="t-num"><span class="t-val">7 Mo.</span></div>\n        <div class="t-cap">Zero GBP<br/>Activity</div>',
    'data-target="5" data-suffix=" / 8" data-comma="0">\n        <div class="t-head">&gt; POSTS_30D</div>\n        <div class="t-num"><span class="t-val">5 / 8</span></div>\n        <div class="t-cap">Sales Posts in 30<br/>Days (Std. 8)</div>')
rep("Google Profile Links<br/>in sameAs Schema", "Non-Google Profile Links<br/>in sameAs Schema")
rep('data-target="3" data-suffix="" data-comma="0">\n        <div class="t-head">&gt; AI_VIS_GAPS</div>\n        <div class="t-num"><span class="t-val">3</span>',
    f'data-target="{AI_VIS_GAPS}" data-suffix="" data-comma="0">\n        <div class="t-head">&gt; AI_VIS_GAPS</div>\n        <div class="t-num"><span class="t-val">{AI_VIS_GAPS}</span>')
stats = ["Major", "Major", "Major", "Major"]
parts = s.split('<div class="t-status">&gt; Status: <b>Critical</b></div>')
assert len(parts) == 5
s = parts[0]
for k in range(4):
    s += f'<div class="t-status">&gt; Status: <b>{stats[k]}</b></div>' + parts[k + 1]
cnt = [0]
def addst(m):
    k = cnt[0]; cnt[0] += 1
    return m.group(0).replace('<div class="t-stat"', f'<div class="t-stat" data-status="{stats[k]}"')
s = re.sub(r'<div class="t-stat" data-target="\d+" data-suffix="[^"]*" data-comma="0">', addst, s)
rep("c.querySelector('.t-status').innerHTML='&gt; Status: <b>Critical</b>';", "c.querySelector('.t-status').innerHTML='&gt; Status: <b>'+(c.getAttribute('data-status')||'Major')+'</b>';")
# blurred locked findings 06-08 (premises of the template versions do not hold for this dealer)
rep("Entity Authority: sameAs Links to Facebook Only &mdash; Knowledge Graph Signals Are Critically Thin", "Entity Authority: sameAs Lists Only the Google Profile &mdash; Other Official Profiles Not Linked")
rep("This dealership&rsquo;s lists Facebook only &mdash; the Google Business Profile isn&rsquo;t among the linked profiles &mdash; so the site&rsquo;s entity data is thinner than a fully built profile set.",
    "This dealership&rsquo;s lists only the Google Business Profile &mdash; Facebook, Instagram, Yelp and the other official profiles aren&rsquo;t among the linked profiles &mdash; so the site&rsquo;s entity data is thinner than a fully built profile set.")
rep("Market Reach Undefined: No areaServed in Site Schema &mdash; Surrounding Markets Not Stated", "Department Schema Out of Step: No Sales Entity, and the Parts Phone Repeats the Main Number")
rep("The site&rsquo;s structured data defines no areaServed property, so it never states which cities this dealership serves. Vacaville, CA sits within a large metro market &mdash; every city left unstated is a missed chance to say where the dealership competes.",
    "The site&rsquo;s structured data describes Service and Parts departments, but has no separate Sales department entity, and the Parts entry repeats the main phone number while the page shows a different Parts number.")
rep("GBP Category Configuration Not Fully Optimized &mdash; High-Value Queries Being Missed", "Service Hours Differ Between the Website and the Mitsubishi Locator")
rep("Category selection directly determines which searches trigger a GBP listing. Outdated or incomplete configurations suppress visibility for the highest-value transactional queries &mdash; financing, service, parts, and new vehicle searches.",
    "The Mitsubishi dealer locator lists Service hours of 7:30 AM to 5:30 PM, while the website and Google show 8:00 AM to 5:00 PM &mdash; one more place where the dealership&rsquo;s facts do not line up.")
rep('https://clikdatamarketing.com/james-mitsubishi-greece-digital-health-analysis-proposal-page', DHAP_URL)
(OUT / "vacaville-mitsubishi_hotsheet_v27.html").write_text(s, encoding="utf-8")
print("built", SCORE, STATUS, FILL, "AI_VIS_GAPS", AI_VIS_GAPS)
