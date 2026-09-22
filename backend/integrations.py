"""Circle.so member sync + LinkedIn Events (best-effort).

Uses Bearer→Token auto-fallback to handle Circle's documented inconsistency between
the quick-start (Bearer) and Swagger spec (Token) auth schemes.
"""
from __future__ import annotations
import logging
from typing import Dict, Any, List
import re as _re

import httpx

logger = logging.getLogger("showup.integrations")


async def _circle_get(api_token: str, path: str, params: Dict[str, Any] | None = None) -> tuple[int, str, Dict[str, Any], str]:
    """GET helper with Bearer→Token + US→EU base auto-fallback. Returns (status, text, json_or_empty, scheme_used)."""
    bases = ["https://app.circle.so", "https://eu.app.circle.so"]
    redacted = (api_token[:4] + "…" + api_token[-4:]) if api_token and len(api_token) > 8 else "(empty)"
    last_err = ""
    last_status, last_text = 401, ""
    for base in bases:
        url = f"{base}{path}"
        for scheme in ("Bearer", "Token"):
            headers = {"Authorization": f"{scheme} {api_token}", "Accept": "application/json"}
            logger.info(f"Circle request → GET {url} | scheme={scheme} token={redacted} params={params}")
            try:
                async with httpx.AsyncClient(timeout=30) as c:
                    r = await c.get(url, params=params, headers=headers)
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                logger.warning(f"Circle GET failed: {e}")
                continue
            logger.info(f"Circle response ← {r.status_code} | base={base} scheme={scheme} | body[:200]={r.text[:200]}")
            last_status, last_text = r.status_code, r.text
            if r.status_code == 401:
                continue
            try:
                data = r.json() if r.text else {}
            except Exception:  # noqa: BLE001
                data = {}
            return r.status_code, r.text, data, f"{scheme} @ {base.rsplit('//',1)[-1]}"
    return last_status, last_text or last_err or "All combinations returned 401", {}, "none"


async def circle_sync_members(api_token: str, per_page: int = 100) -> List[Dict[str, Any]]:
    """Fetch all community members from Circle.so Admin API v2."""
    if not api_token:
        return []
    out: List[Dict[str, Any]] = []
    page = 1
    while True:
        status, text, data, _ = await _circle_get(api_token, "/api/admin/v2/community_members",
                                                    params={"page": page, "per_page": per_page})
        if status >= 400:
            logger.warning(f"Circle.so sync failed page={page}: {status} {text[:200]}")
            break
        records = data.get("records") or data.get("data") or []
        out.extend(records)
        if not data.get("has_next_page") or not records:
            break
        page += 1
        if page > 50:
            break
    return out


async def circle_diagnose(api_token: str) -> Dict[str, Any]:
    """Run a 'whoami' style check against multiple Circle endpoints to identify the token type.

    Returns {ok, scheme, community?, error?, hint} so the user can self-diagnose the 401.
    """
    if not api_token:
        return {"ok": False, "error": "No circle_api_key configured"}
    # Try the lightest admin endpoint — list 1 space
    status, text, data, scheme = await _circle_get(api_token, "/api/admin/v2/spaces",
                                                     params={"per_page": 1})
    if status == 200:
        sample = (data.get("records") or data.get("data") or [{}])[0] if data else {}
        return {
            "ok": True,
            "scheme_that_worked": scheme,
            "first_space": {"id": sample.get("id"), "name": sample.get("name")} if sample else None,
            "raw_keys": list(data.keys()) if isinstance(data, dict) else None,
            "hint": f"✓ Connected via '{scheme}' scheme. Token is a valid Admin v2 API token.",
        }
    # Try v1 endpoint to identify if user gave us a v1 token (v1 returns 200 with success:false on auth failure)
    s2, t2, d2, _ = await _circle_get(api_token, "/api/v1/spaces")
    is_v1_valid = s2 == 200 and isinstance(d2, dict) and d2.get("status") != "unauthorized"
    if is_v1_valid:
        return {
            "ok": False, "error": "Token works against v1 API, not v2.",
            "status": status, "response": text[:300],
            "hint": "You pasted an Admin v1 token. Go to Circle → Settings → Developers → Tokens "
                    "and create a NEW token (the form should say 'Admin v2 API'). Paste THAT one."
        }
    hint = "Token rejected by both schemes (Bearer + Token). Likely causes:"
    return {
        "ok": False, "error": "Token invalid", "status": status, "response": text[:300],
        "hint": hint + " (1) Token type wrong — make sure it's 'Admin v2 API', not Headless or Data API. "
                "(2) Token revoked or admin lost privileges. (3) Workspace deleted/renamed. "
                "Re-create from Circle → Settings → Developers → Tokens.",
    }


