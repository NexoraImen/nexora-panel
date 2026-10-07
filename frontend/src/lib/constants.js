/**
 * ثابت‌های سراسری پنل.
 *
 * از App.jsx جدا شد؛ آن فایل ۱۱۴۰۰ خط بود و پیداکردن یک کامپوننت
 * در آن عملاً ناممکن.
 */
import {
  Activity, AlertTriangle, Apple, Bell, Bot, Clock, Coins, CreditCard, Database, DollarSign, Eye, FileText, Gift, HelpCircle, Key, Layers, LayoutGrid, Link2, MessageCircle, MessageSquare, Monitor, Megaphone, Network, Package, Power, Send, Server, ShieldCheck, Sliders, Smartphone, Tag, TrendingUp, Users, Video, Wallet, XCircle, Zap,
} from "lucide-react";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8100";

export const OS_TABS = [
  { key: "android", label: "اندروید", icon: Smartphone },
  { key: "ios", label: "آیفون / آیپد", icon: Apple },
  { key: "desktop", label: "ویندوز", icon: Monitor },
];

export const LANG_TABS = [
  { key: "fa", label: "فارسی" }, { key: "en", label: "English" },
  { key: "tr", label: "Türkçe" }, { key: "ar", label: "العربية" },
];

export const SCHEME_OPTIONS = [
  { value: "happ", label: "Happ", icon: Zap },
  { value: "v2rayng", label: "v2rayNG", icon: Send },
  { value: "v2box", label: "V2Box", icon: ShieldCheck },
  { value: "none", label: "بدون افزودن یک‌کلیک", icon: Package },
];

export const SCHEME_ICON = Object.fromEntries(SCHEME_OPTIONS.map((s) => [s.value, s.icon]));

