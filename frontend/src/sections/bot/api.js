/**
 * هوک مشترک صداکردن API ربات.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import React, { useState, useEffect } from "react";
import { API_URL } from "../../lib/constants";
import { errText } from "../../lib/format";

export function useBotApi(password) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState(null);

  const call = async (path, opts = {}) => {
    const res = await fetch(`${API_URL}${path}`, {
      ...opts,
      headers: { "Content-Type": "application/json", "X-Admin-Password": password, ...(opts.headers || {}) },
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(errText(d.detail, "خطای سرور"));
    return d;
  };

  useEffect(() => { if (msg) { const t = setTimeout(() => setMsg(null), 4000); return () => clearTimeout(t); } }, [msg]);

  return { data, setData, loading, setLoading, msg, setMsg, call };
}