async def linkedin_list_events(access_token: str, organization_urn: str) -> Dict[str, Any]:
    """Best-effort: list events for an organisation. Returns the raw response or an error dict."""
    if not access_token or not organization_urn:
        return {"_error": "Missing linkedin_marketing_token or linkedin_org_urn"}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                "https://api.linkedin.com/rest/events",
                params={"organization": organization_urn},
                headers={**headers, "LinkedIn-Version": "202604"})
        if r.status_code >= 400:
            return {"_error": f"{r.status_code}: {r.text[:300]}",
                    "_note": "Most third-party apps don't have Event Management API scope. "
                             "Use the CSV import path in the Registrants tab instead."}
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e)}


# ══════════════════════════════════════════════
# WEBINAR FETCH FROM LINK
# ══════════════════════════════════════════════

def detect_platform(url: str) -> str:
    """Detect platform from URL."""
    url = url.lower().strip()
    if "circle.so" in url or "schoolbusinessmanager.uk" in url or "app.circle.so" in url:
        return "circle"
    if "zoom.us" in url:
        return "zoom"
    if "meet.google.com" in url:
        return "google_meet"
    if "teams.microsoft.com" in url or "teams.live.com" in url:
        return "teams"
    if "linkedin.com/events" in url:
        return "linkedin"
    if "webex.com" in url:
        return "webex"
    if "whereby.com" in url:
        return "whereby"
    if "calendly.com" in url:
        return "calendly"
    if "streamyard.com" in url:
        return "streamyard"
    if "eventbrite.com" in url or "eventbrite.co.uk" in url:
        return "eventbrite"
    if "lu.ma" in url:
        return "luma"
    if "hopin.com" in url:
        return "hopin"
    if "airmeet.com" in url:
        return "airmeet"
    return "unknown"