// ═══ دو حالت کاری پنل ═══
// کاربر با یک سوییچ بین «مدیریت صفحه اشتراک» و «مدیریت ربات» جابه‌جا می‌شود.
// این کار منو را کوتاه و متمرکز نگه می‌دارد.
export const WORKSPACES = {
  sub: {
    key: "sub",
    label: "صفحه اشتراک",
    shortLabel: "ساب",
    icon: Layers,
    groups: [
      {
        title: "مدیریت",
        items: [
          { key: "overview", label: "داشبورد", icon: LayoutGrid },
          { key: "preview", label: "پیش‌نمایش زنده", icon: Eye },
          { key: "resellers", label: "واسطه‌ها", icon: Users },
        ],
      },
      {
        title: "محتوای صفحه",
        items: [
          { key: "apps", label: "اپلیکیشن‌ها", icon: Smartphone },
          { key: "faq", label: "سوالات متداول", icon: HelpCircle },
          { key: "videos", label: "ویدیوهای آموزشی", icon: Video },
          { key: "links", label: "لینک‌ها", icon: Link2 },
        ],
      },
      {
        title: "ظاهر و رفتار",
        items: [
          { key: "banners", label: "بنرهای هشدار", icon: Bell },
          { key: "popup", label: "پاپ‌آپ راهنما", icon: MessageSquare },
          { key: "referral", label: "رفرال", icon: Gift },
          { key: "themes", label: "قالب‌ها", icon: Layers },
          { key: "settings", label: "تنظیمات ظاهری", icon: Sliders },
        ],
      },
      {
        title: "سیستم",
        items: [
          { key: "system", label: "به‌روزرسانی", icon: Server },
        ],
      },
    ],
  },
  billing: {
    key: "billing",
    label: "حسابداری",
    shortLabel: "حساب",
    icon: Wallet,
    groups: [
      {
        title: "نمای کلی",
        items: [
          { key: "bill-dash", label: "داشبورد", icon: TrendingUp, pro: "accounting" },
          { key: "bill-ledger", label: "دفتر کل", icon: FileText, pro: "accounting" },
          { key: "bill-expenses", label: "هزینه‌ها", icon: DollarSign, pro: "accounting" },
        ],
      },
      {
        title: "واسطه‌ها",
        items: [
          { key: "bill-groups", label: "واسطه‌ها و نرخ", icon: Users, pro: "accounting" },
          { key: "bill-invoice", label: "صورتحساب", icon: FileText, pro: "accounting" },
          { key: "bill-period", label: "صورتحساب دوره", icon: Clock, pro: "accounting" },
          { key: "bill-pay", label: "پرداخت‌ها", icon: Wallet, pro: "accounting" },
          { key: "bill-clients", label: "همه کاربران", icon: Users, pro: "accounting" },
        ],
      },
      {
        title: "سیستم",
        items: [
          { key: "bill-settings", label: "تنظیمات و بک‌آپ", icon: Sliders },
        ],
      },
    ],
  },
  tunnel: {
    key: "tunnel",
    label: "تانل",
    shortLabel: "تانل",
    icon: Network,
    groups: [
      {
        title: "زیرساخت",
        items: [
          { key: "tun-overview", label: "داشبورد", icon: LayoutGrid, pro: "monitoring_multi" },
          { key: "tun-nodes", label: "سرورها", icon: Server, pro: "monitoring_multi" },
          { key: "tun-list", label: "تانل‌ها", icon: Network, pro: "monitoring_multi" },
          { key: "tun-inbounds", label: "اینباندها", icon: ShieldCheck, pro: "diagnostics" },
        ],
      },
      {
        title: "پایش و عیب‌یابی",
        items: [
          { key: "tun-diag", label: "عیب‌یابیِ ارتباط", icon: Zap, pro: "diagnostics" },
          { key: "tun-traffic", label: "حجمِ ترافیک", icon: TrendingUp, pro: "monitoring_multi" },
          { key: "monitor", label: "مانیتورینگ سرور", icon: Activity },
          { key: "nodes-monitor", label: "مانیتورینگ سرورهای دیگر", icon: Server, pro: "monitoring_multi" },
          { key: "tun-health", label: "سلامت سرورها", icon: ShieldCheck, pro: "monitoring_multi" },
          { key: "tun-events", label: "رویدادها", icon: Clock, pro: "monitoring_multi" },
          { key: "tun-bot", label: "ربات تانل", icon: Bot, pro: "monitoring_multi" },
        ],
      },
    ],
  },
  reseller: {
    key: "reseller",
    label: "نمایندگی",
    shortLabel: "نماینده",
    icon: Link2,
    groups: [
      {
        title: "نماینده‌ها",
        items: [
          { key: "bill-portal", label: "نماینده‌ها و دسترسی", icon: Users, pro: "resellers" },
          { key: "res-inbounds", label: "اینباند نماینده‌ها", icon: Network, pro: "resellers" },
        ],
      },
    ],
  },
  channel: {
    key: "channel",
    label: "کانال",
    shortLabel: "کانال",
    icon: Megaphone,
    groups: [
      {
        title: "محتوا",
        items: [
          { key: "channel", label: "نوشتن و زمان‌بندی", icon: Megaphone, pro: "channel" },
        ],
      },
    ],
  },
  firewall: {
    key: "firewall",
    label: "فایروال",
    shortLabel: "فایروال",
    icon: ShieldCheck,
    groups: [
      {
        title: "امنیت سرور",
        items: [
          { key: "fw-enable", label: "روشن‌کردن فایروال", icon: Power, pro: "diagnostics" },
          { key: "fw-rules", label: "قواعد فایروال", icon: ShieldCheck, pro: "diagnostics" },
          { key: "fw-intrusion", label: "تلاش برای نفوذ", icon: AlertTriangle, pro: "diagnostics" },
          { key: "fw-blocked", label: "آی‌پی‌های بسته‌شده", icon: XCircle, pro: "diagnostics" },
        ],
      },
    ],
  },
  bot: {
    key: "bot",
    label: "ربات تلگرام",
    shortLabel: "ربات",
    icon: Bot,
    groups: [
      // چهار دسته به ترتیبِ کارِ روزانه: اول چیزی که هر روز باز می‌شود
      {
        title: "فروش",
        items: [
          { key: "bot-orders", label: "سفارش‌ها و رسیدها", icon: CreditCard,
            alert: "receipts" },
          { key: "bot-inbox", label: "پیام‌ها", icon: MessageCircle,
            alert: "messages" },
          { key: "bot-users", label: "کاربران ربات", icon: Users },
          { key: "bot-smspay", label: "تأیید خودکار رسید", icon: Zap, pro: "accounting" },
          { key: "bot-stats", label: "آمار و قیف", icon: TrendingUp, pro: "insights" },
          { key: "bot-report", label: "گزارش فروش", icon: FileText },
        ],
      },
      {
        title: "بازاریابی",
        items: [
          { key: "bot-coins", label: "سکه و دعوت", icon: Gift, pro: "loyalty" },
          { key: "bot-discounts", label: "کدهای تخفیف", icon: Tag, pro: "loyalty" },
          { key: "bot-affiliates", label: "همکاری در فروش", icon: Coins,
            alert: "affRequests", pro: "affiliates" },
        ],
      },
      {
        title: "پیکربندی",
        items: [
          { key: "bot", label: "اتصال و تنظیمات", icon: Key },
          { key: "bot-plans", label: "پلن‌ها و قیمت", icon: Package },
          { key: "bot-inbounds", label: "اینباندها", icon: Network },
          { key: "bot-texts", label: "متن‌ها و یادآوری‌ها", icon: MessageCircle },
          { key: "bot-mini", label: "پوسته‌ی مینی‌اپ", icon: Smartphone, pro: "mini_app" },
          { key: "bot-preview", label: "پیش‌نمایش ربات", icon: Eye, pro: "insights" },
        ],
      },
      {
        title: "سیستم",
        items: [
          { key: "bot-events", label: "رویدادها", icon: Clock },
          { key: "bot-backup", label: "ربات مدیریت و پشتیبان", icon: Database },
          { key: "system", label: "به‌روزرسانی", icon: Server },
        ],
      },
    ],
  },
};

export const WS_MODES = {
  accordion: { label: "تاشو", desc: "هر سه دیده می‌شوند، منوی فضای فعلی باز است" },
  dropdown:  { label: "کشویی", desc: "فضای فعلی بزرگ، بقیه با یک کلیک" },
  rail:      { label: "نوار آیکون", desc: "ستون باریک با آیکون و راهنمای شناور" },
};

export const WS_COLOR = {
  sub: "var(--accent-2)",
  billing: "#D4AF37",
  tunnel: "#34D399",
  bot: "#A78BFA",
  reseller: "#38BDF8",
  firewall: "#F87171",
};
