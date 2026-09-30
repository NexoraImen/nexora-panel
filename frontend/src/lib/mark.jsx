/**
 * نشانِ نکسورا و صفحه‌ی ورود.
 *
 * چرا این‌جا و نه در `ui/index.jsx`: صفحه‌ی ورود را `main.jsx` نشان
 * می‌دهد، یعنی *قبل* از رسیدنِ تکه‌ی اپ. اگر از کتابخانه‌ی UI بیاید،
 * کلِ آن کتابخانه (با همه‌ی آیکون‌هایش) داخل تکه‌ی ورودی می‌نشیند و
 * همان کاری را می‌کند که lazy برای جلوگیری‌اش گذاشته شده.
 *
 * پس این ماژول عمداً هیچ وابستگی‌ای جز خودِ React ندارد — مثل
 * `lib/route.js`.
 */
import React from "react";
import { ShopLogo } from "./shoplogo.jsx";

/* شناسه‌ی یکتا برای گرادیان‌ها: اگر دو نشان هم‌زمان رندر شوند و هر دو
   یک id داشته باشند، مرورگر اولی را به هر دو می‌دهد و دومی رنگِ
   اشتباه می‌گیرد. */
let _seq = 0;

/**
 * نشان — یا لوگوی آپلودشده‌ی همان فروشگاه.
 *
 * `src` که بیاید، تصویرِ خودِ نماینده نشان داده می‌شود و نشانِ نکسورا
 * کنار می‌رود. این همان چیزی است که مینی‌اپِ هر نماینده را مالِ خودش
 * می‌کند.
 *
 * اگر تصویر بالا نیاید (پاک شده، شبکه قطع)، بی‌صدا به نشانِ نکسورا
 * برمی‌گردد — نه قابِ خالیِ شکسته.
 */
export function NexoraMark({ size = 96, animate = false, src = "",
                             alt = "", className = "", neutral = false }) {
  const uid = React.useMemo(() => "nx" + (++_seq), []);
  const [failed, setFailed] = React.useState(false);
  React.useEffect(() => { setFailed(false); }, [src]);

  if (src && !failed) {
    return (
      <img src={src} alt={alt || "لوگو"} width={size} height={size}
        className={`nx-logo ${animate ? "go" : ""} ${className}`}
        onError={() => setFailed(true)} />
    );
  }

  // نشانِ خنثی: وقتی نمی‌دانیم فروشگاه مالِ کیست، نشانِ **خودمان**
  // را نشان نمی‌دهیم. مشتریِ نماینده نباید بفهمد پشتش نکسوراست.
  if (neutral) {
    return (
      <svg viewBox="0 0 120 120" width={size} height={size}
        className={`nx-mark ${animate ? "go" : ""} ${className}`}
        role="img" aria-label={alt || "فروشگاه"}>
        <defs>
          <linearGradient id={uid + "q"} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="currentColor" stopOpacity=".55" />
            <stop offset="100%" stopColor="currentColor" stopOpacity=".18" />
          </linearGradient>
        </defs>
        <rect x="18" y="18" width="84" height="84" rx="26"
          fill={`url(#${uid}q)`} />
        <circle cx="60" cy="60" r="17" fill="none" stroke="currentColor"
          strokeWidth="5" strokeLinecap="round" opacity=".85"
          strokeDasharray="80 27" />
      </svg>
    );
  }

  const gN = uid + "n";
  const gR = uid + "r";

  return (
    <svg viewBox="0 0 120 120" width={size} height={size}
      className={`nx-mark ${animate ? "go" : ""} ${className}`}
      role="img" aria-label="نکسورا">
      <defs>
        {/* آبیِ برند → فیروزه‌ای، همان زاویه‌ی نشانِ نوار کناری */}
        <linearGradient id={gN} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#8FC1EE" />
          <stop offset="58%" stopColor="#2B7FD6" />
          <stop offset="100%" stopColor="#2DD4BF" />
        </linearGradient>
        {/* حلقه نقره‌ای است، نه آبی — در لوگو همین تضاد است که
            حجم می‌سازد */}
        <linearGradient id={gR} x1="0" y1="0" x2="1" y2="0.6">
          <stop offset="0%" stopColor="#EEF3F9" />
          <stop offset="45%" stopColor="#93A4B8" />
          <stop offset="100%" stopColor="#5AA9E6" />
        </linearGradient>
      </defs>

      {/* حلقه دو نیمه است تا مثل خودِ لوگو از پشتِ N رد شود و
          جلویش دربیاید — همین تقاطع است که به نشان حجم می‌دهد.
          دو نقطه‌ی انتها روی بیضیِ چرخیده‌ی (rx 50، ry 17، ‎-22°)
          حساب شده‌اند؛ اگر یکی را دست بزنی، حلقه باز می‌ماند. */}
      <path className="nx-ring back"
        d="M96.97 35.90 A50 17 -22 0 0 23.04 84.10"
        fill="none" stroke={`url(#${gR})`} strokeWidth="5"
        strokeLinecap="round" opacity=".5" />

      <path className="nx-n"
        d="M30 92 V28 H50 L74 70 V28 H90 V92 H70 L46 50 V92 Z"
        fill={`url(#${gN})`} />

      <path className="nx-ring front"
        d="M23.04 84.10 A50 17 -22 0 0 96.97 35.90"
        fill="none" stroke={`url(#${gR})`} strokeWidth="5"
        strokeLinecap="round" />
    </svg>
  );
}

