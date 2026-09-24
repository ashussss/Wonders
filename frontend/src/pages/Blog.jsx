import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, fmtDate, API_BASE } from "@/lib/api";
import SubscribeBox from "@/components/SubscribeBox";
import BlogHeader from "@/components/BlogHeader";

function setMeta(name, content, attr = "name") {
  let el = document.head.querySelector(`meta[${attr}="${name}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, name);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

export default function BlogPage() {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    document.title = "Blog | ShowUpAI — Make People Actually Show Up to Your Webinar";
    setMeta("description", "Guides to increase webinar attendance and make people actually show up from ShowUpAI.");
    setMeta("og:title", "ShowUpAI Blog", "property");
  }, []);

  useEffect(() => {
    api
      .get("/blog")
      .then((res) => setPosts(Array.isArray(res.data) ? res.data : []))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen p-8 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block w-6 h-6 border-2 border-current border-t-transparent rounded-full animate-spin" />
          <p className="mt-4 text-lg text-muted-foreground">Loading blog posts...</p>
        </div>
      </div>
    );
  }

  return (
    <motion.div
      className="max-w-5xl mx-auto p-6"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <BlogHeader />

      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight" style={{ fontFamily: "Outfit" }}>
          Blog
        </h1>
        <p className="text-muted-foreground mt-1">
          Guides to increase webinar attendance and make people actually show up
        </p>
      </div>

      <SubscribeBox variant="card" placement="blog-index" />

      {(error || posts.length === 0) && (
        <div className="p-8 text-center text-muted-foreground">
          <p>{error ? "Couldn't load posts right now." : "No blog posts yet."}</p>
          <p className="mt-2">Published posts will appear here automatically.</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {posts.map((post, i) => (
          <motion.div
            key={post.slug}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3, delay: 0.05 * i }}
          >
            <Link to={`/blog/${post.slug}`} target="_blank" rel="noopener" className="block h-full">
              <Card className="h-full overflow-hidden hover:shadow-lg transition-shadow">
                <img
                  src={`${API_BASE}/blog/${post.slug}/cover.png?v=${encodeURIComponent(post.updated_at || "")}`}
                  alt=""
                  loading="lazy"
                  width="1200"
                  height="630"
                  className="w-full aspect-[1200/630] object-cover border-b"
                />
                <CardHeader>
                  <CardTitle className="font-medium line-clamp-2">{post.title}</CardTitle>
                </CardHeader>
                <CardContent className="pb-4 flex flex-col min-h-[160px]">
                  <p className="text-sm text-muted-foreground line-clamp-3">
                    {post.excerpt || post.meta_description || ""}
                  </p>
                  <div className="mt-auto pt-3 flex items-center justify-between text-xs text-muted-foreground">
                    <span>{post.reading_time || 5} min read</span>
                    {post.published_at && <span>{fmtDate(post.published_at)}</span>}
                  </div>
                </CardContent>
              </Card>
            </Link>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
