import datetime

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
    
    # For now, simulate research results based on week type
    # This could be extended to perform actual scraping
    if week_type == "KIDS":
        activities = [
            {"category": "Museums", "items": ["Nuremberg Toy Museum", "Erlangen City Museum"]},
            {"category": "Outdoors", "items": ["Climbing Park", "Local Pool"]}
        ]
    else:
        activities = [
            {"category": "Social", "items": ["Meetup: Expat Drinks", "Stammtisch Erlangen"]},
            {"category": "Culture", "items": ["Language Café"]}
        ]

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
    <h1>Activity List for Week {week_num} ({week_type})</h1>
    <p>Date Range: {next_monday.strftime('%Y-%m-%d')} to {(next_monday + datetime.timedelta(days=6)).strftime('%Y-%m-%d')}</p>
"""

    for category in activities:
        html_content += f"    <h2>{category['category']}</h2>\n    <ul>\n"
        for item in category['items']:
            html_content += f"        <li>{item}</li>\n"
        html_content += "    </ul>\n"

    html_content += "</body>\n</html>"

    with open('index.html', 'w') as f:
        f.write(html_content)

if __name__ == "__main__":
    generate_html()
