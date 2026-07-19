import datetime
import os
import sys
import json
import google.generativeai as genai

# Attempt to load .env, but don't fail if it's missing (e.g., in GitHub Actions)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Get API key and model from environment
api_key = os.environ.get("AI_API_KEY")
# Fall back to a default model so a missing GEMINI_MODEL secret doesn't crash the run
model_name = os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash"

print(f"DEBUG: Using model {model_name}")
if not api_key:
    print("ERROR: AI_API_KEY not found in environment!")
    sys.exit(1)

# Configure Gemini API
genai.configure(api_key=api_key)
model = genai.GenerativeModel(
    model_name,
    generation_config={"response_mime_type": "application/json"},
)


def extract_json(text):
    """Parse model output as JSON, tolerating ```json ... ``` code fences."""
    text = text.strip()
    if text.startswith("```"):
        # Drop the opening fence line (with optional language tag)
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return json.loads(text)

def get_upcoming_week_info():
    # Get current date
    today = datetime.date.today()
    # Find the Monday of the upcoming week. If today IS Monday (the CI cron
    # runs Mondays at 00:00 UTC), plan the week starting today rather than
    # skipping ahead a full week.
    days_ahead = (7 - today.weekday()) % 7
    next_monday = today + datetime.timedelta(days=days_ahead)
    
    # Get ISO week number
    year, week_num, day_of_week = next_monday.isocalendar()
    
    # Odd = KIDS, Even = SOLO
    week_type = "KIDS" if week_num % 2 != 0 else "SOLO"
    
    return next_monday, week_num, week_type

def generate_activity_files():
    next_monday, week_num, week_type = get_upcoming_week_info()
    
    # Construct prompt
    prompt = f"""
    You are a family assistant for Fernando, living in Erlangen/Nuremberg, Germany.
    It is ISO week {week_num}, which is a {week_type} week.
    The dates are {next_monday.strftime('%Y-%m-%d')} to {(next_monday + datetime.timedelta(days=6)).strftime('%Y-%m-%d')}.
    
    If it is a KIDS week, please plan activities for two boys aged 8 and 11.
    If it is a SOLO week, plan activities for an adult.
    
    Instructions for research and generation:
    1. Research real, current events for the upcoming week for the Erlangen/Nuremberg region (secondarily Fürth).
    2. Specific criteria:
        - KIDS week: Activities suitable for boys aged 8 and 11 (dated events: festivals, museum programs, workshops, sports; anytime options: climbing parks, pools, museums, zoo). Check local family event calendars (frankenkids.de, erlangen.de, nuernberg.de, eventcorner.de).
        - SOLO week: Social events for meeting new people (Meetup.com, Stammtisch, internationals/expat meetups, language cafés, new-in-town events).
    3. Important: EXCLUDE any religious events.
    4. Output: Produce a concise, well-organized list (5–10 items) ordered by day of the week, each with:
       - event/activity name
       - date and time
       - location
       - why it's a good fit
       - a link
       - flag if advance registration/tickets required.
    5. At the top, state clearly which kind of week it is (SOLO or KIDS) and the date range.
    6. Language: Keep everything in English.
    7. Verify dates carefully — only include events actually happening in the upcoming week, preferring official/primary sources.
    
    Generate the activity plan in a valid JSON format with two fields: "markdown" and "html".
    "markdown": The plan in Markdown format (use # for title, a line for date range, ## for categories, UL/LI lists for activities).
    "html": The plan as an HTML fragment (use <h1>, <p>, <h2>, <ul>/<li>).
    
    Ensure the JSON is strictly valid. Do not include markdown formatting like ```json ... ```.
    """
    
    try:
        print("DEBUG: Calling Gemini API...")
        response = model.generate_content(prompt)
        print("DEBUG: API call successful.")
    except Exception as e:
        print(f"ERROR: API call failed: {e}")
        sys.exit(1)

    try:
        # Parse JSON (tolerates accidental ```json fences)
        content_json = extract_json(response.text)
        activity_md = content_json["markdown"]
        activity_html_body = content_json["html"]

        print(f"DEBUG: Generated content length: {len(activity_md)}")
    except Exception as e:
        print(f"ERROR: Parsing model output failed: {e}")
        # Use repr() to ensure the output is safe and escaped
        print(f"DEBUG: Raw model output (first 500 chars): {repr(response.text[:500])}")
        sys.exit(1)
    
    # Write Markdown
    with open('index.md', 'w', encoding='utf-8') as f:
        f.write(activity_md)
    print("DEBUG: Successfully wrote index.md")
    
    # Write HTML
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Activity List for Week {week_num} ({week_type})</title>
    <style>
        body {{ font-family: sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #555; }}
    </style>
</head>
<body>
{activity_html_body}
</body>
</html>
"""
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    print("DEBUG: Successfully wrote index.html")

if __name__ == "__main__":
    generate_activity_files()
