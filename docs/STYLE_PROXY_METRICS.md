# Style Proxy Metrics

These metrics are not true tracking or event style. They are free-data proxies from match-level stats.

- `control_proxy`: shot share, corner share, and odds-implied dominance when available.
- `attacking_pressure_proxy`: shots, shots on target, corners, and goals pressure.
- `defensive_shell_proxy`: low shots allowed, low SOT allowed, low goals allowed, and low match volume.
- `tempo_proxy`: total shots, total corners, goals, cards, and fouls.
- `chaos_proxy`: cards, fouls, red cards, goal volatility, and shot volatility.
- `finishing_proxy`: goals per shot and goals per shot on target. This is unstable on small samples.
- `chance_quality_proxy`: SOT rate and goals per shot until real xG is available.
- `directness_proxy`: high pressure output with lower control share. This is a weak proxy.
- `under_profile_proxy`: low total shots, low goals, low SOT allowed, and low tempo.

Every proxy includes a numeric value, percentile, z-score, evidence metrics, reliability label, and warning when sample size or missing columns weaken it.
