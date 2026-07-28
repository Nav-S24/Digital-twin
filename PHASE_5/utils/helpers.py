"""
Utility helpers for Phase 5 OBD Diagnostics Intelligence.
"""

from __future__ import annotations

SEVERITY_COLORS = {
    'Critical': '#FF0000',
    'High':     '#FF6600',
    'Medium':   '#FFB300',
    'Low':      '#00AA44',
    'Unknown':  '#808080',
}

TRIP_STATUS_ICONS = {
    'STOP':    '🔴',
    'CAUTION': '🟡',
    'OK':      '🟢',
}


def format_diagnostic_report(diag: dict) -> str:
    """
    Render a diagnostic dict as a human-readable plain-text report.
    Useful for CLI output, logging, or SMS alerts.
    """
    sep = '─' * 60
    codes = ', '.join(diag.get('fault_codes', [])) or 'None'
    icon  = TRIP_STATUS_ICONS.get(diag.get('trip_status', 'OK'), '⚪')

    lines = [
        sep,
        '  VEHICLE HEALTH INTELLIGENCE ENGINE  –  Phase 5 Report',
        sep,
        f"  Fault Codes     : {codes}",
        f"  Overall Severity: {diag.get('severity', 'Unknown')}",
        f"  Trip Status     : {icon}  {diag.get('trip_status', 'OK')}",
        '',
        f"  Failure Probability : {diag.get('failure_probability', 0):.1%}",
        f"  Failure Risk        : {diag.get('failure_risk', 'Low')}",
        f"  Remaining Life      : {diag.get('remaining_life', 'N/A')} cycles  "
            f"({diag.get('remaining_life_pct', 'N/A')}%  –  {diag.get('rul_category', '')})",
        f"  Component Risk      : {diag.get('component_risk', 'Low')}",
        '',
        '  DRIVER ADVICE',
        f"  {diag.get('driver_advice', '')}",
        '',
        '  MAINTENANCE ACTIONS',
    ]

    for i, action in enumerate(diag.get('maintenance_actions', []), 1):
        lines.append(f"  {i}. {action}")

    recall = diag.get('nhtsa_recall_check_url')
    if recall:
        lines += ['', f"  NHTSA Recall Check: {recall}"]

    lines.append(sep)
    return '\n'.join(lines)


def kelvin_to_celsius(k: float) -> float:
    return round(k - 273.15, 1)


def celsius_to_kelvin(c: float) -> float:
    return round(c + 273.15, 1)
