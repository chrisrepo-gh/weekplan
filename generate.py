"""Generate the weekly activity plan (index.md + index.html).

Flow:
1. Work out the upcoming week (Monday-Sunday) and whether it is a KIDS or SOLO
   week from the fixed 14-day cycle in weekplan.yaml.
2. Ask Gemini, with Google Search grounding switched on, for real events and
   places as structured JSON items.
3. Drop dated items that fall outside the week, check every link, and render
   Markdown + HTML ourselves (the model never writes the page).

If anything fails, the script exits non-zero WITHOUT touching index.md/index.html,
so the last good plan stays online and the GitHub Action shows as failed.
"""

import datetime as dt
import html
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "weekplan.yaml"
OUT_DIR = Path(os.environ.get("OUT_DIR", ROOT))
FALLBACK_MODEL = "gemini-flash-latest"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# --------------------------------------------------------------------------- #
# Week logic
# --------------------------------------------------------------------------- #
def upcoming_monday(today):
    """Monday of the week to plan.

    Sunday (scheduled run) -> tomorrow. Monday -> today. Any other day -> next Monday.
    """
    return today + dt.timedelta(days=(7 - today.weekday()) % 7)


def week_type(monday, kids_reference):
    """KIDS or SOLO from a fixed reference Monday and a strict 14-day rhythm.

    Unlike ISO-week parity this does not break in years with 53 ISO weeks.
    """
    if kids_reference.weekday() != 0:
        raise ValueError(f"kids_week_reference {kids_reference} is not a Monday")
    weeks = (monday - kids_reference).days // 7
    return "KIDS" if weeks % 2 == 0 else "SOLO"


def child_age(child, on_date):
    """Age on a given date: exact from 'born' (YYYY-MM), else 'age' + full years since 'age_as_of'."""
    if child.get("born"):
        year, month = (int(x) for x in str(child["born"]).split("-")[:2])
        return on_date.year - year - (1 if on_date.month < month else 0)
    as_of = dt.date.fromisoformat(str(child["age_as_of"]))
    years = on_date.year - as_of.year - ((on_date.month, on_date.day) < (as_of.month, as_of.day))
    return int(child["age"]) + max(years, 0)


# --------------------------------------------------------------------------- #
# Prompt + model call
# --------------------------------------------------------------------------- #
def build_prompt(cfg, monday, kind, ages):
    sunday = monday + dt.timedelta(days=6)
    days = ", ".join(
        f"{WEEKDAYS[i]} {(monday + dt.timedelta(days=i)).isoformat()}" for i in range(7)
    )
    if kind == "KIDS":
        who = cfg["kids"]["who"].format(ages=" and ".join(str(a) for a in ages))
        focus = cfg["kids"]["focus"]
    else:
        who = cfg["solo"]["who"]
        focus = cfg["solo"]["focus"]
    exclusions = "; ".join(cfg.get("exclude", []))

    return f"""You plan the coming week for Fernando, who lives in {cfg['location']}.
Week: {monday.isoformat()} to {sunday.isoformat()} ({days}). This is a {kind} week.
Plan for: {who}.
What to look for: {focus}
Exclude: {exclusions}.

Use Google Search. Rules:
- A DATED item must be an event you found in search results with an explicit date inside
  this week. Give its date and start time exactly as the source states them.
- Places that can be visited any day (zoo, pool, museum, climbing hall) are ANYTIME items:
  set "date" and "time" to null. Never invent a date or time for them.
- "url" must be a page you actually saw in the search results, preferably the official page
  of the event or venue. Do not construct or guess URLs.
- If you cannot confirm a detail, write "unknown" rather than guessing.
- Aim for {cfg.get('min_items', 5)}-{cfg.get('max_items', 10)} items, at least half of them DATED if such events exist.
- Write in English.

Return ONLY a JSON object, no code fences, with this shape:
{{"items": [{{
  "name": "...",
  "date": "YYYY-MM-DD" or null,
  "time": "HH:MM" or "HH:MM-HH:MM" or null,
  "location": "venue, street, town",
  "why": "one sentence why it fits",
  "url": "https://...",
  "registration": "required" | "recommended" | "not required" | "unknown",
  "cost": "short text or unknown"
}}]}}"""


def extract_json(text):
    """Parse model output as JSON, tolerating code fences and text around the object."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in model output")
    return json.JSONDecoder().raw_decode(text[start:])[0]


def call_gemini(prompt, model_name, api_key):
    """Call Gemini with Google Search grounding. Returns (data, sources)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    search = types.Tool(google_search=types.GoogleSearch())

    configs = [
        # Gemini 3 accepts JSON mode together with built-in tools ...
        types.GenerateContentConfig(tools=[search], response_mime_type="application/json"),
        # ... older models reject that combination, so retry with plain text.
        types.GenerateContentConfig(tools=[search]),
    ]
    models = [model_name] + ([FALLBACK_MODEL] if model_name != FALLBACK_MODEL else [])

    last_error = None
    for model in models:
        for config in configs:
            try:
                print(f"INFO: calling {model} (json_mode={config.response_mime_type is not None})")
                response = client.models.generate_content(model=model, contents=prompt, config=config)
                data = extract_json(response.text)
                return data, grounding_sources(response), model
            except Exception as e:  # noqa: BLE001 - try next variant, report at the end
                print(f"WARN: {model} failed: {type(e).__name__}: {str(e)[:300]}")
                last_error = e
    raise RuntimeError(f"all model calls failed, last error: {last_error}")


