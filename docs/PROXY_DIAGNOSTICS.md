# Proxy Diagnostics

Phase 8 exists because the first real Football-Data smoke test showed the free proxy layer slightly hurt performance. Proxy explanations can still be useful, but score adjustments must earn their place in real backtests.

## What Diagnostics Test

The diagnostics runner compares:

- baseline-only model
- all proxy groups enabled
- each proxy group enabled individually
- each proxy group disabled individually
- several total adjustment caps: `0`, `0.03`, `0.05`, `0.08`, `0.12`, `0.20`

Proxy groups remain `free_proxy_style` only. They do not represent true event/tracking style.

## Interpreting Lift

Positive lift means the tested proxy configuration reduced total-goals MAE versus baseline. Negative lift means it made the total-goals estimate worse. Near-zero lift should be treated as neutral and not enough to justify default score adjustments.

## Recommendations

- `disable_proxy_adjustments`: proxy adjustments are negative or near zero across most windows.
- `use_proxy_adjustments_low_cap`: only one or two groups help consistently at a low cap.
- `use_proxy_adjustments_context_only`: proxy results are unstable; keep explanations but avoid score movement.
- `needs_more_data`: not enough matches to judge.

The default current projection now keeps proxy score adjustments disabled unless explicitly enabled. Proxy explanations remain visible.
