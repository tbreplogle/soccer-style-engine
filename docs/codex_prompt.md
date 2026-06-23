# Codex Build Prompt

You are working on a project called Soccer Style Engine. This is not a generic soccer prediction model. The core goal is to track **how teams play**: possession behavior, field occupation, movement, pace, defensive shape, pressing, runs, and matchup style clashes.

Do not jump straight into betting predictions. Build the foundation correctly.

## Current objective

Implement Phase 3: Team Identity Agent Foundation.

The agent must read measured style metrics and produce a team identity report and matchup intelligence report. It must separate measured evidence from human scouting notes.

## Non-negotiable rules

1. No prediction should be made unless the style reason is explainable.
2. The agent cannot use team reputation as evidence.
3. Human notes are allowed but must be labeled separately from measured evidence.
4. If tracked sample size is small, the agent must say so.
5. If evidence is weak, the agent must not force a confident identity.
6. Keep the system deterministic and auditable before adding LLM calls.

## Files to build or update

- `src/style_features.py`
- `src/evidence.py`
- `src/team_identity_agent.py`
- `src/matchup_agent.py`
- `src/run_phase3.py`
- `data/sample_scouting_notes.csv`
- `tests/test_phase3.py`
- `docs/agent_design.md`

## Expected outputs

When running:

```bash
python src/run_phase3.py
```

Generate:

- `outputs/team_style_summary.csv`
- `outputs/team_identity_agent_report.csv`
- `outputs/team_identity_agent_report.md`
- `outputs/matchup_agent_report.csv`
- `outputs/matchup_agent_report.md`

## Style identities to support

- Defensive Low Block
- Fast / Vertical Run Threat
- Possession + High Press
- Possession Controller
- Aggressive Pressing
- Fast / Vertical
- Off-Ball Runner
- Wide Field Stretcher
- Balanced / Mixed

## Metrics to use

- possession_pct
- field_tilt_pct
- avg_possession_seconds
- passes_per_possession
- central_progression_pct
- direct_speed_mps
- fast_attacks_per90
- progressive_passes_per90
- progressive_carries_per90
- runs_in_behind_per90
- avg_block_height
- ppda
- high_regains_per90
- opponent_box_touches_allowed
- xga_per90
- avg_team_width
- avg_team_depth
- touch_x_mean
- touch_y_spread
- sprints_per90

## Acceptance criteria

- Morocco-style sample should classify as Defensive Low Block.
- Brazil-style sample should classify as Fast / Vertical Run Threat.
- Reports must include measured evidence.
- Reports must include human notes separately.
- Matchup report must say `STYLE READ ONLY - no betting projection until backtest layer exists`.
- Tests must pass with `pytest -q`.
