import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/*
 * یک بیلدِ تک‌فایلی برای تستِ اجرا.
 *
 * `tests/test-panel-runtime.js` باندل را در jsdom اجرا می‌کند تا مطمئن شود
 * پنل واقعاً در مرورگر بالا می‌آید — بیلدِ موفق تضمینی نیست، یک
 * import جاافتاده صفحه‌ی سفید می‌دهد بدون هیچ خطایی در لاگ بیلد.
 *
 * ولی jsdom ماژولِ ES را اجرا نمی‌کند، و بعد از تکه‌تکه‌کردن، تکه‌ها
 * با `import` به هم وصل‌اند. پس برای تست یک نسخه‌ی تک‌فایلی هم
 * ساخته می‌شود. این نسخه هیچ‌وقت سرو نمی‌شود؛ فقط تست از آن
 * می‌خواند.
 */
const SINGLE = !!process.env.NEXORA_SINGLE_BUNDLE;

export default defineConfig({
  plugins: [react()],
  server: { port: 5174 },
  build: {
    outDir: SINGLE ? "dist-test" : "dist",
    rollupOptions: {
      output: SINGLE ? { inlineDynamicImports: true } : {
        /*
         * سه اپ در یک فایل بودند.
         *
         * مشتری‌ای که مینی‌اپ را روی موبایل باز می‌کند، کلِ پنل مدیر
         * را هم دانلود می‌کرد — ۱۷۲ کیلوبایتِ فشرده برای صفحه‌ای که
         * سه کارت نشان می‌دهد. و همان مشتری، همان کسی است که
         * اینترنتش محدود است.
         *
         * حالا React و lucide در تکه‌های جدا می‌نشینند: مینی‌اپ و
         * پنل نماینده فقط چیزی را می‌گیرند که لازم دارند، و
         * تکه‌های مشترک یک‌بار کش می‌شوند و در آپدیت بعدی دوباره
         * دانلود نمی‌شوند.
         */
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (id.includes("react-dom") || id.includes("/react/") ||
              id.includes("scheduler")) return "react";
          if (id.includes("lucide-react")) return "icons";
          return "vendor";
        },
      },
    },
  },
});
