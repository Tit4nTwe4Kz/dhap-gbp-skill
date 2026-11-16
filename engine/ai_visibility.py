#!/usr/bin/env python3
"""DHAP GBP engine — AI visibility check (v16.0, mandatory on every audit dated on or after Oct 27 2026; decided by Travis).

Replaces the v15.1 AI answer check. The old check named the dealer in the question, which skews the answer (a false
positive). This one asks what shoppers actually ask, with only the dealer's city and state, and counts how often AI names
the dealer. No dealer name and no brand is added to a question.
  questions  v16.1 (audits dated Oct 28 2026 or later): the 5 in QUESTIONS (2 Sales — new and used, 2 Service, 1 Parts),
             word for word, {city_st} = the dealer's "City, ST". The same 5 every run. v16.0 audits (Oct 27 2026) keep
             the 7 in QUESTIONS_V160.
  tools      v16.1 (audits dated Oct 28 2026 or later): the 5 in TOOLS — ChatGPT, Gemini, Google AI (AI Overview or AI
             Mode), Claude, Brave — asked through their APIs (run/scripts/ai_api_runner.py): 125 answers. Copilot and
             Perplexity were dropped (robot checks and sign-in walls in the browser; decided by Travis Oct 27 2026).
             v16.0 audits (Oct 27 2026) keep the 7 in TOOLS_V160 asked in the browser: 490 answers.
             Each question is asked RUNS (5; 10 on v16.0) times on each tool, in a fresh chat each time.
  record     every answer word for word, every business it names with its type, and whether it names this dealer.
             v17.1 (audits dated Nov 16 2026 or later; decided by Travis): the answer's number one suggestion is
             recorded, and the answer counts for the dealer only when that suggestion is this dealer (the answer text is
             kept as proof).
             A tool that will not answer (sign-in wall, error, nothing within 60 seconds) is recorded as blocked with the
             reason; never retried. (v16.1: an API's rate limit or server error is retried with backoff; that is the API
             asking us to slow down, not a robot check. An ask that still fails is recorded as blocked.)
  score      per question: answers naming the dealer (v17.1: as the number one suggestion) / answers given for that
             question x 100. Said everywhere as "[Dealer] was named only X times out of 125" ("only" left out when X is 0).
             The category (scorecard row 9, "AI Answer Visibility"): answers naming the dealer / all answers given x 10
             (0..10; 10% = 1). Blocked answers are not counted on either side.
  outputs    the rep brief gets the business named most for each question on each tool; the spreadsheet
             <slug>_ai-answers_<MM-DD-YY>.xlsx has one tab per tool and one row per answer.
Evidence: ai_visibility = {method, city_st, answers: [{tool, q, run, status: answered|blocked, asked, when,
          answer, businesses: [{name, type, brand?}], named, reason?, proof?}]}
Usage:
  python3 ai_visibility.py check evidence.json            -> the problems, or AI VISIBILITY OK
  python3 ai_visibility.py score evidence.json            -> per-question scores and the category score (JSON)
  python3 ai_visibility.py brief evidence.json            -> the rep-brief winners table (markdown)
  python3 ai_visibility.py sheet evidence.json OUT.xlsx   -> the spreadsheet, one tab per tool
  python3 ai_visibility.py questions "Greece, NY"         -> the 5 questions to ask (v16.1), word for word
"""
import collections, datetime, json, pathlib, re, sys

