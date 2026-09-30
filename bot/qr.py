"""
ساخت کیوآر لینک اشتراک.

چرا محلی و نه سرویس آنلاین:
    لینک اشتراک عملاً رمز مشتری است. فرستادنش به یک کیوآرساز شخص
    ثالث یعنی دادن دسترسی کامل سرویس به آن سایت. پس همین‌جا ساخته
    می‌شود و هیچ‌جا نمی‌رود.

segno اختیاری است — اگر نصب نباشد، تحویل کانفیگ مثل قبل انجام
می‌شود و فقط کیوآر همراهش نیست. یک قابلیت اضافه نباید بتواند
مسیر فروش را بشکند.
"""
import logging

log = logging.getLogger("nexora.qr")

try:
    import segno as _segno
except ImportError:
    _segno = None


def available():
    return _segno is not None


def make(data, scale=8, border=3):
    """
    کیوآر را به‌صورت بایت PNG برمی‌گرداند، یا None اگر نشد.

    رنگ‌ها روشن روی تیره نیستند: بعضی دوربین‌ها کیوآر معکوس را
    نمی‌خوانند، پس مشکی روی سفید می‌ماند که همه‌جا کار می‌کند.
    """
    if not _segno or not data:
        return None
    try:
        import io
        buf = io.BytesIO()
        # error='m' یعنی تا ۱۵٪ خرابی قابل جبران است — برای کیوآری
        # که از صفحه‌ی گوشی اسکن می‌شود کافی و اندازه را کوچک نگه
        # می‌دارد.
        _segno.make(str(data), error="m").save(
            buf, kind="png", scale=scale, border=border,
            dark="#000000", light="#FFFFFF")
        return buf.getvalue()
    except Exception as e:
        log.warning("ساخت کیوآر ناموفق: %s", e)
        return None
