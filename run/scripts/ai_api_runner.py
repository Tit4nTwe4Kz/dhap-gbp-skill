#!/usr/bin/env python3
"""DHAP GBP AI visibility check through official APIs (no browser windows, no robot checks).

Asks the 5 questions 5 times on each of the 5 tools (125 asks, v16.1), all in parallel, and saves every answer to
<out>/dhap_ai_<tool>.json in the same record format as ai_runner.py / aicap.js, so ai_merge.py reads it unchanged.
v16.1 keeps only the top 2: each answer is capped at OUTPUT_CAP tokens (the first names come first) and Claude Haiku
pulls the first 2 businesses it names, in its order, into "top2": [{name, type}]. The answer text is kept as proof.

  chatgpt    OpenAI Responses API + web_search tool, approximate user location = the dealer's city
  gemini     Gemini API + Grounding with Google Search
  google_ai  SerpApi: Google's AI Overview for the question as Google shows it in the dealer's city; AI Mode when no
             Overview shows (the rule: "the AI Overview, or AI Mode when no Overview shows")
  claude     Claude API (Anthropic SDK) + web search tool, approximate user location = the dealer's city
  brave      Brave Search API, AI Grounding (chat/completions)

Keys come from keys.env next to this script or ~/.dhap-gbp-local/keys.env (chmod 600; see keys.env.example; never
commit it), or the environment. A tool with no key is skipped and says so.
Rate limits and server errors are retried with backoff (an API asking us to slow down is not a robot check); an ask that
still fails is recorded as blocked with the reason, never counted.

Usage:
  ~/.dhap-gbp-venv/bin/python ai_api_runner.py --city "Greece, NY" --out <run>/ai [--tools chatgpt,gemini,...] [--runs 1-5]
  ~/.dhap-gbp-venv/bin/python ai_api_runner.py --check-keys
"""
import argparse, concurrent.futures as cf, datetime, json, os, pathlib, random, re, threading, time
import urllib.error, urllib.parse, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
QUESTIONS = {   # v16.1, word for word (engine/ai_visibility.py QUESTIONS)
    "sales_new_family_suv": "best family SUV under 40k near {c}",
    "sales_used_midsize_suv": "used midsize SUV near {c}",
    "service_oil_change_near": "oil change near {c}",
    "service_brake_job": "brake job near {c}",
    "parts_brake_pads": "brake pads for my SUV near {c}",
}
TOP = 2
OUTPUT_CAP = 2500   # tokens, thinking included; an answer that comes back empty at the cap is asked once more without it
EXTRACT_MODEL = "claude-haiku-5-5"
TYPES = ["dealership", "oil_change", "tire_shop", "parts_store", "repair_shop", "retailer", "other"]
TOOLS = ("chatgpt", "gemini", "google_ai", "claude", "brave")
KEY = {"chatgpt": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "google_ai": "SERPAPI_API_KEY",
       "claude": "ANTHROPIC_API_KEY", "brave": "BRAVE_API_KEY"}
MODEL_DEFAULT = {"chatgpt": "gpt-5.4-mini", "gemini": "gemini-3.8-flash", "claude": "claude-sonnet-5-5"}   # the cheaper models (Travis, Oct 27 2026): only the top 2 names count
PARALLEL = {"chatgpt": 10, "gemini": 10, "google_ai": 10, "claude": 8, "brave": 2}   # Brave's base plan: 2 requests/second
STATES = dict(AL="Alabama", AK="Alaska", AZ="Arizona", AR="Arkansas", CA="California", CO="Colorado", CT="Connecticut",
              DE="Delaware", DC="District of Columbia", FL="Florida", GA="Georgia", HI="Hawaii", ID="Idaho", IL="Illinois",
              IN="Indiana", IA="Iowa", KS="Kansas", KY="Kentucky", LA="Louisiana", ME="Maine", MD="Maryland",
              MA="Massachusetts", MI="Michigan", MN="Minnesota", MS="Mississippi", MO="Missouri", MT="Montana",
              NE="Nebraska", NV="Nevada", NH="New Hampshire", NJ="New Jersey", NM="New Mexico", NY="New York",
              NC="North Carolina", ND="North Dakota", OH="Ohio", OK="Oklahoma", OR="Oregon", PA="Pennsylvania",
              RI="Rhode Island", SC="South Carolina", SD="South Dakota", TN="Tennessee", TX="Texas", UT="Utah",
              VT="Vermont", VA="Virginia", WA="Washington", WV="West Virginia", WI="Wisconsin", WY="Wyoming")