START = "2026-10-27"
START_161 = "2026-10-28"   # v16.1: 5 tools through their APIs
RUNS = 5         # v16.1
RUNS_V160 = 10
START_171 = "2026-11-16"   # v17.1: only the number one suggestion counts
QUESTIONS = [   # v16.1 (id, department, question) — word for word; never add the dealer's name or a brand
    ("sales_new_family_suv", "sales", "best family SUV under 40k near {city_st}"),
    ("sales_used_midsize_suv", "sales", "used midsize SUV near {city_st}"),
    ("service_oil_change_near", "service", "oil change near {city_st}"),
    ("service_brake_job", "service", "brake job near {city_st}"),
    ("parts_brake_pads", "parts", "brake pads for my SUV near {city_st}"),
]
QUESTIONS_V160 = [
    ("sales_dealership", "sales", "What's the best car dealership near {city_st}?"),
    ("sales_new_suv", "sales", "Where can I get a good deal on a new SUV near {city_st}?"),
    ("sales_used_car", "sales", "Where's the best place to buy a used car near {city_st}?"),
    ("service_oil_change", "service", "Where's the cheapest place to get my oil changed today near {city_st}?"),
    ("service_tires", "service", "Where can I get a good deal on tires near {city_st}?"),
    ("parts_wipers", "parts", "Where can I buy windshield wipers for my car near {city_st}?"),
    ("parts_car_parts", "parts", "Where's the best place to buy car parts near {city_st}?"),
]
TOOLS = ("chatgpt", "gemini", "google_ai", "claude", "brave")   # v16.1
TOOLS_V160 = ("chatgpt", "gemini", "perplexity", "google_ai", "claude", "copilot", "brave")
NAME = {"chatgpt": "ChatGPT", "gemini": "Gemini", "perplexity": "Perplexity", "google_ai": "Google AI", "claude": "Claude",
        "copilot": "Copilot", "brave": "Brave"}
TYPES = ("dealership", "oil_change", "tire_shop", "parts_store", "repair_shop", "retailer", "other")
TYPE_LABEL = {"dealership": "dealership", "oil_change": "oil-change shop", "tire_shop": "tire shop", "parts_store": "parts store",
              "repair_shop": "repair shop", "retailer": "retailer", "other": "other"}
DEPT_LABEL = {"sales": "Sales", "service": "Service", "parts": "Parts"}

def applies(ev): return str(ev.get("audit_date", "")) >= START
def v161(ev): return str(ev.get("audit_date", "")) >= START_161
def v171(ev): return str(ev.get("audit_date", "")) >= START_171
def ONLY(n): return "only " if n else ""   # "only" never stands before 0 (Travis, Nov 16 2026)
def named_line(ev, named, answered):
    """The one way the count is said, everywhere (v17.1, decided by Travis Nov 16 2026)."""
    return f"{ev.get('dealer', 'The dealer')} was named {ONLY(named)}{named} {'time' if named == 1 else 'times'} out of {answered}"
def only(named, answered):
    """Table and card form of the same count: 'only X times out of Y' (v17.1)."""
    return f"{ONLY(named)}{named} {'time' if named == 1 else 'times'} out of {answered:,}"
def count_cell(ev, named, answered): return only(named, answered) if v171(ev) else f"{named} of {answered}"
def _key(name): return " ".join(w for w in fold(name).split() if w not in ("of", "the", "at", "inc", "llc"))
def top_rival(ev):
    """v17.1 (Travis, Nov 16 2026): the dealership AI suggests number one most often when it is not this dealer.
    Each answered answer's number one suggestion is tallied (dealerships only, answers naming this dealer left out);
    a short name joins the one longer name that starts with it ('CarMax' -> 'CarMax Myrtle Beach'), never when two could match; names differing only in spacing are one; the most-used spelling is shown.
    Returns {'names': [tied names], 'times', 'answered', 'tally': [(name, times), ...]} or None when no dealership was suggested."""
    A = _answered(ev); c = collections.Counter(); spell = collections.defaultdict(collections.Counter); same = {}
    for a in A:
        B = a.get("businesses") or []
        if a.get("named") or not B or B[0].get("type") != "dealership": continue
        k = _key(B[0]["name"]); k = same.setdefault(k.replace(" ", ""), k)   # 'Auto Mall' = 'Automall'
        if k: c[k] += 1; spell[k][B[0]["name"]] += 1
    for k in sorted(list(c), key=len):
        longer = [o for o in c if o != k and o.startswith(k + " ")]
        if len(longer) == 1: c[longer[0]] += c.pop(k); spell[longer[0]].update(spell.pop(k))
    if not c: return None
    tally = sorted(((spell[k].most_common(1)[0][0], n) for k, n in c.items()), key=lambda x: (-x[1], x[0].casefold())); top = tally[0][1]
    return {"names": [n for n, t in tally if t == top], "times": top, "answered": len(A), "tally": tally}
