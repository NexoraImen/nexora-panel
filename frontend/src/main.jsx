import React, { Suspense, lazy } from "react";

const PRO_MINI = import.meta.glob("./pro/mini.jsx");
const PRO_PORTAL = import.meta.glob("./pro/portal/index.jsx");
const PRO_AFF = import.meta.glob("./pro/aff/index.jsx");
import ReactDOM from "react-dom/client";
import { isAff, isMini, portalSlug } from "./lib/route.js";
import { SLOW_MS, SLOW_NOTE, Splash } from "./lib/mark.jsx";
import "./index.css";
import { applyTheme, markScheme } from "./lib/mini-themes.js";
import { readShop, writeShop } from "./lib/shopcache.js";
import { API_URL } from "./lib/constants";
import { watchStaleChunks } from "./lib/stale.js";

watchStaleChunks();

// آدرس تعیین می‌کند کدام اپ بالا بیاید.
//
// /r/<نشانی> پنل نماینده است و /app مینی‌اپ مشتری. هیچ‌کدام ربطی به
// پنل مدیر ندارند — نه کدشان، نه مسیرهایشان. این شرط تنها جایی است
// که این سه به هم می‌رسند، و عمداً همین‌قدر کوچک نگه داشته شده.
//
// و با lazy بارگذاری می‌شوند، نه با import مستقیم: وگرنه هر سه در
// یک فایل می‌نشینند و مشتریِ مینی‌اپ کلِ پنل مدیر را هم دانلود
// می‌کند. شرط از `lib/route.js` می‌آید که هیچ وابستگی‌ای ندارد، پس
// خودِ تصمیم چیزی را بار نمی‌کند.
const PICK = {
  // The mini app is Pro (src/pro/, absent from the Community build). Without
  // it a customer who opens an old link gets a page that says what to do.
  mini: PRO_MINI["./pro/mini.jsx"] || (() => import("./lib/mini-off.jsx")),
  // The reseller portal is Pro too; a reseller who opens their link on a
  // Community build is told the portal is not available here.
  portal: PRO_PORTAL["./pro/portal/index.jsx"] || (() => import("./lib/portal-off.jsx")),
  // The sales-partner app is Pro too (src/pro/aff/).
  aff: PRO_AFF["./pro/aff/index.jsx"] || (() => import("./lib/aff-off.jsx")),
  admin: () => import("./App.jsx"),
};

const WHICH = isMini() ? "mini" : isAff() ? "aff"
  : portalSlug() ? "portal" : "admin";

/*
 * نشانیِ مخفیِ پنلِ مدیر — https://دامنه/<نشانی>/
 *
 * برگه: docs/specs/2026-09-28-admin-path-and-aff-payouts.md
 *
 * «هر مسیرِ دیگر پنلِ مدیر است» یعنی نماینده و همکار (و حتی مشتری) با
 * پاک‌کردنِ نوارِ آدرس به صفحه‌ی ورودِ مالک می‌رسیدند. حالا اولین تکه‌ی
 * مسیر همان نشانی است و هر درخواستِ مدیر (admin و login) آن را در
 * هدرِ `X-Admin-Path` می‌برد. اجرای واقعی روی سرور است (بی آن هدر ۴۰۴)؛
 * این‌جا فقط تصمیم گرفته می‌شود صفحه‌ی ورود نشان داده شود یا «پیدا نشد».
 */
const DEV = !!(import.meta.env && import.meta.env.DEV);
const ADMIN_PATH = WHICH !== "admin" ? ""
  : ((window.location.pathname || "").split("/")[1] || (DEV ? (import.meta.env.VITE_ADMIN_PATH || "") : ""));

if (WHICH === "admin" && ADMIN_PATH) {
  // یک در برای ۱۶۸ فراخوانی: هدر همین‌جا به هر درخواستِ مدیر اضافه می‌شود،
  // نه در تک‌تکِ `fetch`ها — که یکی‌شان روزی جا می‌ماند و بی‌صدا ۴۰۴ می‌گرفت.
  const orig = window.fetch.bind(window);
  window.fetch = (input, init) => {
    try {
      const url = typeof input === "string" ? input : (input && input.url) || "";
      if (/\/api\/(admin|login)(\/|\?|$)/.test(url)) {
        const h = init && init.headers;
        if (h && typeof h.set === "function") {
          h.set("X-Admin-Path", ADMIN_PATH);
        } else {
          init = { ...(init || {}), headers: { ...(h || {}), "X-Admin-Path": ADMIN_PATH } };
        }
      }
    } catch { /* هدر نرسید؛ سرور ۴۰۴ می‌دهد و صفحه خطا را می‌گوید */ }
    return orig(input, init);
  };
}

