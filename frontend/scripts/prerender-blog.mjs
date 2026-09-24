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
  return md.parseMarkdown(content).map((b, i) => {
    if (b.type === "h") return `<h${b.level} id="${esc(md.headingId(b.text))}">${esc(b.text)}</h${b.level}>`;
    if (b.type === "p" && i === 0) return `<div class="qa"><p><strong>Quick answer:</strong> ${inlineHtml(md, b.text)}</p></div>`;
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
.pr pre{white-space:pre-wrap;background:#f6f6f6;padding:12px;border-radius:8px}
.pr .qa{background:#f6f6f6;border-left:4px solid #EA580C;padding:4px 16px;border-radius:8px}</style>`;

function withRoot(shell, html) {
  return shell.replace(/<div id="root"><\/div>/, `<div id="root">${STYLE}<div class="pr">${html}</div></div>`);
}

function graphFrom(shell) {
  const m = shell.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
  try { return JSON.parse(m[1])["@graph"] || []; } catch (e) { return []; }
}

function homeHtml(graph, posts) {
  const app = graph.find((n) => n["@type"] === "SoftwareApplication") || {};
  const faq = (graph.find((n) => n["@type"] === "FAQPage") || {}).mainEntity || [];
  const offers = ((app.offers || {}).offers) || [];
  return `<header><p><a href="/">ShowUpAI</a> · <a href="/blog">Blog</a> · <a href="/about">About</a> · <a href="/waitlist">Start free trial</a></p></header>
<main>
<h1>Make people actually show up for your webinar</h1>
<p class="hero-description">${esc(app.description || "")}</p>
<p><a href="/waitlist">Start your 14-day free trial</a> (no card required)</p>
<h2>How ShowUpAI works</h2>
<ol><li>Add your webinar (paste the event URL or enter the details).</li><li>ShowUpAI builds an 11-touch send plan and writes the copy for every channel, in two variants.</li><li>You review, edit and approve. Nothing sends without approval.</li><li>Approved touches go out on schedule; see attendance by channel afterwards.</li></ol>
<h2>The 11-touch sequence</h2>
<ol><li>Registration confirmation + calendar invite (on registration)</li><li>Awareness post (21 days before)</li><li>Newsletter / insight (19 days before)</li><li>Engagement poll (14 days before)</li><li>Case study (10 days before)</li><li>Infographic teaser (8 days before)</li><li>Urgency message (5 days before)</li><li>Final warm-up (1 day before)</li><li>Join link (1 hour before)</li><li>Thank-you for attendees (after the event)</li><li>No-show follow-up (2 days after)</li></ol>
<h2>Features</h2>
<ul>${(app.featureList || []).map((f) => `<li>${esc(f)}</li>`).join("")}</ul>
<h2>Pricing</h2>
<ul>${offers.map((o) => `<li><strong>${esc(o.name)}</strong>: $${esc(o.price)}/month. ${esc(o.description)}</li>`).join("")}</ul>
<h2>Frequently asked questions</h2>
${faq.map((q) => `<h3>${esc(q.name)}</h3><p>${esc((q.acceptedAnswer || {}).text || "")}</p>`).join("\n")}
${posts && posts.length ? `<h2>Latest from the blog</h2><ul>${posts.slice(0, 6).map((p) => `<li><a href="/blog/${esc(p.slug)}">${esc(p.title)}</a></li>`).join("")}</ul>` : ""}
</main>
<footer><p>© ShowUpAI · <a href="/about">About</a> · <a href="/blog">Blog</a> · <a href="mailto:hello@showupai.live">hello@showupai.live</a></p></footer>`;
}

function aboutHtml() {
  return `<header><p><a href="/">ShowUpAI</a> · <a href="/blog">Blog</a> · <a href="/about">About</a></p></header>
<main><h1>About ShowUpAI</h1>
<p>ShowUpAI is webinar attendance software. It exists for one reason: to make the people who register for your webinar actually show up.</p>
<h2>What we do</h2><p>You add a webinar, and ShowUpAI writes, schedules and sends an 11-touch reminder sequence across email, LinkedIn, Facebook, Instagram, WhatsApp/SMS, Circle.so and calendar invites. It starts three weeks before the event with value-led touches, moves to urgency and the join link, and ends with separate follow-ups for attendees and no-shows. You approve every message before it goes out.</p>
<p>ShowUpAI works alongside whichever webinar platform you already use, including Zoom, Microsoft Teams, Google Meet, Livestorm, Circle.so events, Eventbrite and Luma.</p>
<h2>Why we built it</h2><p>Running webinars for B2B and education communities, we kept seeing a good topic, a good speaker, plenty of registrations and a mostly empty room. The difference was what happened between sign-up and start time. ShowUpAI automates that part.</p>
<h2>Who's behind it</h2><p>ShowUpAI is built by Ashutosh Kumar Singh, a B2B marketer with 13+ years across SEO, content, demand generation and events.</p>
<h2>Facts</h2><ul><li>Product: webinar attendance software (web app)</li><li>Website: <a href="https://showupai.live">showupai.live</a></li><li>Launched: 2026</li><li>Plans: Starter $29/month, Growth $79/month, Agency $199/month; 14-day free trial, no card required</li><li>Contact: <a href="mailto:hello@showupai.live">hello@showupai.live</a></li></ul>
<p><a href="/waitlist">Increase my attendance</a> · <a href="/blog">Read the blog</a></p></main>`;
}

async function main() {
  const shellPath = path.join(BUILD, "index.html");
  const cleanPath = path.join(BUILD, "app-shell.html");
  if (!fs.existsSync(shellPath)) return console.log("[prerender] no build/index.html, skipping");
  // Re-runs start from the clean shell saved by the first run
  const shell = fs.readFileSync(fs.existsSync(cleanPath) ? cleanPath : shellPath, "utf8");
  if (!shell.includes('<div id="root"></div>')) return console.log("[prerender] root div not found, skipping");
  // Clean SPA shell for every non-prerendered route (/_redirects: /* -> /app-shell.html)
  fs.writeFileSync(path.join(BUILD, "app-shell.html"), shell);

  const list = await getJSON(`${API}/blog`);
  const graph = graphFrom(shell);

  // Homepage + About: static, crawler-readable HTML (React mounts over it for humans)
  // Hide the static copy from JS-enabled browsers (the dark landing page renders over it) to avoid a flash;
  // crawlers without JavaScript still read the full text in the HTML.
  const homeShell = shell.replace("</head>", `<script>document.documentElement.classList.add("js")</script><style>html.js #root > .pr, html.js #root > style{display:none}</style>\n</head>`);
  fs.writeFileSync(shellPath, withRoot(homeShell, homeHtml(graph, Array.isArray(list) ? list : [])));
  const aboutPage = withRoot(setHead(shell, {
    title: "About ShowUpAI — Webinar Attendance Software",
    description: "ShowUpAI is webinar attendance software built to make registrants actually show up. What it does, why it exists, who builds it, and the facts.",
    url: `${SITE}/about`, image: `${SITE}/og-image.png`, type: "website",
    jsonld: { "@context": "https://schema.org", "@type": "AboutPage", "@id": `${SITE}/about#webpage`, url: `${SITE}/about`,
      name: "About ShowUpAI", about: { "@id": `${SITE}/#organization` }, isPartOf: { "@id": `${SITE}/#website` } },
  }), aboutHtml());
  fs.mkdirSync(path.join(BUILD, "about"), { recursive: true });
  fs.writeFileSync(path.join(BUILD, "about", "index.html"), aboutPage);
  console.log("[prerender] wrote homepage + about + app-shell");

  if (!Array.isArray(list)) return console.log("[prerender] could not load posts, skipping blog pages (site still works client-side)");
  const md = await loadMarkdown();
  const posts = [];
  for (const item of list) {
    const p = await getJSON(`${API}/blog/${encodeURIComponent(item.slug)}`, 2);
    if (p && p.slug) posts.push(p);
  }

  const nav = `<p><a href="/">ShowUpAI</a> · <a href="/blog">Blog</a></p>`;
  for (const p of posts) {
    const url = `${SITE}/blog/${p.slug}`;
    const image = `${API}/blog/${p.slug}/cover.png`;
    const desc = p.seo_description || p.meta_description || p.excerpt || "";
    const faqs = (p.faq_items || []).filter((f) => f.question && f.answer);
    const related = posts.filter((x) => x.slug !== p.slug).slice(0, 3);
    const person = p.author && p.author !== "ShowUpAI Team";
    const graph = [
      {
        "@type": "Article", headline: p.title, description: desc, image, url,
        datePublished: p.published_at, dateModified: p.updated_at || p.published_at,
        author: person ? { "@type": "Person", name: p.author, description: p.author_bio, ...(p.author_url ? { url: p.author_url } : {}) }
                       : { "@type": "Organization", name: "ShowUpAI" },
        publisher: { "@type": "Organization", name: "ShowUpAI", url: SITE },
        mainEntityOfPage: url,
      },
      { "@type": "BreadcrumbList", itemListElement: [
        { "@type": "ListItem", position: 1, name: "Blog", item: `${SITE}/blog` },
        { "@type": "ListItem", position: 2, name: p.title, item: url } ] },
    ];
    if (faqs.length) graph.push({ "@type": "FAQPage", mainEntity: faqs.map((f) => ({
      "@type": "Question", name: f.question, acceptedAnswer: { "@type": "Answer", text: f.answer } })) });

    const html = `${nav}<article><h1>${esc(p.title)}</h1>
<p>${person ? `By ${esc(p.author)} · ` : ""}Published <time datetime="${esc(p.published_at || "")}">${esc((p.published_at || "").slice(0, 10))}</time>${p.updated_at && (p.updated_at || "").slice(0, 10) !== (p.published_at || "").slice(0, 10) ? ` · Updated <time datetime="${esc(p.updated_at)}">${esc(p.updated_at.slice(0, 10))}</time>` : ""} · ${p.reading_time || 5} min read</p>
<img src="${esc(image)}" alt="${esc(p.title)}" width="1200" height="630" />
${(() => { const toc = md.tocFrom(p.content || ""); return toc.length >= 3 ? `<nav aria-label="Table of contents"><p><strong>In this article</strong></p><ol>${toc.map((t) => `<li><a href="#${esc(t.id)}">${esc(t.text)}</a></li>`).join("")}</ol></nav>` : ""; })()}
${bodyHtml(md, p.content || "")}
${faqs.length ? `<h2>Frequently asked questions</h2>${faqs.map((f) => `<h3>${esc(f.question)}</h3><p>${esc(f.answer)}</p>`).join("")}` : ""}
${person ? `<aside><p><strong>Written by ${esc(p.author)}</strong></p><p>${esc(p.author_bio || "")}</p></aside>` : ""}
${(p.sources || []).length ? `<p><strong>Sources:</strong> ${p.sources.map((s) => `<a href="${esc(s.url)}" rel="noopener">${esc(s.source)}</a>`).join(", ")}</p>` : ""}
${related.length ? `<h2>Related articles</h2><ul>${related.map((r) => `<li><a href="/blog/${esc(r.slug)}">${esc(r.title)}</a></li>`).join("")}</ul>` : ""}
<p><a href="/waitlist">Try ShowUpAI free</a></p></article>`;

    const page = withRoot(setHead(shell, { title: p.seo_title || `${p.title} | ShowUpAI`, description: desc, url, image, type: "article", jsonld: { "@context": "https://schema.org", "@graph": graph } }), html);
    const dir = path.join(BUILD, "blog", p.slug);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "index.html"), page);
  }

  const listHtml = `${nav}<h1>ShowUpAI Blog</h1><p>Insights on webinars, attendance, and growing your audience.</p>
<ul>${posts.map((p) => `<li><a href="/blog/${esc(p.slug)}">${esc(p.title)}</a><p>${esc(p.excerpt || "")}</p></li>`).join("")}</ul>`;
  const listPage = withRoot(setHead(shell, { title: "Blog | ShowUpAI — Webinar Attendance Insights",
    description: "Practical guides on webinar attendance, reminder sequences and no-show reduction from ShowUpAI.",
    url: `${SITE}/blog`, type: "website",
    jsonld: { "@context": "https://schema.org", "@type": "Blog", name: "ShowUpAI Blog", url: `${SITE}/blog`,
      blogPost: posts.map((p) => ({ "@type": "BlogPosting", headline: p.title, url: `${SITE}/blog/${p.slug}`, datePublished: p.published_at })) } }), listHtml);
  fs.mkdirSync(path.join(BUILD, "blog"), { recursive: true });
  fs.writeFileSync(path.join(BUILD, "blog", "index.html"), listPage);
  // RSS feed
  const rfc = (d) => { try { return new Date(d).toUTCString(); } catch (e) { return ""; } };
  const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>
<title>ShowUpAI Blog</title><link>${SITE}/blog</link>
<description>Practical, number-backed guides on webinar attendance, reminders and no-shows.</description>
<language>en</language><atom:link href="${SITE}/rss.xml" rel="self" type="application/rss+xml" />
${posts.map((p) => `<item><title>${esc(p.title)}</title><link>${SITE}/blog/${esc(p.slug)}</link><guid>${SITE}/blog/${esc(p.slug)}</guid>${p.published_at ? `<pubDate>${rfc(p.published_at)}</pubDate>` : ""}<description>${esc(p.excerpt || p.meta_description || "")}</description>${p.author ? `<author>hello@showupai.live (${esc(p.author)})</author>` : ""}</item>`).join("\n")}
</channel></rss>`;
  fs.writeFileSync(path.join(BUILD, "rss.xml"), rss);

  // llms.txt: append a list of articles so AI assistants can find them
  const llmsPath = path.join(BUILD, "llms.txt");
  if (fs.existsSync(llmsPath) && posts.length) {
    const base = fs.readFileSync(llmsPath, "utf8").trimEnd();
    const block = `\n\n## Blog articles\n\n${posts.map((p) => `- [${p.title}](${SITE}/blog/${p.slug}): ${(p.excerpt || p.meta_description || "").replace(/\s+/g, " ")}`).join("\n")}\n`;
    fs.writeFileSync(llmsPath, base + block);
  }
  console.log(`[prerender] wrote ${posts.length} post pages + blog index + rss.xml + llms.txt list`);
}

main().catch((e) => console.log("[prerender] error (ignored):", e.message)).finally(() => process.exit(0));
