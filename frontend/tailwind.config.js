/** @type {import('tailwindcss').Config} */

/*
 * توکن‌ها به تیلویند وصل‌اند، نه فقط در CSS.
 *
 * چرا لازم شد: تا امروز `theme.extend` خالی بود، پس تیلویند از وجود
 * رنگ‌ها و فاصله‌های ما خبر نداشت و هر کامپوننت مجبور بود با
 * `style={{ color: "var(--muted)" }}` دستی بنویسد — ۱۶۶۲ بار در
 * ۱۹ فایل. عوض‌کردن یک رنگ یعنی گشتن در همه‌شان.
 *
 * همه از همان متغیرهای `index.css` می‌خوانند، پس یک منبع حقیقت
 * می‌ماند و چیزی دو جا تعریف نمی‌شود.
 */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        "surface-3": "var(--surface-3)",
        line: "var(--border)",
        "line-2": "var(--border-2)",
        accent: "var(--accent)",
        "accent-2": "var(--accent-2)",
        cyan: "var(--cy)",
        body: "var(--text)",
        dim: "var(--dim)",
        muted: "var(--muted)",
        ok: "var(--ok)",
        warn: "var(--warn)",
        danger: "var(--danger)",
        purple: "var(--purple)",
      },
      fontFamily: {
        sans: ["var(--sans)"],
        mono: ["var(--mono)"],
      },
      borderRadius: {
        s: "var(--r-s)", m: "var(--r-m)", l: "var(--r-l)", xl2: "var(--r-xl)",
      },
      boxShadow: {
        e1: "var(--e-1)", e2: "var(--e-2)", e3: "var(--e-3)",
      },
      spacing: {
        s2: "var(--space-2)", s3: "var(--space-3)",
        s4: "var(--space-4)", s6: "var(--space-6)", s8: "var(--space-8)",
      },
      transitionTimingFunction: {
        snappy: "var(--sp-snappy)",
        soft: "var(--sp-soft)",
        inout: "var(--sp-inout)",
      },
      transitionDuration: {
        fast: "130ms", base: "220ms", slow: "420ms",
      },
    },
  },
  plugins: [],
};