/** «این نشانی درست است؟» — پیش از دانلودِ خودِ پنل. */
async function adminGate() {
  if (WHICH !== "admin") return "ok";
  if (!ADMIN_PATH) return "hidden";
  // سقفِ ۴ ثانیه: سروری که جواب نمی‌دهد نباید صفحه را برای همیشه سفید نگه
  // دارد — بعدش صفحه‌ی ورود می‌آید و خودش «اتصال برقرار نشد» را می‌گوید
  const ctl = typeof AbortController === "function" ? new AbortController() : null;
  const timer = ctl && setTimeout(() => ctl.abort(), 4000);
  try {
    const r = await fetch(`${API_URL}/api/admin/ping`, ctl ? { signal: ctl.signal } : undefined);
    return r.status === 404 ? "hidden" : "ok";
  } catch {
    // شبکه: صفحه‌ی ورود خودش خطای اتصال را می‌گوید — «پیدا نشد» دروغ بود
    return "ok";
  } finally { if (timer) clearTimeout(timer); }
}
const GATE = adminGate();

/** «پیدا نشد»ِ خنثی — نه صفحه‌ی ورود، نه نامِ نکسورا. */
function Hidden() {
  React.useEffect(() => { try { document.title = "404"; } catch { /* */ } }, []);
  return (
    <div dir="rtl" style={{ minHeight: "100vh", display: "grid", placeContent: "center",
      justifyItems: "center", gap: 8, background: "var(--bg)", color: "var(--muted)",
      fontFamily: "var(--sans)" }}>
      <b style={{ fontSize: 44, color: "var(--text)", fontFamily: "var(--num)" }}>۴۰۴</b>
      <span style={{ fontSize: 14 }}>صفحه پیدا نشد</span>
    </div>
  );
}

// دانلود **همین حالا** شروع می‌شود، نه موقع رندر.
//
// `lazy()` تا اولین رندر چیزی را نمی‌آورد. با کفِ زمانیِ پایین، آن
// یعنی اول ۱٫۹ ثانیه صبر و *بعد* شروعِ دانلود — دو کار پشت سر هم به
// جای هم‌زمان. این‌طور هر دو با هم می‌دوند و کف واقعاً فقط کف است.
const CHUNK = WHICH === "admin"
  ? GATE.then((g) => (g === "ok" ? PICK.admin() : { default: Hidden }))
  : PICK[WHICH]();
const Root = lazy(() => CHUNK);

// تا رسیدنِ تکه، صفحه نباید سفید بماند.
//
// `Splash` از `lib/mark.jsx` می‌آید که مثل `lib/route.js` هیچ
// وابستگی‌ای ندارد — اگر از کتابخانه‌ی UI می‌آمد، همه‌ی آیکون‌هایش
// هم داخل تکه‌ی ورودی می‌نشستند و lazy بی‌معنی می‌شد.
const BOOT_LABEL = { mini: "اشتراک من", portal: "پنل نمایندگی",
                     aff: "پنل همکار فروش", admin: "پنل مدیریت" }[WHICH];

/*
 * برندِ فروشگاه، از کشِ دفعه‌ی قبل.
 *
 * موقعِ اسپلش هنوز `/api/mini/me` نیامده، پس نمی‌دانیم مشتریِ کدام
 * فروشگاه است. دفعه‌ی قبل می‌دانستیم و نگهش داشتیم.
 *
 * و اگر هیچ‌وقت ندانستیم، نشانِ **خودمان** را نشان نمی‌دهیم —
 * مشتریِ نماینده نباید بفهمد پشتِ فروشگاه نکسوراست. یک نشانِ خنثی
 * می‌آید تا وقتی برند برسد.
 *
 * `localStorage` ممکن است در حالتِ ناشناس یا با کوکیِ بسته اصلاً
 * کار نکند، پس هر خواندنی داخلِ try است و نبودنش فقط یعنی اسپلشِ
 * خنثی.
 */
function cachedShop() {
  if (WHICH !== "mini") return null;
  // پیش‌نمایشِ پرتال فروشگاهِ نمونه است؛ کشِ مرورگرِ نماینده را نخواند
  try { if (new URLSearchParams(window.location.search).get("preview") === "1") return null; }
  catch { /* */ }
  return readShop();
}

let SHOP = cachedShop();

