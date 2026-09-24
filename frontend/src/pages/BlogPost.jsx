import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { api, fmtDate, API_BASE } from "@/lib/api";
import { parseMarkdown, splitInline } from "@/lib/markdown";

function setMeta(name, content, attr = "name") {
  if (!content) return;
  let el = document.head.querySelector(`meta[${attr}="${name}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, name);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function setCanonical(href) {
  let el = document.head.querySelector('link[rel="canonical"]');
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", "canonical");
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

function Inline({ text }) {
  return splitInline(text).map((part, i) =>
    part.t === "b" ? (
      <strong key={i}>{part.v}</strong>
    ) : part.t === "code" ? (
      <code key={i} className="px-1 py-0.5 rounded bg-black/5 text-[0.9em]">{part.v}</code>
    ) : (
      <React.Fragment key={i}>{part.v}</React.Fragment>
    )
  );
}

const looksLikeHtml = (s) => /^\s*<(p|h[1-6]|div|section|article|ul|ol)[\s>]/i.test(s || "");

function MarkdownBody({ content }) {
  let h = 0;
  return parseMarkdown(content).map((b, i) => {
    if (b.type === "h") {
      const Tag = `h${b.level}`;
      const size = b.level === 2 ? "text-2xl mt-10" : "text-xl mt-8";
      return (
        <Tag key={i} id={`section-${h++}`} className={`${size} font-semibold mb-3 tracking-tight`}>
          {b.text}
        </Tag>
      );
    }
    if (b.type === "p") {
      return (
        <p key={i} className="my-4">
          <Inline text={b.text} />
        </p>
      );
    }
    if (b.type === "code") {
      return (
        <pre key={i} className="my-5 p-4 rounded-lg border bg-black/[0.03] text-sm whitespace-pre-wrap overflow-x-auto font-mono leading-relaxed">
          {b.text}
        </pre>
      );
    }
    if (b.type === "table") {
      return (
        <div key={i} className="my-6 overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr>
                {b.head.map((c, j) => (
                  <th key={j} className="text-left font-semibold border-b-2 px-3 py-2">
                    <Inline text={c} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {b.rows.map((r, j) => (
                <tr key={j} className="border-b">
                  {r.map((c, k) => (
                    <td key={k} className="px-3 py-2 align-top">
                      <Inline text={c} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    const ListTag = b.type === "ol" ? "ol" : "ul";
    const listCls = b.checklist ? "list-none pl-0" : b.type === "ol" ? "list-decimal pl-6" : "list-disc pl-6";
    return (
      <ListTag key={i} className={`${listCls} space-y-2 my-4`}>
        {b.items.map((it, j) => (
          <li key={j}>
            {it.check && <span className="inline-block w-4 h-4 mr-2 align-[-2px] border rounded-sm" aria-hidden="true" />}
            <Inline text={it.text} />
            {it.children.length > 0 && (
              <ul className="list-disc pl-6 mt-1 space-y-1">
                {it.children.map((c, k) => (
                  <li key={k}>
                    <Inline text={c} />
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ListTag>
    );
  });
}

export default function BlogPostPage() {
  const { slug } = useParams();
  const [post, setPost] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    api
      .get(`/blog/${slug}`)
      .then((res) => setPost(res.data))
      .catch(() => setPost(null))
      .finally(() => setLoading(false));
  }, [slug]);

  useEffect(() => {
    if (!post) return;
    const title = post.seo_title || `${post.title} | ShowUp.ai`;
    const desc = post.seo_description || post.meta_description || post.excerpt || "";
    document.title = title;
    setMeta("description", desc);
    setMeta("keywords", post.seo_keywords || post.meta_keywords);
    setMeta("og:title", post.og_title || post.title, "property");
    setMeta("og:description", post.og_description || desc, "property");
    const cover = `${API_BASE}/blog/${post.slug}/cover.png`;
    setMeta("og:image", post.og_image || cover, "property");
    setMeta("twitter:image", post.og_image || cover);
    setMeta("twitter:card", post.twitter_card || "summary_large_image");
    setMeta("twitter:title", post.twitter_title || post.title);
    setMeta("twitter:description", post.twitter_description || desc);
    setCanonical(`https://showupai.live/blog/${post.slug}`);

    // Structured data (Article + FAQPage) for rich results / AEO
    const graph = [
      {
        "@type": "Article",
        headline: post.title,
        description: desc,
        datePublished: post.published_at,
        dateModified: post.updated_at || post.published_at,
        author: { "@type": "Organization", name: "ShowUp.ai" },
        publisher: { "@type": "Organization", name: "ShowUp.ai", url: "https://showupai.live" },
        image: `${API_BASE}/blog/${post.slug}/cover.png`,
        mainEntityOfPage: `https://showupai.live/blog/${post.slug}`,
      },
    ];
    const faqList = (post.faq_items || []).filter((f) => f && f.question && f.answer);
    if (faqList.length) {
      graph.push({
        "@type": "FAQPage",
        mainEntity: faqList.map((f) => ({
          "@type": "Question",
          name: f.question,
          acceptedAnswer: { "@type": "Answer", text: f.answer },
        })),
      });
    }
    let ld = document.getElementById("blog-jsonld");
    if (!ld) {
      ld = document.createElement("script");
      ld.type = "application/ld+json";
      ld.id = "blog-jsonld";
      document.head.appendChild(ld);
    }
    ld.textContent = JSON.stringify({ "@context": "https://schema.org", "@graph": graph });
    return () => {
      const el = document.getElementById("blog-jsonld");
      if (el) el.remove();
    };
  }, [post]);

  if (loading) {
    return (
      <div className="min-h-screen p-8 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block w-6 h-6 border-2 border-current border-t-transparent rounded-full animate-spin" />
          <p className="mt-4 text-lg text-muted-foreground">Loading blog post...</p>
        </div>
      </div>
    );
  }

  if (!post) {
    return (
      <div className="min-h-screen p-8 text-center">
        <p className="text-lg text-muted-foreground">Blog post not found</p>
        <Link to="/blog" className="text-sm underline mt-4 inline-block">
          Back to blog
        </Link>
      </div>
    );
  }

  const content = post.content || "";
  const readingTime = post.reading_time || Math.max(1, Math.ceil(content.split(/\s+/).length / 200));
  const faqs = Array.isArray(post.faq_items) ? post.faq_items.filter((f) => f && f.question) : [];

  return (
    <motion.div
      className="max-w-2xl mx-auto p-6"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <nav className="mb-6 text-sm" aria-label="breadcrumb">
        <Link to="/blog" className="hover:underline">
          Blog
        </Link>
        <span className="text-muted-foreground"> / {post.title}</span>
      </nav>

      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight mb-3" style={{ fontFamily: "Outfit" }}>
          {post.title}
        </h1>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {post.published_at && <span>{fmtDate(post.published_at)}</span>}
          {post.published_at && <span>·</span>}
          <span>{readingTime} min read</span>
          {post.author && <span>· {post.author}</span>}
        </div>
      </header>

      <img
        src={`${API_BASE}/blog/${post.slug}/cover.png?v=${encodeURIComponent(post.updated_at || "")}`}
        alt={post.title}
        width="1200"
        height="630"
        className="w-full aspect-[1200/630] object-cover rounded-xl border mb-8"
      />

      <article className="max-w-none text-[17px] leading-[1.75]">
        {looksLikeHtml(content) ? (
          <div dangerouslySetInnerHTML={{ __html: content }} />
        ) : (
          <MarkdownBody content={content} />
        )}
      </article>

      {faqs.length > 0 && (
        <section className="mt-10 p-4 border rounded-lg">
          <h2 className="text-lg font-semibold mb-3">Frequently asked questions</h2>
          <div className="space-y-2 text-sm">
            {faqs.map((f, i) => (
              <details key={i} className="border-b pb-2 last:border-b-0">
                <summary className="cursor-pointer font-medium">{f.question}</summary>
                {f.answer && <p className="text-muted-foreground mt-1">{f.answer}</p>}
              </details>
            ))}
          </div>
        </section>
      )}

      <section className="mt-12 pt-8 border-t">
        <h2 className="text-lg font-bold mb-3">Turn your webinar attendance around</h2>
        <p className="text-muted-foreground mb-5">
          Most registrants never show up — ShowUp.ai's 8-touch AI reminder sequence helps change that.
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          <Link
            to="/waitlist"
            className="flex-1 text-center px-5 py-3 rounded-full bg-primary text-primary-foreground font-semibold hover:opacity-90 transition-opacity"
          >
            Start free →
          </Link>
          <Link
            to="/blog"
            className="flex-1 text-center px-5 py-3 rounded-full border font-semibold hover:bg-secondary/10 transition-colors"
          >
            More insights →
          </Link>
        </div>
      </section>
    </motion.div>
  );
}
