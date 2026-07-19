import datetime
import os
import sys
import google.generativeai as genai

# Attempt to load .env, but don't fail if it's missing (e.g., in GitHub Actions)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Get API key and model from environment
api_key = os.environ.get("AI_API_KEY")
model_name = os.environ.get("GEMINI_MODEL")

print(f"DEBUG: Using model {model_name}")
if not api_key:
    print("ERROR: AI_API_KEY not found in environment!")
    sys.exit(1)

# Configure Gemini API
genai.configure(api_key=api_key)
model = genai.GenerativeModel(model_name)

def get_upcoming_week_info():
    # Get current date
    today = datetime.date.today()
    # Find the next Monday
    days_ahead = 7 - today.weekday()
    if days_ahead <= 0: # Already Monday or later, get next Monday
        days_ahead += 7
    next_monday = today + datetime.timedelta(days=days_ahead)
    
    # Get ISO week number
    year, week_num, day_of_week = next_monday.isocalendar()
    
    # Odd = KIDS, Even = SOLO
    week_type = "KIDS" if week_num % 2 != 0 else "SOLO"
    
    return next_monday, week_num, week_type

def generate_html():
    next_monday, week_num, week_type = get_upcoming_week_info()
    
    # Construct prompt
    prompt = f"""
    You are a family assistant for Fernando, living in Erlangen/Nuremberg, Germany.
    It is ISO week {week_num}, which is a {week_type} week.
    The dates are {next_monday.strftime('%Y-%m-%d')} to {(next_monday + datetime.timedelta(days=6)).strftime('%Y-%m-%d')}.
    
    If it is a KIDS week, please plan activities for two boys aged 8 and 11.
    If it is a SOLO week, plan activities for an adult.
    
    Generate an HTML-formatted body content for an activity plan.
    Include an H1 title with the week type, a P tag with the date range, and then structured H2 categories with UL/LI lists for activities.
    Make it detailed and engaging.
    """
    
    try:
        print("DEBUG: Calling Gemini API...")
        response = model.generate_content(prompt)
        print("DEBUG: API call successful.")
        activity_html_body = response.text
        print(f"DEBUG: Generated content length: {len(activity_html_body)}")
    except Exception as e:
        print(f"ERROR: API call failed: {e}")
        sys.exit(1)
    
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
    
    with open('index.html', 'w') as f:
        f.write(html_content)
    print("DEBUG: Successfully wrote index.html")

if __name__ == "__main__":
    generate_html()
