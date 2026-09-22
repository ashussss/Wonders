import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/ui/use-toast";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";
import { AiOutlineStar, AiFillStar } from "react-icons/ai";
import { Lambda } from "react-icons/lambda";
import { Github } from "react-icons/gi";

import { api } from "@/lib/api";
import { fmtDate, fmtReadingTime } from "@/lib/api";
import LoadingSkeleton from "@/components/LoadingSkeleton";
import { useTheme } from "@/lib/theme";
import { usePathname, useSEO } from "@/lib/seo";
import { useIntersectionObserver } from "@/lib/hooks";

export default function BlogPostPage() {
  const { slug } = useParams();
  const [post, setPost] = useState(null);
  const [loading, setLoading] = useState(true);
  const { isDark } = useTheme();
  const pathname = usePathname();

  // SEO setup based on post or default
  useSEO({
    title: post ? `${post.title} | ShowUp.ai` : "Blog | ShowUp.ai",
    description: post ? post.meta_description || "Webinar attendance optimization & audience growth" : "Latest insights on webinars, attendance strategies, and audience growth",
    keywords: post ? post.meta_keywords || "webinar, attendance, software, education" : "webinar attendance, audience optimization, edtech",
    canonical: post ? `https://showupai.live/blog/${post.slug}` : "https://showupai.live/blog",
    openGraph: {
      title: post ? post.title : "ShowUp.ai Blog",
      description: post ? post.meta_description || "Webinar attendance optimization" : "Build better webinars",
      images: post && post.cover_image ? [{ url: post.cover_image }] : [{ url: "/blog-featured.jpg" }],
    },
    twitter: {
      card: "summary_large_image",
      title: post ? post.title : "ShowUp.ai Blog",
      description: post ? post.meta_description || "Webinar attendance optimization" : "Build better webinars",
      images: post && post.cover_image ? [post.cover_image] : ["/blog-featured.jpg"],
    },
  });

  useEffect(() => {
    if (!slug) return;
    api.get(`/api/blog/${slug}`).then((res) => {
      setPost(res.data);
      setLoading(false);
    });
  }, [slug]);

  if (loading) {
    return (
      <motion.div
        className="min-h-screen p-8 flex items-center justify-center"
        initial={{ opacity: 0}}
        animate={{ opacity: 1}}
        transition={{ duration: 0.5 }}
      >
        <div className="text-center">
          <div className="inline-block w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
          <p className="mt-4 text-lg text-muted-foreground">Loading blog post...</p>
        </div>
      </motion.div>
    );
  }

  if (!post) {
    return (
      <motion.div
        className="min-h-screen p-8 text-center"
        initial={{ opacity: 0}}
        animate={{ opacity: 1}}
        transition={{ duration: 0.5 }}
      >
        <p className="text-lg text-muted-foreground">Blog post not found</p>
      </motion.div>
    );
  }

  // Reading time calculation
  const readingTime = post.reading_time || Math.ceil(post.content.split(/\s+/).length / 200);
  
  // Extract key sections from markdown for AEO
  const sections = extractSections(post.content);
  const hasQ&A = post.content.includes("?") || post.faqItems?.length > 0;
  const hasListicles = /^\d+\./m.test(post.content);
  const hasTables = post.content.includes("|") && post.content.split("|").length > 6;

  return (
    <motion.div
      className="max-w-2xl mx-auto p-6"
      initial={{ opacity: 0, y: 20}}
      animate={{ opacity: 1, y: 0}}
      transition={{ duration: 0.5}}
      style={{ background: isDark ? "var(--bg)" : "#fff", color: isDark ? "var(--text-body)" : "#1f2937" }}
    >
      {/* BREADCRUMBS */}
      {/\/blog/.test(pathname) && (
        <nav className="mb-6" aria-label="breadcrumb">
          <ol className="flex flex-col sm:flex-row space-y-2 sm:space-y-0 sm:space-x-2">
            <li>
              <a href="/blog" className="text-sm text-primary hover:underline">
                Blog
              </a>
            </li>
            {slug && (
              <li className="text-sm text-muted-foreground">
                <span>{post.title}</span>
              </li>
            )}
          </ol>
        </nav>
      )}

      {/* POST HEADER WITH METADATA */}
      <header className="mb-8 fade-in-up" style={{ transition: "transform 0.6s ease 0.1s" }}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "Outfit", color: isDark ? "var(--text-primary)" : "#1f2937" }}>
            {post.title}
          </h1>
          
          <div className="flex items-center gap-3">
            <span className="text-xs text-secondary/70">
              {fmtDate(post.published_at)} · 
            </span>
            <span className="text-xs text-secondary/70">
              {readingTime} min read
            </span>
            {post.author && (
              <span className="text-xs text-secondary/70">
                · {post.author}
              </span>
            )}
          </div>
        </div>

        {/* AO Metrics / Engagement Stats */}
        {post.registrations_from_page !== undefined && (
          <div className="mt-3 p-3 bg-primary/5 border border-primary/10 rounded-lg">
            <p className="text-xs text-primary">
              <AiFillStar size={12} /> {post.registrations_from_page} registrations
              {post.attendees_from_page !== undefined && (
                ` · ${post.attendees_from_page} attended`
              )}
            </p>
          </div>
        )}
      </header>

      {/* CONTENT AREA */}
      <article className="prose lg:prose-2xl max-w-none" style={{ 
        color: isDark ? "var(--text-body)" : "#374151",
        lineHeight: "1.7",
        maxWidth: "none"
      }}>
        {/* Embed Images with Lazy Load */}
        <div dangerouslySetInnerHTML={{ __html: post.content }} />
      </article>

      {/* AEO: Q&A Schema if questions present */}
      {hasQ&A && (
        <div className="mt-8 p-4 bg-secondary/5 border border-secondary/10 rounded-lg mb-6">
          <h3 className="text-sm font-medium text-secondary mb-3">Frequently Asked Questions</h3>
          <div className="space-y-2 text-sm">
            {sections.questions.map((q, i) => (
              <details key={i} className="border-b pb-2 border-b-gray-200/5 last:border-b-0">
                <summary 
                  className="cursor-pointer hover:text-primary transition-colors"
                >
                  {q.question || q.substring(0, 80) + "..."}
                </summary>
                <p className="text-muted-foreground mt-1 line-clamp-2">
                  {q.answer || q.substring(80) + "..."}
                </p>
              </details>
            ))}
          </div>
        </div>
      )}

      {/* GEO: Entity Relationships / Related Content */}
      <div className="mt-8 p-4 bg-primary/5 border border-primary/10 rounded-lg">
        <h3 className="text-sm font-medium text-primary mb-3">
          <Lambda size={12} /> Related Reading
        </h3>
        <p className="text-xs text-primary/80">
          {post.related_posts?.length > 0 
            ? post.related_posts.map((r, i) => `${i + 1}. ${r.title}`).join(". ")
            : "Other webinar optimization guides on ShowUp.ai"}
        </p>
      </div>

      {/* CTA AT BOTTOM - Value-Driven */}
      <div class="mt-12 pt-8 border-t border-secondary/5">
        <h3 className="text-lg font-bold mb-4">Turn Your Webinar Attendance Around</h3>
        <p className="text-muted-foreground mb-4">
          65% of registrants never show up — but it doesn't have to be that way. 
          ShowUp.ai's 8-touch AI sequence consistently drives 62%+ attendance.
        </p>
        
        <div className="flex gap-3">
          <a 
            href="https://showupai.live/waitlist" 
            className="flex-1 px-5 py-3 rounded-xl bg-primary text-white font-semibold hover:bg-primary/90 transition-colors"
            target="_blank"
            rel="noopener noreferrer"
          >
            Start Free Trial →
          </a>
          <a 
            href="/blog" 
            className="flex-1 px-5 py-3 rounded-xl border border-secondary text-secondary font-semibold hover:bg-secondary/5 transition-colors"
          >
            More Insights →
          </a>
        </div>
      </div>

      {/* TABLE OF CONTENTS for long posts */}
      {hasListicles && sections.headings.length > 3 && (
        <div className="mt-8 p-4 bg-secondary/5 border border-secondary/10 rounded-lg mb-6">
          <h3 className="text-sm font-medium text-secondary mb-3">On This Page</h3>
          <ol className="text-sm text-secondary/80 space-y-1">
            {sections.headings.slice(0, 6).map((h, i) => (
              <li key={i}>
                <a href={`#section-${i}`} className="hover:text-primary transition-colors">
                  {h}
                </a>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* AUTHOR BOX */}
      {post.author && post.author !== "Admin" && (
        <div className="mt-8 pt-6 border-t border-secondary/5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-primary/5 flex items-center justify-center flex-shrink-0">
              {post.author.match(/[a-z]/i) ? post.author.slice(0, 2).toUpperCase() : "U"}
            </div>
            <div>
              <p className="text-sm font-medium">{post.author}</p>
              <p className="text-xs text-secondary/70">Content strategist at ShowUp.ai</p>
            </div>
          </div>
        </div>
      )}

      {/* SHARE BOTTOM */}
      <div className="mt-8 border-t border-secondary/5 pt-6">
        <p className="text-xs text-secondary/70">
          <Github size={12} /> Share on X | <AiOutlineStar size={12} /> Save for later
        </p>
      </div>
    </motion.div>
  );
}

/* Animations */
.fade-in-up {
  animation: fadeInUp 0.6s ease forwards;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Extract sections from content for AEO/TOC */
function extractSections(content) {
  const headings = [];
  const questions = [];
  
  // Extract H2/H3 headings
  const headingRegex = /^(#{2,3})\s+(.+)$/m;
  let match;
  while ((match = headingRegex.exec(content)) !== null) {
    const level = match[1].length;
    const text = match[2].trim();
    headings.push({ level, text });
    
    // Check if it's a question
    if (text.includes("?")) {
      questions.push({ question: text, answer: "" });
    }
  }
  
  // Extract explicit Q&A blocks
  const qaRegex = /(Q:[^\n]*(?:\n|$))|(A:[^\n]*(?:\n|$))/g;
  const qaMatches = content.match(qaRegex) || [];
  qaMatches.forEach((match, i) => {
    if (match.startsWith("Q:")) {
      questions.push({ question: match.replace("Q:", "").trim(), answer: "" });
    }
  });
  
  return { headings, questions };
}