/**
 * حلقه‌ی راه‌اندازی.
 *
 * چرخنده نیست. یک مدارِ نقطه‌چین با کمانی که رویش می‌چرخد — حسِ
 * «دارد وصل می‌شود»، نه «منتظر بمان». تعمداً نامعین است: پیشرفتِ
 * دانلودِ یک تکه را نمی‌شود صادقانه اندازه گرفت، و درصدِ ساختگی
 * دروغ است.
 *
 * فقط `transform` و `stroke-dashoffset` حرکت می‌کنند — هیچ‌کدام
 * چیدمان را دوباره حساب نمی‌کنند. این صفحه دقیقاً وقتی دیده می‌شود
 * که مرورگر دارد یک باندل را parse می‌کند، یعنی بدترین لحظه برای
 * انیمیشنی که نخِ اصلی را بگیرد.
 */
function OrbitRing({ size = 168, state = "load" }) {
  const R = 78;
  const C = 2 * Math.PI * R;
  // شش گرهِ روی مدار — «شبکه»، نه تزئین
  const nodes = [0, 60, 120, 180, 240, 300];
  return (
    <svg className={`nx-orbit ${state}`} width={size} height={size}
      viewBox="0 0 180 180" aria-hidden="true">
      {/* مدارِ کم‌رنگ */}
      <circle cx="90" cy="90" r={R} fill="none"
        stroke="var(--hair-3)" strokeWidth="1" strokeDasharray="2 6" />
      {/* کمانِ چرخان */}
      <circle className="nx-sweep" cx="90" cy="90" r={R} fill="none"
        stroke="url(#nxSweep)" strokeWidth="2.5" strokeLinecap="round"
        strokeDasharray={`${C * 0.16} ${C}`} />
      <defs>
        <linearGradient id="nxSweep" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0" />
          <stop offset="60%" stopColor="var(--accent-2)" />
          <stop offset="100%" stopColor="var(--cy)" />
        </linearGradient>
      </defs>
      {nodes.map((deg, i) => {
        const a = (deg - 90) * Math.PI / 180;
        return (
          <circle key={deg} className="nx-node" r="2.5"
            cx={90 + R * Math.cos(a)} cy={90 + R * Math.sin(a)}
            style={{ animationDelay: `${i * 0.22}s` }} />
        );
      })}
    </svg>
  );
}