// پوسته‌ی فروشگاه (قالب + پالت) پیش از اولین رندر، تا صفحه‌ی ورود هم
// مالِ خودش باشد — قالبِ «پررنگ» اسپلشِ تمام‌رنگ دارد، «مینیمال» بی‌مدار.
// پوسته‌ی تلگرام این‌جا هنوز روی ریشه ننشسته، پس از خودِ SDK پرسیده
// می‌شود؛ مینی‌اپ بعداً با پوسته‌ی قطعی دوباره می‌سازدش.
const themeOf = (sh) => (sh
  ? (sh.theme || (sh.accent ? { palette: "custom", accent: sh.accent } : null))
  : null);
let SHOP_THEME = themeOf(SHOP);
function paintShop() {
  try {
    if (WHICH === "mini") {
      const scheme = markScheme(window.Telegram && window.Telegram.WebApp);
      if (SHOP_THEME) applyTheme(SHOP_THEME, scheme);
    }
  } catch { /* رنگ تزئین است، نه شرطِ بالاآمدن */ }
}
paintShop();

/**
 * بارِ اول، ظاهرِ فروشگاه را پیش از اولین فریم بپرس.
 *
 * بی‌کش، اسپلش خنثی بود و بعد به لوگو و رنگِ فروشگاه می‌پرید —
 * مالک و نماینده هر دو دیدند «اولش لوگو و رنگ نمی‌آید». حالا اگر
 * کشی نیست و آدرس `?shop=` دارد، `/api/mini/brand` پرسیده می‌شود —
 * با سقفِ ۹۰۰ میلی‌ثانیه، تا سرورِ کُند صفحه را گروگان نگیرد. شکست یعنی
 * همان اسپلشِ خنثیِ قبلی، نه صفحه‌ی سفید.
 */
async function prefetchShop() {
  if (WHICH !== "mini" || SHOP) return;
  let id = "";
  try { id = new URLSearchParams(window.location.search).get("shop") || ""; } catch { return; }
  if (!/^\d{1,9}$/.test(id)) return;
  const ctl = typeof AbortController === "function" ? new AbortController() : null;
  const timer = ctl && setTimeout(() => ctl.abort(), 900);
  try {
    const r = await fetch(`${API_URL}/api/mini/brand?shop=${id}`,
      ctl ? { signal: ctl.signal } : undefined);
    if (!r.ok) return;
    const j = await r.json();
    if (!j || typeof j !== "object") return;
    SHOP = { brand: String(j.brand || ""), logo: String(j.logo || ""),
             accent: String(j.accent || ""), theme: j.theme || null };
    SHOP_THEME = themeOf(SHOP);
    writeShop(SHOP);
    paintShop();
  } catch { /* شبکه یا سقفِ زمان — اسپلشِ خنثی، مثلِ قبل */ }
  finally { if (timer) clearTimeout(timer); }
}

// عنوانِ پنجره هم همین است — تلگرام آن را بالای مینی‌اپ نشان
// می‌دهد، و `index.html` یک عنوانِ مشترک برای هر چهار اپ دارد.
try {
  if (WHICH === "mini") {
    document.title = (SHOP && SHOP.brand) || "اشتراک من";
  }
} catch { /* عنوان تزئین است، نه شرطِ بالاآمدن */ }

/**
 * صفحه‌ی ورود، با وضعیتِ واقعی.
 *
 * `note` را از خودِ کار می‌گیرد، نه از یک تایمر: تا وقتی تکه نرسیده
 * «در حال بارگذاری» و اگر نرسید، «نیامد» با دکمه‌ی تلاش دوباره.
 * درصدِ ساختگی نشان نمی‌دهیم — دروغ است و کاربر هم می‌فهمد.
 */
function Booting({ phase, note, onRetry, slow }) {
  return <Splash label={BOOT_LABEL} phase={phase} note={note}
    onRetry={onRetry} slow={slow}
    name={(SHOP && SHOP.brand) || ""}
    logo={(SHOP && SHOP.logo) || ""}
    logoStyle={SHOP_THEME && SHOP_THEME.logoStyle}
    variant={SHOP_THEME && SHOP_THEME.splash}
    neutral={WHICH === "mini"} />;
}

/**
 * از صفحه‌ی ورود به اپ — با یک خروجِ نرم.
 *
 * سه چیز باید هم‌زمان درست شوند:
 *
 *   ۱. تکه‌ی اپ برسد (کارِ واقعی)
 *   ۲. حرکتِ نشان تا آخر دیده شود (کفِ زمانی)
 *   ۳. قطعِ ناگهانی نباشد (خروجِ نرم)
 *
 * کف، *کف* است نه تأخیر: دانلود از پیش شروع شده و هم‌زمان می‌دود.
 * و اگر کاربر حرکت را خاموش کرده، هر دو برداشته می‌شوند — کسی که
 * `prefers-reduced-motion` گذاشته، انیمیشنی ندارد که منتظرش بماند.
 */
