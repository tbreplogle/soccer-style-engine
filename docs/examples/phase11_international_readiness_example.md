# Phase 11 International Readiness Example

This is a committed example, not a generated audit.

## Example Finding

If local StatsBomb Open Data contains a competition such as FIFA World Cup, the audit can report:

- competition name
- season
- match count
- whether event files exist
- whether 360 files exist

If local data is missing, the audit should say so clearly and recommend setup rather than failing.

## Why International Projections Need Separate Logic

International teams have sparse schedules, neutral sites, tournament effects, roster volatility, and uneven opponent quality. Country ratings should not be pooled with club league ratings.

## Recommended Next International Phase

Build a dedicated international validation module before producing international score projections. It should include sparse-sample priors, neutral-site flags, opponent-strength normalization, and tournament context.