def rival_line(R):
    """'Honda North was named 12 times out of 125' (ties: 'A and B were each named ...')."""
    who = " and ".join(R["names"]); verb = "was" if len(R["names"]) == 1 else "were each"
    return f"{who} {verb} named {R['times']} {'time' if R['times'] == 1 else 'times'} out of {R['answered']}"
def tools(ev): return TOOLS if v161(ev) else TOOLS_V160
def questions(ev): return QUESTIONS if v161(ev) else QUESTIONS_V160
def runs(ev): return RUNS if v161(ev) else RUNS_V160
def ask(q_id, city_st): return next(q for i, _, q in QUESTIONS + QUESTIONS_V160 if i == q_id).format(city_st=city_st)
def fold(name): return " ".join(re.sub(r"[^a-z0-9&]+", " ", str(name).casefold().replace("&amp;", "&")).split())

def check(ev):
    """Problems with evidence.ai_visibility. Empty list = OK (or the audit predates v16)."""
    if not applies(ev): return []
    A = ev.get("ai_visibility")
    if not isinstance(A, dict) or not isinstance(A.get("answers"), list):
        return [f"ai_visibility: missing — every run asks the 7 questions 10 times on each of the {len(tools(ev))} AI tools (SKILL.md AI VISIBILITY CHECK)"]
    P = []; TOOLS, QUESTIONS, RUNS = tools(ev), questions(ev), runs(ev)
    if not str(A.get("method", "")).strip(): P.append("ai_visibility.method: say how the tools were asked (v16.1: each API, its model and the location set)")
    cs = str(A.get("city_st", "")).strip()
    if not re.match(r"^[^,]+, [A-Z]{2}$", cs): P.append("ai_visibility.city_st: the dealer's city and state as asked, e.g. 'Greece, NY'")
    ids = {i for i, _, _ in QUESTIONS}; seen = set()
    for n, a in enumerate(A["answers"]):
        p = f"ai_visibility.answers[{n}]"
        if not isinstance(a, dict): P.append(p + ": must be an object"); continue
        k = (a.get("tool"), a.get("q"), a.get("run"))
        if a.get("tool") not in TOOLS or a.get("q") not in ids or not (isinstance(a.get("run"), int) and not isinstance(a.get("run"), bool) and 1 <= a["run"] <= RUNS):
            P.append(f"{p}: unknown tool / question / run {k}"); continue
        if k in seen: P.append(f"{p}: {k} recorded twice"); continue
        seen.add(k); p = f"ai_visibility[{k[0]}/{k[1]}/{k[2]}]"
        if cs and a.get("asked") != ask(a["q"], cs): P.append(p + f".asked: must be the question word for word: {ask(a['q'], cs)!r}")
        if not re.match(r"^\d{4}-\d{2}-\d{2}", str(a.get("when", ""))): P.append(p + ".when: YYYY-MM-DD (and time) the answer was read")
        st = a.get("status")
        if st == "blocked":
            if not str(a.get("reason", "")).strip(): P.append(p + ".reason: why it could not be read (sign-in wall, error, no answer within 60 seconds)")
            continue
        if st != "answered": P.append(p + ".status: answered | blocked"); continue
        if not str(a.get("answer", "")).strip(): P.append(p + ".answer: the full answer, word for word")
        B = a.get("businesses")
        if not isinstance(B, list) or not all(isinstance(b, dict) and str(b.get("name", "")).strip() and b.get("type") in TYPES for b in B):
            P.append(p + f".businesses: every business the answer names, as {{name, type}} with type one of {', '.join(TYPES)} (empty list when it names none)")
        if not isinstance(a.get("named"), bool): P.append(p + ".named: true/false — is this dealer the answer's number one suggestion (v17.1)")
    missing = [(t, q, r) for t in TOOLS for q in ids for r in range(1, RUNS + 1) if (t, q, r) not in seen]
    if missing: P.append(f"ai_visibility: {len(missing)} of {len(TOOLS) * len(ids) * RUNS} answers not recorded (first: {missing[0]}); record each as answered or blocked")
    if seen and not any(isinstance(a, dict) and a.get("status") == "answered" for a in A["answers"]): P.append("ai_visibility: no tool answered — check the API keys (run/scripts/ai_api_runner.py --check-keys) and re-run the check")
    blocked = [(a.get("tool"), a.get("q"), a.get("run")) for a in A["answers"] if isinstance(a, dict) and a.get("status") == "blocked"]
    if blocked and v161(ev):   # v16.4: through the APIs every ask must be answered; a blocked one is asked again, never left out
        P.append(f"ai_visibility: {len(blocked)} of {len(A['answers'])} answers blocked (first: {blocked[0]}); run ai_api_runner.py again with the same arguments (it re-asks every blocked ask) until all are answered")
    return P

