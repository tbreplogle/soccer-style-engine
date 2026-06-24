# Phase 18 Viewer Guardrails Example

The viewer includes this guardrail note:

```text
This viewer reads generated outputs only. It does not recompute projections, create betting recommendations, or claim proxy metrics are true event/tracking style.
```

Safety scan behavior:

- `No betting recommendation.` is allowed guardrail language.
- `This is a lock.` creates a warning.
- Warnings are reported; files are not deleted or rewritten.

Deferred work remains deferred: PassSonar, heat maps, style fingerprints, dashboards, and event visuals are not part of Phase 18.