/**
 * صفحه‌ی ورود.
 *
 * `phase`:
 *   load   در حال آمدن
 *   done   رسید — خروجِ نرم پیش از نمایشِ اپ
 *   error  نیامد — با دکمه‌ی تلاش دوباره
 *
 * `note` متنِ وضعیت است و باید *واقعی* باشد. درصدِ ساختگی نشان
 * نمی‌دهیم؛ اگر چیزی برای گفتن نیست، هیچ نمی‌گوییم.
 */
/**
 * صفحه‌ی ورودِ **فروشگاه** — مینی‌اپِ مشتری.
 *
 * چرا جدا از صفحه‌ی ورودِ پنل: آن یکی برای «NEXORA» طراحی شده بود —
 * مدارِ نقطه‌چین، واژه‌ای که از فاصله‌ی باز جمع می‌شود. روی نامِ
 * فروشگاه این‌ها خراب می‌شدند:
 *
 *   · حرکتِ «فاصله‌ی باز → بسته» حرف‌های فارسی را از هم جدا می‌کرد؛
 *     «نکسورا» تا آخرِ حرکت «ن ک س و ر ا» بود. قالبِ نئون هم فاصله‌ی
 *     ثابت داشت — نام برای همیشه شکسته.
 *   · قالبِ پررنگ پایینِ صفحه یک نوارِ سیاه داشت (شیب تا زمینه).
 *   · زیرِ نامِ فروشگاه «اشتراک من» تکرار می‌شد.
 *
 * حالا: لوگو، نام، و یک نوارِ پیشرفتِ باریک. هر قالب شکلِ خودش را از
 * CSS می‌گیرد (`html[data-mn-tpl]`). حرکت فقط شفافیت و جابه‌جایی است —
 * هیچ‌وقت فاصله‌ی حروف.
 */
// شناسه‌ها همان `MINI_SPLASHES` در mini-themes.js‌اند. این‌جا فهرست
// کپی نشده: این فایل عمداً به هیچ ماژولِ دیگری جز لوگو وابسته نیست
// (تکه‌ی ورودی)، پس هر شناسه‌ی ناشناس همان «نوار» است.
const SPLASH_IDS = ["bar", "ring", "pulse", "dots", "logo"];

//: بعد از این‌قدر، اسپلش می‌گوید «کُند است» و «دوباره» می‌دهد — ولی هنوز
//: منتظر می‌ماند. یک‌جا، چون دو اسپلش دارد: main.jsx (دریافتِ برنامه) و
//: مینی‌اپ (دریافتِ اطلاعاتِ حساب).
export const SLOW_MS = 10000;
export const SLOW_NOTE = "اتصال کُند است — هنوز در حال دریافت…";