def grounding_sources(response):
    """Web sources Google Search returned for this answer (title + uri)."""
    sources, seen = [], set()
    try:
        meta = response.candidates[0].grounding_metadata
        for chunk in (meta.grounding_chunks or []) if meta else []:
            web = getattr(chunk, "web", None)
            if web and web.uri and web.uri not in seen:
                seen.add(web.uri)
                sources.append({"title": web.title or web.domain or web.uri, "uri": web.uri})
    except (AttributeError, IndexError, TypeError):
        pass
    return sources


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def check_link(url, timeout=12):
    """'ok', 'blocked' (site refuses bots, can't tell) or 'broken'."""
    if not url or not str(url).startswith(("http://", "https://")):
        return "broken"
    headers = {"User-Agent": "Mozilla/5.0 (weekplan link check)"}
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return "ok" if r.status < 400 else "broken"
    except urllib.error.HTTPError as e:
        return "blocked" if e.code in (401, 403, 405, 429) else "broken"
    except Exception:  # noqa: BLE001 - DNS errors, timeouts, TLS ...
        return "broken"


def clean_items(raw_items, monday, link_checker=check_link):
    """Split into dated (inside the week) and anytime items; drop out-of-week dates."""
    sunday = monday + dt.timedelta(days=6)
    dated, anytime, dropped = [], [], []
    for it in raw_items:
        if not isinstance(it, dict) or not it.get("name"):
            continue
        d = it.get("date")
        if d in (None, "", "null", "unknown"):
            it["date"] = None
            it["time"] = None
            target = anytime
        else:
            try:
                day = dt.date.fromisoformat(str(d)[:10])
            except ValueError:
                dropped.append((it["name"], f"bad date {d!r}"))
                continue
            if not monday <= day <= sunday:
                dropped.append((it["name"], f"date {day} outside the week"))
                continue
            it["date"] = day
            target = dated
        it["link_status"] = link_checker(it.get("url"))
        target.append(it)
    dated.sort(key=lambda x: (x["date"], str(x.get("time") or "")))
    for name, why in dropped:
        print(f"INFO: dropped '{name}': {why}")
    return dated, anytime


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
LINK_NOTE = {
    "ok": "",
    "blocked": "link not checkable (site blocks automated checks)",
    "broken": "LINK BROKEN - search for the event by name",
}


def fmt_day(d):
    return f"{WEEKDAYS[d.weekday()]} {d.strftime('%d.%m.')}"


def render_md(kind, monday, header_line, dated, anytime, sources, generated):
    sunday = monday + dt.timedelta(days=6)
    out = [
        f"# {kind} week: {monday.strftime('%d.%m.')} - {sunday.strftime('%d.%m.%Y')}",
        "",
        header_line,
        "",
    ]

    def item_md(it):
        lines = [f"- **{it['name']}**"]
        if it.get("date"):
            lines.append(f"  - When: {fmt_day(it['date'])}, {it.get('time') or 'time unknown'}")
        lines += [
            f"  - Where: {it.get('location') or 'unknown'}",
            f"  - Why: {it.get('why') or ''}",
            f"  - Registration: {it.get('registration') or 'unknown'} | Cost: {it.get('cost') or 'unknown'}",
            f"  - Link: {it.get('url') or 'none'}",
        ]
        note = LINK_NOTE.get(it.get("link_status"), "")
        if note:
            lines.append(f"  - Note: {note}")
        return "\n".join(lines)

    out.append("## Dated events")
    out.append("")
    out += [item_md(i) for i in dated] or ["No dated events found for this week."]
    out += ["", "## Anytime options", ""]
    out += [item_md(i) for i in anytime] or ["None."]
    if sources:
        out += ["", "## Sources searched", ""]
        out += [f"- [{s['title']}]({s['uri']})" for s in sources]
    out += ["", f"_Generated {generated}. Check details with the organiser before going._", ""]
    return "\n".join(out)


