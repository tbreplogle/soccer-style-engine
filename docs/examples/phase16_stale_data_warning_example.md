# Phase 16 Stale Data Warning Example

Example only.

```text
Run status: success_with_warnings
Data currentness status: stale
Currentness policy: warn

Do not trust this slate until stale/unsafe data warnings are resolved.
```

Under `warn`, stale data is allowed through with loud warnings. Under `fail-on-stale`, the run should stop and write a partial manifest/log.
