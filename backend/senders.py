"""Outbound delivery functions for ShowUp.ai. Reads per-user settings from MongoDB."""
from __future__ import annotations
import base64
import logging
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger("showup.senders")

META_GRAPH_URL = "https://graph.facebook.com/v25.0"


class DeliveryResult(dict):
    def __init__(self, ok: bool, provider: str, detail: str = "", external_id: Optional[str] = None):
        super().__init__(ok=ok, provider=provider, detail=detail, external_id=external_id)



def build_email_html(body: str, subject: str = "", sender_name: str = "ShowUp.ai",
                     unsubscribe_url: str = "") -> str:
    """Wrap plain text body in a clean branded HTML email template."""
    # Convert newlines to <br> and handle placeholders
    html_body = body.replace("\n", "<br>")
    
    unsub_html = ""
    if unsubscribe_url:
        unsub_html = f'''<tr><td style="padding:16px 32px;text-align:center;border-top:1px solid #f0f0f0;">
          <p style="color:#9ca3af;font-size:11px;margin:0;">
            You're receiving this because you registered for a webinar.<br>
            <a href="{unsubscribe_url}" style="color:#9ca3af;">Unsubscribe</a>
          </p>
        </td></tr>'''
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
        <!-- Header -->
        <tr><td style="background:#EA580C;padding:20px 32px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:-0.5px;">
                ⚡ {sender_name}
              </td>
            </tr>
          </table>
        </td></tr>
        <!-- Body -->
        <tr><td style="padding:32px 32px 24px;color:#111827;font-size:16px;line-height:1.7;">
          {html_body}
        </td></tr>
        <!-- Footer -->
        {unsub_html}
      </table>
    </td></tr>
  </table>
