import React, { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import "@/App.css";
import { AuthProvider, useAuth } from "@/lib/auth";
import { ThemeProvider } from "@/lib/theme";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
<<<<<<< HEAD
const WebinarDetail = lazy(() => import("@/pages/WebinarDetail"));
import ApprovalQueue from "@/pages/ApprovalQueue";
const Analytics = lazy(() => import("@/pages/Analytics"));
import Settings from "@/pages/Settings";
const Schedule = lazy(() => import("@/pages/Schedule"));
const ContentLibrary = lazy(() => import("@/pages/ContentLibrary"));
const AdminDashboard = lazy(() => import("@/pages/AdminDashboard"));
import Waitlist from "@/pages/Waitlist";
const EmailAnalytics = lazy(() => import("@/pages/EmailAnalytics"));
=======
import WebinarDetail from "@/pages/WebinarDetail";
import ApprovalQueue from "@/pages/ApprovalQueue";
import Analytics from "@/pages/Analytics";
import Schedule from "@/pages/Schedule";
import Settings from "@/pages/Settings";
import ContentLibrary from "@/pages/ContentLibrary";
import AdminDashboard from "@/pages/AdminDashboard";
import Waitlist from "@/pages/Waitlist";
import EmailAnalytics from "@/pages/EmailAnalytics";
>>>>>>> 49ad411 (Implement SEO endpoints for cron jobs)
import PublicRegister from "@/pages/PublicRegister";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
<<<<<<< HEAD
=======
import Blog from "@/pages/Blog";
import BlogPost from "@/pages/BlogPost";
>>>>>>> 49ad411 (Implement SEO endpoints for cron jobs)

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return (
    <div className="min-h-screen bg-[#fffaf5] flex items-center justify-center">
      <div className="w-7 h-7 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Toaster position="top-right" richColors />
<<<<<<< HEAD
          <Suspense fallback={<div style={{display:"flex",alignItems:"center",justifyContent:"center",minHeight:"100vh"}}><div style={{width:32,height:32,border:"2px solid #EA580C",borderTopColor:"transparent",borderRadius:"50%",animation:"spin 0.8s linear infinite"}}/></div>}>
        <Routes>
            {/* Public marketing pages */}
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
          <Route path="/waitlist" element={<Waitlist />} />
            <Route path="/r/:wid" element={<PublicRegister />} />

            {/* Protected app */}
            <Route element={<Protected><Layout /></Protected>}>
              <Route path="/app" element={<Dashboard />} />
              <Route path="/app/webinars/:id" element={<WebinarDetail />} />
              <Route path="/app/approvals" element={<ApprovalQueue />} />
              <Route path="/app/analytics" element={<Analytics />} />
              <Route path="/app/schedule" element={<Schedule />} />
              <Route path="/app/settings" element={<Settings />} />
              <Route path="/app/library" element={<ContentLibrary />} />
              <Route path="/app/admin" element={<AdminDashboard />} />
              <Route path="/app/email" element={<EmailAnalytics />} />
            </Route>

            {/* Legacy redirects */}
            <Route path="/dashboard" element={<Navigate to="/app" replace />} />
          </Routes>
=======
          <Suspense fallback={<div style={{display:"flex",alignItems:"center",justifyContent:"center",minHeight:"100vh"}}><div style={{width:32,height:32,border:"2px solid #EA580C",borderTopColor:"transparent",borderRadius:"50%",animation:"spin 0.8s linear infinite"}}/></div>}><div>
            <Routes>
              {/* Public marketing pages */}
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
            <Route path="/waitlist" element={<Waitlist />} />
              <Route path="/r/:wid" element={<PublicRegister />} />

              {/* Protected app */}
              <Route element={<Protected><Layout /></Protected>}>
                <Route path="/app" element={<Dashboard />} />
                <Route path="/app/webinars/:id" element={<WebinarDetail />} />
                <Route path="/app/approvals" element={<ApprovalQueue />} />
                <Route path="/app/analytics" element={<Analytics />} />
                <Route path="/app/schedule" element={<Schedule />} />
                <Route path="/app/settings" element={<Settings />} />
                <Route path="/app/library" element={<ContentLibrary />} />
                <Route path="/app/admin" element={<AdminDashboard />} />
                <Route path="/app/email" element={<EmailAnalytics />} />
                <Route path="/blog" element={<Blog />} />
                <Route path="/blog/:slug" element={<BlogPost />} />
              </Route>

              {/* Legacy redirects */}
              <Route path="/dashboard" element={<Navigate to="/app" replace />} />
            </Routes>
>>>>>>> 49ad411 (Implement SEO endpoints for cron jobs)
        </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
<<<<<<< HEAD
}
=======
}
>>>>>>> 49ad411 (Implement SEO endpoints for cron jobs)
