import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { api, fmtDate } from "@/lib/api";

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

function inline(text) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part
  );
}

const looksLikeHtml = (s) => /<\/?[a-z][\s\S]*>/i.test(s || "");

// Minimal markdown renderer: headings, lists, paragraphs. Returns React nodes (no innerHTML).
function renderMarkdown(md) {
  const blocks = (md || "").split(/\n{2,}/);
  let h = 0;
  return blocks.map((block, i) => {
    const text = block.trim();
    if (!text) return null;
    const heading = text.match(/^(#{1,4})\s+(.+)$/);
    const firstLine = text.split("\n")[0];
    const headLine = firstLine.match(/^(#{1,4})\s+(.+)$/);
    if (!heading && headLine) {
      const rest = text.split("\n").slice(1).join("\n");
      const level = Math.max(2, Math.min(headLine[1].length, 4));
      const Tag = `h${level}`;
      return (
        <React.Fragment key={i}>
          <Tag id={`section-${h++}`} className="font-semibold mt-8 mb-3">{headLine[2]}</Tag>
          <p className="my-4">{inline(rest)}</p>
        </React.Fragment>
      );
    }
    if (heading) {
      const level = Math.max(2, Math.min(heading[1].length, 4));
      const Tag = `h${level}`;
      return (
        <Tag key={i} id={`section-${h++}`} className="font-semibold mt-8 mb-3">
          {heading[2]}
        </Tag>
      );
    }
    const lines = text.split("\n");
    if (lines.every((l) => /^\s*([-*]|\d+\.)\s+/.test(l))) {
      const ordered = /^\s*\d+\./.test(lines[0]);
      const ListTag = ordered ? "ol" : "ul";
      return (
        <ListTag key={i} className={`${ordered ? "list-decimal" : "list-disc"} pl-6 space-y-1 my-4`}>
          {lines.map((l, j) => (
            <li key={j}>{inline(l.replace(/^\s*([-*]|\d+\.)\s+/, ""))}</li>
          ))}
        </ListTag>
      );
    }
    return (
      <p key={i} className="my-4">
        {inline(text)}
      </p>
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
    setMeta("og:image", post.og_image, "property");
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

      <article className="max-w-none leading-relaxed">
        {looksLikeHtml(content) ? (
          <div dangerouslySetInnerHTML={{ __html: content }} />
        ) : (
          renderMarkdown(content)
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