async def fetch_circle_event(url: str, api_token: str, settings: dict = None) -> dict:
    """Fetch Circle.so event — tries v1 events API first, then v2 posts."""
    import httpx
    settings = settings or {}
    space_id = settings.get("circle_space_id")

    result = {
        "platform": "circle",
        "title": "", "description": "", "starts_at": "",
        "speaker": "", "join_link": url, "attendees": [],
        "raw_url": url,
    }

    # Extract slug from URL
    url_slug = url.rstrip("/").split("/")[-1]
    hash_match = _re.search(r'-([a-f0-9]{4,})$', url_slug)
    url_hash = hash_match.group(1) if hash_match else None
    clean_slug = _re.sub(r'-[a-f0-9]{4,}$', '', url_slug)

    bases = ["https://app.circle.so", "https://eu.app.circle.so"]

    async with httpx.AsyncClient(timeout=30) as client:
        for base in bases:
            for scheme in ("Bearer", "Token"):
                headers = {
                    "Authorization": f"{scheme} {api_token}",
                    "Accept": "application/json"
                }
                try:
                    # METHOD 1: Try v1 events API with space_id
                    if space_id:
                        ev_r = await client.get(
                            f"{base}/api/v1/events",
                            headers=headers,
                            params={"space_id": space_id, "per_page": 100}
                        )
                        logger.info(f"v1 events API: {ev_r.status_code}, space_id={space_id}")
                        if ev_r.status_code == 200:
                            events = ev_r.json() if isinstance(ev_r.json(), list) else ev_r.json().get("events", [])
                            logger.info(f"v1 events count: {len(events)}")
                            for ev in events:
                                ev_name = (ev.get("name") or ev.get("title") or "").lower()
                                ev_slug = (ev.get("slug") or "").lower()
                                name_words = set(w for w in _re.sub(r'[^a-z0-9]', ' ', ev_name).split() if len(w) > 3)
                                slug_words = set(w for w in clean_slug.split('-') if len(w) > 3)
                                score = len(name_words & slug_words)
                                logger.info(f"Event: {ev_name[:50]} | score={score}")
                                if score >= 2 or (url_hash and url_hash in ev_slug):
                                    result["title"] = ev.get("name") or ev.get("title", "")
                                    result["description"] = (ev.get("description") or ev.get("body", ""))[:500]
                                    result["starts_at"] = ev.get("starts_at") or ev.get("start_at") or ev.get("event_date", "")
                                    result["join_link"] = ev.get("location_url") or ev.get("meeting_url") or url
                                    result["cover_image_url"] = ev.get("cover_image_url", "")
                                    logger.info(f"✓ Matched v1 event: {result['title']}")
                                    return result

                    # METHOD 2: v2 posts — try with space_id AND without
                    all_posts = []
                    for params in [
                        {"per_page": 200, "sort": "published_at", "space_id": space_id} if space_id else None,
                        {"per_page": 200, "sort": "latest"},
                        {"per_page": 100, "sort": "published_at"},
                    ]:
                        if params is None:
                            continue
                        r = await client.get(f"{base}/api/admin/v2/posts", headers=headers, params=params)
                        if r.status_code == 200:
                            posts = r.json().get("records", [])
                            logger.info(f"v2 posts ({params}): {len(posts)} posts")
                            all_posts = posts
                            break
                    r = type('obj', (), {'status_code': 200 if all_posts else 404,
                                        'json': lambda self, p=all_posts: {'records': p}})()

                    if r.status_code != 200:
                        continue

                    posts = r.json().get("records", [])

                    # Find best match
                    slug_words = set(w for w in clean_slug.split('-') if len(w) > 3)
                    # Also try matching against original URL slug
                    full_slug_words = set(w for w in url_slug.split('-') if len(w) > 3)
                    best_match = None
                    best_score = 0

                    for post in posts:
                        name = (post.get("name") or "").lower()
                        post_slug = (post.get("slug") or "").lower()
                        post_url_field = (post.get("url") or "").lower()
                        name_words = set(w for w in _re.sub(r'[^a-z0-9]', ' ', name).split() if len(w) > 3)
                        score = len(slug_words & name_words)
                        # Hash match in slug or url field
                        if url_hash and (url_hash in post_slug or url_hash in post_url_field):
                            score += 50  # Very strong bonus
                        # Full slug word match
                        score += len(full_slug_words & name_words) * 0.5
                        if score > best_score:
                            best_score = score
                            best_match = post
                            logger.info(f"Candidate: {name[:60]} score={score:.1f} hash_in_slug={url_hash in post_slug if url_hash else False}")

                    if best_match and best_score >= 2:
                        post = best_match
                        result["title"] = post.get("name", "")
                        result["description"] = (post.get("body_plain_text") or "")[:500]
                        result["cover_image_url"] = post.get("cover_image_url", "")
                        if post.get("published_at"):
                            result["starts_at"] = post["published_at"]

                        # Get full post detail
                        det = await client.get(f"{base}/api/admin/v2/posts/{post['id']}", headers=headers)
                        if det.status_code == 200:
                            d = det.json()
                            ev = d.get("event_setting") or {}
                            logger.info(f"event_setting: {ev}")
                            for field in ["starts_at", "start_at", "event_date", "start_date"]:
                                if ev.get(field):
                                    result["starts_at"] = ev[field]
                                    break
                            if ev.get("location_url"):
                                result["join_link"] = ev["location_url"]
                            result["description"] = (d.get("body_plain_text") or result["description"])[:500]
                            if d.get("cover_image_url"):
                                result["cover_image_url"] = d["cover_image_url"]

                        # Get attendees
                        for att_url in [
                            f"{base}/api/admin/v2/event_attendees?post_id={post['id']}&per_page=100",
                            f"{base}/api/admin/v2/post_members?post_id={post['id']}&per_page=100",
                        ]:
                            att_r = await client.get(att_url, headers=headers)
                            if att_r.status_code == 200:
                                records = att_r.json().get("records", [])
                                result["attendees"] = [
                                    {"name": m.get("name", ""), "email": m.get("email", "")}
                                    for m in records if m.get("email")
                                ]
                                if result["attendees"]:
                                    break

                        logger.info(f"Final: title={result['title']}, starts_at={result['starts_at']}, attendees={len(result['attendees'])}")
                        return result

                    if r.status_code != 401:
                        break
                except Exception as e:
                    logger.error(f"Circle fetch error: {e}")
                    continue

    result["error"] = "Could not find matching event. Try the Circle admin URL directly."
    return result





