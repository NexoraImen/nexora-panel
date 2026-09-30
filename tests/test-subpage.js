// repo root — these tests moved from the root into tests/ (2.0 layout)
const ROOT_DIR = require("path").dirname(__dirname);
const { JSDOM } = require('jsdom');
const fs = require('fs');

const HTML_PATH = process.env.TEST_HTML || require('path').join(ROOT_DIR, 'sub-page-index.html');


// تنظیمات نمونه‌ای که بک‌اند برمی‌گرداند
const MOCK_CONFIG = {
  downloadApps: {
    android: [
      { id:'a1', name:'Happ', url:'https://x/happ.apk', recommended:true, scheme:'happ' },
      { id:'a2', name:'v2rayNG', url:'https://x/ng.apk', recommended:false, scheme:'v2rayng' },
      { id:'a3', name:'اپ سوم', url:'https://x/3.apk', recommended:false, scheme:'none' },
    ],
    ios: [{ id:'i1', name:'Happ iOS', url:'https://x/ios', recommended:true, scheme:'happ' }],
    desktop: [{ id:'d1', name:'Happ Win', url:'https://x/win', recommended:true, scheme:'happ' }],
  },
  faq: {
    fa: [
      { q:'سوال اول تستی', a:'پاسخ اول تستی' },
      { q:'سوال دوم تستی', a:'پاسخ دوم تستی' },
      { q:'سوال سوم تستی', a:'پاسخ سوم تستی' },
    ],
    en: [{ q:'Q1', a:'A1' }],
    tr: [], ar: [],
  },
  banners: { enabled:true, lowQuotaDaysThreshold:5, lowQuotaPercentThreshold:20,
             disabledTitle:'عنوان سفارشی قطعی', lowQuotaTitle:'عنوان سفارشی اتمام' },
  referral: { enabled:true },
  links: { supportUsername:'test_sup', channelUsername:'test_ch' },
  videos: [{ id:'v1', title:'ویدیو تستی', telegramUrl:'https://t.me/x/1', platform:'all' }],
  popup: { enabled:true, icon:'💡', title:'پاپ‌آپ سفارشی', description:'توضیح سفارشی',
           primaryButtonText:'تماس', dismissButtonText:'بعداً', delaySeconds:5, autoCloseSeconds:20 },
  advanced: {
    brandName:'TESTBRAND', pageTitle:'عنوان تست', accentColor:'#FF0000', accentColor2:'#00FF00',
    defaultLanguage:'fa', defaultTheme:'dark', showBrandStrip:true, showReferralCard:true,
    showFaqSection:true, showNotificationPopup:true, notificationDelaySeconds:5,
    allowThemeToggle:true, allowLanguageToggle:true, hideConfigsList:false,
    customCss:'.test{color:red}', customFooterText:'پاورقی تستی',
  },
};

