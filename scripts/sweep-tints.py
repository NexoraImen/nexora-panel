#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rgba()های خامِ JSX → توکن‌های معنایی.

چهار وضعیت پنل در ۳۲۸ جای JSX دستی نوشته شده بودند؛ رنگ هشدار
به‌تنهایی ۶۳ بار با ۱۷ آلفای متفاوت. `.05` و `.06` و `.07` و `.08`
را هیچ طراحی عمداً انتخاب نمی‌کند — آن‌ها ردِ پای کپی‌کردن‌اند، و
نتیجه‌شان این بود که هیچ دو چیپِ «هشدار» دقیقاً یک رنگ نبودند.

هر آلفا به نزدیک‌ترین پله snap می‌شود. این یعنی بعضی رنگ‌ها کمی
عوض می‌شوند — که خودِ هدف است.

  python scripts/sweep-tints.py            # فقط گزارش
  python scripts/sweep-tints.py --write    # اعمال
"""
import glob
import io
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# خانواده → پله‌ها (سقفِ آلفا, نامِ توکن). اولین سقفی که آلفا از آن
# کوچک‌تر یا مساوی باشد، برنده است.
FAMILIES = {
    "52,211,153": ("ok", [(.095, "ok-wash"), (.16, "ok-soft"),
                          (.255, "ok-fill"), (.36, "ok-line"),
                          (1.0, "ok-edge")]),
    "251,191,36": ("warn", [(.095, "warn-wash"), (.16, "warn-soft"),
                            (.255, "warn-fill"), (.36, "warn-line"),
                            (1.0, "warn-edge")]),
    "248,113,113": ("danger", [(.095, "danger-wash"), (.16, "danger-soft"),
                               (.255, "danger-fill"), (.36, "danger-line"),
                               (1.0, "danger-edge")]),
    "43,127,214": ("accent", [(.095, "accent-wash"), (.16, "accent-soft"),
                              (.255, "accent-fill"), (.36, "accent-line"),
                              (1.0, "accent-edge")]),
    # اکسنتِ روشن — همان خانواده ولی تُنِ بازتر
    "90,169,230": ("accent2", [(.30, "accent-halo"), (.47, "accent-line"),
                               (1.0, "accent-edge")]),
    "45,212,191": ("cy", [(.095, "cy-wash"), (.16, "cy-soft"),
                          (.255, "cy-fill"), (1.0, "cy-line")]),
    "167,139,250": ("purple", [(.18, "purple-soft"), (1.0, "purple-line")]),
    "255,255,255": ("hair", [(.045, "hair-1"), (.095, "hair-2"),
                             (.16, "hair-3"), (1.0, "hair-4")]),
    "0,0,0": ("scrim", [(.28, "scrim-1"), (.50, "scrim-2"),
                        (.70, "scrim-3"), (1.0, "scrim-4")]),
    "3,6,12": ("veil", [(1.0, "veil")]),
}

RGBA = re.compile(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*(\d*\.?\d+)\)')


def token_for(rgb, alpha):
    fam = FAMILIES.get(rgb)
    if not fam:
        return None
    for ceiling, name in fam[1]:
        if alpha <= ceiling:
            return name
    return fam[1][-1][1]


def main():
    write = "--write" in sys.argv
    moved = Counter()
    kept = Counter()
    per_file = Counter()

    files = sorted(glob.glob(os.path.join(ROOT, "frontend", "src", "**", "*.jsx"),
                             recursive=True))
    for f in files:
        rel = os.path.relpath(f, ROOT).replace(os.sep, "/")
        # صفحه‌ی طراحیِ پوسته و صفحه‌ی اشتراک رنگِ واقعی نشان
        # می‌دهند (انتخابگرِ رنگ) — آن‌جا literal درست است
        if rel.endswith("bot/themes.jsx") or rel.endswith("sections/subpage.jsx"):
            continue
        src = io.open(f, encoding="utf-8").read()

        def sub(m):
            rgb = ",".join(m.group(1, 2, 3))
            alpha = float(m.group(4))
            tok = token_for(rgb, alpha)
            if not tok:
                kept[rgb] += 1
                return m.group(0)
            moved[tok] += 1
            per_file[rel] += 1
            return "var(--%s)" % tok

        new = RGBA.sub(sub, src)
        if write and new != src:
            io.open(f, "w", encoding="utf-8", newline="").write(new)

    print("replaced: %d" % sum(moved.values()))
    for tok, n in moved.most_common():
        print("  %-14s %d" % (tok, n))
    if kept:
        print("\nleft alone (no family):")
        for rgb, n in kept.most_common():
            print("  rgba(%s)  x%d" % (rgb, n))
    print("\nper file:")
    for rel, n in per_file.most_common():
        print("  %-48s %d" % (rel, n))
    print("\n" + ("WROTE" if write else "dry run — pass --write to apply"))


if __name__ == "__main__":
    main()
