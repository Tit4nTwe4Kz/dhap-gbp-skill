"""Stress test for build.py + the assertion gate + the phone probe. Run with the venv python: tests/test_build.py [rounds]"""
import copy, hashlib, json, pathlib, shutil, subprocess, sys, tempfile
ENG = pathlib.Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ENG))
import score as S, check_all as C
REPO = S.default_repo() if (S.default_repo() / "SKILL.md").exists() else ENG.parent / "repo"; PY = sys.executable; OUT = ENG / "tests" / "out" / "stress"
EV = json.load(open(ENG / "examples/evidence-example-vacaville.json")); CT = json.load(open(ENG / "examples/content-example-vacaville.json"))
JEV = json.load(open(ENG / "examples/evidence-example-james.json")); JCT = json.load(open(ENG / "examples/content-example-james.json"))
V152 = json.load(open(ENG / "examples/evidence-example-v15-2.json")); C152 = json.load(open(ENG / "examples/content-example-v15-2.json"))
fails = 0
def ok(name, cond, extra=""):
    global fails; fails += 0 if cond else 1; print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  " + str(extra)[:300]))
def build(ev, ct, repo=REPO, tag="x"):
    d = pathlib.Path(tempfile.mkdtemp()); (d / "ev.json").write_text(json.dumps(ev)); (d / "ct.json").write_text(json.dumps(ct))
    r = subprocess.run([PY, "-I", str(ENG / "build.py"), "--repo", str(repo), "--evidence", str(d / "ev.json"), "--content", str(d / "ct.json"), "--out", str(OUT / tag)], capture_output=True, text=True)
    return r, (json.loads(r.stdout) if r.returncode == 0 else None)
def suite(ev, ct, out, words):
    D = pathlib.Path(out["dhap"]).read_text(); H = pathlib.Path(out["health_alert"]).read_text()
    try: return True, C.suite(REPO, D, H, ev, ct["report_id"], words), D, H
    except AssertionError as e: return False, str(e), D, H
def probe(out):
    r = subprocess.run([PY, str(ENG / "probe_mobile.py"), out["dhap"], out["health_alert"], str(OUT / "shots")], capture_output=True, text=True)
    return r.returncode == 0, r.stdout[-200:]
JW = ["James Mitsubishi", "Greece, NY", "Greece NY", "Rochester", "GBP-JMGNY"]

def variants():
    v = {}
    v["vacaville (Major Issues)"] = (copy.deepcopy(EV), copy.deepcopy(CT), "Major Issues", "#ea580c")
    v["james (locked reference, Critical)"] = (copy.deepcopy(JEV), copy.deepcopy(JCT), "Critical", "#dc2626")
    # Critical: drop the shared listing's photos/posts and the directory matches so a row falls to 5.0 or below
    e = copy.deepcopy(EV); e["nap"].update(google_vs_site_fields_matching=1, directories_agree=[False] * 5); v["critical"] = (e, copy.deepcopy(CT), "Critical", "#dc2626")
    # Needs Improvement: lift every weak row to 7+ but not all to 9
    e = copy.deepcopy(EV); e["nap"].update(google_vs_site_fields_matching=3, directories_agree=[True] * 5, dept_phones=[{"dept": "service & parts", "gbp": "707-353-4579", "site": "707-353-4579"}])
    for k in ("sales", "combined"): e["listings"][k].update(photos_30d=6, posts_30d=8, last_post_days=2, logo=True, variety=dict(offers=True, events=True, cta=True), newest_review_days=3)
    e["listings"]["combined"].update(coverage=dict(exterior=True, interior_or_team=True, department=True)); e["reviews"].update(real_reviews_visible_on_site=True)
    six = ["Vacaville", "Sacramento", "Davis", "Fairfield", "Vallejo", "Stockton"]   # code and pages agree on every place (rule 4: 2 of 2)
    e["schema"]["areaserved"].update(code_places=six, page_places=six, code_on_page=six)
    v["needs improvement"] = (e, copy.deepcopy(CT), "Needs Improvement", "#ca8a04")
    # Fully Optimized: everything met
    f = copy.deepcopy(e); f["listings"]["combined"].update(checklist_done=8); f["listings"]["sales"].update(coverage=dict(exterior=True, interior_or_team=True, department=True))
    f["reviews"]["facebook"] = {"mode": "stars", "within_half": True}; f["schema"].update(department_entities=3, dept_own_page_address=3, dept_own_phone=3, sameas_other=True, hasmap_or_map=True)
    v["fully optimized"] = (f, copy.deepcopy(CT), "Fully Optimized", "#15803d")
    # odd names: apostrophes and an ampersand must not break the page
    e = copy.deepcopy(EV); c = copy.deepcopy(CT); e["dealer"] = c["dealer"] = "O'Brien Mitsubishi & Sons"; c["city_st"] = "Coeur d'Alene, ID"
    v["odd names (apostrophe, ampersand)"] = (e, c, "Major Issues", "#ea580c")
    v["v15.2 (rule 7 cards, rule 8 NAP tables)"] = (copy.deepcopy(V152), copy.deepcopy(C152), "Major Issues", "#ea580c")
    return v

