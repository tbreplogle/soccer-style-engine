# AGENTS.md

## Project rules

This project is a soccer style engine. The goal is to track HOW teams play before making score projections.

Do not make unsupported soccer claims from reputation. Every identity label and projection adjustment must trace back to measurable metrics.

Do not build a frontend or betting dashboard in this phase.

Use conservative, explainable models before black-box ML.

Separate measured evidence from human scouting notes.

Do not fake tracking or 360 data. If data is missing, output nulls and mark the data quality flag.

## Commands

Use Python 3.11+.

Install:
```bash
pip install -r requirements.txt
```

Run tests:
```bash
pytest
```

## Review expectations

Before finishing, summarize:
- files changed
- commands run
- test results
- what is real
- what is synthetic/proxy
- limitations
- next recommended task
