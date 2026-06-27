from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


AUDIT_TARGETS = [
    {
        "path": "src/international_current/rating_projection.py",
        "module": "src.international_current.rating_projection",
        "formula_area": "current international rating baseline xG",
        "logic_type": "production",
    },
    {
        "path": "src/analysis/baseline_tuning.py",
        "module": "src.analysis.baseline_tuning",
        "formula_area": "diagnostic baseline tuning xG",
        "logic_type": "diagnostic",
    },
    {
        "path": "src/models/international_projection.py",
        "module": "src.models.international_projection",
        "formula_area": "historical international projection xG",
        "logic_type": "production",
    },
    {
        "path": "src/models/baseline_strength.py",
        "module": "src.models.baseline_strength",
        "formula_area": "club baseline expected goals",
        "logic_type": "production",
    },
]


def _classify_line(line: str, logic_type: str) -> tuple[str, str, str]:
    text = line.strip()
    lower = text.lower()
    if "xg_safety_guard" in lower or "broad sanity guard" in lower or "0.05" in lower and "5.0" in lower:
        return "broad safety guard", "keep_extreme_safety_guard", "Broad non-negative/absurd-value protection is acceptable when reported."
    if logic_type == "diagnostic" and "underdog_xg_floor" in lower:
        return "diagnostic underdog floor candidate", "no_action", "Candidate parameter only; includes zero/no-floor candidates."
    if logic_type == "diagnostic" and any(token in lower for token in ["min(", "max(", "tanh", "scoreline_dispersion_multiplier"]):
        return "diagnostic candidate bound", "convert_to_config", "Diagnostic-only bounds should remain explicit candidate parameters."
    if "max(0.15" in lower or "max(0.2" in lower or "max(0.35" in lower:
        return "team xG floor", "convert_to_config", "Production floors can compress or inflate scoreline spread unless only broad safety guards."
    if "min(3.2" in lower or "max(1.6" in lower or "min(350" in lower or "max(-350" in lower:
        return "rating/total hard clamp", "remove_cap", "Hard production clamps can compress favorite/underdog and total spread."
    if "clip(" in lower:
        return "clip", "convert_to_config", "Clip should be documented and configurable if it affects xG."
    if "max(" in lower or "min(" in lower:
        return "min/max guard", "no_action", "General guard; inspect context before changing."
    return "", "no_action", ""


def audit_xg_formula(*, as_of_date: str, output_dir: str | Path = "outputs/calibration") -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for target in AUDIT_TARGETS:
        path = Path(target["path"])
        if not path.exists():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            lower = line.lower()
            if not any(token in lower for token in ["min(", "max(", "clip(", "xg_safety_guard", "baseline_total_goals", "rating_diff_to_goal_scale", "underdog_xg_floor", "favorite_xg_spread_multiplier", "scoreline_dispersion_multiplier"]):
                continue
            found, recommendation, reason = _classify_line(line, str(target["logic_type"]))
            if not found and any(token in lower for token in ["baseline_total_goals", "rating_diff_to_goal_scale", "favorite_xg_spread_multiplier"]):
                found = "configurable parameter"
                recommendation = "no_action"
                reason = "Transparent parameter, not a hidden cap/floor."
            rows.append({
                "file": target["path"],
                "module": target["module"],
                "line": number,
                "formula_area": target["formula_area"],
                "cap_floor_clipping_found": found,
                "value_or_expression": line.strip(),
                "reason_if_documented": reason,
                "logic_type": target["logic_type"],
                "recommendation": recommendation,
            })
    frame = pd.DataFrame(rows, columns=[
        "file",
        "module",
        "line",
        "formula_area",
        "cap_floor_clipping_found",
        "value_or_expression",
        "reason_if_documented",
        "logic_type",
        "recommendation",
    ])
    output = Path(output_dir) / as_of_date / "xg_formula_audit"
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "xg_formula_audit.csv"
    summary_path = output / "xg_formula_audit_summary.md"
    frame.to_csv(csv_path, index=False)
    summary_path.write_text(_summary_markdown(frame, as_of_date), encoding="utf-8")
    return {
        "status": "written",
        "as_of_date": as_of_date,
        "run_dir": output,
        "audit": frame,
        "paths": {
            "xg_formula_audit": str(csv_path),
            "xg_formula_audit_summary": str(summary_path),
        },
        "hard_favorite_caps_exist": bool(frame["value_or_expression"].astype(str).str.contains("1.65|favorite.*min|favorite.*max", case=False, regex=True).any()) if not frame.empty else False,
        "hard_underdog_floors_exist": bool(frame[(frame["logic_type"] == "production") & frame["cap_floor_clipping_found"].astype(str).str.contains("floor", case=False, na=False)].shape[0]) if not frame.empty else False,
    }


def _summary_markdown(frame: pd.DataFrame, as_of_date: str) -> str:
    counts = frame["recommendation"].value_counts().to_dict() if not frame.empty else {}
    production = frame[frame["logic_type"].eq("production")] if not frame.empty else pd.DataFrame()
    hard_favorite = bool(frame["value_or_expression"].astype(str).str.contains("1.65|favorite.*min|favorite.*max", case=False, regex=True).any()) if not frame.empty else False
    hard_underdog = bool(production["cap_floor_clipping_found"].astype(str).str.contains("floor", case=False, na=False).any()) if not production.empty else False
    lines = [
        "# xG Formula Audit",
        "",
        f"- As-of date: `{as_of_date}`",
        f"- Generated at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Rows audited: `{len(frame)}`",
        f"- Hard favorite xG caps found: `{hard_favorite}`",
        f"- Hard production underdog xG floors found: `{hard_underdog}`",
        "",
        "## Recommendation Counts",
        "",
        *[f"- `{key}`: `{value}`" for key, value in counts.items()],
        "",
        "## Notes",
        "",
        "- Current rating baseline production logic now uses broad reported xG safety guards instead of hidden 1.65-style favorite caps or 0.35-style underdog floors.",
        "- Diagnostic tuning can test candidate floors, including zero/no-floor settings, but those are not production defaults.",
        "- No current StatsBomb live data is used and no betting recommendations are produced.",
    ]
    return "\n".join(lines)


def format_xg_audit_terminal(result: dict[str, Any]) -> str:
    frame = result["audit"]
    counts = frame["recommendation"].value_counts().to_dict() if not frame.empty else {}
    return "\n".join([
        "xG Formula Audit",
        f"Status: {result['status']}",
        f"Rows: {len(frame)}",
        f"Hard favorite caps exist: {result['hard_favorite_caps_exist']}",
        f"Hard production underdog floors exist: {result['hard_underdog_floors_exist']}",
        f"Recommendation counts: {counts}",
        f"Summary: {result['paths']['xg_formula_audit_summary']}",
        f"CSV: {result['paths']['xg_formula_audit']}",
    ])

