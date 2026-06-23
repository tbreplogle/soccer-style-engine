# Agent Design Notes

## The agent's job

The Team Identity Agent interprets tracked behavior. It is not allowed to make unsupported predictions.

Correct use:

- "Morocco profiles as a defensive low block because its block height is low, possession is low, and xGA allowed is strong."
- "Brazil profiles as fast/vertical because direct speed, fast attacks, and runs behind are high."

Bad use:

- "Brazil is Brazil, so they will win."
- "Morocco is defensive because everyone knows that."

## Architecture

### 1. Style data engine

Turns match-level tracking/event/location fields into ratings:

- control_rating
- verticality_rating
- low_block_rating
- pressing_rating
- movement_width_rating
- off_ball_run_rating
- territory_rating
- defensive_resistance_rating
- tempo_rating

### 2. Team Identity Agent

Reads style ratings and produces:

- primary identity
- evidence
- human notes
- strengths
- watchouts
- best matchup type
- worst matchup type
- recent shift
- guardrail status

### 3. Matchup Intelligence Agent

Compares two team identities and explains:

- style clash
- likely game state
- tempo read
- what is unsupported

## Why deterministic first

A full LLM agent is useful later, but not first.

First we need the agent to be auditable. If the agent says Brazil is fast/vertical, we need to see exactly which metrics caused that. Once that works, an LLM can be added to write cleaner scouting reports, challenge contradictions, and compare human notes to the data.

## Human notes

Human intuition is allowed, but it must be separated from measured data.

Example:

> Human note: Morocco is comfortable giving up possession if the block stays compact.

The system should then check whether tracked data supports this through possession share, block height, opponent box touches allowed, and xGA allowed.

## Next build after Phase 3

Phase 4 should add real data ingestion:

1. StatsBomb Open Data loader for event/location data.
2. Team-match style log builder from real event files.
3. Pitch-zone heat maps as output visuals.
4. Rolling last-5 and last-10 style summaries.
5. Competition/season baselines so ratings are not only relative to a tiny sample.
