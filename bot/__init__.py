"""
ماژول ربات Nexora.

ماژول‌های داخلی به‌سبک تخت import می‌کنند (`import core`) تا اجرای مستقیم
از داخل پوشه ساده بماند. این فایل مسیر پوشه را به sys.path اضافه می‌کند
تا `from bot import handlers` هم کار کند — بدون نیاز به بازنویسی importها.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

__all__ = ["core", "db", "tg", "xui", "handlers"]
