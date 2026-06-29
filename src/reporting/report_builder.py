"""
Assembles all pipeline outputs into a single ReportData object.

Joins InvestmentMemo + ScoredProject + DeveloperProfile records,
deduplicates by project_id (keeps highest opportunity_score),
and computes portfolio-level summary statistics.

Single responsibility: data assembly only. No HTML, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.models.developer_profile import DeveloperProfile
from src.models.investment_memo import InvestmentMemo, RecommendedAction
from src.models.scored_project import ScoredProject


@dataclass
class DealRecord:
    """One investment opportunity: memo + matching scored project."""
    memo: InvestmentMemo
    project: ScoredProject
    developer: Optional[DeveloperProfile]


@dataclass
class ScoreDistribution:
    """Bucket counts for the score histogram."""
    band_0_20: int = 0
    band_20_40: int = 0
    band_40_60: int = 0
    band_60_80: int = 0
    band_80_100: int = 0

    def bucket(self, score: float) -> None:
        if score < 20:
            self.band_0_20 += 1
        elif score < 40:
            self.band_20_40 += 1
        elif score < 60:
            self.band_40_60 += 1
        elif score < 80:
            self.band_60_80 += 1
        else:
            self.band_80_100 += 1

    def as_dict(self) -> dict[str, int]:
        return {
            "0-20": self.band_0_20,
            "20-40": self.band_20_40,
            "40-60": self.band_40_60,
            "60-80": self.band_60_80,
            "80-100": self.band_80_100,
        }


@dataclass
class ReportSummary:
    """Portfolio-level statistics block."""
    total_projects_scored: int
    total_memos_generated: int
    flag_for_review_count: int
    monitor_count: int
    pass_count: int
    avg_opportunity_score: float
    max_opportunity_score: float
    top_district: str
    score_distribution: ScoreDistribution
    models_used: list[str]
    data_generated_at: datetime
    scoring_rules_path: str


@dataclass
class ReportData:
    """Complete assembled report — everything the renderer needs."""
    summary: ReportSummary
    flag_deals: list[DealRecord]          # FLAG_FOR_REVIEW, sorted desc by score
    monitor_deals: list[DealRecord]       # MONITOR, sorted desc by score
    developer_league: list[DeveloperProfile]  # sorted desc by track_record_score
    all_projects: list[ScoredProject]     # deduplicated, for reference
    scoring_weights: dict[str, float]     # from scoring_rules.yaml (for methodology note)


def build_report(
    memos: list[InvestmentMemo],
    projects: list[ScoredProject],
    developer_profiles: list[DeveloperProfile],
    scoring_weights: dict[str, float],
    scoring_rules_path: str = "config/scoring_rules.yaml",
) -> ReportData:
    """Assemble all pipeline outputs into a ReportData object.

    Deduplication: when the same project_id appears multiple times (e.g. two
    scraper runs produced overlapping output), keep the record with the highest
    opportunity_score. This is conservative — a higher score on the same project
    means more recent/complete data.
    """
    # --- Deduplicate projects by project_id ------------------------------------
    project_index: dict[int, ScoredProject] = {}
    for p in projects:
        existing = project_index.get(p.project_id)
        if existing is None or p.opportunity_score > existing.opportunity_score:
            project_index[p.project_id] = p

    # --- Deduplicate memos by project_id (keep highest score) ------------------
    memo_index: dict[int, InvestmentMemo] = {}
    for m in memos:
        existing = memo_index.get(m.project_id)
        if existing is None or m.opportunity_score > existing.opportunity_score:
            memo_index[m.project_id] = m

    unique_memos = list(memo_index.values())

    # --- Developer index -------------------------------------------------------
    dev_index: dict[Optional[int], DeveloperProfile] = {
        d.promoter_profile_id: d for d in developer_profiles if d.promoter_profile_id
    }

    # --- Build DealRecord list -------------------------------------------------
    deal_records: list[DealRecord] = []
    for memo in unique_memos:
        project = project_index.get(memo.project_id)
        if project is None:
            # Memo without matching project — still include with project data from memo
            project = _stub_project_from_memo(memo)
        developer = dev_index.get(project.promoter_profile_id) if project else None
        deal_records.append(DealRecord(memo=memo, project=project, developer=developer))

    deal_records.sort(key=lambda d: d.memo.opportunity_score, reverse=True)

    flag_deals = [d for d in deal_records if d.memo.recommended_action == RecommendedAction.FLAG_FOR_REVIEW]
    monitor_deals = [d for d in deal_records if d.memo.recommended_action == RecommendedAction.MONITOR]

    # --- Summary statistics ----------------------------------------------------
    all_projects_deduped = list(project_index.values())
    scores = [m.opportunity_score for m in unique_memos]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    max_score = round(max(scores), 2) if scores else 0.0

    dist = ScoreDistribution()
    for s in scores:
        dist.bucket(s)

    # Top district by number of eligible memos (FLAG + MONITOR)
    district_counts: dict[str, int] = {}
    for d in flag_deals + monitor_deals:
        district = d.project.district or "Unknown"
        district_counts[district] = district_counts.get(district, 0) + 1
    top_district = max(district_counts, key=lambda k: district_counts[k]) if district_counts else "N/A"

    models_used = sorted({m.model_used for m in unique_memos if m.model_used})

    summary = ReportSummary(
        total_projects_scored=len(all_projects_deduped),
        total_memos_generated=len(unique_memos),
        flag_for_review_count=len(flag_deals),
        monitor_count=len(monitor_deals),
        pass_count=sum(1 for m in unique_memos if m.recommended_action == RecommendedAction.PASS),
        avg_opportunity_score=avg_score,
        max_opportunity_score=max_score,
        top_district=top_district,
        score_distribution=dist,
        models_used=models_used,
        data_generated_at=datetime.now(timezone.utc),
        scoring_rules_path=scoring_rules_path,
    )

    developer_league = sorted(
        [d for d in developer_profiles if d.track_record_score is not None],
        key=lambda d: d.track_record_score,  # type: ignore[arg-type]
        reverse=True,
    )

    return ReportData(
        summary=summary,
        flag_deals=flag_deals,
        monitor_deals=monitor_deals,
        developer_league=developer_league,
        all_projects=all_projects_deduped,
        scoring_weights=scoring_weights,
    )


def _stub_project_from_memo(memo: InvestmentMemo) -> ScoredProject:
    """Create a minimal ScoredProject from memo fields when the original is missing."""
    from datetime import datetime, timezone
    return ScoredProject(
        project_id=memo.project_id,
        registration_number=memo.registration_number,
        project_name=memo.project_name,
        developer_name=memo.developer_name,
        district=None,
        current_status=None,
        is_lapsed=False,
        is_deregistered=False,
        is_abeyance=False,
        delay_days=memo.delay_days,
        is_delayed=(memo.delay_days or 0) > 0,
        construction_progress_pct=memo.construction_progress_pct,
        extension_count=memo.extension_count,
        proposed_completion_date=None,
        opportunity_score=memo.opportunity_score,
        factor_scores={},
        location_tier="unknown",
        detail_url=None,
        source_url=None,
        scraped_at=datetime.now(timezone.utc),
        cleaned_at=datetime.now(timezone.utc),
        scored_at=datetime.now(timezone.utc),
        promoter_profile_id=None,
    )
