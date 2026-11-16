"""DHAP GBP engine — RULE L (v16.3): colour codes and point breakdowns for the DHAP's tables.

Every row of the Scorecard, the AI Visibility tables and the listing-site tables carries its status colour as a left
bar (red Critical, orange Major Issues, yellow Needs Improvement, green Fully Optimized, grey not scored). Only the
total rows are tinted, plus the red rows of the CLIKsearch network table. Every category shows how its 10 points add
up (score.row_parts) and why; every sub-score says which category it is part of. build.py uses these helpers.
"""
import html as H, re
import score as S

COL = {"red": "#dc2626", "org": "#ea580c", "yel": "#ca8a04", "grn": "#15803d", "gry": "#cbd5e1"}
LABEL = {"red": "CRITICAL", "org": "MAJOR ISSUES", "yel": "NEEDS IMPROVEMENT", "grn": "FULLY OPTIMIZED"}
STATUS_BAND = {"Critical": "red", "Major Issues": "org", "Needs Improvement": "yel", "Fully Optimized": "grn"}

CSS = """
<style id="cc-design">
/* ===== RULE L — colour codes and point breakdowns (v16.3) ===== */
.score-table.cc-tint-red tr.cc-red>td{background:#fef2f2}
.score-table tr.cc-red>td:first-child{box-shadow:inset 5px 0 0 #dc2626}.score-table tr.cc-org>td:first-child{box-shadow:inset 5px 0 0 #ea580c}
.score-table tr.cc-yel>td:first-child{box-shadow:inset 5px 0 0 #ca8a04}.score-table tr.cc-grn>td:first-child{box-shadow:inset 5px 0 0 #15803d}
.score-table tr.cc-gry>td:first-child{box-shadow:inset 5px 0 0 #cbd5e1}
.score-table tr.cc-total>td{font-weight:800;border-top:2px solid var(--cc-ln);border-bottom:2px solid var(--cc-ln);background:var(--cc-bg)!important}
.score-table tr.cc-total>td:first-child{box-shadow:inset 7px 0 0 var(--cc)}
.cc-t-red{--cc:#dc2626;--cc-bg:#fef2f2;--cc-ln:#fecaca}.cc-t-org{--cc:#ea580c;--cc-bg:#fff7ed;--cc-ln:#fed7aa}
.cc-t-yel{--cc:#ca8a04;--cc-bg:#fefce8;--cc-ln:#fde68a}.cc-t-grn{--cc:#15803d;--cc-bg:#f0fdf4;--cc-ln:#bbf7d0}
.cc-sc{font-weight:900;white-space:nowrap}.cc-c-red{color:#dc2626}.cc-c-org{color:#ea580c}.cc-c-yel{color:#a16207}.cc-c-grn{color:#15803d}
.cc-b{display:inline-block;font-size:.66rem;font-weight:800;letter-spacing:.04em;padding:3px 8px;border-radius:999px;white-space:nowrap;margin-top:4px}
.cc-b-red{background:#fee2e2;color:#b91c1c}.cc-b-org{background:#ffedd5;color:#c2410c}.cc-b-yel{background:#fef9c3;color:#a16207}.cc-b-grn{background:#dcfce7;color:#15803d}.cc-b-gry{background:#f1f5f9;color:#64748b}
.cc-pill{display:inline-flex;align-items:center;gap:6px;color:#fff;font-size:.7rem;font-weight:900;letter-spacing:.05em;padding:5px 10px;border-radius:999px;white-space:nowrap;background:var(--cc)}
.cc-pill:before{content:"";width:7px;height:7px;border-radius:50%;background:#fff}
.cc-big{font-size:1.15rem;font-weight:900;white-space:nowrap;color:var(--cc);margin-right:8px}
.cc-sub{display:block;font-size:.74rem;font-weight:600;color:#475569;margin-top:6px;line-height:1.45}.cc-sub b{color:#0f172a}
.cc-pts{margin-top:8px;display:flex;flex-wrap:wrap;gap:5px}
.cc-pt{font-size:.7rem;font-weight:500;border:1px solid #e2e8f0;border-radius:6px;padding:2px 7px;background:#fff;white-space:nowrap;color:#0f172a}
.cc-pt b{font-weight:800}
.cc-pt.full{border-color:#bbf7d0;background:#f0fdf4}.cc-pt.full b{color:#15803d}
.cc-pt.part{border-color:#fde68a;background:#fefce8}.cc-pt.part b{color:#a16207}
.cc-pt.zero{border-color:#fecaca;background:#fef2f2}.cc-pt.zero b{color:#dc2626}
.cc-pt.off{border-style:dashed;color:#64748b}
.cc-why{margin-top:6px;font-size:.74rem;color:#475569;font-weight:500;line-height:1.45}.cc-why strong{color:#0f172a}
mark.cc-m{background:#fecaca;color:#991b1b;font-weight:700;padding:0 3px;border-radius:3px}
mark.cc-m.o{background:#fed7aa;color:#9a3412}
.cc-legend{margin:10px 0 4px;font-size:.74rem;color:#475569;display:flex;gap:14px;flex-wrap:wrap}
.cc-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
@media(max-width:680px){
 .score-table tr.cc-red,.score-table tr.cc-org,.score-table tr.cc-yel,.score-table tr.cc-grn,.score-table tr.cc-gry,.score-table tr.cc-total{border-left-width:6px!important;border-left-style:solid!important}
 .score-table tr.cc-red{border-left-color:#dc2626!important}
 .score-table tr.cc-org{border-left-color:#ea580c!important}
 .score-table tr.cc-yel{border-left-color:#ca8a04!important}
 .score-table.cc-tint-red tr.cc-red{background:#fef2f2!important}
 .score-table tr.cc-grn{border-left-color:#15803d!important}
 .score-table tr.cc-gry{border-left-color:#cbd5e1!important}
 .score-table tr.cc-total{border-left-color:var(--cc)!important;background:var(--cc-bg)!important;border-color:var(--cc-ln)}
 .score-table tr>td:first-child{box-shadow:none!important}
}
</style>
"""

