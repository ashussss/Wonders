import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'https://showup-backend-2bfj.onrender.com';
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("showup_token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

// A session that expired or was signed out (password changed/reset) sends you to login once,
// instead of leaving every page half-broken with errors.
const AUTH_FREE = /\/auth\/(login|register|forgot-password|reset-password)/;
api.interceptors.response.use((r) => r, (err) => {
  const url = err?.config?.url || "";
  if (err?.response?.status === 401 && localStorage.getItem("showup_token") && !AUTH_FREE.test(url)) {
    localStorage.removeItem("showup_token");
    if (window.location.pathname.startsWith("/app")) {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.assign(`/login?expired=1&next=${next}`);
    }
  }
  return Promise.reject(err);
});

export const fmtDate = (iso) => {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }); }
  catch { return iso; }
};

export const daysUntil = (iso) => {
  if (!iso) return null;
  const d = (new Date(iso) - new Date()) / (1000*60*60*24);
  return Math.round(d);
};

export const CHANNEL_META = {
  email:        { label: "Email",            icon: "Mail",         autoSendCapable: true,  manualOnly: false },
  linkedin:     { label: "LinkedIn",         icon: "Linkedin",     autoSendCapable: true,  manualOnly: false },
  linkedin_page: { label: "LinkedIn",        icon: "Linkedin",     autoSendCapable: true,  manualOnly: false },
  linkedin_personal: { label: "LinkedIn (personal)", icon: "Linkedin", autoSendCapable: true, manualOnly: false },
  facebook:     { label: "Facebook Page",    icon: "Facebook",     autoSendCapable: true,  manualOnly: false },
  facebook_page: { label: "Facebook Page",   icon: "Facebook",     autoSendCapable: true,  manualOnly: false },
  instagram:    { label: "Instagram",        icon: "Instagram",    autoSendCapable: true,  manualOnly: false },
  whatsapp:     { label: "WhatsApp / SMS",   icon: "Mail",autoSendCapable: true,  manualOnly: false },
  circle:       { label: "Circle.so",        icon: "Users",        autoSendCapable: true,  manualOnly: false },
};