_u = threading.local()   # usage of the ask running on this thread: tokens, searches, calls (for the cost report)
def use(**n):
    d = getattr(_u, "d", None)
    if d is not None:
        for k, v in n.items():
            d[k] = d.get(k, 0) + int(v or 0)


class Blocked(Exception):
    """The tool gave no usable answer; the message is the reason recorded."""


def load_keys():
    for f in (HERE / "keys.env", pathlib.Path.home() / ".dhap-gbp-local" / "keys.env"):
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and not k.startswith("#") and v.strip() and not os.environ.get(k.strip()):
                os.environ[k.strip()] = v.strip().strip('"').strip("'")


def http(method, url, headers=None, body=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def with_retries(fn, tries=5):
    """Retry rate limits (429), server errors (5xx) and timeouts with backoff; anything else fails at once."""
    for n in range(tries):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            if e.code != 429 and e.code < 500 or n == tries - 1:
                raise Blocked(f"API error {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError) as e:
            if n == tries - 1:
                raise Blocked(f"network error: {e}")
        except Exception as e:   # the Anthropic SDK retries on its own; its errors land here
            status = getattr(e, "status_code", None)
            if status is not None and status != 429 and status < 500 or n == tries - 1:
                raise Blocked(f"API error {status or type(e).__name__}: {str(e)[:300]}")
        time.sleep(2 ** n + random.random())


# ---- one function per tool: (question, place) -> (answer text, [source urls], via) ----

def ask_chatgpt(q, p, cap=OUTPUT_CAP):
    model = os.environ.get("DHAP_OPENAI_MODEL", MODEL_DEFAULT["chatgpt"])
    loc = {"type": "approximate", "country": "US", "city": p["city"], "region": p["state_name"]}
    r = with_retries(lambda: http("POST", "https://api.openai.com/v1/responses",
                                  {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                                  {"model": model, "input": q, "tools": [{"type": "web_search", "user_location": loc}],
                                   **({"max_output_tokens": cap} if cap else {})}))
    u = r.get("usage") or {}
    use(calls=1, input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
        searches=sum(i.get("type") == "web_search_call" for i in r.get("output", [])))
    text, src = [], []
    for item in r.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    text.append(c.get("text", ""))
                    src += [a.get("url") for a in c.get("annotations", []) if a.get("type") == "url_citation"]
    return "\n".join(text), src, f"OpenAI API {model} + web search, location {p['city_st']}"


def ask_gemini(q, p, cap=OUTPUT_CAP):
    model = os.environ.get("DHAP_GEMINI_MODEL", MODEL_DEFAULT["gemini"])
    r = with_retries(lambda: http("POST", f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                  {"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                                  {"contents": [{"parts": [{"text": q}]}], "tools": [{"google_search": {}}],
                                   **({"generationConfig": {"maxOutputTokens": cap}} if cap else {})}))
    cand = (r.get("candidates") or [{}])[0]
    u = r.get("usageMetadata") or {}
    use(calls=1, input_tokens=(u.get("promptTokenCount") or 0) + (u.get("toolUsePromptTokenCount") or 0),
        output_tokens=(u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0),
        searches=len((cand.get("groundingMetadata") or {}).get("webSearchQueries") or []))
    text = "".join(part.get("text", "") for part in (cand.get("content") or {}).get("parts", []))
    src = [(c.get("web") or {}).get("uri") for c in (cand.get("groundingMetadata") or {}).get("groundingChunks", [])]
    if not text and cand.get("finishReason") and cand["finishReason"] != "MAX_TOKENS":
        raise Blocked(f"no answer (finishReason {cand['finishReason']})")
    return text, src, f"Gemini API {model} + Grounding with Google Search"


def _blocks_text(blocks, depth=0):
    """SerpApi text_blocks (paragraph / heading / list / table ...) -> plain text, keeping list nesting."""
    out = []
    for b in blocks or []:
        lr = b.get("local_result") or {}   # a place card: the business name is only here
        line = " ".join(str(x) for x in (lr.get("title"), f"({lr['type']})" if lr.get("type") else None,
                                          b.get("title"), b.get("snippet")) if x)
        if line:
            out.append(("  " * depth + "- " if depth else "") + line)
        for k in ("list", "text_blocks"):
            if isinstance(b.get(k), list):
                out += _blocks_text(b[k], depth + (k == "list"))
        if isinstance(b.get("table"), list):
            out += ["  " * depth + " | ".join(map(str, row)) for row in b["table"]]
    return out


def ask_google_ai(q, p, cap=None):   # SerpApi returns what Google showed; nothing to cap
    key = os.environ["SERPAPI_API_KEY"]
    serp = lambda **kw: (use(calls=1, searches=1), with_retries(lambda: http("GET", "https://serpapi.com/search.json?" + urllib.parse.urlencode({**kw, "api_key": key, "no_cache": "true"}))))[1]
    loc = f"{p['city']}, {p['state_name']}, United States"
    r = serp(engine="google", q=q, location=loc, gl="us", hl="en")
    ov = r.get("ai_overview") or {}
    if ov.get("page_token") and not ov.get("text_blocks"):   # full Overview needs a second call within 1 minute
        ov = serp(engine="google_ai_overview", page_token=ov["page_token"]).get("ai_overview") or {}
    via = "Google AI Overview via SerpApi"
    if not ov.get("text_blocks"):
        ov = serp(engine="google_ai_mode", q=q, location=loc, gl="us", hl="en")
        via = "Google AI Mode via SerpApi (no AI Overview shown)"
        if ov.get("reconstructed_markdown") and not ov.get("text_blocks"):
            return ov["reconstructed_markdown"], [x.get("link") for x in ov.get("references", [])], f"{via}, location {loc}"
    text = "\n".join(_blocks_text(ov.get("text_blocks")))
    return text, [x.get("link") for x in ov.get("references", [])], f"{via}, location {loc}"


_claude = None
def ask_claude(q, p, cap=OUTPUT_CAP):
    global _claude
    import anthropic
    _claude = _claude or anthropic.Anthropic(max_retries=4)
    model = os.environ.get("DHAP_CLAUDE_MODEL", MODEL_DEFAULT["claude"])
    tool = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5,
            "user_location": {"type": "approximate", "city": p["city"], "region": p["state_name"], "country": "US"}}
    messages = [{"role": "user", "content": q}]
    for _ in range(4):   # pause_turn: the server's search loop paused; send the turn back to let it finish
        r = with_retries(lambda: _claude.beta.messages.create(
            model=model, max_tokens=cap or 16000, messages=messages, tools=[tool],
            betas=["server-side-fallback-2026-07-01"], fallbacks="default"), tries=2)
        stu = getattr(r.usage, "server_tool_use", None)
        use(calls=1, input_tokens=r.usage.input_tokens + (r.usage.cache_read_input_tokens or 0) + (r.usage.cache_creation_input_tokens or 0),
            output_tokens=r.usage.output_tokens, searches=getattr(stu, "web_search_requests", 0) if stu else 0)
        if r.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": r.content}]
    if r.stop_reason == "refusal":
        raise Blocked("Claude declined to answer (refusal)")
    text, src = [], []
    for b in r.content:
        if b.type == "text":
            text.append(b.text)
            src += [c.url for c in (b.citations or []) if getattr(c, "url", None)]
    return "".join(text), src, f"Claude API {r.model} + web search, location {p['city_st']}"


def ask_brave(q, p, cap=None):
    r = with_retries(lambda: http("POST", "https://api.search.brave.com/res/v1/chat/completions",
                                  {"X-Subscription-Token": os.environ["BRAVE_API_KEY"], "Accept": "application/json"},
                                  {"model": "brave", "stream": False, "country": "us", "language": "en",
                                   "messages": [{"role": "user", "content": q}]}))
    u = r.get("usage") or {}
    use(calls=1, input_tokens=u.get("prompt_tokens"), output_tokens=u.get("completion_tokens"),
        searches=u.get("search_requests") or u.get("searches"))   # Brave bills per search; recorded when its response reports it
    text = ((r.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    src = re.findall(r"https?://[^\s\"'<>)\]]+", text)
    return text, src, "Brave Search API, AI Grounding"


# ---- top 2: code + Haiku find the names, JEV judges them, a fixed rule checks JEV (SKILL.md: JEV decides first) ----
def _engine():
    """engine/decide.py from the rules repository (one JEV client, model pinned there)."""
    import sys
    for d in (HERE.parents[1] / "engine", pathlib.Path.home() / "dhap-gbp-skill" / "engine"):
        if (d / "decide.py").exists():
            sys.path.insert(0, str(d))
            import decide
            return decide
    raise Blocked("engine/decide.py not found (clone Clikdata2/dhap-gbp-skill to ~/dhap-gbp-skill)")


def fold(s):
    return " ".join(re.sub(r"[^a-z0-9&]+", " ", str(s).casefold()).split())


BOLD = re.compile(r"\*\*([^*\n]{2,80})\*\*")
LEAD = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(?:\*\*)?([A-Z0-9][^:\n–—|(*]{1,70}?)\s*(?:\*\*|[:–—|(]|$)", re.M)
NOT_BUSINESS = re.compile(   # the fixed rule that checks JEV: a car, a website, a place, a heading or advice
    r"\.(com|net|org|io)\b|\b(cargurus|autotrader|edmunds|kelley blue book|kbb|truecar|yelp|google|facebook|craigslist|"
    r"repairpal|carfax|cars com|reddit|youtube|consumer reports)\b|"
    r"^(acura|audi|bmw|buick|cadillac|chevrolet|chevy|chrysler|dodge|ford|gmc|honda|hyundai|infiniti|jeep|kia|lexus|"
    r"lincoln|mazda|mercedes|mitsubishi|nissan|ram|subaru|tesla|toyota|volkswagen|vw|volvo)( [a-z0-9-]+){0,3}$|"
    r"^(address|phone|hours|rating|price|details|why go|tip|tips|note|summary|bottom line|cost|estimate|average)\b|"
    r"\b(near|in) (you|your area)\b|\b(on or near|options|shops|dealerships|dealers|stores|locations)$|"
    r"^(choosing|fastest|cheapest|best|budget|convenience|convenient|quick|overall|pricing|prices|coupons|deals|"
    r"specials|recommendations|independent|dealer|dealership|chains?|national chains?|local shops?|other|more)$", re.I)
ADDRESS = re.compile(r"\(?\d{3}\)?[ .-]?\d{3}[ .-]\d{4}|^\d+\s+\S+|^(located at|location\b|address\b)|\blocation( \d+)?$|\b(ny|n\.y\.) \d{5}$", re.I)
CHUNK = 20   # candidates per JEV request, in reading order; stop once the top 2 are found


def looks_like_business(name):
    """The fixed rule that checks JEV: a proper name (capitalized words, no prices or counts) that is not a car, a
    website, a place, a heading or advice."""
    words = re.findall(r"[A-Za-z][\w'’&-]*", name)
    caps = sum(w[0].isupper() for w in words)
    if not words or not name[0].isupper() or re.search(r"[$%]|\d{2,}", name) or caps < max(1, len(words) // 2):
        return False
    return not NOT_BUSINESS.search(fold(name) if "." not in name else name)


def base(name):
    """A chain's name without the branch: 'Valvoline Instant Oil Change (Latta Rd)', 'Jiffy Lube — Henrietta' and
    'Advance Auto Parts #3555' each count once."""
    return fold(re.sub(r"\s*[(\[].*$|\s+[—–-]\s+.*$|\s*#\s*\d+.*$", "", name))


TYPE_RULE = [("oil_change", r"valvoline|jiffy|take 5|lube|oil change|quick lane|delta sonic"),
             ("parts_store", r"autozone|advance auto|o.?reilly|napa|carquest|pep boys|parts"),
             ("tire_shop", r"tire|discount tire|mavis|firestone|goodyear|dunn"),
             ("retailer", r"walmart|costco|target|sam.?s club|bj.?s|canadian tire|meijer"),
             ("dealership", r"auto group|motors|automotive group|dealership|carmax|carvana|chevrolet|toyota|honda|hyundai|"
                            r"kia|nissan|subaru|ford|mitsubishi|jeep|chrysler|dodge|buick|gmc|mazda|volkswagen|lexus|acura|used"),
             ("repair_shop", r"auto care|repair|automotive|muffler|brake|midas|monro|service center|garage|mechanic")]


def candidates(answer, scan=True):
    """Every name that might be a business, in the order it first appears in the answer (code over-finds; Haiku adds
    names the patterns miss). Each candidate is copied from the answer, so nothing can be made up."""
    found = [m.group(1) for m in BOLD.finditer(answer)] + [m.group(1) for m in LEAD.finditer(answer)]
    if scan:
        found += haiku_names(answer)
    low, seen, out = answer.casefold(), set(), []
    for n in found:
        n = n.strip(" *#.:-–—\t")
        k = fold(n)
        if not k or k in seen or len(n) > 80 or ADDRESS.search(n):
            continue
        pos = low.find(n.casefold())
        if pos < 0:
            continue                      # not in the answer word for word: never used
        seen.add(k); out.append({"name": n, "pos": pos})
    return sorted(out, key=lambda c: c["pos"])


_haiku = None
def haiku_names(answer):
    """Claude Haiku lists names only (no judging, no order): JEV and the rule decide what counts."""
    global _haiku
    import anthropic
    _haiku = _haiku or anthropic.Anthropic(max_retries=4)
    schema = {"type": "object", "additionalProperties": False, "required": ["names"],
              "properties": {"names": {"type": "array", "items": {"type": "string"}}}}
    r = _haiku.messages.create(
        model=EXTRACT_MODEL, max_tokens=1024, output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": "Copy, word for word, every name in this text that could be a business "
                   "(dealerships, shops, stores, service centers, chains). Include doubtful ones. Names only.\n\n<text>\n"
                   + answer[:12000] + "\n</text>"}])
    use(extract_input_tokens=r.usage.input_tokens, extract_output_tokens=r.usage.output_tokens)
    return json.loads(next(b.text for b in r.content if b.type == "text"))["names"]


IS_BUSINESS = ("In this answer an AI assistant gave a local car shopper, is {cand} a specific business the answer "
               "suggests the shopper go to or call?",
               "It is a dealership, dealer group, repair or tire shop, quick-lube, parts store, retailer or service center "
               "that the answer lists, recommends or suggests as a place to go.",
               "It is a car make or model, a website, app, marketplace or review site (Cars.com, CarGurus, Yelp), a town, "
               "road, street address or area, a landmark mentioned only to give directions, a heading or category (for example "
               "'Quick-Service Oil Change Centers'), or general advice.")
TYPE_Q = ("What kind of business is {cand}, going by this answer?",
          {"dealership": "Sells cars (new or used), including dealer groups and used-car lots",
           "oil_change": "Quick-lube or oil-change shop", "tire_shop": "Tire shop or tire and service chain",
           "parts_store": "Auto parts store", "repair_shop": "Independent repair or service shop",
           "retailer": "Big-box or general store", "other": "Anything else"})
IS_DEALER = ("Is {cand} the dealership {dealer}, or one of its departments?",
             "The names differ only by spelling, punctuation, abbreviations, the town, the brand order, or words like Inc, "
             "LLC, Sales, Service or Parts, so a shopper would read them as the same dealership.",
             "It is a different dealership, dealer group, brand or business.")


def _jev(D, url, key, answer, C, dealer):
    """One JEV request for a batch of candidates: is it a business (noul), what kind (choice), is it the dealer (noul)."""
    state = {"answer": answer[:20000], **{f"cand_{i}": c["name"] for i, c in enumerate(C)}}
    qs = {}
    for i in range(len(C)):
        ins, yes, no = IS_BUSINESS
        qs[f"biz_{i}"] = {"type": "noul", "instructions": ins.format(cand=f"cand_{i}"), "criteria": {"true": yes, "false": no}}
        qs[f"type_{i}"] = {"type": "choice", "instructions": TYPE_Q[0].format(cand=f"cand_{i}"), "criteria": TYPE_Q[1]}
        if dealer:
            ins, yes, no = IS_DEALER
            qs[f"dealer_{i}"] = {"type": "noul", "instructions": ins.format(cand=f"cand_{i}", dealer=dealer),
                                 "criteria": {"true": yes, "false": no}}
    auth = {"X-DHAP-Code": key[5:]} if key.startswith("team:") else {"Authorization": f"Bearer {key}"}
    r = with_retries(lambda: http("POST", url, auth, {"model": D.MODEL, "state": state, "questions": qs}, timeout=60), tries=3)
    return r.get("answers") or {}, float((r.get("usage") or {}).get("input_tokens") or 0), r.get("model")


def top2(answer, dealer=None, scan=True):
    """The first 2 businesses the answer names, in its order -> ([{name, type}], JEV ledger).
    JEV sure (yes >= 0.7, no <= 0.3) decides; JEV unsure or unavailable -> the rule decides. A disagreement on a name
    that could put a wrong name in the top 2 (JEV yes / rule no, or JEV unsure) is listed for a person
    (ledger["review"]); JEV turning down what the rule let through is counted in ledger["overruled"]."""
    D = _engine()
    C = candidates(answer, scan)
    led = {"model": D.MODEL, "status": "skipped" if C else "ok", "candidates": [], "review": [], "cost_usd": 0.0}
    url, key = D._service()
    if C and not key:
        led["reason"] = "no JEV key (DHAP_SERVICE_URL + DHAP_TEAM_CODE, or TYPESAFE_API_KEY)"
    dkey = fold(re.sub(r"\b(of|the|inc|llc)\b", " ", dealer or "", flags=re.I)).split()
    top, dealer_hit, tok = [], False, 0.0

    def decide(a, qid, rule, what, name, notes):
        try:
            p = float((a.get(qid) or {})["noul"])
        except (KeyError, TypeError, ValueError):
            return rule, "rule (JEV unavailable)", None
        says = "yes" if p >= D.YES else "no" if p <= D.NO else "unsure"
        if says == "unsure":
            notes.append(f"{name!r} {what}: JEV unsure (p={p:.2f}); the rule's {'yes' if rule else 'no'} is used")
            return rule, "rule (JEV unsure)", p
        if says == "yes" and not rule:      # could put a wrong name in the top 2: a person checks it
            notes.append(f"{name!r} {what}: JEV says yes, the rule says no; JEV's answer is used")
        elif says == "no" and rule:         # JEV turned down what the rule let through: kept in the record, not listed
            led["overruled"] = led.get("overruled", 0) + 1
        return says == "yes", "jev", p

    for s in range(0, len(C), CHUNK):
        batch, a = C[s:s + CHUNK], {}
        if key:
            try:
                a, n, served = _jev(D, url, key, answer, batch, dealer)
                tok += n; led.update(status="ok", model_served=served)
            except Blocked as e:
                led["status"], led["reason"] = "skipped", str(e)[:200]
        for i, c in enumerate(batch):
            notes = []
            rule = looks_like_business(c["name"])
            is_biz, by, p = decide(a, f"biz_{i}", rule, "is a business", c["name"], notes)
            ch = a.get(f"type_{i}") or {}
            typ = ch["choice"] if ch.get("choice") in TYPES and float(ch.get("confidence") or 0) >= D.YES else \
                next((k for k, rx in TYPE_RULE if re.search(rx, c["name"], re.I)), "other")
            row = {"name": c["name"], "pos": c["pos"], "p": p, "rule": rule, "is_business": is_biz, "by": by, "type": typ}
            dup = is_biz and any(base(c["name"]) == base(x["name"]) or base(c["name"]).startswith(base(x["name"]) + " ")
                                 or base(x["name"]).startswith(base(c["name"]) + " ") for x in top)
            row["counted"] = bool(is_biz and not dup)
            if row["counted"]:
                top.append({"name": c["name"], "type": typ})
                if dealer:
                    drule = bool(dkey) and all(w in fold(c["name"]).split() for w in dkey[:2])
                    row["dealer"], row["dealer_by"], row["dealer_p"] = decide(a, f"dealer_{i}", drule, f"is {dealer}", c["name"], notes)
                    dealer_hit |= row["dealer"]
            led["review"] += notes          # only names read up to the 2nd business: these decide the top 2
            led["candidates"].append(row)
            if len(top) == TOP:
                break
        if len(top) == TOP:
            break
    use(jev_input_tokens=tok)
    led["cost_usd"] = round(tok * D.PRICE_PER_M_INPUT / 1e6, 8)
    if led["status"] != "ok":
        led["review"].append(f"JEV did not run ({led.get('reason')}); every answer came from the rule")
    if dealer:
        led["dealer"], led["dealer_in_top2"] = dealer, dealer_hit
    return top, led


ASK = {"chatgpt": ask_chatgpt, "gemini": ask_gemini, "google_ai": ask_google_ai, "claude": ask_claude, "brave": ask_brave}


def reextract(out, tools, dealer=None):
    """Pull the top 2 again from saved answers (after an extraction fix). Re-asks nothing; only Claude Haiku is called."""
    t0, lock = time.time(), threading.Lock()
    for t in tools:
        f = out / f"dhap_ai_{t}.json"
        if not f.exists():
            continue
        recs = json.loads(f.read_text())
        def one(rec):
            _u.d = {}
            try:
                rec["top2"], rec["jev"] = top2(rec["answer"], dealer); rec.pop("top2_error", None)
            except Exception as e:
                rec.pop("top2", None); rec["top2_error"] = f"{type(e).__name__}: {str(e)[:200]}"
            with lock:
                u = rec.setdefault("usage", {})
                u["reextract_input_tokens"] = u.get("reextract_input_tokens", 0) + _u.d.get("extract_input_tokens", 0)
                u["reextract_jev_input_tokens"] = u.get("reextract_jev_input_tokens", 0) + _u.d.get("jev_input_tokens", 0)
                u["reextract_output_tokens"] = u.get("reextract_output_tokens", 0) + _u.d.get("extract_output_tokens", 0)
        with cf.ThreadPoolExecutor(10) as ex:
            list(ex.map(one, [r for r in recs if r.get("status") == "answered"]))
        f.write_text(json.dumps(recs, indent=1, ensure_ascii=False))
        print(t, sum("top2" in r for r in recs), "re-pulled,", sum("top2_error" in r for r in recs), "errors", flush=True)
    print(f"re-pulled in {time.time() - t0:.0f}s")


def parse_runs(s):
    a, _, b = s.partition("-")
    return list(range(int(a), int(b or a) + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", help='the dealer\'s "City, ST"')
    ap.add_argument("--out", help="the run's ai/ folder")
    ap.add_argument("--tools", default=",".join(TOOLS))
    ap.add_argument("--questions", default=",".join(QUESTIONS))
    ap.add_argument("--runs", default="1-5")
    ap.add_argument("--dealer", help='the dealership\'s name, e.g. "James Mitsubishi" (JEV checks whether each top-2 name is this dealer)')
    ap.add_argument("--check-keys", action="store_true")
    ap.add_argument("--reextract", action="store_true", help="pull the top 2 again from the answers already saved in --out (asks nothing)")
    a = ap.parse_args()
    load_keys()
    tools = [t for t in a.tools.split(",") if t]
    missing = [t for t in tools if not os.environ.get(KEY[t])]
    if a.check_keys:
        for t in tools:
            print(f"{t:10} {KEY[t]:18} {'set' if t not in missing else 'MISSING'}")
        return
    if a.reextract:
        if not a.out:
            ap.error("--out is required")
        return reextract(pathlib.Path(a.out), tools, a.dealer)
    if not (a.city and a.out):
        ap.error("--city and --out are required")
    m = re.match(r"^\s*(.+?),\s*([A-Z]{2})\s*$", a.city)
    if not m or m.group(2) not in STATES:
        ap.error('--city must look like "Greece, NY"')
    place = {"city": m.group(1), "state": m.group(2), "state_name": STATES[m.group(2)], "city_st": f"{m.group(1)}, {m.group(2)}"}
    for t in missing:
        print(f"SKIPPED {t}: {KEY[t]} is not set (keys.env)")
    tools = [t for t in tools if t not in missing]
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)

    recs, done, lock = {}, set(), threading.Lock()
    for t in tools:
        f = out / f"dhap_ai_{t}.json"
        recs[t] = json.loads(f.read_text()) if f.exists() else []
        done |= {(t, r["q"], r["run"]) for r in recs[t]}

    def one(t, q, run):
        asked = QUESTIONS[q].format(c=place["city_st"])
        rec = {"tool": t, "q": q, "run": run, "asked": asked}
        _u.d, s0 = {}, time.time()
        try:
            text, src, via = ASK[t](asked, place)
            if len(text.strip()) < 40 and t in ("chatgpt", "gemini", "claude"):   # the cap cut it before any text: once more, uncapped
                text, src, via = ASK[t](asked, place, cap=None)
            if len(text.strip()) < 40:
                raise Blocked("empty or near-empty answer")
            rec.update(status="answered", answer=text.strip(), complete=True, via=via, sources=[s for s in src if s][:40])
            try:
                rec["top2"], rec["jev"] = top2(rec["answer"], a.dealer)
            except Exception as e:   # ai_merge.py falls back to its own name list; the answer is still saved
                rec["top2_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        except Blocked as e:
            rec.update(status="blocked", reason=str(e), via=f"{t} API")
        except KeyError as e:
            rec.update(status="blocked", reason=f"unexpected response shape (missing {e})", via=f"{t} API")
        rec["when"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        rec["seconds"], rec["usage"] = round(time.time() - s0, 1), _u.d
        with lock:
            recs[t].append(rec)
            (out / f"dhap_ai_{t}.json").write_text(json.dumps(recs[t], indent=1, ensure_ascii=False))
            print(t, q, run, rec["status"], " | ".join(b["name"] for b in rec.get("top2", [])), rec.get("reason", "")[:80], flush=True)

    jobs = [(t, q, r) for t in tools for q in a.questions.split(",") for r in parse_runs(a.runs) if (t, q, r) not in done]
    pools = {t: cf.ThreadPoolExecutor(PARALLEL[t]) for t in tools}
    t0 = time.time()
    futs = [pools[t].submit(one, t, q, r) for t, q, r in jobs]
    for f in cf.as_completed(futs):
        f.result()
    for p in pools.values():
        p.shutdown()
    by = {t: sum(r["status"] == "answered" for r in recs[t]) for t in tools}
    rep = {"city": place["city_st"], "seconds_total": round(time.time() - t0), "models": {t: os.environ.get(f"DHAP_{ {'chatgpt': 'OPENAI', 'gemini': 'GEMINI', 'claude': 'CLAUDE'}[t]}_MODEL", MODEL_DEFAULT[t]) for t in tools if t in MODEL_DEFAULT}, "tools": {}}
    for t in tools:
        tot = {}
        for r in recs[t]:
            for k, v in (r.get("usage") or {}).items():
                tot[k] = tot.get(k, 0) + v
        rep["tools"][t] = {"asks": len(recs[t]), "answered": by[t] if t in by else None, "seconds_longest": max([r.get("seconds", 0) for r in recs[t]] or [0]), **tot}
    (out / "dhap_ai_usage.json").write_text(json.dumps(rep, indent=1))
    for t, d in rep["tools"].items():
        print(f"usage {t:10} " + ", ".join(f"{k} {v}" for k, v in d.items()))
    print(f"done in {time.time() - t0:.0f}s: " + ", ".join(f"{t} {n}/{len(recs[t])} answered" for t, n in by.items()))


if __name__ == "__main__":
    main()