// صفحه‌ی اشتراک یک *قالب Go* است، نه HTML آماده: x-ui موقع سرو کردن
// جای {{ .sId }} و امثالش مقدار می‌گذارد. تا قبل از این، تست فایل خام
// را به jsdom می‌داد و پارسر روی اولین {{ می‌شکست — برای همین هر ۱۷
// تست همیشه رد می‌شد و کسی نمی‌فهمید چون خطا فقط یک خط بود.
//
// این‌جا همان کاری را می‌کنیم که x-ui می‌کند: مقدار نمونه می‌گذاریم.
function renderTemplate(src) {
  // مقدارها بدون گیومه‌اند: آن‌هایی که در قالب داخل "..." نشسته‌اند
  // گیومه‌شان را از خود قالب می‌گیرند. اگر اینجا گیومه بگذاریم،
  // """" تولید می‌شود که JS نامعتبر است.
  const vars = {
    sId: 'abc123',
    enabled: 'true',
    expire: '1800000000',
    downloadByte: '10737418240',
    uploadByte: '1073741824',
    totalByte: '53687091200',
    lastOnline: '1800000000',
    subUrl: 'https://sub.test.com/sub/abc123',
    subClashUrl: 'https://sub.test.com/clash/abc123',
    subSupportUrl: 'https://t.me/support',
  };
  return src
    // حلقه‌های range که آرایه می‌سازند، اول و یکجا.
    //
    // شکلشان این است:
    //   [{{ range $i, $e := .emails }}{{ if $i }},{{ end }}"{{ $e }}"{{ end }}]
    //
    // جایگزینی تک‌تکِ جای‌نگهدارها این را به [,""""] تبدیل می‌کرد، چون
    // {{ $e }} داخل یک رشته‌ی جاوااسکریپت نشسته. پس کل بلوک را با یک
    // آرایه‌ی نمونه عوض می‌کنیم.
    .replace(/\[\{\{\s*range[^\]]*\]/g, (m) =>
      m.includes('.links') ? '["vless://sample@host:443#user"]'
                           : '["user@example.com"]')
    // بلوک‌های شرطی — خود تگ می‌رود، محتوایش می‌ماند
    .replace(/\{\{\s*(if|range|else|end)[^}]*\}\}/g, '')
    // جایگزینی آگاه از بافت.
    //
    // قالب گاهی جای‌نگهدار را داخل گیومه گذاشته ("{{ .subUrl }}") و
    // گاهی لخت ({{ .expire }}). اگر همیشه یک شکل بگذاریم، یکی از دو
    // حالت خراب می‌شود: یا """" می‌سازیم یا مقدار بی‌گیومه در جای
    // رشته. پس به کاراکتر قبل و بعد نگاه می‌کنیم.
    .replace(/\{\{\s*\.?([A-Za-z_$][\w.$]*)\s*\}\}/g, (m, name, off, full) => {
      const key = name.split('.').pop();
      const quoted = full[off - 1] === '"' && full[off + m.length] === '"';
      if (Object.prototype.hasOwnProperty.call(vars, key)) return vars[key];
      return quoted ? 'sample' : '0';
    })
    .replace(/\{\{[^}]*\}\}/g, (m, off, full) =>
      (full[off - 1] === '"' && full[off + m.length] === '"') ? 'sample' : '0');
}

