# Projection Reporting

Phase 13 adds command-line reporting for projection outputs. It does not add a frontend or betting workflow.

Reports call the existing projection functions and format their outputs. They do not duplicate model logic.

Generated Markdown reports include:

- title
- generation timestamp
- data source
- slate type
- model guardrails
- summary table
- matchup detail sections
- confidence and risk notes
- market/proxy warnings where available

Reports are context documents. They are not betting recommendations.