</body>
</html>"""

# ---------------- Brevo email ----------------
async def send_brevo_email(settings: Dict[str, Any], to_email: str, subject: str, html: str,
                           ics_bytes: Optional[bytes] = None) -> DeliveryResult:
    api_key = settings.get("brevo_api_key")
    sender = settings.get("brevo_sender_email")
    if not api_key and not sender:
        return DeliveryResult(False, "brevo", "Missing brevo_api_key and brevo_sender_email — add both in Settings → Email provider")
    if not api_key:
        return DeliveryResult(False, "brevo", "Missing brevo_api_key — add it in Settings → Email provider")
    if not sender:
        return DeliveryResult(False, "brevo", "Missing brevo_sender_email — add a verified sender email in Settings → Email provider")
    sender_name = settings.get("brevo_sender_name") or "ShowUp.ai"
    # Wrap in branded template if plain text passed
    if html and not html.strip().startswith("<!DOCTYPE") and not html.strip().startswith("<html"):
        html = build_email_html(html, subject=subject, sender_name=sender_name)
    payload: Dict[str, Any] = {
        "sender": {"email": sender, "name": sender_name},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html,
    }
    if ics_bytes:
        payload["attachment"] = [{
            "name": "invite.ics",
            "content": base64.b64encode(ics_bytes).decode("ascii"),
        }]
    headers = {"api-key": api_key, "accept": "application/json", "content-type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.brevo.com/v3/smtp/email", json=payload, headers=headers)
        if r.status_code >= 400:
            return DeliveryResult(False, "brevo", f"{r.status_code}: {r.text[:200]}")
        data = r.json()
        return DeliveryResult(True, "brevo", external_id=data.get("messageId"))
    except Exception as e:
        return DeliveryResult(False, "brevo", str(e))


# ---------------- SendGrid email ----------------
async def send_sendgrid_email(settings: Dict[str, Any], to_email: str, subject: str, html: str,
                              ics_bytes: Optional[bytes] = None) -> DeliveryResult:
    api_key = settings.get("sendgrid_api_key")
    sender = settings.get("sendgrid_sender_email")
    name = settings.get("sendgrid_sender_name") or "ShowUp.ai"
    if not api_key:
        return DeliveryResult(False, "sendgrid", "Missing sendgrid_api_key — add it in Settings → Email provider")
    if not sender:
        return DeliveryResult(False, "sendgrid", "Missing sendgrid_sender_email — add a verified sender email in Settings → Email provider")
    if html and not html.strip().startswith("<!DOCTYPE") and not html.strip().startswith("<html"):
        html = build_email_html(html, subject=subject, sender_name=name)
    payload: Dict[str, Any] = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": sender, "name": name},
        "subject": subject,
        "content": [{"type": "text/html", "value": html}],
    }
    if ics_bytes:
        payload["attachments"] = [{
            "filename": "invite.ics",
            "type": "text/calendar",
            "content": base64.b64encode(ics_bytes).decode("ascii"),
        }]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers)
        if r.status_code >= 400:
            return DeliveryResult(False, "sendgrid", f"{r.status_code}: {r.text[:200]}")
        return DeliveryResult(True, "sendgrid", external_id=r.headers.get("X-Message-Id"))
    except Exception as e:
        return DeliveryResult(False, "sendgrid", str(e))


# ---------------- Mailchimp Transactional (Mandrill) ----------------
async def send_mailchimp_email(settings: Dict[str, Any], to_email: str, subject: str, html: str,
                               ics_bytes: Optional[bytes] = None) -> DeliveryResult:
    api_key = settings.get("mailchimp_api_key")
    sender = settings.get("mailchimp_sender_email")
    name = settings.get("mailchimp_sender_name") or "ShowUp.ai"
    if not api_key:
        return DeliveryResult(False, "mailchimp", "Missing mailchimp_api_key — add it in Settings → Email provider")
    if not sender:
        return DeliveryResult(False, "mailchimp", "Missing mailchimp_sender_email — add a verified sender email in Settings → Email provider")
    payload: Dict[str, Any] = {
        "key": api_key,
        "message": {
            "html": html,
            "subject": subject,
            "from_email": sender,
            "from_name": name,
            "to": [{"email": to_email, "type": "to"}],
        }
    }
    if ics_bytes:
        payload["message"]["attachments"] = [{
            "type": "text/calendar",
            "name": "invite.ics",
            "content": base64.b64encode(ics_bytes).decode("ascii"),
        }]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://mandrillapp.com/api/1.0/messages/send.json", json=payload)
        if r.status_code >= 400:
            return DeliveryResult(False, "mailchimp", f"{r.status_code}: {r.text[:200]}")
        # Mandrill returns a list of {email, status, _id, reject_reason}
        data = r.json()
        if isinstance(data, list) and data and data[0].get("status") in ("sent", "queued", "scheduled"):
            return DeliveryResult(True, "mailchimp", external_id=data[0].get("_id"))
        return DeliveryResult(False, "mailchimp", str(data)[:200])
    except Exception as e:
        return DeliveryResult(False, "mailchimp", str(e))


async def send_email(settings: Dict[str, Any], to_email: str, subject: str, html: str,
                     ics_bytes: Optional[bytes] = None) -> DeliveryResult:
    """Route to the user's selected email provider."""
    provider = (settings.get("email_provider") or "Brevo").strip().lower()
    if provider == "sendgrid":
        return await send_sendgrid_email(settings, to_email, subject, html, ics_bytes=ics_bytes)
    if provider == "mailchimp":
        return await send_mailchimp_email(settings, to_email, subject, html, ics_bytes=ics_bytes)
    if provider == "buzzai":
        return await send_buzzai_email(settings, to_email, subject, html, ics_bytes=ics_bytes)
    return await send_brevo_email(settings, to_email, subject, html, ics_bytes=ics_bytes)


