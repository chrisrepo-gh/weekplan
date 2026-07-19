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
        print(f"ERROR