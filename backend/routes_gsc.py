"""Google Search Console + FastAPI Integration for ShowUp AI Live.

Queries Google Search Console API → returns impressions, clicks, CTR, position
→ updates MongoDB seo_performance collection → triggers optimization recommendations.
"""

"""GSC + SEO Performance endpoints."""

import asyncio
import base64
import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks
from pymongo import ReturnDocument

from database import db
from auth_utils import get_user, now_iso

router = APIRouter(prefix="/api")


# ✅ Helper: Decode base64 GSC Service Account Key
def _get_gsc_credentials():
    """Decode GSC_SERVICE_ACCOUNT_BASE64 from env into service account info."""
    base64_key = os.environ.get("GSC_SERVICE_ACCOUNT_BASE64", "")
    if not base64_key:
        return None
    try:
        sa_info = json.loads(base64.b64decode(base64_key).decode("utf-8"))
        return sa_info
    except Exception:
        return None


# ✅ Endpoint: Fetch GSC Data for a Property
@router.post("/seo/gsc-fetch")
async def gsc_fetch(
    payload: dict = Body(default={}),
    user=Depends(get_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Fetch Search Console data and update MongoDB performance collection."""
    # Check auth
    if user.get("role", "") != "superadmin":
        raise HTTPException(403, "Superadmin access required")

    property_url = (payload.get("property") or "").strip()
    if not property_url:
        raise HTTPException(400, "Property URL required")

    # Ensure https://
    if not property_url.startswith("https://"):
        property_url = "https://" + property_url

    # Build GSC service
    sa_info = _get_gsc_credentials()
    if not sa_info:
        raise HTTPException(500, "GSC service account not configured")

    try:
        from googleapiclient.discovery import build
        service = build("searchconsole", "v1", credentials=sa_info)
    except Exception as e:
        raise HTTPException(500, f"Failed to build GSC service: {e}")

    # Calculate date range: last 28 days (GSC max)
    today = datetime.now(timezone.utc)
    end_date = today.strftime("%Y-%m-%d")
    start_date = (today - timedelta(days=28)).strftime("%Y-%m-%d")

    # Fetch performance data
    try:
        site_url = property_url + "/"
        request = service.searchanalytics().query(
            siteUrl=site_url,
            requestBody={
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["page", "query", "country", "device"],
            },
        )
        response = await asyncio.get_event_loop().run_in_executor(
            None, lambda: request.execute()
        )

        # Extract rows
        rows = response.get("rows", [])

        # Process and update MongoDB in background
        if rows:
            updates = []
            for row in rows:
                page = row.get("keys", [""])[0] or "/"
                performance = {
                    "page": page,
                    "impressions": row.get("impressions", 0),
                    "clicks": row.get("clicks", 0),
                    "ctr": round(row.get("ctr", 0) * 100, 2),
                    "position": row.get("position", 0),
                    "last_checked": now_iso(),
                    "date_range": {"start": start_date, "end": end_date},
                }
                updates.append({
                    "page": page,
                    "performance_data": performance,
                })

            for update in updates:
                background_tasks.add(
                    _update_seo_performance,
                    update["page"],
                    update["performance_data"],
                )

        return {
            "ok": True,
            "property": property_url,
            "date_range": {"start": start_date, "end": end_date},
            "pages_fetched": len(rows),
            "message": f"Fetched GSC data for {len(rows)} pages",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"GSC fetch failed: {e}")


# ✅ Helper: Update Single SEO Performance Record
async def _update_seo_performance(page: str, performance_data: dict):
    """Update SEO performance for a single page in MongoDB."""
    await db.seo_performance.update_one(
        {"page": page},
        {
            "$set": {
                **performance_data,
                "updated_at": now_iso(),
            }
        },
        upsert=True,
    )


# ✅ Endpoint: Get SEO Performance Summary
@router.get("/seo/performance")
async def seo_performance(user=Depends(get_user)):
    """Get overall SEO performance summary from GSC + GA4 data."""
    # Check auth
    if user.get("role", "") != "superadmin":
        raise HTTPException(403, "Superadmin access required")

    # Aggregate from seo_performance collection
    pipeline = [
        {
            "$group": {
                "_id": None,
                "total_impressions": {"$sum": "$impressions"},
                "total_clicks": {"$sum": "$clicks"},
                "avg_ctr": {"$avg": "$ctr"},
                "avg_position": {"$avg": "$position"},
                "total_pages": {"$sum": 1},
            }
        }
    ]
    agg_result = await db.seo_performance.aggregate(pipeline).to_list(1)

    total_impressions = 0
    total_clicks = 0
    avg_ctr = 0
    avg_position = 0
    total_pages = 0

    if agg_result:
        total_impressions = agg_result[0].get("total_impressions", 0) or 0
        total_clicks = agg_result[0].get("total_clicks", 0) or 0
        avg_ctr = round(agg_result[0].get("avg_ctr", 0) or 0, 2)
        avg_position = round(agg_result[0].get("avg_position", 10) or 5, 2)
        total_pages = agg_result[0].get("total_pages", 0) or 0

    # Calculate CTR
    ctr = (total_clicks / total_impressions * 100) if total_impressions else 0

    # Top performing pages (from blog_posts with performance fields)
    top_pages = []
    performed_posts = await db.blog_posts.find(
        {"published": True},
        {"slug": 1, "title": 1, "impressions": 1, "clicks": 1, "position": 1}
    ).limit(10).to_list(10)

    for post in performed_posts:
        imp = post.get("impressions", 0)
        click = post.get("clicks", 0)
        pos = post.get("position", 0)
        ctr_val = round((click / max(imp, 1)) * 100, 2) if imp else 0
        top_pages.append({
            "url": f"/blog/{post['slug']}",
            "title": post.get("title", "Unknown"),
            "impressions": imp,
            "clicks": click,
            "ctr": ctr_val,
            "position": pos,
        })

    # Ranking distribution
    ranking_4to10 = 0
    ranking_11to30 = 0
    ranking_30plus = 0

    all_perf = await db.seo_performance.find({}).to_list(1000)
    for p in all_perf:
        pos = p.get("avg_position", 5)
        if pos <= 10:
            ranking_4to10 += 1
        elif pos <= 30:
            ranking_11to30 += 1
        else:
            ranking_30plus += 1

    # Needs optimization
    needs_optimization = []
    all_posts = await db.blog_posts.find({"published": True}).to_list(200)
    seen = set()
    for post in all_posts:
        pos = post.get("position", 0)
        ctr = post.get("ctr", 0)
        if pos > 20 and ctr < 5 and post["slug"] not in seen:
            needs_optimization.append(post["slug"])
            seen.add(post["slug"])
        if pos > 1 and post.get("impressions", 0) < 50 and post["slug"] not in seen:
            needs_optimization.append(post["slug"])
            seen.add(post["slug"])

    # Deduplicate and limit
    needs_optimization = list(set(needs_optimization))[:50]

    return {
        "ok": True,
        "summary": {
            "total_indexed": total_pages,
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "ctr": round(ctr, 2),
            "avg_position": avg_position,
            "total_pages_reported": total_pages,
            "top_pages_ranking_4to10": ranking_4to10,
            "top_pages_ranking_11to30": ranking_11to30,
            "top_pages_ranking_30plus": ranking_30plus,
        },
        "top_pages": top_pages,
        "needs_optimization": needs_optimization,
        "generated_at": now_iso(),
    }


# ✅ Endpoint: Manual GSC Trigger (for testing)
@router.post("/seo/manual-gsc-trigger")
async def manual_gsc_trigger(
    payload: dict = Body(default={}),
    user=Depends(get_user),
):
    """Manually trigger GSC fetch (for testing outside scheduler)."""
    # Check auth
    if user.get("role", "") != "superadmin":
        raise HTTPException(403, "Superadmin access required")

    property_url = payload.get("property", "https://showupai.live")
    if not property_url:
        raise HTTPException(400, "Property URL required")

    try:
        sa_info = _get_gsc_credentials()
        if not sa_info:
            raise HTTPException(500, "GSC service account not configured")

        from googleapiclient.discovery import build
        service = build("searchconsole", "v1", credentials=sa_info)

        # Fetch last 28 days
        today = datetime.now(timezone.utc)
        end_date = today.strftime("%Y-%m-%d")
        start_date = (today - timedelta(days=28)).strftime("%Y-%m-%d")

        site_url = property_url + "/"
        request = service.searchanalytics().query(
            siteUrl=site_url,
            requestBody={
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["page"],
            },
        )
        response = await asyncio.get_event_loop().run_in_executor(
            None, lambda: request.execute()
        )

        rows = response.get("rows", [])

        # Update MongoDB
        for row in rows:
            page = row.get("keys", [""])[0] or "/"
            imp = row.get("impressions", 0)
            click = row.get("clicks", 0)
            pos = row.get("position", 0)
            ctr_val = round(row.get("ctr", 0) * 100, 2)

            await db.seo_performance.update_one(
                {"page": page},
                {
                    "$set": {
                        "impressions": imp,
                        "clicks": click,
                        "ctr": ctr_val,
                        "position": pos,
                        "last_checked": now_iso(),
                        "date_range": {"start": start_date, "end": end_date},
                    }
                },
                upsert=True,
            )

        return {
            "ok": True,
            "property": property_url,
            "pages_fetched": len(rows),
            "message": "Manual GSC fetch completed",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Manual GSC trigger failed: {e}")