def _answered(ev): return [a for a in (ev.get("ai_visibility") or {}).get("answers", []) if a.get("status") == "answered"]

def scores(ev):
    """{'questions': {q_id: {'named', 'answered', 'score'}}, 'named', 'answered', 'row'} — score 0..100, row 0..10 (unrounded)."""
    A = _answered(ev); Q = {}
    for i, d, _ in questions(ev):
        x = [a for a in A if a["q"] == i]; n = sum(1 for a in x if a["named"])
        Q[i] = {"dept": d, "named": n, "answered": len(x), "score": round(100 * n / len(x)) if x else 0}
    n = sum(1 for a in A if a["named"])
    return {"questions": Q, "named": n, "answered": len(A), "row": 10 * n / len(A) if A else 0.0}

def winners(ev, n=1):
    """{(q_id, tool): (name, type, times, answered)} — the business named most for that question on that tool.
    n>1: {(q_id, tool): [(name, type, times, answered), ...]} — the n named most."""
    out = {}
    for i, _, _ in questions(ev):
        for t in tools(ev):
            x = [a for a in _answered(ev) if a["q"] == i and a["tool"] == t]
            c = collections.Counter(); first = {}
            for a in x:
                for b in {fold(b["name"]): b for b in a.get("businesses") or []}.values():
                    c[fold(b["name"])] += 1; first.setdefault(fold(b["name"]), b)
            ranked = [(first[k]["name"], first[k]["type"], times, len(x)) for k, times in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]
            out[(i, t)] = ranked if n > 1 else (ranked[0] if ranked else (None, None, 0, len(x)))
    return out

def brief(ev):
    A = ev.get("ai_visibility") or {}; S = scores(ev); W = winners(ev)
    out = [f"### AI visibility check ({A.get('method', '')})", "",
           f"**{named_line(ev, S['named'], S['answered'])} — {round(10 * S['row'])}% ({S['row']:.1f}/10).**"]
    R = top_rival(ev) if v171(ev) else None
    if R: out += ["", f"**Named most instead: {rival_line(R)}.**", ""]
    else: out += [""]
    blocked = [a for a in A.get("answers", []) if a.get("status") == "blocked"]
    if blocked:
        by = collections.Counter(NAME[a["tool"]] for a in blocked)
        out += ["Not read (blocked, not counted): " + ", ".join(f"{t} {n}" for t, n in by.items()) + ".", ""]
    for i, d, _ in questions(ev):
        q = S["questions"][i]
        out += [f"**{DEPT_LABEL[d]} — \"{ask(i, A.get('city_st', '[City, ST]'))}\"** — named {ONLY(q['named'])}{q['named']} {'time' if q['named'] == 1 else 'times'} out of {q['answered']} ({q['score']}/100)", "",
                "| Tool | Dealer named | Named most | Type | Times |", "|---|---|---|---|---|"]
        for t in tools(ev):
            nm, ty, times, n = W[(i, t)]
            dn = sum(1 for a in _answered(ev) if a["q"] == i and a["tool"] == t and a["named"])
            out.append(f"| {NAME[t]} | {dn} of {n} | {nm or '— (none named)'} | {TYPE_LABEL.get(ty, '—') if ty else '—'} | {times} of {n} |")
        out.append("")
    return "\n".join(out)

