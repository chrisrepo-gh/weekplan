# Project Memory: Weekplan

## Summary
Automated weekly activity plan for Fernando in the Erlangen/Nuremberg area. Alternating weeks:
KIDS weeks (activities with his two boys) and SOLO weeks (social events to meet new people).
Published via GitHub Pages from `index.html`.

## Core logic (`generate.py`)
- Plans the week starting the next Monday (Sunday run -> tomorrow; Monday run -> today).
- KIDS/SOLO comes from a fixed reference Monday in `weekplan.yaml` and a strict 14-day rhythm
  (not ISO-week parity, which breaks in 53-week years such as 2026).
- Children's ages are computed from `weekplan.yaml` (`age` + `age_as_of`, or exact `born: YYYY-MM`).
- Gemini is called through the `google-genai` SDK with Google Search grounding, and returns
  structured JSON items (name, date/null, time, location, why, url, registration, cost).
- Python then: drops dated items outside the week, checks every link (ok / blocked / broken),
  separates dated events from anytime options, and renders `index.md` + `index.html` itself.
- On any failure the script exits non-zero and leaves the previous plan untouched.
- Model: `GEMINI_MODEL` (env / GitHub secret); falls back to `gemini-flash-latest`.
  Tries JSON mode + search first, then plain text + search (older models reject the combination).

## Configuration
- `weekplan.yaml`: location, KIDS reference Monday, children, search focus per week type, exclusions.
- `.env` (local only, not committed): `AI_PROVIDER=gemini`, `AI_API_KEY`, `GEMINI_MODEL`.
- GitHub secrets: `AI_API_KEY`, `GEMINI_MODEL`.
- `PLAN_DATE=YYYY-MM-DD` (optional env) simulates the run date; `OUT_DIR` redirects output for tests.

## Workflow
- `.github/workflows/generate.yml`: Sundays 06:00 UTC + manual trigger; installs
  `requirements.txt`, runs `generate.py`, commits `index.html`/`index.md` if changed.
- `bike-tour/`: separate, hand-made trip page; not touched by the generator.

## Preferences
- Language of the plan: English. No religious events.
