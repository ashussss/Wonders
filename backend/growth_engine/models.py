"""Pydantic schemas for the Growth Engine.

These are internal-to-module validation contracts. The API layer also accepts raw
dict bodies for the admin endpoints (matching the style of routes_blog.py) but the
engine core validates every AI-produced campaign through ``CampaignDraft`` before
it is persisted, so a malformed model response can never reach the queue.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

CampaignKind = Literal["blog", "news", "pain_point", "engagement"]
FunnelStage = Literal["awareness", "consideration", "intent", "conversion", "retention"]
VisualFormat = Literal[
    "carousel", "infographic", "stat_card", "checklist", "comparison", "quote"
]
Platform = Literal["linkedin", "facebook", "instagram"]


class PlatformCopy(BaseModel):
    """Copy written for one platform's conventions."""

    caption: str = Field(default="", max_length=5000)
    hashtags: List[str] = Field(default_factory=list)
    cta: str = ""

    @field_validator("hashtags")
    @classmethod
    def clean_tags(cls, v: List[str]) -> List[str]:
        out: List[str] = []
        for tag in v or []:
            t = str(tag).strip().lstrip("#").strip()
            if t and t not in out:
                out.append(t)
        return out[:15]


class Strategy(BaseModel):
    """The 'why' behind the campaign — the part a human reviewer must judge."""

    target_audience: str = Field(min_length=3, max_length=300)
    pain_point: str = Field(min_length=3, max_length=400)
    intent: str = Field(min_length=3, max_length=300)
    funnel_stage: FunnelStage
    content_angle: str = Field(min_length=3, max_length=500)
    hook: str = Field(min_length=3, max_length=300)
    cta: str = Field(default="", max_length=300)
    rationale: str = Field(default="", max_length=1200)
    keywords: List[str] = Field(default_factory=list)

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, v: List[str]) -> List[str]:
        return [str(k).strip().lower() for k in (v or []) if str(k).strip()][:20]


class VisualSpec(BaseModel):
    """Declarative description of the visual the render engine must produce.

    The AI returns *content*, never image bytes. ``visual_engine`` turns this into
    branded JPEG/PNG assets.
    """

    format: VisualFormat
    title: str = Field(default="", max_length=200)
    subtitle: str = Field(default="", max_length=300)
    slides: List[Dict[str, str]] = Field(default_factory=list)
    rows: List[str] = Field(default_factory=list)
    items: List[Dict[str, str]] = Field(default_factory=list)
    number: str = ""
    label: str = ""
    source: str = ""
    cta: str = ""
    quote: str = ""
    attribution: str = ""
    # Comparison sides hold {"title": str, "rows": List[str]} — hence the Any values.
    left: Dict[str, Any] = Field(default_factory=dict)
    right: Dict[str, Any] = Field(default_factory=dict)


class CampaignDraft(BaseModel):
    """A complete, validated campaign as produced by the content engine."""

    kind: CampaignKind
    source_type: str = ""            # blog | news | original
    source_slug: str = ""
    source_url: str = ""
    source_title: str = ""
    strategy: Strategy
    # NOTE: named platform_copy, not copy — a `copy` field shadows BaseModel.copy().
    platform_copy: Dict[str, PlatformCopy]
    platforms: List[Platform] = Field(default_factory=list)
    visual: VisualSpec
    hashtags: List[str] = Field(default_factory=list)
    link_url: str = ""
    link_title: str = ""

    @field_validator("platforms")
    @classmethod
    def clean_platforms(cls, v: List[str]) -> List[str]:
        allowed = {"linkedin", "facebook", "instagram"}
        return [p for p in (v or []) if p in allowed] or ["linkedin"]

    @model_validator(mode="after")
    def _ensure_postable(self) -> "CampaignDraft":
        """Never let a campaign reach the queue with nowhere to publish.

        Defaults are not run through field_validators, so without this an omitted
        ``platforms``/``platform_copy`` would silently produce an unpostable draft.
        """
        allowed = {"linkedin", "facebook", "instagram"}
        platforms = [p for p in (self.platforms or []) if p in allowed] or ["linkedin"]
        copy = dict(self.platform_copy or {})
        # Drop platforms with no usable caption rather than posting an empty message.
        platforms = [p for p in platforms if (copy.get(p) and copy[p].caption.strip())] or ["linkedin"]
        object.__setattr__(self, "platforms", platforms)
        object.__setattr__(self, "platform_copy", copy)
        return self


class CampaignDoc(CampaignDraft):
    """Persisted campaign — adds queue/approval/analytics bookkeeping."""

    id: str
    plan_day: str
    status: str = "pending_review"
    scheduled_at: str = ""
    created_at: str = ""
    updated_at: str = ""
    asset_ids: List[str] = Field(default_factory=list)
    asset_urls: List[str] = Field(default_factory=list)
    results: Dict[str, Any] = Field(default_factory=dict)
    review: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class ProspectRecord(BaseModel):
    """A prospect identified from a permitted (non-automated) data source."""

    id: str
    name: str = ""
    headline: str = ""
    company: str = ""
    role: str = ""
    linkedin_url: str = ""
    source: str = ""
    score: float = 0.0
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    intent_signals: List[str] = Field(default_factory=list)
    activity: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_actions: List[Dict[str, Any]] = Field(default_factory=list)
    connection_message: str = ""
    history: List[Dict[str, Any]] = Field(default_factory=list)
    status: str = "new"
    created_at: str = ""
    updated_at: str = ""


class MetricSample(BaseModel):
    """One performance datapoint used to learn which variables work."""

    campaign_id: str
    platform: str
    metric: str
    value: float = 0.0
    dims: Dict[str, str] = Field(default_factory=dict)
    at: str = ""


__all__ = [
    "PlatformCopy",
    "Strategy",
    "VisualSpec",
    "CampaignDraft",
    "CampaignDoc",
    "ProspectRecord",
    "MetricSample",
]