# ---------------- Meta Facebook Page ----------------
async def post_facebook_page(settings: Dict[str, Any], message: str,
                                scheduled_time: int = None, image_url: str = None) -> DeliveryResult:
    """Post to Facebook Page — supports scheduled publishing and image attachment."""
    token = settings.get("meta_graph_token")
    page_id = settings.get("meta_page_id")
    if not token or not page_id:
        return DeliveryResult(False, "facebook", "Missing meta_graph_token or meta_page_id")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            payload = {"message": message, "access_token": token}

            if scheduled_time:
                # Schedule for future — must be 10min to 30 days in future
                payload["published"] = "false"
                payload["scheduled_publish_time"] = str(scheduled_time)
            else:
                payload["published"] = "true"

            if image_url:
                # Post with image link
                payload["link"] = image_url

            r = await client.post(f"{META_GRAPH_URL}/{page_id}/feed", data=payload)

        if r.status_code >= 400:
            return DeliveryResult(False, "facebook", f"{r.status_code}: {r.text[:200]}")
        post_id = r.json().get("id")
        status = "scheduled" if scheduled_time else "published"
        return DeliveryResult(True, "facebook", external_id=post_id, note=status)
    except Exception as e:
        return DeliveryResult(False, "facebook", str(e))


# ---------------- Meta Instagram ----------------
async def post_instagram(settings: Dict[str, Any], caption: str, image_url: Optional[str] = None) -> DeliveryResult:
    token = settings.get("meta_graph_token")
    ig_id = settings.get("instagram_business_id")
    if not token or not ig_id:
        return DeliveryResult(False, "instagram", "Missing meta_graph_token or instagram_business_id")
    if not image_url:
        # IG requires media; v1 limitation when caller doesn't supply an image
        return DeliveryResult(False, "instagram", "Instagram requires an image_url — caption-only posts are not supported by IG Graph API")
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            c = await client.post(f"{META_GRAPH_URL}/{ig_id}/media",
                                   data={"caption": caption, "image_url": image_url, "access_token": token})
            if c.status_code >= 400:
                return DeliveryResult(False, "instagram", f"create:{c.status_code}: {c.text[:200]}")
            cid = c.json().get("id")
            p = await client.post(f"{META_GRAPH_URL}/{ig_id}/media_publish",
                                   data={"creation_id": cid, "access_token": token})
            if p.status_code >= 400:
                return DeliveryResult(False, "instagram", f"publish:{p.status_code}: {p.text[:200]}")
            return DeliveryResult(True, "instagram", external_id=p.json().get("id"))
    except Exception as e:
        return DeliveryResult(False, "instagram", str(e))


# ---------------- Twilio WhatsApp / SMS ----------------
async def send_twilio(settings: Dict[str, Any], to_e164: str, body: str, prefer_whatsapp: bool = True) -> DeliveryResult:
    sid = settings.get("twilio_sid")
    token = settings.get("twilio_token")
    frm = settings.get("twilio_from")
    if not (sid and token and frm):
        return DeliveryResult(False, "whatsapp", "Missing twilio_sid / twilio_token / twilio_from")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    if prefer_whatsapp:
        from_addr = frm if frm.startswith("whatsapp:") else f"whatsapp:{frm}"
        to_addr = to_e164 if to_e164.startswith("whatsapp:") else f"whatsapp:{to_e164}"
    else:
        from_addr = frm.replace("whatsapp:", "")
        to_addr = to_e164.replace("whatsapp:", "")
    data = {"From": from_addr, "To": to_addr, "Body": body}
    try:
        async with httpx.AsyncClient(timeout=30, auth=(sid, token)) as client:
            r = await client.post(url, data=data)
        if r.status_code >= 400:
            if prefer_whatsapp:
                # fall back to SMS
                return await send_twilio(settings, to_e164, body, prefer_whatsapp=False)
            return DeliveryResult(False, "twilio", f"{r.status_code}: {r.text[:200]}")
        return DeliveryResult(True, "whatsapp" if prefer_whatsapp else "sms", external_id=r.json().get("sid"))
    except Exception as e:
        return DeliveryResult(False, "twilio", str(e))


