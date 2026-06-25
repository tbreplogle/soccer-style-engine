# V1 Limitations

V1 is useful, but it is not magic.

## Not A Betting System

This is not a betting-pick system. It does not provide wagering instructions, staking guidance, or picks.

## Projections Are Not Guarantees

Projection outputs are estimates from available data. They can be wrong. Soccer is noisy, and the model does not know everything a human analyst might know.

## Data Support / Risk Context

Confidence-style fields should be read as Data Support / Risk Context. They are context for review, not certainty.

## Market Gaps

Market gaps are diagnostic comparisons. They are not recommendations.

## Free Proxy Style

Free proxy style is not true tracking or event style. It comes from match-level data such as goals, shots, shots on target, corners, and odds fields where available.

## Current Club Data

Current club data comes from Football-Data-style CSVs. This is useful for a free v1, but it is not a live event feed.

## Historical Event Data

Historical event-style data comes from local StatsBomb Open Data when available. If event, tracking, or 360 fields are missing, the engine should leave them missing.

## International Projections

International projections are sparse and historical unless current international data is supplied. Club and international ratings stay separate.

## Missing Inputs

V1 does not yet include:

- roster or injury modeling
- live xG feeds
- lineup confirmation
- transfer/news ingestion
- full style visuals
- PassSonar
- heat maps
- style fingerprints
- dashboards