def band(x10):
    """Status colour of a score out of 10 (the same lines as score.status)."""
    return "red" if x10 <= 5.0 else "org" if x10 < 7.0 else "yel" if x10 < 9.0 else "grn"

def num(x): return f"{x:.0f}" if abs(x - round(x)) < 1e-9 else f"{S.r1d(x):.1f}"
def esc(t): return H.escape(t, quote=False)

def legend(kind):
    items = ([("red", "5.0 or below &mdash; Critical"), ("org", "above 5.0 to 6.9 &mdash; Major Issues"), ("yel", "7.0 to 8.9 &mdash; Needs Improvement"), ("grn", "9.0 or higher &mdash; Fully Optimized")]
             if kind == "score" else
             [("red", "Wrong or missing &mdash; fix"), ("org", "Matches, with a warning"), ("grn", "Matches"), ("gry", "Not listed / not compared &mdash; not scored")])
    return '<div class="cc-legend">' + "".join(f'<span><i style="background:{COL[c]}"></i>{t}</span>' for c, t in items) + "</div>"

def bar(x10, k, label):
    """A score bar in its status colour, the score, and its status chip."""
    return (f'<div class="bar-wrap"><div class="bar-fill" style="width:{round(x10 * 10)}%;background:{COL[k]};"></div></div>'
            f'<span class="cc-sc cc-c-{k}">{label}</span>')

def chip(k, text): return f'<span class="cc-b cc-b-{k}">{text}</span>'
def pill(k): return f'<span class="cc-pill">{LABEL[k]}</span>'

def chips(parts):
    out = []
    for p in parts:
        if len(p) == 2: out.append(f'<span class="cc-pt off">{esc(p[0])} <b>{esc(p[1])}</b></span>'); continue
        lab, e, m = p
        k = "full" if e >= m - 1e-9 else "zero" if e <= 1e-9 else "part"
        val = f"{S.ai_visibility.ONLY(e)}{num(e)} out of {num(m)}" if lab == S.AI_PART_171 else f"{num(e)} / {num(m)}"
        out.append(f'<span class="cc-pt {k}">{esc(lab)} <b>{val}</b></span>')
    return '<div class="cc-pts">' + "".join(out) + "</div>"

def why(i, entry, raw, ev):
    """The line under the chips: the arithmetic, or the points lost and where."""
    P = [x for x in entry["parts"] if len(x) == 3]
    if i == 8:
        n, a = P[0][1], P[0][2]
        return f"<strong>{n} &divide; {a} &times; 10 = {S.r1d(raw):.1f}.</strong> Question-by-question table in the AI Visibility tab."
    e, m = sum(x[1] for x in P), sum(x[2] for x in P)
    if abs(m - 10) > 1e-9:
        return f"{num(e)} of {num(m)} points, rescaled to 10 (<strong>{num(e)} &divide; {num(m)} &times; 10 = {S.r1d(raw):.1f}</strong>): {esc(entry['note'] or '')}"
    lost = [(x[0], x[2] - x[1]) for x in P if x[2] - x[1] > 1e-9]
    if not lost: return "Full points."
    t = f"<strong>{num(10 - raw)} point{'' if S.r1d(10 - raw) == 1 else 's'} lost</strong>: " + ", ".join(f"{esc(l)} {num(v)}" for l, v in lost) + "."
    if i == 5 and ev["nap"].get("_directory_results"): t += " Site-by-site tables in the AI Visibility and Findings tabs."
    return t

def nap_sum(ev, rows, own):
    """The listing-site total's line: the group is part of NAP Consistency, and how NAP's 10 points add up (own group bold)."""
    P = S.row_parts(ev)[5]["parts"]
    name = {"network": "CLIKsearch network sites", "ai": "AI &amp; car-shopper sites"}
    bits = []
    for lab, e, m in P:
        t = re.sub(r" \(\d+ of \d+\)$", "", lab)
        t = {"CLIKsearch network sites": "network sites"}.get(t, t)
        h = f"{esc(t[0].lower() + t[1:]) if bits and t[1:2].islower() else esc(t)} {num(e)}"
        bits.append(f"<b>{h}</b>" if name[own].replace("&amp;", "&") == lab.split(" (")[0] else h)
    return (f"Part of <b>NAP Consistency {rows[5]:.1f}/10</b> = " + " + ".join(bits) +
            ". Sites with no listing, or only the legal company name, are not scored.")