def sheet(ev, path):
    """The spreadsheet: one tab per AI tool, one row per answer (blocked answers included, marked)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    A = ev.get("ai_visibility") or {}; wb = Workbook(); wb.remove(wb.active)
    cols = ["Dealer", "City & State", "Department", "Question", "Run", "When", "Status", "Answer",
            "Business Suggested" if v171(ev) else "Businesses Named", "Business Types", "Dealer Named"]
    QUESTIONS = questions(ev); S = scores(ev); R = top_rival(ev) if v171(ev) else None
    if v171(ev):   # v17.1: the count and the competitor tally, straight from the number one suggestion of every answer
        ws = wb.create_sheet("Summary")
        ws.append([named_line(ev, S["named"], S["answered"]) + "."])
        ws.append(["Named most instead: " + rival_line(R) + "." if R else "No other dealership was suggested number one."])
        ws.append([]); ws.append(["Dealership suggested number one (answers naming this dealer left out)", "Times out of " + str(S["answered"])])
        for c in ws[1] + ws[2] + ws[4]: c.font = Font(bold=True)
        for name, n in (R or {}).get("tally", []): ws.append([name, n])
        ws.column_dimensions["A"].width = 70; ws.column_dimensions["B"].width = 16
    for t in tools(ev):
        ws = wb.create_sheet(NAME[t]); ws.append(cols)
        for c in ws[1]: c.font = Font(bold=True)
        rows = sorted((a for a in A.get("answers", []) if a.get("tool") == t), key=lambda a: ([i for i, _, _ in QUESTIONS].index(a["q"]), a["run"]))
        for a in rows:
            d = next(d for i, d, _ in QUESTIONS if i == a["q"]); B = a.get("businesses") or []
            ws.append([ev.get("dealer", ""), A.get("city_st", ""), DEPT_LABEL[d], a.get("asked", ""), a["run"], a.get("when", ""),
                       a.get("status", ""), a.get("answer", "") if a.get("status") == "answered" else "blocked: " + str(a.get("reason", "")),
                       "; ".join(b["name"] for b in B), "; ".join(TYPE_LABEL[b["type"]] for b in B),
                       ("Yes" if a.get("named") else "No") if a.get("status") == "answered" else ""])
        for col, w in zip("ABCDEFGHIJK", (24, 14, 11, 52, 6, 17, 10, 90, 48, 36, 12)): ws.column_dimensions[col].width = w
        for r in ws.iter_rows(min_row=2):
            for c in r: c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
    wb.save(path); return path

def file_name(dealer, date):
    return f"{re.sub(r'[^a-z0-9]+', '-', dealer.lower()).strip('-')}_ai-answers_{datetime.date.fromisoformat(date).strftime('%m-%d-%y')}.xlsx"

if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "questions":
        print("\n".join(f"{DEPT_LABEL[d]:8} {i:22} {q.format(city_st=a[1])}" for i, d, q in QUESTIONS)); sys.exit(0)
    if len(a) < 2 or a[0] not in ("check", "score", "brief", "sheet") or (a[0] == "sheet" and len(a) != 3): print(__doc__); sys.exit(2)
    ev = json.load(open(a[1]))
    if a[0] == "check":
        p = check(ev); print("AI VISIBILITY OK" if not p else "AI VISIBILITY INCOMPLETE:\n  - " + "\n  - ".join(p)); sys.exit(1 if p else 0)
    if a[0] == "score": print(json.dumps(scores(ev), indent=2)); sys.exit(0)
    if a[0] == "brief": print(brief(ev)); sys.exit(0)
    print(sheet(ev, a[2]))