const SPLASH_MS = 1700;
const EXIT_MS = 380;
/* The longest the boot splash waits for the mini app's first data. */
const APP_WAIT_MS = 8000;

const reload = () => { try { window.location.reload(); } catch { /* */ } };

function Gate({ children }) {
  // پیش‌نمایشِ پرتال: هر بار که قاب بار می‌شود ۱٫۷ ثانیه صفحه‌ی ورودِ
  // بی‌نام نشان می‌داد، پیش از آنکه پوسته برسد. پخشش با دکمه است.
  const skip = typeof window !== "undefined"
    && (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
        || /[?&]preview=1\b/.test(window.location.search));

  const [phase, setPhase] = React.useState(skip ? "in" : "load");
  const [err, setErr] = React.useState("");
  const [ready, setReady] = React.useState(false);
  // The mini app loads its data after its code arrives, and showed its own
  // splash meanwhile: the buyer saw this splash fade out and the same splash
  // start over (docs/specs/2026-09-30-vpn-fixes.md, task 2). So for the
  // mini app this one stays on top, over the mounting app, until the app
  // says it has something to show (`nx-app-ready`), with a cap so a slow
  // answer never holds the screen.
  const waitApp = WHICH === "mini" && !skip;
  const [appReady, setAppReady] = React.useState(!waitApp);
  React.useEffect(() => {
    if (!waitApp) return undefined;
    const on = () => setAppReady(true);
    window.addEventListener("nx-app-ready", on);
    const cap = setTimeout(on, APP_WAIT_MS);
    return () => { window.removeEventListener("nx-app-ready", on); clearTimeout(cap); };
  }, [waitApp]);
  const [slow, setSlow] = React.useState(false);
  const t0 = React.useRef(Date.now());

  // ۱. تکه واقعاً رسید؟
  React.useEffect(() => {
    let alive = true;
    CHUNK.then(() => { if (alive) { setErr(""); setReady(true); } })
         .catch(() => { if (alive) setErr("برنامه بارگذاری نشد."); });
    return () => { alive = false; };
  }, []);

  // ۲. دیده‌بان: دانلودی که نه می‌رسد نه شکست می‌خورد (اینترنتِ قطع‌ووصل)
  // تا امروز اسپلشِ بی‌پایان بود — نه خطا، نه «دوباره». مالک و نماینده
  // هر دو روی همان صفحه ماندند.
  React.useEffect(() => {
    if (ready || err) return undefined;
    const id = setTimeout(() => setSlow(true), SLOW_MS);
    return () => clearTimeout(id);
  }, [ready, err]);

  // ۳+۴. کف، بعد خروج — فقط وقتی تکه رسیده. خروجِ نرم پیش از رسیدن یعنی
  // صفحه محو می‌شد و همان اسپلش دوباره از Suspense بالا می‌آمد.
  React.useEffect(() => {
    if (skip || err || !ready || !appReady) return undefined;
    const wait = Math.max(0, SPLASH_MS - (Date.now() - t0.current));
    const a = setTimeout(() => setPhase("done"), wait);
    const b = setTimeout(() => setPhase("in"), wait + EXIT_MS);
    return () => { clearTimeout(a); clearTimeout(b); };
  }, [skip, err, ready, appReady]);

  if (err) {
    return <Booting phase="error" note={err} onRetry={reload} />;
  }
  if (phase === "in" && (ready || skip)) return children;
  if (ready && waitApp) {
    // The app mounts underneath and fetches; this splash covers it and
    // fades out over it, so there is one splash, not two.
    return (
      <>
        {children}
        <div className="nx-boot-over">
          <Booting phase={phase === "in" ? "load" : phase} note="در حال آماده‌سازی…"
            onRetry={reload} />
        </div>
      </>
    );
  }
  return <Booting phase={phase === "in" ? "load" : phase} note="در حال آماده‌سازی…"
    slow={slow && !ready ? SLOW_NOTE : ""} onRetry={reload} />;
}

Promise.all([prefetchShop(), GATE]).finally(async () => {
  try { if (WHICH === "mini") document.title = (SHOP && SHOP.brand) || document.title; }
  catch { /* عنوان تزئین است */ }
  // نشانیِ غلط: همان «پیدا نشد»، بی اسپلشِ «پنل مدیریت» — وگرنه همان اسپلش
  // می‌گفت این‌جا پنلی هست
  if ((await GATE) !== "ok") {
    ReactDOM.createRoot(document.getElementById("root")).render(<Hidden />);
    return;
  }
  ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <Suspense fallback={<Booting />}>
        <Gate><Root /></Gate>
      </Suspense>
    </React.StrictMode>
  );
});
