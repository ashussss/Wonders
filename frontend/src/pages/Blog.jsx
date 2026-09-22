import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/ui/use-toast";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";
import { AiOutlineStar, AiFillStar } from "react-icons/ai";

import { api } from "@/lib/api";
import { fmtDate } from "@/lib/api";
import LoadingSkeleton from "@/components/LoadingSkeleton";
import { useTheme } from "@/lib/theme";
import { usePathname } from "@/lib/router";

export default function BlogPage() {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const { isDark } = useTheme();
  const pathname = usePathname();

  useEffect(() => {
    api.get("/api/blog").then((res) => {
      setPosts(res.data || []);
      setLoading(false);
    });
  }, []);

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
          <p className="mt-4 text-lg text-muted-foreground">Loading blog posts...</p>
        </div>
      </motion.div>
    );
  }

  // Determine page type for breadcrumbs
  const isBlogPage = pathname === "/blog" || pathname.startsWith("/blog/");
  const slugFromPath = pathname.replace("/blog", "").replace("/", "") || "home";

  return (
    <>
      <style jsx>{`
        .fade-in {
          animation: fadeIn 0.6s ease forwards;
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
      `}</style>
      <motion.div
        className="max-w-3xl mx-auto p-6"
        initial={{ opacity: 0, y: 20}}
        animate={{ opacity: 1, y: 0}}
        transition={{ duration: 0.5}}
        style={{ background: isDark ? "var(--bg)" : "#fff", color: isDark ? "var(--text-body)" : "#1f2937" }}
      >
        {/* SEO Meta Tags - these are injected by _document or next/head, but we set defaults */}
        {/* In Next.js: <Head><title>ShowUp Blog | Webinar Attendance Software</title></Head> */}

        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight" style={{ fontFamily: "Outfit", color: isDark ? "var(--text-primary)" : "#1f2937" }}>
            Blog
          </h1>
          <p className="text-muted-foreground mt-1">
            Insights on webinars, attendance, and growing your audience
          </p>
        </div>

        {/* Value-Driven Introduction */}
        <div className="bg-secondary/5 border border-secondary/10 rounded-lg p-6 mb-8 opacity-0 fade-in" style={{ transition: "opacity 0.6s ease 0.2s" }}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-sm font-medium text-secondary/80 mb-1">Why Read?</p>
              <ul className="list-disc list-inside space-y-1 text-sm">
                <li>Data-driven webinar strategies</li>
                <li>AI-powered attendance optimization</li>
                <li>Real-world case studies</li>
                <li>Proven attendance boost tactics</li>
              </ul>
            </div>
            <div>
              <p className="text-sm font-medium text-secondary/80 mb-1">Who Is It For?</p>
              <ul className="list-disc list-inside space-y-1 text-sm">
                <li>EdTech founders & instructors</li>
                <li>Corporate training leaders</li>
                <li>Agency owners running webinars</li>
                <li>Education sector consultants</li>
              </ul>
            </div>
          </div>
        </div>

        {posts.length === 0 && (
          <div className="p-8 text-center text-muted-foreground">
            <p>No blog posts yet.</p>
            <p className="mt-2">Published posts will appear here automatically.</p>
          </div>
        )}

        {/* Blog Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {posts.map((post) => (
            <motion.div
              key={post.slug}
              initial={{ opacity: 0, x: -20}}
              animate={{ opacity: 1, x: 0}}
              exit={{ opacity: 0, x: 20}}
              transition={{ duration: 0.3, delay: 0.05 * posts.indexOf(post)}}
            >
              <Card
                className="h-full hover:shadow-lg transition-shadow cursor-pointer"
                style={{ borderColor: isDark ? "var(--border)" : "var(--border)" }}
                onClick={() => window.location.href = `/blog/${post.slug}`}
              >
                <CardHeader>
                  <CardTitle className="font-medium line-clamp-2">
                    {post.title}
                  </CardTitle>
                </CardHeader>

                <CardContent className="pb-4 flex flex-col min-h-[200px]">
                  {/* AI-Enhanced Excerpt with value proposition */}
                  <p className="text-sm text-muted-foreground line-clamp-3">
                    {post.excerpt ||
                      post.content.substring(0, 120) + "..."}
                  </p>

                  {/* Reading time and date */}
                  <div className="pt-2 flex items-center justify-between text-xs">
                    <span>
                      {post.reading_time} min read
                    </span>
                    <span>
                      {fmtDate(post.published_at)}
                    </span>
                  </div>
                </CardContent>

                {/* CTA Preview - what reader gains */}
                <div className="pt-3 p-3 bg-primary/5 border border-primary/10 rounded-t-lg">
                  <p className="text-xs text-primary">
                    <strong>Key takeaway:</strong> {post.excerpt?.substring(0, 60) || "Actionable insight"}
                  </p>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>

        {/* Pagination / Load More */}
        {posts.length > 0 && (
          <div className="mt-8 pt-8 border-t text-center text-xs text-muted-foreground">
            <p>
              {posts.length} {"post" + (posts.length !== 1 ? "s" : "")} loaded{" — "}
              {"more available" /* would add load more logic */}
            </p>
          </div>
        )}
      </motion.div>
    </>
  );
}