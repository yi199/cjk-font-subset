#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成一个极小的测试字体（约 2~3 KB），只含你指定的字符。

用途：让子集化流水线**不依赖任何系统字体**就能端到端自测（离线 / CI / 干净机器）。
字形都是同一个方块，只保证 cmap 与 glyph 存在，够验证「抽字 → 子集化 → 缺字检查」这条路。

    python3.12 make_test_font.py out.ttf --chars 甲乙丙丁戊
"""
import argparse
import sys


def build(path, chars, upem=1000):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    names = ["uni%04X" % ord(c) for c in chars]
    order = [".notdef"] + names

    fb = FontBuilder(upem, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(dict(zip([ord(c) for c in chars], names)))

    box = TTGlyphPen(None)
    box.moveTo((80, 0))
    box.lineTo((80, 700))
    box.lineTo((560, 700))
    box.lineTo((560, 0))
    box.closePath()
    glyph = box.glyph()

    glyphs = {".notdef": glyph}
    for n in names:
        glyphs[n] = glyph
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(dict((n, (600, 80)) for n in order))
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({
        "familyName": "MiniSubsetTest",
        "styleName": "Regular",
        "uniqueFontIdentifier": "MiniSubsetTest Regular",
        "fullName": "MiniSubsetTest Regular",
        "psName": "MiniSubsetTest-Regular",
        "version": "Version 1.000",
    })
    fb.setupOS2()
    fb.setupPost()
    fb.save(path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--chars", default="甲乙丙丁戊己庚辛")
    a = ap.parse_args(argv)
    try:
        build(a.out, a.chars)
    except ImportError as e:
        sys.exit("✗ 缺依赖（%s）。装：python3.12 -m pip install fonttools brotli" % e)
    print("✓ 生成 %s（%d 个字符）" % (a.out, len(a.chars)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
