import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = localStorage.getItem("showup_token");
    if (!t) { setLoading(false); return; }
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => {
      localStorage.removeItem("showup_token");
    }).finally(() => setLoading(false));
  }, []);

  const login = async (email, password) => {
    const r = await api.post("/auth/login", { email, password });
    localStorage.setItem("showup_token", r.data.token);
    setUser(r.data.user);
  };
  const register = async (name, email, password) => {
    const r = await api.post("/auth/register", { name, email, password });
    localStorage.setItem("showup_token", r.data.token);
    setUser(r.data.user);
  };
  const logout = () => { localStorage.removeItem("showup_token"); setUser(null); };

  return <AuthCtx.Provider value={{ user, loading, login, register, logout }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
