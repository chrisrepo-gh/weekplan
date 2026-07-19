# Project Memory: Weekplan

## Summary
The goal of this project is to automate the generation of a weekly activity report for a family in the Erlangen/Nuremberg area, switching from a static implementation to an AI-powered one.

## Core Logic
- `generate.py`: The main script that calculates the ISO week number and determines if it's a "KIDS" or "SOLO" week.
- AI Integration: Uses the Gemini API (`gemini-3.1-flash`) via the `google-generativeai` Python library to generate structured HTML content for the activities based on the week type.
- Dependencies: `google-generativeai` and `python-dotenv`.

## Configuration
- `.env`: Contains the environment variables `AI_API_KEY` (Gemini API Key) and `GEMINI_MODEL` (e.g., `gemini-3.1-flash`).
- GitHub Secrets: The GitHub Actions workflow relies on repository secrets `AI_API_KEY` and `GEMINI_MODEL` to run successfully in the CI/CD environment.

## Workflow
- `.github/workflows/generate.yml`: A GitHub Actions workflow that runs every Monday via cron, installs dependencies, runs `generate.py`, and commits the updated `index.html` to the repository.
- GitHub Pages: Automatically deploys the updated `index.html` to the live website upon any push to the main branch.

## Preferences
- Language: English
- Model: `gemini-3.1-flash` (or as configured in `.env`/Secrets)
- Output: HTML
