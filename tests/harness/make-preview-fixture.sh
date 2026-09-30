#!/bin/sh
# داده‌ی پیش‌نمایشِ ربات برای هارنس — از خودِ موتور (bot/pro/preview_flows.py)، نه دست‌نوشته.
# بعد از هر تغییر در متن‌ها یا مسیرهای ربات اجرا کنید؛ test-shop-funnel اگر کهنه باشد می‌گوید.
cd "$(dirname "$0")/../.." && PYTHONIOENCODING=utf-8 python -m bot.pro.preview_flows < tests/harness/fixtures/preview-input.json > tests/harness/fixtures/preview-flows.json
