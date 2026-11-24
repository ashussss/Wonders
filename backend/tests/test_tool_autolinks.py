import pseo

HOME = pseo.SITE_URL


def test_blog_posts_link_to_free_tools_once_and_idempotently():
    md = ("## Intro\n\nYour webinar attendance rate tells you how many registrants joined. "
          "A low attendance rate is common.\n\n## ROI\n\nWork out your webinar ROI before the next event.\n")
    out = pseo.autolink(md, "x", [])
    assert out.count(f"]({HOME}/tools/webinar-no-show-calculator)") == 1
    assert out.count(f"]({HOME}/tools/webinar-roi-calculator)") == 1
    assert pseo.autolink(out, "x", []) == out


def test_tool_links_capped_at_two_per_post():
    md = ("No-show rate matters. Webinar ROI matters. "
          "Here is how to increase webinar attendance and pick a webinar title.\n")
    out = pseo.autolink(md, "x", [])
    tool_urls = [u for u, _ in pseo.TOOL_LINKS]
    assert sum(out.count(f"]({HOME}{u})") for u in tool_urls) == 2
