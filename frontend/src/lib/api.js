import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'https://showup-backend-2bfj.onrender.com';
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("showup_token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
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
  linkedin:     { label: "LinkedIn Page",    icon: "Linkedin",     autoSendCapable: true,  manualOnly: false },
  linkedin_personal: { label: "LinkedIn (personal)", icon: "Linkedin", autoSendCapable: false, manualOnly: true },
  facebook:     { label: "Facebook Page",    icon: "Facebook",     autoSendCapable: true,  manualOnly: false },
  instagram:    { label: "Instagram",        icon: "Instagram",    autoSendCapable: true,  manualOnly: false },
  whatsapp:     { label: "WhatsApp / SMS",   icon: "Mail",autoSendCapable: true,  manualOnly: false },
  circle:       { label: "Circle.so",        icon: "Users",        autoSendCapable: true,  manualOnly: false },
};
