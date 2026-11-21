#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文子集化：把项目里**会显示**的汉字抽出来，从源字体生成一份极小的 woff2。

三种落地方式（--mode）：
  file    输出 .woff2 文件（H5 / Electron / PWA 用）
  css     输出 .css（@font-face + base64 内联，单文件自包含）
  inject  直接替换项目里已有的 `var ZH = 'data:font/woff2;base64,...'`（小程序 / 单文件内联常见写法）

用法
----
    # 1) 先量一下缺多少字，不写文件
    python3.12 subset_cjk.py ./app --src C:/Windows/Fonts/NotoSansSC-VF.ttf --dry-run

    # 2) 出文件
    python3.12 subset_cjk.py ./app --src <源字体.ttf> --mode file

    # 3) 内联成 CSS
    python3.12 subset_cjk.py ./app --src <源字体.ttf> --mode css --family "MyCJK"

    # 4) 回写项目已有的 fonts.js
    python3.12 subset_cjk.py ./app --src <源字体.ttf> --mode inject \
        --target app/data/fonts.js --var ZH

    # 5) 独立复验（另一个脚本，口径更严格）
    python3.12 check_cmap.py ./app --fonts app/data/fonts.js --var ZH

⚠️ 顺序铁律：字体子集是全局生成物，依赖**全部**文案。
所有会改文案的改动（含数据表、测试断言里的中文）都合完之后，最后再单独跑一次子集化。
否则每合一个 PR 就要重建一次，做多少轮都是白做。

`--dry-run` 的缺字是「重建口径」（只跳整行注释）；严格口径以 check_cmap.py 为准。
两个口径的差别是刻意的：重建要宁可多带字，检查要宁可报严。
"""
import argparse
import base64
import glob
import io
import os
import re
import sys

HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# 常用标点（中文正文一定会用到）
PUNCT = "，。、；：？！（）《》「」『』【】—…·×÷°″′％＃＆＊＋－＝＜＞～"
# 常见 ASCII（数字、单位、英文标签）
ASCII = ("0123456789.,:;!?()[]%+-/*=<>~abcdefghijklmnopqrstuvwxyz"
         "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
# 保险字：当前文案没出现、但改文案马上会用到的（可按项目口味改；不带也行）
SAFETY = "早中晚夜今日明天昨天本周月年第一二三四五六七八九十百千万组次个分秒时"

ZH_VAR = re.compile(r"(\b\w+\s*=\s*'data:font/woff2;base64,)([^']*)(')")


# ---------------------------------------------------------------- 抽字
def strip_comments(src, mode):
    """mode: 'loose' 只去整行 // 与块注释（重建口径）；'strict' 去所有 // 但保留字符串。"""
    if mode == "loose":
        src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
        src = re.sub(r"(?m)^\s*//.*$", "", src)
        return src
    # strict：状态机，别把 'https://…' 截断
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


