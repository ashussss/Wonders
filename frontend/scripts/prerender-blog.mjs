// Prerender published blog posts into static HTML after `craco build`.
// Crawlers that don't run JavaScript (GPTBot, PerplexityBot, ClaudeBot, LinkedIn, X) then see the full article.
// Humans still get the React app: it mounts over this HTML on load.
// This script must never fail the build.
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const SITE = "https://showupai.live";
const API = (process.env.REACT_APP_BACKEND_URL || "https://showup-backend-2bfj.onrender.com") + "/api";
const BUILD = path.resolve(process.cwd(), "build");

const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

async function getJSON(url, tries = 4) {
  for (let i = 0; i < tries; i++) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 70000); // Render can take ~60s to wake up
      const r = await fetch(url, { signal: ctrl.signal });
      clearTimeout(t);
      if (r.ok) return await r.json();
      console.log(`[prerender] ${url} -> HTTP ${r.status}`);
    } catch (e) {
      console.log(`[prerender] ${url} attempt ${i + 1} failed: ${e.message}`);
    }
    await new Promise((res) => setTimeout(res, 5000));
  }
  return null;
}

async function loadMarkdown() {
  // src/lib/markdown.js is ESM source inside a CommonJS package; load it through a temp .mjs copy.
  const src = fs.readFileSync(path.resolve("src/lib/markdown.js"), "utf8");
  const tmp = path.join(os.tmpdir(), `md-${Date.now()}.mjs`);
  fs.writeFileSync(tmp, src);
  return import(tmp);
}

function inlineHtml(md, text) {
  return md.splitInline(text).map((p) =>
    p.t === "b" ? `<strong>${esc(p.v)}</strong>`
    : p.t === "code" ? `<code>${esc(p.v)}</code>`
    : p.t === "a" ? `<a href="${esc(p.href)}" rel="noopener">${esc(p.v)}</a>`
    : esc(p.v)
  ).join("");
}