async function run() {
  // شمارنده و چک قبل از رندر ساخته می‌شوند: بررسی‌های ایستا
  // پایین‌تر به آن‌ها نیاز دارند و باید *پیش از* jsdom اجرا شوند.
  const results = [];
  const check = (name, cond, detail='') => {
    results.push(cond);
    console.log(`${cond ? '✅' : '❌'} ${name}${detail ? ' — ' + detail : ''}`);
  };

  // ═══ پیش از رندر: سلامتِ خودِ قالب ═══
  //
  // این‌ها فقط متن فایل را می‌خواهند. اجرای‌شان پیش از رندر یعنی
  // صفحه‌ای که می‌ترکد هم دلیل دقیق می‌گیرد، نه یک stack trace —
  // و دقیقاً همان حالتی که این بررسی‌ها برایش نوشته شده‌اند،
  // همان حالتی است که رندر را می‌شکند.
  //
  // سه چیزی که CONTRIBUTING صریح هشدار می‌دهد و هیچ‌کدام نگهبان
  // نداشتند. هر سه یک شکل شکست دارند: صفحه برای *همه‌ی* مشتری‌ها
  // خراب می‌شود، و این‌جا هیچ خطایی دیده نمی‌شود چون قالب را Go
  // روی سرور رندر می‌کند نه این تست.
  const RAW = fs.readFileSync(HTML_PATH, 'utf8');

  // ── الف) آکولادها باید جفت باشند ──
  //
  // یک «}}» جاافتاده یعنی Go کل قالب را رد می‌کند و مشتری صفحه‌ی
  // خطای خام می‌بیند.
  const opens = (RAW.match(/\{\{/g) || []).length;
  const closes = (RAW.match(/\}\}/g) || []).length;
  check('آکولادهای قالب جفت‌اند', opens === closes,
        `${opens} باز · ${closes} بسته`);

  // ── ب) هر متغیر باید در فهرست رسمی ۳x-ui باشد ──
  //
  // فهرست از docs/custom-subscription-templates.md مخزن MHSanaei
  // گرفته شده. متغیری که آن‌جا نباشد خالی رندر می‌شود یا قالب را
  // می‌شکند — و روی این ماشین هیچ‌وقت معلوم نمی‌شود.
  const XUI_VARS = new Set([
    'sId', 'enabled', 'isOnline', 'download', 'upload', 'total', 'used',
    'remained', 'expire', 'lastOnline', 'downloadByte', 'uploadByte',
    'totalByte', 'subUrl', 'subJsonUrl', 'subClashUrl', 'subTitle',
    'subSupportUrl', 'links', 'emails', 'announce', 'datepicker',
  ]);
  const unknown = [];
  for (const m of RAW.matchAll(/\{\{\s*([^}]{0,60}?)\s*\}\}/g)) {
    const expr = m[1];
    // ساختارهای خودِ Go و متغیرهای حلقه، نه فیلدهای داده
    if (/^(end|else|if |range |\$)/.test(expr)) continue;
    for (const f of expr.matchAll(/\.([A-Za-z_]\w*)/g)) {
      if (!XUI_VARS.has(f[1]) && !unknown.includes(f[1])) unknown.push(f[1]);
    }
  }
  check('همه‌ی متغیرهای قالب در فهرست رسمی ۳x-ui هستند',
        unknown.length === 0,
        unknown.length ? unknown.join('، ') : 'هیچ نام ناشناخته‌ای نیست');

  // ── ج) هیچ getElementById به شناسه‌ی ناموجود ──
  //
  // «Cannot set properties of null» اجرای بقیه‌ی اسکریپت را متوقف
  // می‌کند، پس یک غلط تایپی می‌تواند نیمی از صفحه را از کار بیندازد.
  const defined = new Set();
  for (const m of RAW.matchAll(/\bid\s*=\s*["']([^"']+)["']/g)) defined.add(m[1]);
  for (const m of RAW.matchAll(/id\s*=\s*\\?["']([A-Za-z0-9_-]+)\\?["']/g)) {
    defined.add(m[1]);
  }
  const dangling = [];
  for (const m of RAW.matchAll(/getElementById\(\s*["']([^"']+)["']\s*\)/g)) {
    if (!defined.has(m[1]) && !dangling.includes(m[1])) dangling.push(m[1]);
  }
  check('هر getElementById به عنصری می‌رسد که وجود دارد',
        dangling.length === 0,
        dangling.length ? dangling.join('، ') : `${defined.size} شناسه`);

  // ═══ ۱۳. حالت‌های واقعی مشتری ═══
  //
  // نامحدود و بدون انقضا حالت‌های عادی‌اند، نه لبه: مشتری‌ای که
  // «NaN روز» یا «-۱» ببیند فکر می‌کند سرویسش خراب شده.
  check('حالت نامحدودِ روز جدا مدیریت می‌شود',
        RAW.includes('sanaeiClientData.daysLeft === null'),
        'daysLeft برابر null یعنی بدون انقضا');
  check('حالت منقضی‌شده هم جدا',
        RAW.includes('sanaeiClientData.daysLeft === -1'));
  check('حجم نامحدود عدد خام نشان نمی‌دهد',
        RAW.includes('sanaeiClientData.totalByte > 0 ?'),
        'صفر یعنی نامحدود، نه صفر بایت');
  check('پرشدن حجم فقط وقتی سقفی هست سنجیده می‌شود',
        RAW.includes('sanaeiClientData.totalByte > 0 && totalUsage'),
        'بدون این، کانفیگ نامحدود همیشه «تمام‌شده» بود');


  let html = renderTemplate(fs.readFileSync(HTML_PATH, 'utf8'));

  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    url: 'https://sub.test.com/sub/abc123',
    beforeParse(window) {
      // شبیه‌سازی پاسخ بک‌اند
      window.fetch = (url) => {
        if (String(url).includes('/api/public/config')) {
          return Promise.resolve({ ok:true, json:()=>Promise.resolve(MOCK_CONFIG) });
        }
        // درخواست live data: صفحه لینک اشتراک خودش را می‌خواند تا
        // مصرف و آخرین اتصال را از هدرها بگیرد.
        //
        // قبلاً اینجا ۴۰۴ برمی‌گرداندیم و بعد تست شکایت می‌کرد که
        // «خطای جاوااسکریپت هست» — خطایی که خودمان ساخته بودیم.
        // با پاسخ درست، آن تست دوباره معنا پیدا می‌کند: از این به
        // بعد فقط وقتی قرمز می‌شود که خطای *واقعی* در صفحه باشد.
        const headers = new Map([
          ['subscription-userinfo',
           'upload=1073741824; download=10737418240; total=53687091200; expire=1800000000'],
          ['subscription-last-online', '1800000000'],
        ]);
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: { get: (k) => headers.get(String(k).toLowerCase()) ?? null },
          text: () => Promise.resolve(''),
          json: () => Promise.resolve({}),
        });
      };
      window.AbortSignal = { timeout: () => null };
      // ثبت خطاها
      window.__errors = [];
      window.addEventListener('error', e => window.__errors.push(e.message));
    },
  });

  const { window } = dom;
  const errors = [];
  window.onerror = (msg) => { errors.push(msg); };
  const origErr = console.error;
  console.error = (...a) => { errors.push(a.join(' ')); };

  // صبر برای اجرای DOMContentLoaded و promiseهای async
  await new Promise(r => setTimeout(r, 1500));

  console.error = origErr;
  const doc = window.document;

  console.log('╔══════════════════════════════════════════╗');
  console.log('║   تست واقعی با DOM (مثل مرورگر)          ║');
  console.log('╚══════════════════════════════════════════╝\n');


  // ═══ خطاهای جاوااسکریپت ═══
  const jsErrors = [...errors, ...(window.__errors||[])].filter(e =>
    !String(e).includes('Not implemented') && !String(e).includes('css')
  );
  check('بدون خطای جاوااسکریپت', jsErrors.length === 0,
        jsErrors.length ? jsErrors.slice(0,2).join(' | ') : '');

  // ═══ ۱. سوالات متداول ═══
  const faqSection = doc.getElementById('faq-section');
  const faqItems = faqSection ? faqSection.querySelectorAll('.faq-item') : [];
  check('سوالات متداول رندر شد', faqItems.length === 3, `${faqItems.length} سوال (انتظار: 3)`);
  if (faqItems.length > 0) {
    const firstQ = faqItems[0].querySelector('.faq-question span')?.textContent;
    check('  متن سوال درست است', firstQ === 'سوال اول تستی', firstQ || 'خالی');
  }

  // ═══ ۲. اپلیکیشن‌ها ═══
  const appCards = doc.querySelectorAll('#client-cards-container .client-card-item');
  check('اپلیکیشن‌ها رندر شدند', appCards.length === 3, `${appCards.length} اپ (انتظار: 3)`);
  if (appCards.length > 0) {
    const hasRibbon = appCards[0].querySelector('.recommended-ribbon');
    check('  نشان پیشنهادی روی اپ اول', !!hasRibbon);
    const quickBtn = appCards[0].querySelector('.client-quickadd-btn');
    check('  دکمه افزودن یک‌کلیک', !!quickBtn, quickBtn?.getAttribute('href')?.slice(0,25) || '');
  }

  // ═══ ۳. برند ═══
  const brandName = doc.getElementById('nexora-brand-name')?.textContent;
  check('نام برند اعمال شد', brandName === 'TESTBRAND', brandName || 'خالی');
  check('عنوان صفحه اعمال شد', doc.title === 'عنوان تست', doc.title);

  // ═══ ۴. رنگ سفارشی ═══
  const styleEl = doc.getElementById('nexora-brand-colors');
  check('استایل رنگ برند تزریق شد', !!styleEl && styleEl.textContent.includes('#FF0000'));

  // ═══ ۵. CSS سفارشی ═══
  check('CSS سفارشی تزریق شد', !!doc.getElementById('nexora-custom-css'));

  // ═══ ۶. پاورقی ═══
  const footer = doc.getElementById('nexora-custom-footer');
  check('پاورقی سفارشی اضافه شد', footer?.textContent === 'پاورقی تستی', footer?.textContent || 'نیست');

  // ═══ ۷. لینک‌ها ═══
  const designerLink = doc.querySelector('.designer-name-title')?.textContent;
  check('لینک کانال به‌روز شد', designerLink === '@test_ch', designerLink || 'خالی');

  // ═══ ۸. ویدیوها ═══
  const videoText = doc.getElementById('video-tutorial-text')?.textContent;
  check('ویدیو آموزشی اعمال شد', videoText === 'ویدیو تستی', videoText || 'خالی');

  // ═══ ۹. تنظیمات سراسری ═══
  check('NEXORA_FAQ در window', !!window.NEXORA_FAQ?.fa?.length, `${window.NEXORA_FAQ?.fa?.length || 0} سوال`);
  check('NEXORA_APPS در window', !!window.NEXORA_APPS?.android?.length, `${window.NEXORA_APPS?.android?.length || 0} اپ`);
  check('NEXORA_POPUP در window', window.NEXORA_POPUP?.title === 'پاپ‌آپ سفارشی');
  check('آستانه بنر اعمال شد', window.NEXORA_LOW_QUOTA_DAYS === 5, String(window.NEXORA_LOW_QUOTA_DAYS));
  check('لینک پشتیبانی اعمال شد', window.NEXORA_SUPPORT_URL === 'https://t.me/test_sup', window.NEXORA_SUPPORT_URL || '');

  // ═══ ۱۰. تعویض تب دانلود ═══
  try {
    window.switchDownloadTab('ios');
    const iosCards = doc.querySelectorAll('#client-cards-container .client-card-item');
    check('تعویض تب به iOS', iosCards.length === 1, `${iosCards.length} اپ`);
    window.switchDownloadTab('android');
  } catch(e) {
    check('تعویض تب به iOS', false, e.message);
  }

  // ═══ ۱۱. تعویض زبان ═══
  try {
    window.selectLanguage('en');
    const enFaq = doc.getElementById('faq-section').querySelectorAll('.faq-item');
    check('تعویض زبان به انگلیسی', enFaq.length === 1, `${enFaq.length} سوال`);
    window.selectLanguage('fa');
    const faFaq = doc.getElementById('faq-section').querySelectorAll('.faq-item');
    check('بازگشت به فارسی', faFaq.length === 3, `${faFaq.length} سوال`);
  } catch(e) {
    check('تعویض زبان', false, e.message);
  }

  // ═══ مشتریِ منقضی‌شده باید بنر تمدید ببیند ═══
  //
  // calculateDaysLeft برای اشتراکِ تمام‌شده -1 برمی‌گرداند، ولی شرط
  // بنر «daysLeft >= 0» بود. یعنی دقیقاً همان کسی که باید همین حالا
  // تمدید کند، هیچ دعوتی به تمدید نمی‌دید. اگر حجمش تمام می‌شد بنر
  // می‌گرفت (درصد به صفر می‌رسید)، ولی اگر زمانش تمام می‌شد نه.
  try {
    const banner = doc.getElementById('lowQuotaBanner');

    // sanaeiClientData با let تعریف شده، پس روی window ننشسته —
    // باید در دامنه‌ی خود صفحه اجرا شود.
    const drive = (days, pct) => window.eval(
      `sanaeiClientData.daysLeft = ${days};`
      + (pct === undefined ? '' : ` sanaeiClientData.percentRemaining = ${pct};`)
      + ' updateAlertBanners();');

    drive(30, 90);
    check('مشتری سالم بنر نمی‌بیند', banner.style.display === 'none',
          banner.style.display);

    drive(-1);
    check('مشتری منقضی بنر می‌بیند', banner.style.display === 'flex',
          banner.style.display);

    // innerText در jsdom تازه نمی‌شود و مقدار اولیه‌ی HTML را
    // برمی‌گرداند؛ صفحه textContent می‌نویسد، پس همان را می‌خوانیم.
    const title = doc.getElementById('lowQuotaTitle').textContent || '';
    const desc = doc.getElementById('lowQuotaDesc').textContent || '';
    check('عنوانش می‌گوید منقضی شده، نه رو به اتمام',
          title.includes('منقضی'), title);
    check('متنش هم درباره‌ی پایان است، نه نزدیک‌شدن',
          desc.includes('پایان') || desc.includes('منقضی'), desc);

    drive(2);
    check('هشدار «رو به اتمام» هنوز کار می‌کند',
          banner.style.display === 'flex'
          && (doc.getElementById('lowQuotaDesc').textContent || '').includes('2'),
          doc.getElementById('lowQuotaDesc').textContent);

    drive(null, 100);
    check('اشتراک نامحدود بنر نمی‌گیرد', banner.style.display === 'none',
          'daysLeft = null یعنی بی‌پایان');
  } catch(e) {
    check('بنر منقضی‌شده', false, e.message);
  }

  // ═══ Contact links belong to the operator ═══
  //
  // The template used to hard-code Nexora's own support and channel handles.
  // Whenever the panel config did not arrive, every buyer's customers were sent
  // to Nexora. Now: panel usernames, then 3x-ui's support URL, else hidden.
  try {
    const RAWSRC = fs.readFileSync(HTML_PATH, 'utf8');
    check('No vendor handle in the template', !/nexoravpn/i.test(RAWSRC),
          (RAWSRC.match(/[\w/.:]*nexoravpn[\w/]*/i) || [''])[0]);

    const off = (el) => !!el && !!(el.closest('[data-contact-off]'));
    const promo = doc.querySelector('.promo-btn[data-contact="support"]');
    const renew = doc.querySelector('.action-card.renew');
    const chName = doc.querySelector('.designer-name-title');
    check('Support button uses the panel username',
          promo && promo.getAttribute('href') === 'https://t.me/test_sup', promo && promo.getAttribute('href'));
    check('Channel link and name use the panel username',
          chName && chName.getAttribute('href') === 'https://t.me/test_ch' && chName.textContent === '@test_ch',
          chName && chName.getAttribute('href') + ' ' + chName.textContent);
    check('With links set, nothing is hidden', !off(promo) && !off(renew) && !off(chName));

    // panel has no usernames → 3x-ui's own support URL
    window.eval("window.NEXORA_SUPPORT_URL=''; window.NEXORA_CHANNEL_URL=''; applyContactLinks(); setupReferral();");
    check("No panel username: falls back to 3x-ui's support URL",
          promo.getAttribute('href') === 'https://t.me/support' && !off(promo), promo.getAttribute('href'));
    check('No channel: the channel card hides', off(chName));

    // neither → hidden, never a link to someone else
    window.eval("sanaeiTemplateData.subSupportUrl=''; applyContactLinks(); setupReferral();");
    check('No support link at all: support button hides', off(promo));
    check('No support link at all: renew card hides', off(renew));
    check('No support link at all: referral card hides', off(doc.getElementById('referral-card')));
    const cs = window.getComputedStyle(doc.getElementById('sec-promo'));
    check('Hidden means display:none (beats the card\'s own display)', cs.display === 'none', cs.display);
  } catch (e) {
    check('Contact links', false, e.message);
  }

  // ═══ نتیجه ═══
  const passed = results.filter(Boolean).length;
  console.log('\n' + '─'.repeat(46));
  console.log(`نتیجه: ${passed}/${results.length} تست پاس شد`);
  console.log('─'.repeat(46));

  // صفحه دو setInterval برای به‌روزرسانی زنده دارد. تا وقتی پنجره
  // باز باشد، حلقه‌ی رویداد Node تمام نمی‌شود و تست برای همیشه
  // معلق می‌ماند — بدون اینکه حتی نتیجه را چاپ کند.
  try { dom.window.close(); } catch { /* بی‌اهمیت */ }

  if (passed < results.length) {
    console.log('\n⚠️ خطاهای ثبت‌شده:');
    jsErrors.slice(0,5).forEach(e => console.log('  •', String(e).slice(0,150)));
    process.exit(1);
  } else {
    console.log('\n🎉 همه تست‌ها پاس شدند');
    process.exit(0);
  }
}

run().catch(e => { console.error('خطای تست:', e); process.exit(1); });
