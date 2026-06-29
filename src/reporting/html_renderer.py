"""
Renders a ReportData object to a self-contained HTML string.

Uses only Python stdlib (html.escape, string formatting).
No Jinja2, no external CSS frameworks, no JavaScript.
The output is print-friendly: browser File → Print → Save as PDF produces
a clean investment committee brief.
"""

from __future__ import annotations

import html
from typing import Optional

from src.reporting.report_builder import DealRecord, ReportData


# ---------------------------------------------------------------------------
# CSS — embedded inline so the HTML file is fully self-contained
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: #1a1a2e;
    background: #f8f9fa;
    padding: 0;
}
.page {
    max-width: 960px;
    margin: 0 auto;
    background: #fff;
    padding: 48px 56px;
}
/* Cover */
.cover { border-bottom: 3px solid #1a1a2e; padding-bottom: 28px; margin-bottom: 36px; }
.cover h1 { font-size: 26px; font-weight: 700; letter-spacing: -0.5px; color: #1a1a2e; }
.cover .subtitle { font-size: 13px; color: #555; margin-top: 6px; }
.cover .meta { display: flex; gap: 32px; margin-top: 20px; flex-wrap: wrap; }
.cover .meta-item { }
.cover .meta-item .label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.8px; color: #888; }
.cover .meta-item .value { font-size: 14px; font-weight: 600; color: #1a1a2e; margin-top: 2px; }
/* Section headings */
h2 {
    font-size: 15px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.6px; color: #1a1a2e;
    border-bottom: 1px solid #e0e0e0; padding-bottom: 8px;
    margin: 36px 0 18px;
}
h3 { font-size: 13px; font-weight: 700; color: #1a1a2e; margin: 0 0 4px; }
/* Summary grid */
.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 28px; }
.stat-box {
    border: 1px solid #e0e0e0; border-radius: 6px;
    padding: 14px 16px; background: #fafafa;
}
.stat-box .stat-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.7px; color: #777; }
.stat-box .stat-value { font-size: 22px; font-weight: 700; color: #1a1a2e; margin-top: 4px; line-height: 1; }
.stat-box .stat-sub { font-size: 11px; color: #888; margin-top: 4px; }
/* Score bar */
.score-bar-wrap { margin: 12px 0 24px; }
.score-bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.score-bar-label { width: 60px; font-size: 11px; color: #555; text-align: right; flex-shrink: 0; }
.score-bar-track { flex: 1; background: #efefef; border-radius: 3px; height: 16px; }
.score-bar-fill { height: 16px; border-radius: 3px; background: #1a1a2e; }
.score-bar-count { width: 28px; font-size: 11px; color: #333; text-align: right; flex-shrink: 0; }
/* Action badge */
.badge {
    display: inline-block; font-size: 10px; font-weight: 700;
    letter-spacing: 0.5px; padding: 2px 7px; border-radius: 3px;
    text-transform: uppercase; vertical-align: middle;
}
.badge-flag { background: #fff3cd; color: #856404; border: 1px solid #ffc107; }
.badge-monitor { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
.badge-pass { background: #e2e3e5; color: #383d41; border: 1px solid #ccc; }
/* Deal card */
.deal-card {
    border: 1px solid #e0e0e0; border-radius: 6px;
    padding: 20px 22px; margin-bottom: 18px;
    page-break-inside: avoid;
}
.deal-card-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.deal-card-title { }
.deal-card-title h3 { font-size: 14px; }
.deal-card-title .reg { font-size: 11px; color: #777; margin-top: 2px; }
.deal-card-scores { display: flex; gap: 20px; flex-shrink: 0; }
.score-pill { text-align: right; }
.score-pill .sp-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: #888; }
.score-pill .sp-value { font-size: 20px; font-weight: 700; color: #1a1a2e; }
.score-pill .sp-sub { font-size: 10px; color: #aaa; }
.deal-section { margin-top: 14px; }
.deal-section-label {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.7px; color: #888; margin-bottom: 5px;
}
.deal-thesis { font-size: 12px; line-height: 1.6; color: #333; }
.risk-list { list-style: none; padding: 0; }
.risk-list li { font-size: 12px; color: #333; padding: 2px 0 2px 14px; position: relative; line-height: 1.5; }
.risk-list li::before { content: "!"; position: absolute; left: 0; color: #dc3545; font-weight: 700; font-size: 11px; }
.gap-list { list-style: none; padding: 0; }
.gap-list li { font-size: 11px; color: #888; padding: 2px 0 2px 14px; position: relative; }
.gap-list li::before { content: "?"; position: absolute; left: 0; color: #aaa; font-weight: 700; }
/* Metrics row inside deal card */
.metrics-row { display: flex; gap: 24px; flex-wrap: wrap; margin-top: 12px; padding-top: 12px; border-top: 1px solid #f0f0f0; }
.metric-item .m-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: #999; }
.metric-item .m-value { font-size: 13px; font-weight: 600; color: #1a1a2e; margin-top: 1px; }
/* Factor score mini-bar */
.factor-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
.factor-table td { padding: 3px 6px; font-size: 11px; vertical-align: middle; }
.factor-table td:first-child { width: 160px; color: #555; }
.factor-track { width: 120px; background: #efefef; border-radius: 2px; height: 8px; }
.factor-fill { height: 8px; border-radius: 2px; background: #1a1a2e; }
/* Watchlist table */
.data-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.data-table th {
    background: #f5f5f5; font-size: 10px; text-transform: uppercase;
    letter-spacing: 0.5px; color: #666; padding: 8px 10px;
    border-bottom: 2px solid #e0e0e0; text-align: left; font-weight: 600;
}
.data-table td { padding: 8px 10px; border-bottom: 1px solid #f0f0f0; color: #333; }
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: #fafafa; }
/* Developer league */
.dev-rank { font-weight: 700; color: #1a1a2e; width: 28px; }
.track-bar-wrap { width: 100px; }
.track-fill { height: 8px; border-radius: 2px; background: #1a1a2e; }
/* Methodology */
.method-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 12px; }
.method-item { font-size: 12px; display: flex; justify-content: space-between; padding: 6px 10px; background: #f5f5f5; border-radius: 4px; }
.method-key { color: #555; text-transform: capitalize; }
.method-val { font-weight: 600; color: #1a1a2e; }
/* Footer */
.footer { margin-top: 48px; padding-top: 16px; border-top: 1px solid #e0e0e0; font-size: 11px; color: #aaa; }
/* Print */
@media print {
    body { background: #fff; }
    .page { padding: 24px 32px; }
    .deal-card { page-break-inside: avoid; }
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _e(text) -> str:
    """HTML-escape a value, converting None to empty string."""
    if text is None:
        return ""
    return html.escape(str(text))


def _fmt_score(score: Optional[float], decimals: int = 1) -> str:
    if score is None:
        return "N/A"
    return f"{score:.{decimals}f}"


def _fmt_int(value: Optional[int]) -> str:
    if value is None:
        return "N/A"
    return str(value)


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


def _badge(action: str) -> str:
    cls = {"FLAG_FOR_REVIEW": "badge-flag", "MONITOR": "badge-monitor", "PASS": "badge-pass"}.get(action, "badge-pass")
    label = action.replace("_", " ")
    return f'<span class="badge {_e(cls)}">{_e(label)}</span>'


def _score_bar_row(label: str, count: int, max_count: int) -> str:
    pct = int(count / max_count * 100) if max_count > 0 else 0
    return (
        f'<div class="score-bar-row">'
        f'<span class="score-bar-label">{_e(label)}</span>'
        f'<div class="score-bar-track"><div class="score-bar-fill" style="width:{pct}%"></div></div>'
        f'<span class="score-bar-count">{count}</span>'
        f'</div>'
    )


def _factor_row(name: str, score: float) -> str:
    pct = int(score * 100)
    label = name.replace("_", " ").title()
    return (
        f'<tr>'
        f'<td>{_e(label)}</td>'
        f'<td><div class="factor-track"><div class="factor-fill" style="width:{pct}%"></div></div></td>'
        f'<td style="color:#555">{score:.2f}</td>'
        f'</tr>'
    )


def _risk_flags_html(flags) -> str:
    if not flags:
        return '<p style="font-size:12px;color:#aaa">No risk flags identified.</p>'
    # flags may arrive as list[str] or a single pipe-separated string (CSV round-trip)
    if isinstance(flags, str):
        items = [f.strip() for f in flags.split("|") if f.strip()]
    else:
        items = [str(f) for f in flags if f]
    if not items:
        return '<p style="font-size:12px;color:#aaa">No risk flags identified.</p>'
    lis = "".join(f"<li>{_e(item)}</li>" for item in items)
    return f'<ul class="risk-list">{lis}</ul>'


def _data_gaps_html(gaps) -> str:
    if not gaps:
        return '<span style="font-size:11px;color:#aaa">None — all key fields present.</span>'
    if isinstance(gaps, str):
        items = [g.strip() for g in gaps.split("|") if g.strip()]
    else:
        items = [str(g) for g in gaps if g]
    if not items:
        return '<span style="font-size:11px;color:#aaa">None — all key fields present.</span>'
    lis = "".join(f"<li>{_e(item)}</li>" for item in items)
    return f'<ul class="gap-list">{lis}</ul>'


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_cover(data: ReportData) -> str:
    s = data.summary
    ts = s.data_generated_at.strftime("%d %b %Y, %H:%M UTC")
    models = ", ".join(s.models_used) if s.models_used else "N/A"
    return f"""
<div class="cover">
  <div class="cover-brand" style="font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:#888;margin-bottom:10px">REDO Platform &mdash; Category II AIF</div>
  <h1>Maharashtra Real Estate<br>Deal Origination Report</h1>
  <div class="subtitle">MAHARERA Registered Projects &mdash; Investment Opportunity Assessment</div>
  <div class="meta">
    <div class="meta-item"><div class="label">Generated</div><div class="value">{_e(ts)}</div></div>
    <div class="meta-item"><div class="label">Projects Scored</div><div class="value">{s.total_projects_scored}</div></div>
    <div class="meta-item"><div class="label">Memos Generated</div><div class="value">{s.total_memos_generated}</div></div>
    <div class="meta-item"><div class="label">AI Model</div><div class="value">{_e(models)}</div></div>
    <div class="meta-item"><div class="label">Data Source</div><div class="value">MAHARERA Portal</div></div>
  </div>
</div>
"""


def _render_summary(data: ReportData) -> str:
    s = data.summary
    dist = s.score_distribution.as_dict()
    max_band = max(dist.values(), default=1)
    bar_rows = "".join(_score_bar_row(band, count, max_band) for band, count in dist.items())

    return f"""
<h2>Executive Summary</h2>
<div class="summary-grid">
  <div class="stat-box">
    <div class="stat-label">Flag for Review</div>
    <div class="stat-value" style="color:#856404">{s.flag_for_review_count}</div>
    <div class="stat-sub">Warrants immediate attention</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">Monitor</div>
    <div class="stat-value" style="color:#0c5460">{s.monitor_count}</div>
    <div class="stat-sub">Borderline / data gaps</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">Pass</div>
    <div class="stat-value" style="color:#383d41">{s.pass_count}</div>
    <div class="stat-sub">Low score or lapsed</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">Avg Opportunity Score</div>
    <div class="stat-value">{_fmt_score(s.avg_opportunity_score)}</div>
    <div class="stat-sub">out of 100</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">Top Score</div>
    <div class="stat-value">{_fmt_score(s.max_opportunity_score)}</div>
    <div class="stat-sub">out of 100</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">Top District</div>
    <div class="stat-value" style="font-size:16px">{_e(s.top_district)}</div>
    <div class="stat-sub">by eligible deal count</div>
  </div>
</div>
<div style="margin-bottom:8px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.6px;color:#888">Score Distribution</div>
<div class="score-bar-wrap">{bar_rows}</div>
"""


def _render_deal_card(deal: DealRecord, rank: int) -> str:
    m = deal.memo
    p = deal.project
    dev = deal.developer

    track_html = ""
    if dev and dev.track_record_score is not None:
        ts = dev.track_record_score
        track_html = (
            f'<div class="score-pill">'
            f'<div class="sp-label">Track Record</div>'
            f'<div class="sp-value">{ts:.1f}</div>'
            f'<div class="sp-sub">/ 100</div>'
            f'</div>'
        )

    factor_rows = ""
    if p.factor_scores:
        factor_rows = (
            '<table class="factor-table">'
            + "".join(_factor_row(k, v) for k, v in sorted(p.factor_scores.items()))
            + "</table>"
        )

    dev_stats = ""
    if dev:
        dev_stats = (
            f'<div class="metrics-row">'
            f'<div class="metric-item"><div class="m-label">Developer</div><div class="m-value">{_e(dev.developer_name)}</div></div>'
            f'<div class="metric-item"><div class="m-label">Total Projects</div><div class="m-value">{dev.total_projects}</div></div>'
            f'<div class="metric-item"><div class="m-label">Completed</div><div class="m-value">{dev.completed_projects}</div></div>'
            f'<div class="metric-item"><div class="m-label">On-Time Rate</div><div class="m-value">{_fmt_pct(dev.on_time_rate * 100 if dev.on_time_rate is not None else None)}</div></div>'
            f'<div class="metric-item"><div class="m-label">Avg Delay</div><div class="m-value">{_fmt_int(int(dev.avg_delay_days) if dev.avg_delay_days else None)} days</div></div>'
            f'</div>'
        )

    return f"""
<div class="deal-card">
  <div class="deal-card-header">
    <div class="deal-card-title">
      <div style="margin-bottom:4px">{_badge(m.recommended_action.value)} <span style="font-size:12px;color:#888;margin-left:6px">#{rank}</span></div>
      <h3>{_e(m.project_name)}</h3>
      <div class="reg">{_e(m.registration_number)} &mdash; {_e(m.developer_name)}</div>
      {f'<div style="font-size:11px;color:#888;margin-top:2px">{_e(p.district)}</div>' if p.district else ''}
    </div>
    <div class="deal-card-scores">
      <div class="score-pill">
        <div class="sp-label">Opportunity</div>
        <div class="sp-value">{_fmt_score(m.opportunity_score)}</div>
        <div class="sp-sub">/ 100</div>
      </div>
      <div class="score-pill">
        <div class="sp-label">Confidence</div>
        <div class="sp-value">{_fmt_score(m.confidence_score * 100, 0)}</div>
        <div class="sp-sub">/ 100</div>
      </div>
      {track_html}
    </div>
  </div>

  <div class="metrics-row">
    <div class="metric-item"><div class="m-label">Construction</div><div class="m-value">{_fmt_pct(m.construction_progress_pct)}</div></div>
    <div class="metric-item"><div class="m-label">Delay</div><div class="m-value">{_fmt_int(m.delay_days)} days</div></div>
    <div class="metric-item"><div class="m-label">Extensions</div><div class="m-value">{m.extension_count}</div></div>
    <div class="metric-item"><div class="m-label">Status</div><div class="m-value">{_e(p.current_status or "N/A")}</div></div>
    <div class="metric-item"><div class="m-label">AI Model</div><div class="m-value" style="font-size:11px">{_e(m.model_used)}</div></div>
  </div>

  <div class="deal-section">
    <div class="deal-section-label">Opportunity Thesis</div>
    <div class="deal-thesis">{_e(m.opportunity_thesis)}</div>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:14px">
    <div class="deal-section">
      <div class="deal-section-label">Risk Flags</div>
      {_risk_flags_html(m.risk_flags)}
    </div>
    <div class="deal-section">
      <div class="deal-section-label">Data Gaps</div>
      {_data_gaps_html(m.data_gaps)}
    </div>
  </div>

  {f'<div class="deal-section"><div class="deal-section-label">Score Breakdown</div>{factor_rows}</div>' if factor_rows else ''}
  {dev_stats}
</div>
"""


def _render_flag_section(data: ReportData) -> str:
    if not data.flag_deals:
        return '<h2>Top Opportunities (Flag for Review)</h2><p style="color:#aaa;font-size:12px">No projects flagged for review in this dataset.</p>'
    cards = "".join(_render_deal_card(d, i + 1) for i, d in enumerate(data.flag_deals))
    return f"<h2>Top Opportunities &mdash; Flag for Review ({len(data.flag_deals)})</h2>{cards}"


def _render_monitor_section(data: ReportData) -> str:
    if not data.monitor_deals:
        return '<h2>Watchlist (Monitor)</h2><p style="color:#aaa;font-size:12px">No projects in watchlist.</p>'

    rows = ""
    for i, deal in enumerate(data.monitor_deals):
        m = deal.memo
        p = deal.project
        tr_score = _fmt_score(m.track_record_score) if m.track_record_score else "N/A"
        rows += (
            f"<tr>"
            f"<td>{i + 1}</td>"
            f"<td>{_e(m.registration_number)}</td>"
            f"<td>{_e(m.project_name[:35])}</td>"
            f"<td>{_e(m.developer_name[:25])}</td>"
            f"<td>{_e(p.district or 'N/A')}</td>"
            f"<td style='text-align:right'><strong>{_fmt_score(m.opportunity_score)}</strong></td>"
            f"<td style='text-align:right'>{_fmt_pct(m.construction_progress_pct)}</td>"
            f"<td style='text-align:right'>{_fmt_int(m.delay_days)}</td>"
            f"<td style='text-align:right'>{tr_score}</td>"
            f"</tr>"
        )

    return f"""
<h2>Watchlist &mdash; Monitor ({len(data.monitor_deals)})</h2>
<table class="data-table">
  <thead>
    <tr>
      <th>#</th><th>Registration</th><th>Project</th><th>Developer</th>
      <th>District</th><th style="text-align:right">Score</th>
      <th style="text-align:right">Progress</th>
      <th style="text-align:right">Delay (d)</th>
      <th style="text-align:right">Track Rec.</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
"""


def _render_developer_league(data: ReportData) -> str:
    if not data.developer_league:
        return '<h2>Developer League Table</h2><p style="color:#aaa;font-size:12px">No developer profiles available.</p>'

    rows = ""
    for i, dev in enumerate(data.developer_league):
        score = dev.track_record_score or 0.0
        bar_pct = int(score)
        rows += (
            f"<tr>"
            f"<td class='dev-rank'>{i + 1}</td>"
            f"<td>{_e(dev.developer_name)}</td>"
            f"<td>{_e(dev.primary_district or 'N/A')}</td>"
            f"<td style='text-align:right'>{dev.total_projects}</td>"
            f"<td style='text-align:right'>{dev.completed_projects}</td>"
            f"<td style='text-align:right'>{_fmt_pct(dev.completion_rate * 100 if dev.completion_rate else None)}</td>"
            f"<td style='text-align:right'>{_fmt_pct(dev.on_time_rate * 100 if dev.on_time_rate else None)}</td>"
            f"<td style='text-align:right'>{_fmt_int(int(dev.avg_delay_days) if dev.avg_delay_days else None)}</td>"
            f"<td><div class='track-bar-wrap'><div style='background:#efefef;border-radius:2px;height:8px'>"
            f"<div class='track-fill' style='width:{bar_pct}%'></div></div></div></td>"
            f"<td style='text-align:right'><strong>{score:.1f}</strong></td>"
            f"</tr>"
        )

    return f"""
<h2>Developer League Table</h2>
<table class="data-table">
  <thead>
    <tr>
      <th>#</th><th>Developer</th><th>Primary District</th>
      <th style="text-align:right">Projects</th>
      <th style="text-align:right">Completed</th>
      <th style="text-align:right">Completion</th>
      <th style="text-align:right">On-Time</th>
      <th style="text-align:right">Avg Delay</th>
      <th>Track Record</th>
      <th style="text-align:right">Score</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
"""


def _render_methodology(data: ReportData) -> str:
    weights = data.scoring_weights
    if not weights:
        return ""

    items = "".join(
        f'<div class="method-item">'
        f'<span class="method-key">{_e(k.replace("_", " "))}</span>'
        f'<span class="method-val">{v:.0%}</span>'
        f'</div>'
        for k, v in sorted(weights.items(), key=lambda x: -x[1])
    )

    return f"""
<h2>Methodology Note</h2>
<p style="font-size:12px;color:#555;margin-bottom:12px;line-height:1.6">
  Opportunity scores are computed from MAHARERA registry data using a config-driven
  weighted scoring model. <strong>Project viability acts as a multiplier</strong> — any
  lapsed or deregistered project scores zero regardless of other factors.
  AI investment theses are generated from structured data only; no external facts are used.
</p>
<div style="margin-bottom:6px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.6px;color:#888">Scoring Weights</div>
<div class="method-grid">{items}</div>
<p style="font-size:11px;color:#aaa;margin-top:12px">
  Data source: MAHARERA Portal (maharera.maharashtra.gov.in).
  Rules file: {_e(data.summary.scoring_rules_path)}.
  This report is for internal investment committee use only.
</p>
"""


def _render_footer(data: ReportData) -> str:
    ts = data.summary.data_generated_at.strftime("%d %b %Y at %H:%M UTC")
    return f"""
<div class="footer">
  REDO Platform &mdash; Deal Origination Report &mdash; Generated {_e(ts)} &mdash; CONFIDENTIAL &mdash; Internal Use Only
</div>
"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_html(data: ReportData) -> str:
    """Render a complete self-contained HTML report from ReportData."""
    body = (
        _render_cover(data)
        + _render_summary(data)
        + _render_flag_section(data)
        + _render_monitor_section(data)
        + _render_developer_league(data)
        + _render_methodology(data)
        + _render_footer(data)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>REDO Platform &mdash; Deal Origination Report</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">
{body}
</div>
</body>
</html>
"""
