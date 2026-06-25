# Phase 22 Source Priority Update Example

World Cup source priority:

1. OpenFootball World Cup fixture cache.
2. TheStatsAPI World Cup fixture cache.
3. SofaScore current international adapter when safely available.
4. EloRatings strength prior cache.
5. ESPN scoreboard fallback.
6. FBref aggregate fallback.
7. Manual fallback.
8. Historical StatsBomb Open Data only as historical context, never current data.

This order keeps fixture availability separate from true event or tracking data.