def round_once(n):
    print(f"--- round {n}")
    hashes = {}
    for name, (ev, ct, want, col) in variants().items():
        r, out = build(ev, ct, tag=name.split()[0])
        if not out: ok(name + " builds", False, r.stdout + r.stderr); continue
        good, msg, D, H = suite(ev, ct, out, [] if name.startswith("james") else JW)   # the template IS James, so his words belong there
        ok(f"{name}: builds and passes the repository assertions", good, msg)
        st = S.status(S.score_rows(ev)[1])
        ok(f"{name}: status is {want}", st["label"] == want, st)
        tag = 'clarity("set","prospect",' + json.dumps(ev["dealer"], ensure_ascii=False).replace("</", "<\\/") + ")"
        ok(f"{name}: Clarity code (RULE M) once on each page, tagged with the dealer and report type",
           all(p.count("clarity.ms/tag/") == 1 and tag in p and p.index("clarity.ms/tag/") < p.index("</head>") for p in (D, H))
           and 'clarity("set","report_type","DHAP")' in D and 'clarity("set","report_type","ALERT")' in H)
        inv = D[D.index("<!-- INVESTMENT TAB -->"):]; banner = inv[inv.index('<div class="roi-sub">'):]; banner = banner[:banner.index("</div>")]
        ok(f"{name}: the Investment banner says 'Results in 90 days.' once, right after 'Go-live in 72 hours after onboarding.' (v16.9)",
           banner.endswith("Up to 100% MiDS reimbursement, based on available funds. Go-live in 72 hours after onboarding. Results in 90 days.</strong>")
           and banner.count("Results in 90 days.") == 1, banner[-200:])
        if want != "Critical": ok(f"{name}: verdict colour {col} and label [{want.upper()}]", col in H and f"[</span>{want.upper()}<" in H and "[</span>CRITICAL<" not in H)
        else: ok(f"{name}: verdict stays [CRITICAL] red", "[</span>CRITICAL<" in H and "#dc2626" in H)
        if name.startswith("james"): ok("james: rows and overall equal the locked reference in SKILL.md", S.score_rows(ev)[1] == [10.0, 4.0, 2.3, 8.4, 0.0, 9.2, 5.6, 5.0] and S.overall(S.score_rows(ev)[1]) == 5.6)
        if name.startswith("v15.2"):
            ok("v15.2: the Alert shows the engine's four cards", out["alert_cards"] == ["NAP_MISMATCHES", "POSTS_30D", "PHOTOS_30D", "LAST_REVIEW_DAYS"], out["alert_cards"])
            ok("v15.2: both NAP tables are on the DHAP", "Where AI Tools &amp; Car Shoppers Read Your Name" in D and "Directory Network Check" in D)
            e = copy.deepcopy(V152); e["nap"]["google_phones"]["sales"] = "888-555-0100"; r2, o2 = build(e, copy.deepcopy(C152), tag="v152tf")
            ok("v15.2: a toll-free Google number adds a 'should be local' finding", o2 is not None and "Sales Number Is Toll-Free &mdash; It Should Be Local" in pathlib.Path(o2["dhap"]).read_text(), (r2.stdout + r2.stderr)[-300:])
        if name.startswith("odd"): ok("odd names are escaped in the page title", "O'Brien Mitsubishi &amp; Sons" in D and "Coeur d'Alene, ID" in D and "Sons &mdash;" in H)
        hashes[name] = hashlib.sha256((D + H).encode()).hexdigest()[:12]
        if name in ("critical", "fully optimized", "odd names (apostrophe, ampersand)", "james (locked reference, Critical)", "v15.2 (rule 7 cards, rule 8 NAP tables)"):
            pg, tail = probe(out); ok(f"{name}: phone-width probe 360/390/430", pg, tail)
    # unsafe or incomplete content must be refused, each with its own reason
    def refuse(name, mut, needle, ev=None):
        c = copy.deepcopy(CT); e = copy.deepcopy(ev or EV); mut(c, e); r, out = build(e, c, tag="refuse")
        ok("refuses " + name, out is None and needle in (r.stdout + r.stderr), (r.stdout + r.stderr)[-200:])
    refuse("a <script> tag", lambda c, e: c["findings"][0]["cards"][0].update(body="x<script>alert(1)</script>"), "unsafe HTML")
    refuse("an onclick= handler", lambda c, e: c["summary"].update(red='<b onclick="x()">x</b>'), "unsafe HTML")
    refuse("a <div> inside content", lambda c, e: c["summary"].update(context="<div>x</div>"), "<div> is not allowed")
    refuse("a TODO placeholder", lambda c, e: c["why_card"].update(body="TODO write this"), "placeholder")
    refuse("hand-written stat cards on a v15.2 audit (rule 7)", lambda c, e: None, "leave it out", ev=V152)
    refuse("a stat header over 16 characters", lambda c, e: c["alert"]["stats"][0].__setitem__(0, "DIFFERENT_PHONE_NUMBERS"), "at most 16 characters")
    refuse("5 tiles instead of 6", lambda c, e: c["alert"]["tiles"].pop(), "exactly 6")
    refuse("content for a different dealer", lambda c, e: c.update(dealer="Someone Else Mitsubishi"), "content is for")
    refuse("no 'Reviews Not Shown' tile", lambda c, e: c["alert"]["tiles"].__setitem__(5, c["alert"]["tiles"][4]), "Reviews Not Shown on Website")
    refuse("no omni-social card", lambda c, e: [s.pop("add_omni_social", None) for s in c["findings"]], "add_omni_social")
    refuse("incomplete evidence", lambda c, e: e.pop("ledger"), "evidence incomplete")
    # a changed template must stop the build with a clear message (never a half-built page)
    tmp = pathlib.Path(tempfile.mkdtemp()); shutil.copytree(REPO, tmp / "repo", ignore=shutil.ignore_patterns(".git"))
    t = sorted((tmp / "repo/templates").glob("*_dhap_v*.html"))[-1]; t.write_text(t.read_text().replace("<!-- SOLUTION TAB -->", "<!-- SOLUTIONS TAB -->"))
    r, out = build(copy.deepcopy(EV), copy.deepcopy(CT), repo=tmp / "repo", tag="tpl")
    ok("refuses when the repository template changed", out is None and "template marker missing" in r.stdout + r.stderr, (r.stdout + r.stderr)[-200:])
    shutil.rmtree(tmp)
    return hashes

rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
H = [round_once(i + 1) for i in range(rounds)]
ok("same input -> byte-identical pages every round", all(h == H[0] for h in H), H)
print(f"\n{'ALL PASSED' if fails == 0 else str(fails) + ' FAILED'}"); sys.exit(1 if fails else 0)