async def _circle_request(token: str, method: str, path: str, *, json_body=None, params=None,
                          base_override: Optional[str] = None) -> tuple[int, str, Dict[str, Any], str]:
    """Single Circle.so HTTP call with Bearer→Token + US→EU base auto-fallback on 401.

    Returns (status_code, response_text, response_json_or_empty, scheme_used).
    """
    bases = [base_override.rstrip("/")] if base_override else [
        "https://app.circle.so", "https://eu.app.circle.so",
    ]
    redacted = (token[:4] + "…" + token[-4:]) if token and len(token) > 8 else "(empty)"
    last_err = ""
    last_status = 401
    last_text = ""
    for base in bases:
        url = f"{base}{path}"
        for scheme in ("Bearer", "Token"):
            headers = {"Authorization": f"{scheme} {token}", "Accept": "application/json"}
            if json_body is not None:
                headers["Content-Type"] = "application/json"
            logger.info(f"Circle request → {method} {url} | scheme={scheme} token={redacted} "
                        f"params={params} body_keys={list(json_body.keys()) if json_body else None}")
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.request(method, url, headers=headers, json=json_body, params=params)
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                logger.warning(f"Circle request failed: {e}")
                continue
            logger.info(f"Circle response ← {r.status_code} | base={base} scheme={scheme} | "
                        f"body[:200]={r.text[:200]}")
            last_status, last_text = r.status_code, r.text
            if r.status_code == 401:
                continue  # try next scheme / next base
            try:
                data = r.json() if r.text else {}
            except Exception:  # noqa: BLE001
                data = {}
            return r.status_code, r.text, data, f"{scheme} @ {base.rsplit('//',1)[-1]}"
    return last_status, last_text or last_err or "All combinations returned 401", {}, "none"


# ---------------- Circle.so post to space (Admin API v2) ----------------
def _circle_tiptap_body(text: str) -> Dict[str, Any]:
    lines = (text or "").split("\n")
    content: list = []
    for i, line in enumerate(lines):
        if line:
            content.append({"type": "text", "text": line})
        if i < len(lines) - 1:
            content.append({"type": "hardBreak"})
    return {
        "body": {
            "type": "doc",
            "content": [{"type": "paragraph", "content": content or [{"type": "text", "text": ""}]}],
        }
    }


async def post_circle_space(settings: Dict[str, Any], title: str, body: str) -> DeliveryResult:
    api_key = settings.get("circle_api_key")
    space_id = settings.get("circle_space_id")
    if not api_key:
        return DeliveryResult(False, "circle", "Missing circle_api_key — add it in Settings → Circle.so")
    if not space_id:
        return DeliveryResult(False, "circle", "Missing circle_space_id — add the numeric Space ID in Settings → Circle.so")
    try:
        space_id_int = int(str(space_id).strip())
    except ValueError:
        return DeliveryResult(False, "circle", f"circle_space_id must be a number, got: {space_id!r}")
    payload = {
        "space_id": space_id_int,
        "name": (title or "Webinar announcement")[:120],
        "status": "published",
        "tiptap_body": _circle_tiptap_body(body),
    }
    status, text, data, scheme = await _circle_request(api_key, "POST", "/api/admin/v2/posts",
                                                        json_body=payload)
    if status >= 400:
        # Surface the full Circle error verbatim so the user can debug
        hint = ""
        if status == 401:
            hint = (" — token rejected by both Bearer and Token schemes. Confirm you copied an "
                    "Admin v2 API token from Circle → Settings → Developers → Tokens (NOT a "
                    "Headless Auth token, NOT an Admin v1 token, NOT a Data API token).")
        elif status == 404:
            hint = " — space_id may not exist in this community, or this space doesn't accept posts (try a 'Posts' type space)."
        elif status == 422:
            hint = " — TipTap body rejected; try a shorter title or simpler body."
        return DeliveryResult(False, "circle", f"{status}: {text[:400]}{hint}")
    return DeliveryResult(True, "circle", external_id=str(data.get("id", "")))