function ShopSplash({ logo, name, logoStyle, phase, note, onRetry, label, variant, slow }) {
  const known = !!(logo || name);
  const v = SPLASH_IDS.includes(variant) ? variant : "bar";
  const big = v === "logo" ? 128 : 96;
  const busy = note || "در حال آماده‌سازی";
  return (
    <div className={`nx-splash nx-shop sp-${v} ${phase}`} dir="rtl" role="status" aria-live="polite">
      <div className="nx-shop-glow" aria-hidden="true" />
      <div className="nx-shop-stage">
        <div className="nx-shop-mark">
          {/* حلقه و موج دورِ خودِ لوگو می‌نشینند، نه زیرش */}
          {v === "ring" && phase !== "error" && <span className="nx-sp-ring" aria-hidden="true" />}
          {v === "pulse" && phase !== "error" && (
            <span className="nx-sp-pulse" aria-hidden="true"><i /><i /><i /></span>
          )}
          {known ? (
            <ShopLogo src={logo} name={name} style={logoStyle} size={big}
              className="nx-shop-logo" />
          ) : (
            // هنوز نمی‌دانیم فروشگاه کیست (اولین بازکردن): جای لوگو،
            // نه نشانِ کسِ دیگری
            <span className="nx-shop-ghost" aria-hidden="true" />
          )}
        </div>
        {/* «فقط لوگو» نام را نمی‌نویسد — مگر هنوز لوگویی نیست، که آن‌وقت
            صفحه فقط یک مربعِ خالی می‌شد */}
        {(v !== "logo" || !known) && <div className="nx-shop-name">{name || label}</div>}
        {phase === "error" ? (
          <div className="nx-fail">
            <p>{note || "اتصال برقرار نشد."}</p>
            {onRetry && <button className="nx-retry" onClick={onRetry}>تلاش دوباره</button>}
          </div>
        ) : v === "bar" ? (
          <div className="nx-shop-bar" aria-label={busy}><i /></div>
        ) : v === "dots" ? (
          <div className="nx-sp-dots" aria-label={busy}><i /><i /><i /></div>
        ) : (
          // حلقه و موج و لوگو خودشان نشانِ «در حال آمدن»‌اند؛ متن فقط
          // برای صفحه‌خوان
          <span className="sr-only">{busy}</span>
        )}
        {/* کُند: هنوز منتظریم، ولی کاربر باید بداند و راهِ «دوباره» داشته
            باشد. بی این، دانلودی که روی اینترنتِ قطع‌ووصل وسطِ راه ماند
            اسپلشِ بی‌پایان بود — مالک و نماینده هر دو دیدند. */}
        {slow && phase !== "error" && (
          <div className="nx-slow">
            <p>{slow}</p>
            {onRetry && <button className="nx-retry" onClick={onRetry}>دوباره</button>}
          </div>
        )}
      </div>
    </div>
  );
}

export function Splash({ label = "", logo = "", name = "",
                        phase = "load", note = "", onRetry,
                        neutral = false, logoStyle = null, variant = "", slow = "" }) {
  // مینی‌اپِ فروشگاه صفحه‌ی ورودِ خودش را دارد
  if (neutral) {
    return <ShopSplash logo={logo} name={name} logoStyle={logoStyle} phase={phase}
      note={note} onRetry={onRetry} label={label} variant={variant} slow={slow} />;
  }
  return (
    <div className={`nx-splash ${phase}`} dir="rtl" role="status" aria-live="polite">
      {/* نورِ محیطی — دو لکه‌ی بسیار محو که آرام جابه‌جا می‌شوند */}
      <div className="nx-amb-a" aria-hidden="true" />
      <div className="nx-amb-b" aria-hidden="true" />

      <div className="nx-stage">
        {phase !== "error" && <OrbitRing state={phase} />}
        <div className="nx-mark-wrap">
          {/* مینی‌اپِ فروشگاهی که می‌شناسیم: لوگوی خودش با همان قاب و
              زمینه‌ای که در سربرگ دارد — یا نشانِ خودکار از نامش.
              نشانِ خنثی فقط وقتی هنوز هیچ نمی‌دانیم. */}
          <NexoraMark size={84} animate src={logo} alt={name} />
        </div>
      </div>

      {/* «NEXORA» فقط وقتی نوشته می‌شود که خودمان باشیم. روی
          مینی‌اپِ نماینده، یا نامِ فروشگاهِ اوست یا هیچ. */}
      {(name || !neutral) && (
        <div className="nx-word">{name || "NEXORA"}</div>
      )}
      {label ? <div className="nx-sub">{label}</div> : null}

      {phase === "error" ? (
        <div className="nx-fail">
          <p>{note || "اتصال برقرار نشد."}</p>
          {onRetry && (
            <button className="nx-retry" onClick={onRetry}>تلاش دوباره</button>
          )}
        </div>
      ) : (
        note ? <div className="nx-note">{note}</div> : null
      )}
      {slow && phase !== "error" && (
        <div className="nx-slow">
          <p>{slow}</p>
          {onRetry && <button className="nx-retry" onClick={onRetry}>دوباره</button>}
        </div>
      )}
    </div>
  );
}
