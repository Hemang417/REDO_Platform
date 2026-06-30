"""
Builds the structured project brief passed to Claude.

Single responsibility: format ScoredProject + DeveloperProfile into a
deterministic, human-readable text block. No API calls, no I/O.

Design principle: the brief reads like a memo from an analyst to another analyst —
structured sections with labelled fields so Claude cannot confuse data with inference.
"""

from __future__ import annotations

from typing import Optional

from src.models.developer_profile import DeveloperProfile
from src.models.scored_project import ScoredProject

_FACTOR_LABELS = {
    "construction_progress": "Construction Progress",
    "delay_severity": "Delay Severity",
    "extension_history": "Extension History",
    "project_viability": "Project Viability",
    "location": "Location",
}

_NA = "null (data gap)"


def _fmt(value, fmt: str = "", suffix: str = "") -> str:
    """Format a value for the brief; return _NA if None."""
    if value is None:
        return _NA
    if fmt:
        return format(value, fmt) + suffix
    return str(value) + suffix


def build_project_brief(
    project: ScoredProject,
    developer: Optional[DeveloperProfile],
) -> str:
    """Produce a structured text brief for Claude to reason over.

    Args:
        project:   The scored project to assess.
        developer: The developer's aggregated profile, or None if unavailable.

    Returns:
        Multi-line string formatted as a structured investment brief.
    """
    lines: list[str] = []

    # ------------------------------------------------------------------ Header
    lines += [
        "PROJECT BRIEF",
        "=" * 60,
        f"Registration Number : {project.registration_number}",
        f"Project Name        : {project.project_name or _NA}",
        f"Developer           : {project.developer_name or _NA}",
        f"District            : {project.district or _NA} ({project.location_tier.upper()})",
        f"Project Type        : {_fmt(project.project_type)}",
        "",
    ]

    # ------------------------------------------------------------------ Status
    lines += [
        "REGULATORY STATUS",
        "-" * 40,
        f"Current Status      : {_fmt(project.current_status)}",
        f"Is Lapsed           : {_fmt(project.is_lapsed)}",
        f"Is Deregistered     : {_fmt(project.is_deregistered)}",
        f"Is In Abeyance      : {_fmt(project.is_abeyance)}",
        "",
        "LITIGATION / LEGAL",
        "-" * 40,
        f"MAHARERA Litigation Present : {_fmt(project.is_litigation_present)}",
        f"Litigation Declared         : {_fmt(project.is_litigation_declared)}",
        f"MAHARERA Complaint Count    : {_fmt(project.complaint_count)}",
        f"Criminal Cases vs Promoter  : {_fmt(project.is_criminal_cases)}",
        "(Note: NCLT/IBC tribunal filings are not captured in MAHARERA data.)",
        "",
    ]

    # ------------------------------------------------------------------ Progress
    lines += [
        "CONSTRUCTION & TIMELINE",
        "-" * 40,
        f"Construction Progress    : {_fmt(project.construction_progress_pct, '.1f', '%')}",
        f"Proposed Completion Date : {_fmt(project.proposed_completion_date)}",
        f"Original Completion Date : {_fmt(project.original_completion_date)}",
        f"Delay (days)             : {_fmt(project.delay_days)}",
        f"Is Delayed               : {_fmt(project.is_delayed)}",
        f"Extension Count          : {project.extension_count}",
        f"Registration Date        : {_fmt(project.registration_date)}",
        "",
    ]

    # ------------------------------------------------------------------ Scores
    lines += [
        "OPPORTUNITY SCORE BREAKDOWN",
        "-" * 40,
        f"Overall Opportunity Score : {project.opportunity_score:.1f} / 100",
        "Factor Scores (0.0 – 1.0):",
    ]
    for factor_key, label in _FACTOR_LABELS.items():
        score = project.factor_scores.get(factor_key)
        lines.append(f"  {label:<25}: {_fmt(score, '.4f')}")
    lines.append("")

    # ------------------------------------------------------------------ Developer
    lines += [
        "DEVELOPER TRACK RECORD",
        "-" * 40,
    ]
    if developer is None:
        lines.append("  No developer profile available (data gap).")
    else:
        comp_pct = f"{developer.completion_rate * 100:.0f}%" if developer.completion_rate is not None else _NA
        ot_pct = f"{developer.on_time_rate * 100:.0f}%" if developer.on_time_rate is not None else _NA
        lapse_pct = f"{developer.lapse_rate * 100:.0f}%" if developer.lapse_rate is not None else _NA
        lines += [
            f"  Developer Name      : {developer.developer_name}",
            f"  Total Projects      : {developer.total_projects}",
            f"  Completion Rate     : {comp_pct}",
            f"  On-Time Rate        : {ot_pct}",
            f"  Lapse Rate          : {lapse_pct}",
            f"  Avg Delay (days)    : {_fmt(developer.avg_delay_days, '.0f')}",
            f"  Max Delay (days)    : {_fmt(developer.max_delay_days)}",
            f"  Track Record Score  : {_fmt(developer.track_record_score, '.1f')} / 100",
            f"  Primary District    : {_fmt(developer.primary_district)}",
        ]
    lines.append("")

    return "\n".join(lines)