# ---------------- Buzz.ai (configurable custom endpoint) ----------------
async def send_buzzai(settings: Dict[str, Any], kind: str, body_payload: Dict[str, Any]) -> DeliveryResult:
    """Buzz.ai has no documented public outreach API. The user pastes the endpoint URL +
    auth header they got from Buzz.ai support; we POST JSON to it.
    kind: 'email' or 'linkedin'.
    """
    api_key = settings.get("buzzai_api_key")
    endpoint = settings.get(f"buzzai_{kind}_endpoint")
    if not api_key:
        return DeliveryResult(False, f"buzzai_{kind}", "Missing buzzai_api_key — add it in Settings → Buzz.ai")
    if not endpoint:
        return DeliveryResult(False, f"buzzai_{kind}",
                              f"Missing buzzai_{kind}_endpoint URL — paste the URL Buzz.ai support gave you in Settings → Buzz.ai")
    header_name = settings.get("buzzai_auth_header_name") or "Authorization"
    header_prefix = settings.get("buzzai_auth_header_prefix")
    if header_prefix is None:
        header_prefix = "Bearer "
    headers = {header_name: f"{header_prefix}{api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(endpoint, json=body_payload, headers=headers)
        if r.status_code >= 400:
            return DeliveryResult(False, f"buzzai_{kind}", f"{r.status_code}: {r.text[:200]}")
        try:
            ext_id = str(r.json().get("id", ""))
        except Exception:
            ext_id = None
        return DeliveryResult(True, f"buzzai_{kind}", external_id=ext_id)
    except Exception as e:
        return DeliveryResult(False, f"buzzai_{kind}", str(e))


async def send_buzzai_email(settings: Dict[str, Any], to_email: str, subject: str, html: str,
                            ics_bytes: Optional[bytes] = None) -> DeliveryResult:
    body_payload: Dict[str, Any] = {"to": to_email, "subject": subject, "html": html}
    if ics_bytes:
        body_payload["attachments"] = [{
            "filename": "invite.ics",
            "content_type": "text/calendar",
            "content_b64": base64.b64encode(ics_bytes).decode("ascii"),
        }]
    return await send_buzzai(settings, "email", body_payload)
async def post_linkedin_company(settings: Dict[str, Any], message: str) -> DeliveryResult:
    token = settings.get("linkedin_marketing_token")
    org_urn = settings.get("linkedin_org_urn")
    if not token or not org_urn:
        return DeliveryResult(False, "linkedin", "Missing linkedin_marketing_token or linkedin_org_urn")
    payload = {
        "author": org_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": message},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    headers = {"Authorization": f"Bearer {token}",
               "X-Restli-Protocol-Version": "2.0.0",
               "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.linkedin.com/v2/ugcPosts", json=payload, headers=headers)
        if r.status_code >= 400:
            return DeliveryResult(False, "linkedin", f"{r.status_code}: {r.text[:200]}")
        return DeliveryResult(True, "linkedin", external_id=r.headers.get("x-restli-id"))
    except Exception as e:
        return DeliveryResult(False, "linkedin", str(e))


# Dispatcher: takes channel name + the body/subject and routes to the right provider.
async def dispatch(channel: str, settings: Dict[str, Any], to_email: Optional[str], to_phone: Optional[str],
                   subject: str, body: str, ics_bytes: Optional[bytes] = None,
                   image_url: Optional[str] = None) -> DeliveryResult:
    if channel == "email":
        if not to_email:
            return DeliveryResult(False, "email", "No recipient email")
        return await send_email(settings, to_email, subject, body.replace("\n", "<br/>"), ics_bytes=ics_bytes)
    if channel == "facebook":
        return await post_facebook_page(settings, body)
    if channel == "instagram":
        return await post_instagram(settings, body, image_url=image_url)
    if channel == "linkedin":
        # Per-channel provider routing: marketing_api (default) or buzzai
        provider = (settings.get("linkedin_provider") or "marketing_api").strip().lower()
        if provider == "buzzai":
            return await send_buzzai(settings, "linkedin", {"text": body, "subject": subject})
        return await post_linkedin_company(settings, body)
    if channel == "linkedin_personal":
        return DeliveryResult(False, "linkedin_personal", "Manual copy-paste only — no auto-post allowed")
    if channel == "whatsapp":
        if not to_phone:
            return DeliveryResult(False, "whatsapp", "No recipient phone")
        return await send_twilio(settings, to_phone, body, prefer_whatsapp=True)
    if channel == "circle":
        return await post_circle_space(settings, subject, body)
    return DeliveryResult(False, channel, "Unknown channel")
