# Design: Weekly Activity List Generation

## Input Format (`activities.yaml`)
We will use YAML to store the weekly activities.

```yaml
week: 2026-W29
activities:
  - category: "Work"
    items:
      - "Project X kickoff"
      - "Team meeting"
  - category: "Personal"
    items:
      - "Gym"
      - "Reading"
```

## HTML Output
The output file will be `index.html`. It should be a clean, styled HTML document.

- Structure:
  - Title: "Weekly Activity Report - [Week]"
  - Sections based on categories.
  - Bulleted list of items.
- Styling: Minimalist, clean CSS in a `<style>` block.
