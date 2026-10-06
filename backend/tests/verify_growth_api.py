#!/usr/bin/env python
"""Growth Engine — end-to-end API verification against a real mongod.

Run it directly:

    MONGO_URL=mongodb://127.0.0.1:27019 python tests/verify_growth_api.py

WHY A STANDALONE RUNNER AND NOT A pytest MODULE
------------------------------------------------
``database.py`` creates the app's motor client at import time, and motor pins a
client to the event loop it is first awaited on. A pytest process shares one loop
across modules, so when another test module awaits ``database.client`` first, every
subsequent request to the app fails with "Future attached to a different loop" —
a harness limitation, not an engine fault (all of these checks pass here). This
script owns its loop end-to-end, so it is deterministic.

Boots the real FastAPI app (real routers, real auth guard, real MongoDB) with the
AI stubbed at the seam every generator funnels through, so no API key is needed.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27019")
os.environ.setdefault("DB_NAME", "growth_api_test")
os.environ.setdefault("SUPERADMIN_SECRET", "testkey")
os.environ.setdefault("GROWTH_APPROVAL_MODE", "true")
os.environ.setdefault("GROWTH_AUTO_PUBLISH", "false")

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

FAILS = []
KEY = {"X-API-KEY": "testkey"}

STUB_STRATEGY = {
    "target_audience": "Event and webinar hosts", "pain_point": "Registrations but no attendees",
    "intent": "Fix attendance", "funnel_stage": "consideration",
    "content_angle": "Reminders beat broadcasts", "hook": "Registrations are not attendance.",
    "cta": "Read the guide", "rationale": "Core problem.", "keywords": ["attendance"],
}
STUB_COPY = {
    "linkedin": {"caption": "Registrations are not attendance. " * 8, "hashtags": ["#webinars"], "cta": "Read"},
    "facebook": {"caption": "Registrations are not attendance. " * 4, "hashtags": ["#webinars"]},
    "instagram": {"caption": "Registrations are not attendance. " * 6, "hashtags": ["#webinars"]},
}
STUB_VISUAL = {
    "format": "carousel", "title": "Attendance is earned",
    "slides": [{"title": "Nudge early", "body": "Three days out."},
               {"title": "One job", "body": "Calendar invite."},
               {"title": "Measure", "body": "Track no-shows."},
               {"title": "Record", "body": "Catch the rest."}],
    "cta": "Read the guide",
}


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + str(detail)[:140] if detail and not cond else ''}")
    if not cond:
        FAILS.append(name)


async def _stub_campaign(kind, **kw):
    from growth_engine.models import CampaignDraft, PlatformCopy, Strategy, VisualSpec
    return CampaignDraft(
        kind=kind, source_type=kw.get("source_type") or "original",
        source_slug=kw.get("source_slug", "stub"), source_title=kw.get("source_title", ""),
        strategy=Strategy(**STUB_STRATEGY), visual=VisualSpec(**STUB_VISUAL),
        platform_copy={p: PlatformCopy(**STUB_COPY[p]) for p in STUB_COPY},
        platforms=list(STUB_COPY), link_url=kw.get("link_url", ""), link_title=kw.get("link_title", ""))


async def _generate(c, day):
    return (await c.post("/api/growth/generate", headers=KEY,
                         json={"render": True, "force": True, "day": day})).json()


async def main():
    import httpx
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    mdb = client[os.environ["DB_NAME"]]
    await client.drop_database(os.environ["DB_NAME"])

    import server
    from growth_engine import content_engine, news_engine
    import growth_engine.queue as q

    content_engine.build_campaign = _stub_campaign
    q.build_campaign = _stub_campaign

    now = datetime.now(timezone.utc).isoformat()
    for i in range(4):
        await mdb.blog_posts.insert_one({
            "slug": f"live-blog-{i}", "title": f"Benchmark {i}", "content": "x" * 200,
            "published": True, "published_at": now,
            "sources": [{"source": "Livestorm", "url": "u"}], "word_count": 200})

    async def fake_news(_self, want=2, exclude_ids=None):
        return [{"id": f"news-{i}", "title": f"Story {i}", "url": "https://e.test/i",
                 "summary": "B2B event benchmark.", "source": "Pub", "published_at": now,
                 "relevance": 5} for i in range(want)]
    news_engine.pick_news = fake_news

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        print("\n=== 1. auth guard ===")
        check("no key -> 403", (await c.get("/api/growth/status")).status_code == 403)
        check("bad key -> 403", (await c.get("/api/growth/status", headers={"X-API-KEY": "x"})).status_code == 403)
        r = await c.get("/api/growth/status", headers=KEY)
        check("good key -> 200", r.status_code == 200, r.text[:200])
        st = r.json()
        check("approval mode on", st["approval_mode"] is True)
        check("publishing blocked", st["publishing_blocked"] is True)
        check("target 9/day", st["targets_per_day"] == 9, st["targets_per_day"])
        check("mix 4/2/2/1", st["mix"] == {"blog": 4, "news": 2, "pain_point": 2, "engagement": 1}, st["mix"])

        print("\n=== 2. compliance contract ===")
        pc = (await c.get("/api/growth/config", headers=KEY)).json()["prospect_compliance"]
        check("no browser automation", pc["no_browser_automation"] is True)
        check("no login scrape", pc["no_login_scrape"] is True)
        check("no auto dm/connect", pc["no_auto_dm_or_connect"] is True)
        check("automated engagement disabled", pc["automated_engagement_enabled"] is False)

        print("\n=== 3. full 9-campaign day ===")
        gen = await _generate(c, "2031-01-01")
        made = [x for x in gen["created"] if x.get("id")]
        kinds = [x["kind"] for x in made]
        print(f"      created: {len(made)} -> {kinds}")
        check("9 campaigns", len(made) == 9, len(made))
        check("4 blog", kinds.count("blog") == 4, kinds.count("blog"))
        check("2 news", kinds.count("news") == 2, kinds.count("news"))
        check("2 pain_point", kinds.count("pain_point") == 2, kinds.count("pain_point"))
        check("1 engagement", kinds.count("engagement") == 1, kinds.count("engagement"))
        check("all pending_review", all(x["status"] == "pending_review" for x in made))
        check("visual rendered for all", all(x["assets"] >= 1 for x in made), [x["assets"] for x in made])
        print(f"      visual formats: {sorted({x['visual'] for x in made})}")

        print("\n=== 4. queue + detail ===")
        rows = (await c.get("/api/growth/queue", headers=KEY)).json()
        check("queue lists 9", len(rows) == 9, len(rows))
        one = (await c.get(f"/api/growth/campaign/{made[0]['id']}", headers=KEY)).json()
        check("full strategy block", all(k in one["strategy"] for k in
              ("target_audience", "pain_point", "intent", "funnel_stage", "content_angle", "hook", "cta")))
        check("copy for 3 platforms", set(one["platform_copy"]) == {"linkedin", "facebook", "instagram"})
        check("404 unknown", (await c.get("/api/growth/campaign/nope", headers=KEY)).status_code == 404)

        print("\n=== 5. asset route (public read) ===")
        aid = one["asset_urls"][0].split("/")[-1].replace(".jpg", "")
        r = await c.get(f"/api/growth/asset/{aid}.jpg")
        check("public -> 200", r.status_code == 200, r.status_code)
        check("content-type jpeg", r.headers.get("content-type") == "image/jpeg")
        check("real JPEG bytes", r.content[:2] == b"\xff\xd8", r.content[:4])
        check("404 missing", (await c.get("/api/growth/asset/deadbeef.jpg")).status_code == 404)

        print("\n=== 6. dispatch blocked in approval mode ===")
        await c.post("/api/growth/approve", headers=KEY, json={"ids": [made[0]["id"]]})
        check("dispatch skipped", (await c.post("/api/growth/dispatch", headers=KEY, json={})).json()
              .get("skipped") == "approval_mode")

        print("\n=== 7. post-now refuses non-approved ===")
        cid = made[1]["id"]
        r = await c.post(f"/api/growth/post-now/{cid}", headers=KEY)
        check("pending refused", r.status_code == 400 and "pending review" in r.text.lower(), r.status_code)
        await c.post("/api/growth/reject", headers=KEY, json={"ids": [cid]})
        r = await c.post(f"/api/growth/post-now/{cid}", headers=KEY)
        check("rejected refused", r.status_code == 400 and "reject" in r.text.lower(), r.status_code)
        ok = made[2]["id"]
        await c.post("/api/growth/approve", headers=KEY, json={"ids": [ok]})
        r = await c.post(f"/api/growth/post-now/{ok}", headers=KEY)
        check("approved posts (no creds -> failed)", r.status_code == 200 and len(r.json()["results"]) == 3, r.text[:150])

        print("\n=== 8. edit guard ===")
        r = await c.post(f"/api/growth/edit/{made[3]['id']}", headers=KEY,
                         json={"status": "approved", "_id": "x"})
        check("edit rejects status/_id", r.json()["ok"] is False, r.text[:150])

        print("\n=== 9. prospects ===")
        csv = ("name,title,company,linkedin_url\n"
               "Dana Fox,Demand Generation Lead,Acme SaaS,https://linkedin.com/in/danafox\n"
               "Lee Park,Head of Events,Big Events,https://linkedin.com/in/leepark\n")
        r = await c.post("/api/growth/prospects/import", headers=KEY, json={"csv": csv})
        check("2 imported", r.json().get("added") == 2, r.json())
        ps = (await c.get("/api/growth/prospects", headers=KEY)).json()
        top = max(ps, key=lambda p: p["score"])
        check("demand gen ranks first", top["name"] == "Dana Fox", top["name"])
        rec = (await c.post(f"/api/growth/prospects/{top['id']}/recommend", headers=KEY)).json()
        check("actions manual-only", all("manual" in a["execute"] for a in rec["actions"]))

        print("\n=== 10. analytics ===")
        await _generate(c, "2031-01-07")
        blogs = (await c.get("/api/growth/queue?kind=blog", headers=KEY)).json()
        r = await c.post(f"/api/growth/metrics/{blogs[0]['id']}", headers=KEY,
                         json={"linkedin": {"impressions": 5000, "engagements": 250, "clicks": 90},
                               "facebook": {"impressions": 1000, "engagements": 10}})
        check("metrics recorded", r.json().get("recorded") == 2, r.json())
        learn = (await c.get("/api/growth/analytics/learn?metric=engagements", headers=KEY)).json()
        check("samples > 0", learn.get("samples", 0) >= 1)
        check("platform ranked", "linkedin" in dict(learn.get("platform") or []), learn.get("platform"))
        check("eng rate computed", learn["platform_summary"]["linkedin"]["eng_rate_pct"] > 0)
        check("visual/hook/cta ranked", all(learn.get(d) for d in ("visual", "hook", "cta")))
        check("bad metric rejected",
              (await c.get("/api/growth/analytics/learn?metric=bogus", headers=KEY)).json()["ok"] is False)

        print("\n=== 11. isolation ===")
        colls = await mdb.list_collection_names()
        check("growth_campaigns exists", "growth_campaigns" in colls, colls)
        check("social_posts NOT created", "social_posts" not in colls, colls)
        check("existing social queue still responds",
              (await c.get("/api/social/queue", headers=KEY)).status_code in (200, 403))

    await client.drop_database(os.environ["DB_NAME"])
    client.close()
    print(f"\n{'ALL API CHECKS PASSED' if not FAILS else 'FAILURES: ' + str(FAILS)}")
    sys.exit(0 if not FAILS else 1)


if __name__ == "__main__":
    asyncio.run(main())