def collect_chars(root, exts, skip_names, skip_dirs, mode="loose"):
    chars, files = set(), 0
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in fs:
            if not f.lower().endswith(exts):
                continue
            if f in skip_names:
                continue
            p = os.path.join(dp, f)
            try:
                src = io.open(p, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            files += 1
            chars |= set(HAN.findall(strip_comments(src, mode)))
    return chars, files


# ---------------------------------------------------------------- 字体
def covered_chars(font_path):
    from fontTools.ttLib import TTFont
    f = TTFont(font_path, fontNumber=0)
    return set(chr(c) for c in f.getBestCmap().keys())


def covered_from_b64(b64):
    from fontTools.ttLib import TTFont
    from io import BytesIO
    return set(chr(c) for c in TTFont(BytesIO(base64.b64decode(b64))).getBestCmap().keys())


def build_subset(src_font, text, out_path, flavor="woff2"):
    from fontTools import subset
    opts = subset.Options()
    opts.flavor = flavor
    opts.desubroutinize = True        # CFF 源字体也能安全转 woff2
    font = subset.load_font(src_font, opts)
    sub = subset.Subsetter(options=opts)
    sub.populate(text=text)
    sub.subset(font)
    subset.save_font(font, out_path, opts)


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="中文子集化：抽字 → 生成极小 woff2")
    ap.add_argument("root", help="项目根目录（扫它下面的源码）")
    ap.add_argument("--src", required=True, help="源字体 .ttf/.otf（如 NotoSansSC-VF.ttf）")
    ap.add_argument("--mode", default="file", choices=["file", "css", "inject"])
    ap.add_argument("--out", default="", help="file/css 模式的输出路径；默认 <root>/.font-dist/")
    ap.add_argument("--family", default="CJKSubset", help="css 模式的 font-family 名")
    ap.add_argument("--target", default="", help="inject 模式要改写的文件")
    ap.add_argument("--var", default="ZH", help="inject 模式的变量名（默认 ZH）")
    ap.add_argument("--exts", default=".js,.ts,.jsx,.tsx,.vue,.wxml,.html,.json",
                    help="参与抽字的扩展名，逗号分隔")
    ap.add_argument("--skip-names", default="fonts.js",
                    help="跳过的文件名（这些是字体本身，不是文案），逗号分隔")
    ap.add_argument("--skip-dirs", default="node_modules,.git,dist,build,.font-dist",
                    help="跳过的目录名，逗号分隔")
    ap.add_argument("--no-safety", action="store_true", help="不加保险字（体积最小）")
    ap.add_argument("--loose", action="store_true", default=True, help="重建口径（默认）")
    ap.add_argument("--dry-run", action="store_true", help="只报缺字，不写文件")
    a = ap.parse_args(argv)

    root = a.root.replace("\\", "/").rstrip("/")
    if not os.path.isdir(root):
        sys.exit("✗ 目录不存在：%s" % root)
    if not os.path.isfile(a.src):
        sys.exit("✗ 源字体不存在：%s" % a.src)

    exts = tuple(x.strip().lower() for x in a.exts.split(",") if x.strip())
    skip_names = set(x.strip() for x in a.skip_names.split(",") if x.strip())
    skip_dirs = set(x.strip() for x in a.skip_dirs.split(",") if x.strip())

    used, files = collect_chars(root, exts, skip_names, skip_dirs, mode="loose")
    han_used = set(c for c in used if HAN.match(c))
    extras = set(PUNCT) | set(ASCII) | (set() if a.no_safety else set(SAFETY))
    charset = used | extras

    print("扫描 %d 个文件，会显示的文字 %d 个（其中汉字 %d）" % (files, len(used), len(han_used)))

    old_cov = None
    if a.mode == "inject":
        target = a.target or os.path.join(root, "data", "fonts.js")
        if not os.path.isfile(target):
            sys.exit("✗ inject 模式找不到 --target：%s" % target)
        src_txt = io.open(target, encoding="utf-8").read()
        pat = re.compile(r"(\b%s\s*=\s*'data:font/woff2;base64,)([^']*)(')" % re.escape(a.var))
        m = pat.search(src_txt)
        if not m:
            sys.exit("✗ 在 %s 里找不到 %s = 'data:font/woff2;base64,…'" % (target, a.var))
        old_cov = covered_from_b64(m.group(2))
        print("现有子集覆盖 %d 字（含标点/ASCII）" % len(old_cov))
        missing = sorted(han_used - old_cov)
        print("按重建口径缺汉字 %d 个%s" % (len(missing), ("：" + "".join(missing[:60])) if missing else ""))

    src_cov = covered_chars(a.src)
    not_in_src = sorted(c for c in charset if c not in src_cov)
    if not_in_src:
        print("⚠️ 源字体本身没有这 %d 个字符（会被丢弃）：%s" % (len(not_in_src), "".join(not_in_src[:40])))

    if a.dry_run:
        print("\n[dry-run] 未写文件")
        return 0

    out_dir = os.path.join(root, ".font-dist")
    text = "".join(sorted(c for c in charset if c in src_cov))

    if a.mode in ("file", "css"):
        out = a.out or os.path.join(out_dir, "zh-subset.woff2" if a.mode == "file" else "zh-subset.css")
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        if a.mode == "file":
            build_subset(a.src, text, out)
        else:
            tmp = os.path.join(os.path.dirname(os.path.abspath(out)), ".zh.tmp.woff2")
            build_subset(a.src, text, tmp)
            b64 = base64.b64encode(open(tmp, "rb").read()).decode()
            os.remove(tmp)
            with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("/* 由 cjk-font-subset 生成：只含界面用到的 %d 个字，勿手改 */\n" % len(han_used))
                fh.write("@font-face{font-family:'%s';font-style:normal;font-weight:400;"
                         "font-display:swap;src:url(data:font/woff2;base64,%s) format('woff2');}\n"
                         % (a.family, b64))
        kb = os.path.getsize(out) / 1024.0
        print("\n✅ 写出 %s（%.1f KB）" % (out, kb))
        return 0

    # inject
    tmp = os.path.join(out_dir, ".zh.tmp.woff2")
    os.makedirs(out_dir, exist_ok=True)
    build_subset(a.src, text, tmp)
    raw = open(tmp, "rb").read()
    os.remove(tmp)
    new_b64 = base64.b64encode(raw).decode()

    src_txt = io.open(target, encoding="utf-8").read()
    pat = re.compile(r"(\b%s\s*=\s*'data:font/woff2;base64,)([^']*)(')" % re.escape(a.var))
    out, n = pat.subn(lambda m: m.group(1) + new_b64 + m.group(3), src_txt)
    if n != 1:
        sys.exit("✗ 期望替换 1 处 %s，实际 %d 处" % (a.var, n))
    io.open(target, "w", encoding="utf-8", newline="").write(out)
    print("\n✅ 已回写 %s" % target)
    print("   子集 woff2 %.1f KB（base64 后约 %.1f KB）" % (len(raw) / 1024.0, len(new_b64) / 1024.0))
    print("   下一步复验：python3.12 check_cmap.py %s --fonts %s --var %s" % (root, target, a.var))
    return 0


if __name__ == "__main__":
    sys.exit(main())