function bodyHtml(md, content) {
  return md.parseMarkdown(content).map((b) => {
    if (b.type === "h") return `<h${b.level}>${esc(b.text)}</h${b.level}>`;
    if (b.type === "p") return `<p>${inlineHtml(md, b.text)}</p>`;
    if (b.type === "code") return `<pre>${esc(b.text)}</pre>`;
    if (b.type === "table")
      return `<table><thead><tr>${b.head.map((c) => `<th>${inlineHtml(md, c)}</th>`).join("")}</tr></thead><tbody>${b.rows
        .map((r) => `<tr>${r.map((c) => `<td>${inlineHtml(md, c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    const tag = b.type === "ol" ? "ol" : "ul";
    return `<${tag}>${b.items.map((it) => `<li>${inlineHtml(md, it.text)}${it.children.length ? `<ul>${it.children.map((c) => `<li>${inlineHtml(md, c)}</li>`).join("")}</ul>` : ""}</li>`).join("")}</${tag}>`;
  }).join("\n");
}

function setHead(shell, { title, description, url, image, type, jsonld }) {
  let h = shell;
  const rep = (re, val) => { h = re.test(h) ? h.replace(re, val) : h.replace("</head>", `${val}\n</head>`); };
  rep(/<title>[\s\S]*?<\/title>/, `<title>${esc(title)}</title>`);
  rep(/<meta name="description"[^>]*>/, `<meta name="description" content="${esc(description)}" />`);
  rep(/<meta property="og:title"[^>]*>/, `<meta property="og:title" content="${esc(title)}" />`);
  rep(/<meta property="og:description"[^>]*>/, `<meta property="og:description" content="${esc(description)}" />`);
  rep(/<meta property="og:url"[^>]*>/, `<meta property="og:url" content="${esc(url)}" />`);
  rep(/<meta property="og:type"[^>]*>/, `<meta property="og:type" content="${type}" />`);
  rep(/<meta name="twitter:title"[^>]*>/, `<meta name="twitter:title" content="${esc(title)}" />`);
  rep(/<meta name="twitter:description"[^>]*>/, `<meta name="twitter:description" content="${esc(description)}" />`);
  if (image) {
    rep(/<meta property="og:image"[^>]*>/, `<meta property="og:image" content="${esc(image)}" />`);
    rep(/<meta name="twitter:image"[^>]*>/, `<meta name="twitter:image" content="${esc(image)}" />`);
  }
  rep(/<link rel="canonical"[^>]*>/, `<link rel="canonical" href="${esc(url)}" />`);
  if (jsonld) h = h.replace("</head>", `<script type="application/ld+json">${JSON.stringify(jsonld).replace(/</g, "\\u003c")}</script>\n</head>`);
  return h;
}

const STYLE = `<style>.pr{max-width:720px;margin:0 auto;padding:24px;font-family:system-ui,sans-serif;line-height:1.7;color:#111}
.pr img{max-width:100%;height:auto;border-radius:12px}.pr table{border-collapse:collapse;width:100%}.pr td,.pr th{border-bottom:1px solid #ddd;padding:6px;text-align:left}
.pr pre{white-space:pre-wrap;background:#f6f6f6;padding:12px;border-radius:8px}</style>`;

function withRoot(shell, html) {
  return shell.replace(/<div id="root"><\/div>/, `<div id="root">${STYLE}<div class="pr">${html}</div></div>`);
}

async function main() {
  const shellPath = path.join(BUILD, "index.html");
  if (!fs.existsSync(shellPath)) return console.log("[prerender] no build/index.html, skipping");
  const shell = fs.readFileSync(shellPath, "utf8");
  if (!shell.includes('<div id="root"></div>')) return console.log("[prerender] root div not found, skipping");

  const list = await getJSON(`${API}/blog`);
  if (!Array.isArray(list)) return console.log("[prerender] could not load posts, skipping (site still works client-side)");
  const md = await loadMarkdown();
  const posts = [];
  for (const item of list) {
    const p = await getJSON(`${API}/blog/${encodeURIComponent(item.slug)}`, 2);
    if (p && p.slug) posts.push(p);
  }

  const nav = `<p><a href="/">ShowUp.ai</a> · <a href="/blog">Blog</a></p>`;
  for (const p of posts) {
    const url = `${SITE}/blog/${p.slug}`;
    const image = `${API}/blog/${p.slug}/cover.png`;
    const desc = p.seo_description || p.meta_description || p.excerpt || "";
    const faqs = (p.faq_items || []).filter((f) => f.question && f.answer);
    const related = posts.filter((x) => x.slug !== p.slug).slice(0, 3);
    const person = p.author && p.author !== "ShowUp.ai Team";
    const graph = [
      {
        "@type": "Article", headline: p.title, description: desc, image, url,
        datePublished: p.published_at, dateModified: p.updated_at || p.published_at,
        author: person ? { "@type": "Person", name: p.author, description: p.author_bio, ...(p.author_url ? { url: p.author_url } : {}) }
                       : { "@type": "Organization", name: "ShowUp.ai" },
        publisher: { "@type": "Organization", name: "ShowUp.ai", url: SITE },
        mainEntityOfPage: url,
      },
      { "@type": "BreadcrumbList", itemListElement: [
        { "@type": "ListItem", position: 1, name: "Blog", item: `${SITE}/blog` },
        { "@type": "ListItem", position: 2, name: p.title, item: url } ] },
    ];
    if (faqs.length) graph.push({ "@type": "FAQPage", mainEntity: faqs.map((f) => ({
      "@type": "Question", name: f.question, acceptedAnswer: { "@type": "Answer", text: f.answer } })) });

    const html = `${nav}<article><h1>${esc(p.title)}</h1>
<p>${person ? `By ${esc(p.author)} · ` : ""}${esc((p.published_at || "").slice(0, 10))} · ${p.reading_time || 5} min read</p>
<img src="${esc(image)}" alt="${esc(p.title)}" width="1200" height="630" />
${bodyHtml(md, p.content || "")}
${faqs.length ? `<h2>Frequently asked questions</h2>${faqs.map((f) => `<h3>${esc(f.question)}</h3><p>${esc(f.answer)}</p>`).join("")}` : ""}
${person ? `<aside><p><strong>Written by ${esc(p.author)}</strong></p><p>${esc(p.author_bio || "")}</p></aside>` : ""}
${(p.sources || []).length ? `<p><strong>Sources:</strong> ${p.sources.map((s) => `<a href="${esc(s.url)}" rel="noopener">${esc(s.source)}</a>`).join(", ")}</p>` : ""}
${related.length ? `<h2>Related articles</h2><ul>${related.map((r) => `<li><a href="/blog/${esc(r.slug)}">${esc(r.title)}</a></li>`).join("")}</ul>` : ""}
<p><a href="/waitlist">Try ShowUp.ai free</a></p></article>`;

    const page = withRoot(setHead(shell, { title: p.seo_title || `${p.title} | ShowUp.ai`, description: desc, url, image, type: "article", jsonld: { "@context": "https://schema.org", "@graph": graph } }), html);
    const dir = path.join(BUILD, "blog", p.slug);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "index.html"), page);
  }

  const listHtml = `${nav}<h1>ShowUp.ai Blog</h1><p>Insights on webinars, attendance, and growing your audience.</p>
<ul>${posts.map((p) => `<li><a href="/blog/${esc(p.slug)}">${esc(p.title)}</a><p>${esc(p.excerpt || "")}</p></li>`).join("")}</ul>`;
  const listPage = withRoot(setHead(shell, { title: "Blog | ShowUp.ai — Webinar Attendance Insights",
    description: "Practical guides on webinar attendance, reminder sequences and no-show reduction from ShowUp.ai.",
    url: `${SITE}/blog`, type: "website",
    jsonld: { "@context": "https://schema.org", "@type": "Blog", name: "ShowUp.ai Blog", url: `${SITE}/blog`,
      blogPost: posts.map((p) => ({ "@type": "BlogPosting", headline: p.title, url: `${SITE}/blog/${p.slug}`, datePublished: p.published_at })) } }), listHtml);
  fs.mkdirSync(path.join(BUILD, "blog"), { recursive: true });
  fs.writeFileSync(path.join(BUILD, "blog", "index.html"), listPage);
  console.log(`[prerender] wrote ${posts.length} post pages + blog index`);
}

main().catch((e) => console.log("[prerender] error (ignored):", e.message)).finally(() => process.exit(0));
