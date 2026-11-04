import re
from pathlib import Path

import pseo

SEO_JS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "seoPages.js"


def _keys(block_name: str) -> set:
    src = SEO_JS.read_text()
    block = src.split(f"export const {block_name} = {{", 1)[1]
    # top-level keys are indented by exactly two spaces
    return set(re.findall(r'^  "?([a-z0-9-]+)"?: \{', block.split("\n};", 1)[0], re.M))


def test_sitemap_lists_every_compare_and_tool_page():
    pages = set(pseo.SEO_PAGES)
    for k in _keys("COMPARE"):
        assert f"/compare/{k}" in pages, k
    for k in _keys("TOOLS"):
        assert f"/tools/{k}" in pages, k
    assert {"/compare", "/tools", "/webinar-attendance"} <= pages
    assert len(pages) == len(pseo.SEO_PAGES)