async def scrape_and_extract(url: str) -> dict:
    """Fetch page HTML and extract webinar details using regex/parsing."""
    import httpx
    import re
    
    result = {
        "platform": "scraped",
        "title": "", "description": "", "starts_at": "",
        "speaker": "", "join_link": url, "attendees": [],
    }
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            
        if r.status_code != 200:
            result["error"] = f"Could not fetch page ({r.status_code})"
            return result
            
        html = r.text
        
        # Extract title — try multiple patterns
        title_patterns = [
            r'<meta property="og:title" content="([^"]+)"',
            r'<meta name="twitter:title" content="([^"]+)"',
            r'<title>([^<]+)</title>',
            r'<h1[^>]*>([^<]+)</h1>',
        ]
        for pat in title_patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                result["title"] = m.group(1).strip()
                break
        
        # Extract description
        desc_patterns = [
            r'<meta property="og:description" content="([^"]+)"',
            r'<meta name="description" content="([^"]+)"',
            r'<meta name="twitter:description" content="([^"]+)"',
        ]
        for pat in desc_patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                result["description"] = m.group(1).strip()[:500]
                break
        
        # Extract date — look for common date patterns in meta/JSON-LD
        date_patterns = [
            r'"startDate"\s*:\s*"([^"]+)"',
            r'"start_time"\s*:\s*"([^"]+)"',
            r'"starts_at"\s*:\s*"([^"]+)"',
            r'<meta[^>]*itemprop="startDate"[^>]*content="([^"]+)"',
            r'"event_start"\s*:\s*"([^"]+)"',
        ]
        for pat in date_patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                result["starts_at"] = m.group(1).strip()
                break
        
        # Extract image
        img_patterns = [
            r'<meta property="og:image" content="([^"]+)"',
            r'<meta name="twitter:image" content="([^"]+)"',
        ]
        for pat in img_patterns:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                result["cover_image_url"] = m.group(1).strip()
                break
        
        # Extract zoom/meet/teams join links from page
        zoom_m = re.search(r'https://[a-z0-9]+\.zoom\.us/j/[0-9]+[^\s<>\"]*', html)
        meet_m = re.search(r'https://meet\.google\.com/[a-z-]+', html)
        teams_m = re.search(r'https://teams\.microsoft\.com/l/meetup[^\s<>"]*', html)
        for m in [zoom_m, meet_m, teams_m]:
            if m:
                result["join_link"] = m.group(0)
                break
        
        if result["title"]:
            logger.info(f"Scraped: title={result['title'][:50]}, date={result['starts_at']}")
        else:
            result["error"] = "Could not extract details — fill manually"
            
    except Exception as e:
        result["error"] = f"Scraping failed: {str(e)}"
    
    return result

async def fetch_webinar_from_url(url: str, settings: dict) -> dict:
    """Master fetch function — routes to correct platform fetcher."""
    platform = detect_platform(url)

    base_result = {
        "platform": platform,
        "title": "",
        "description": "",
        "starts_at": "",
        "speaker": "",
        "join_link": url,
        "attendees": [],
        "error": None,
    }

    if platform == "circle":
        api_key = settings.get("circle_api_key")
        if not api_key:
            # Try scraping as fallback
            scraped = await scrape_and_extract(url)
            scraped["platform"] = "circle"
            if not scraped.get("title"):
                scraped["error"] = "Circle API key not configured — add in Settings, or fill manually"
            return scraped
        try:
            result = await fetch_circle_event(url, api_key, settings=settings)
            # If Circle API didn't get title, try scraping
            if not result.get("title"):
                scraped = await scrape_and_extract(url)
                if scraped.get("title"):
                    result["title"] = scraped["title"]
                    result["description"] = result.get("description") or scraped.get("description", "")
                    result["starts_at"] = result.get("starts_at") or scraped.get("starts_at", "")
                    result["cover_image_url"] = result.get("cover_image_url") or scraped.get("cover_image_url", "")
            return result
        except Exception as e:
            scraped = await scrape_and_extract(url)
            scraped["platform"] = "circle"
            return scraped

    elif platform == "zoom":
        import re as _re2
        m = _re2.search(r'/j/(\d+)', url)
        if m:
            base_result["title"] = f"Zoom Meeting {m.group(1)}"
        base_result["error"] = "Zoom API not connected — title/date must be filled manually. Join link auto-set."
        return base_result

    elif platform == "google_meet":
        base_result["title"] = "Google Meet Session"
        base_result["error"] = "Fill title and date manually. Join link auto-set."
        return base_result

    elif platform == "teams":
        base_result["title"] = "Microsoft Teams Meeting"
        base_result["error"] = "Fill title and date manually. Join link auto-set."
        return base_result

    elif platform == "linkedin":
        import re as _re2
        m = _re2.search(r'/events/(\d+)', url)
        if m:
            base_result["linkedin_event_id"] = m.group(1)
        base_result["error"] = "LinkedIn detected — fill title, date and speaker manually. Join link has been set."
        return base_result

    elif platform == "eventbrite":
        return await fetch_eventbrite_event(url)

    elif platform == "luma":
        return await fetch_luma_event(url)

    else:
        # Try scraping for any unknown platform
        scraped = await scrape_and_extract(url)
        if scraped.get("title"):
            return scraped
        base_result["error"] = f"Platform detected — join link set. Fill remaining details manually."
        return base_result
