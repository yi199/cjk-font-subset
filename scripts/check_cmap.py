#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""缺字检查：按字体 cmap 实测，不是比字数。

为什么不能比字数：「代码用到 871 个汉字 / 字表 878 个 ✓ 没有缺字」这种检查会漏。
数量够 ≠ 字够。真实翻车现场：数量检查全过，真机上仍有 7 个字显示成方框
（全部来自刚合进来的两个新页面）。唯一可靠判据是「会渲染的汉字」是否都在字体 cmap 里。

口径（定过一次别改，否则两次结果不可比）：
  .wxml / .html   去掉 <!-- --> 后取文本
  .js/.ts/.vue    去掉 // 与 /* */，**保留**字符串字面量里的中文
  .json           全算（navigationBarTitleText / app name 这类会显示）
  .css/.wxss      不算（只有类名和注释，没有文案）
  test*.js        不算（进不了线上包，但**它的断言文案也算字** → 按需用 --include-tests）
  字体文件本身    不算

用法
----
    python3.12 check_cmap.py ./app --fonts app/data/fonts.js --var ZH
    python3.12 check_cmap.py ./app --fonts dist/zh-subset.woff2
    python3.12 check_cmap.py ./app --fonts x.woff2 --include-tests

退出码：0 = 没有缺字；1 = 有缺字（可直接挂进 CI）。缺依赖时退出码 2。
"""
import argparse
import base64
import io
import os
import re
import sys

HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
CODE_EXT = (".js", ".ts", ".jsx", ".tsx", ".vue", ".wxml", ".html", ".htm", ".json")


def strip_comments_js(src):
    """去 // 与 /* */，但保留字符串字面量内容（否则 'https://…' 会被截断）。"""
    out, i, n, quote = [], 0, len(src), None
    while i < n:
        c = src[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ('"', "'", "`"):
            quote = c
            out.append(c)
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def collect(root, skip_dirs, include_tests, skip_names):
    used = {}
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in fs:
            low = f.lower()
            if not low.endswith(CODE_EXT):
                continue
            if f in skip_names:
                continue
            is_test = re.match(r"(test|spec)[^/]*\.(js|ts|jsx|tsx)$", low) is not None
            if is_test and not include_tests:
                continue
            p = os.path.join(dp, f)
            try:
                src = io.open(p, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            if low.endswith((".wxml", ".html", ".htm")):
                src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
            elif not low.endswith(".json"):
                src = strip_comments_js(src)
            for lineno, line in enumerate(src.splitlines(), 1):
                for ch in HAN.findall(line):
                    used.setdefault(ch, []).append(
                        (p.replace(os.sep, "/"), lineno, line.strip()[:80]))
    return used


def font_cmap(path, var="ZH"):
    """支持两种来源：字体文件（.woff2/.ttf/.otf），或内联 base64 的 js。"""
    from fontTools.ttLib import TTFont
    from io import BytesIO

    if path.lower().endswith((".js", ".ts", ".vue", ".html")):
        src = io.open(path, encoding="utf-8").read()
        m = re.search(r"\b%s\s*=\s*['\"]([^'\"]+)['\"]" % re.escape(var), src)
        if not m:
            sys.exit("✗ 在 %s 里找不到 %s 字体变量" % (path, var))
        b64 = m.group(1)
        if "base64," in b64:
            b64 = b64.split("base64,", 1)[1]
        return set(chr(c) for c in TTFont(BytesIO(base64.b64decode(b64))).getBestCmap().keys())
    return set(chr(c) for c in TTFont(path, fontNumber=0).getBestCmap().keys())


def main(argv=None):
    ap = argparse.ArgumentParser(description="按字体 cmap 检查缺字")
    ap.add_argument("root", help="项目根目录")
    ap.add_argument("--fonts", required=True, help="字体文件，或内联 base64 的 js/css 文件")
    ap.add_argument("--var", default="ZH", help="js 内联时的变量名（默认 ZH）")
    ap.add_argument("--include-tests", action="store_true",
                    help="把 test*.js 也算进字表（断言文案里的中文同样会被渲染到终端，但进不了线上包）")
    a = ap.parse_args(argv)

    root = a.root.replace("\\", "/").rstrip("/")
    if not os.path.isdir(root):
        sys.exit("✗ 目录不存在：%s" % root)
    if not os.path.isfile(a.fonts):
        sys.exit("✗ 找不到字体来源：%s" % a.fonts)

    try:
        covered = font_cmap(a.fonts, a.var)
    except ImportError as e:
        sys.exit("✗ 缺依赖（%s）。装：python3.12 -m pip install fonttools brotli" % e)

    used = collect(root, {"node_modules", ".git", "dist", "build", ".font-dist"},
                   a.include_tests, {"fonts.js"})
    missing = sorted(set(used) - covered)

    print("会渲染的汉字: %d 个" % len(used))
    print("字体覆盖汉字: %d 个" % len([c for c in covered if HAN.match(c)]))
    print("真实缺字: %d 个" % len(missing))

    for ch in missing:
        print("\n  缺「%s」" % ch)
        seen = set()
        for p, ln, txt in used[ch]:
            if (p, ln) in seen:
                continue
            seen.add((p, ln))
            print("      %s:%d  %s" % (p, ln, txt))
            if len(seen) >= 4:
                break

    if missing:
        print("\n→ 两选一：改文案（更便宜），或重跑子集化（数据表/长文案只能重建）")
        return 1
    print("\n✅ 没有缺字")
    return 0


if __name__ == "__main__":
    sys.exit(main())
