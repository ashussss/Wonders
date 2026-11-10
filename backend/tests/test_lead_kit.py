from datetime import datetime, timezone

import lead_kit


def test_fallback_kit_is_complete_and_mentions_the_webinar():
    kit = lead_kit.assemble("Pricing Teardown Live", "Tue 1 Dec, 7:00 PM", "SaaS founders",
                            lead_kit.parse_start("2026-12-01T19:00"), {})
    assert [i["key"] for i in kit] == lead_kit.KIT_KEYS
    assert all("Pricing Teardown Live" in (i["body"] + i["subject"]) for i in kit)
    assert all(i["subject"] for i in kit if i["channel"] == "Email")
    assert not any(i["ai"] for i in kit)
    live = next(i for i in kit if i["key"] == "live_now")
    assert len(live["body"]) <= 160


def test_send_times_follow_the_start_time():
    start = datetime(2026, 12, 1, 19, 0, tzinfo=timezone.utc)
    kit = {i["key"]: i for i in lead_kit.assemble("X webinar", "w", "", start, {})}
    assert kit["confirmation"]["send_at"] is None
    assert kit["day_before"]["send_at"].startswith("2026-11-30T19:00")
    assert kit["hour_before"]["send_at"].startswith("2026-12-01T18:00")
    assert kit["replay"]["send_at"].startswith("2026-12-02T13:00")


def test_parse_llm_keeps_good_items_and_drops_bad_ones():
    raw = ('Sure! {"items": {"confirmation": {"subject": "You are in", "body": "Hi {first_name}, you are registered for X."},'
           ' "live_now": {"body": "short"}, "nope": {"body": "ignored because unknown key here"}}}')
    got = lead_kit.parse_llm(raw)
    assert set(got) == {"confirmation"}
    kit = {i["key"]: i for i in lead_kit.assemble("X", "w", "", None, got)}
    assert kit["confirmation"]["ai"] and kit["confirmation"]["subject"] == "You are in"
    assert not kit["live_now"]["ai"]  # too short -> template copy
    assert lead_kit.parse_llm("{}") == {} and lead_kit.parse_llm("not json") == {}


def test_inputs_are_cleaned_and_dates_are_readable():
    assert lead_kit.clean("  a \n  b  ", 10) == "a b"
    assert lead_kit.clean("x" * 50, 5) == "xxxxx"
    assert lead_kit.when_text("2026-12-01T19:05") == "Tue 1 Dec, 7:05 PM"
    assert lead_kit.when_text("") == "the scheduled time"
    assert lead_kit.parse_start("garbage") is None


def test_email_escapes_user_text():
    items = lead_kit.assemble("<script>x</script>", "w", "", None, {})
    out = lead_kit.email_html("<b>Bo</b>", "<script>x</script>", "w", items, "https://showupai.live")
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "https://showupai.live/register" in out