def render_html(kind, monday, header_line, dated, anytime, sources, generated):
    e = lambda s: html.escape(str(s or ""))  # noqa: E731
    sunday = monday + dt.timedelta(days=6)

    def card(it):
        when = (
            f"<div class='when'>{e(fmt_day(it['date']))} · {e(it.get('time') or 'time unknown')}</div>"
            if it.get("date")
            else ""
        )
        url = it.get("url") or ""
        link = f"<a href='{e(url)}' rel='noopener'>{e(url)}</a>" if url else "no link"
        note = LINK_NOTE.get(it.get("link_status"), "")
        note_html = f"<div class='warn {e(it.get('link_status'))}'>{e(note)}</div>" if note else ""
        return f"""<li class="card">
  {when}<div class="name">{e(it['name'])}</div>
  <div>{e(it.get('location') or 'unknown')}</div>
  <div class="why">{e(it.get('why'))}</div>
  <div class="meta">Registration: {e(it.get('registration') or 'unknown')} · Cost: {e(it.get('cost') or 'unknown')}</div>
  <div class="link">{link}</div>{note_html}
</li>"""

    dated_html = "\n".join(card(i) for i in dated) or "<li>No dated events found for this week.</li>"
    any_html = "\n".join(card(i) for i in anytime) or "<li>None.</li>"
    src_html = ""
    if sources:
        src_html = "<h2>Sources searched</h2><ul class='src'>" + "".join(
            f"<li><a href='{e(s['uri'])}' rel='noopener'>{e(s['title'])}</a></li>" for s in sources
        ) + "</ul>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{kind} week {monday.strftime('%d.%m.')} - {sunday.strftime('%d.%m.%Y')}</title>
<style>
  :root {{ --bg:#fafafa; --fg:#222; --muted:#666; --card:#fff; --line:#e3e3e3; --accent:{'#1f7a4d' if kind == 'KIDS' else '#2b5c9e'}; --warn:#9a5b00; --bad:#b00020; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#16181b; --fg:#e8e8e8; --muted:#a0a0a0; --card:#202327; --line:#33373c; --warn:#e0a54a; --bad:#ff6b7f; }} }}
  body {{ font-family: system-ui, sans-serif; background:var(--bg); color:var(--fg); margin:0 auto; max-width:760px; padding:16px; line-height:1.5; }}
  h1 {{ margin:8px 0 4px; }} h1 span {{ color:var(--accent); }}
  .sub {{ color:var(--muted); margin:0 0 16px; }}
  h2 {{ border-bottom:1px solid var(--line); padding-bottom:4px; margin-top:28px; }}
  ul {{ list-style:none; padding:0; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-left:4px solid var(--accent); border-radius:6px; padding:10px 14px; margin:10px 0; }}
  .when {{ font-weight:600; color:var(--accent); }} .name {{ font-weight:700; font-size:1.05em; }}
  .why {{ margin:4px 0; }} .meta {{ color:var(--muted); font-size:.92em; }}
  .link a {{ word-break:break-all; font-size:.92em; }}
  .warn {{ color:var(--warn); font-size:.9em; }} .warn.broken {{ color:var(--bad); font-weight:600; }}
  .src li {{ font-size:.9em; }} footer {{ color:var(--muted); font-size:.85em; margin-top:28px; }}
</style>
</head>
<body>
<h1><span>{kind}</span> week · {monday.strftime('%d.%m.')} - {sunday.strftime('%d.%m.%Y')}</h1>
<p class="sub">{e(header_line)}</p>
<h2>Dated events</h2>
<ul>
{dated_html}
</ul>
<h2>Anytime options</h2>
<ul>
{any_html}
</ul>
{src_html}
<footer>Generated {e(generated)}. Check details with the organiser before going.</footer>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
def main():
    cfg = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))

    provider = (os.environ.get("AI_PROVIDER") or "gemini").strip().lower()
    if provider != "gemini":
        print(f"ERROR: AI_PROVIDER={provider!r} is not supported; only 'gemini' is implemented.")
        sys.exit(1)
    api_key = os.environ.get("AI_API_KEY")
    if not api_key:
        print("ERROR: AI_API_KEY not set.")
        sys.exit(1)
    model_name = os.environ.get("GEMINI_MODEL") or FALLBACK_MODEL

    today = dt.date.fromisoformat(os.environ["PLAN_DATE"]) if os.environ.get("PLAN_DATE") else dt.date.today()
    monday = upcoming_monday(today)
    kind = week_type(monday, dt.date.fromisoformat(str(cfg["kids_week_reference"])))
    ages = sorted(child_age(c, monday) for c in cfg.get("children", []))
    print(f"INFO: planning {monday} ({kind}), ages {ages}")

    data, sources, used_model = call_gemini(build_prompt(cfg, monday, kind, ages), model_name, api_key)
    dated, anytime = clean_items(data.get("items", []), monday)
    if not dated and not anytime:
        print("ERROR: no usable items, keeping the previous plan.")
        sys.exit(1)

    header = (
        f"Planned for {' and '.join(str(a) for a in ages)}-year-olds." if kind == "KIDS" else "Social events for meeting new people."
    ) + f" {len(dated)} dated events, {len(anytime)} anytime options."
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + f" with {used_model} + Google Search"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.md").write_text(render_md(kind, monday, header, dated, anytime, sources, generated), encoding="utf-8")
    (OUT_DIR / "index.html").write_text(render_html(kind, monday, header, dated, anytime, sources, generated), encoding="utf-8")
    print(f"INFO: wrote index.md/index.html ({len(dated)} dated, {len(anytime)} anytime, {len(sources)} sources)")


if __name__ == "__main__":
    main()
