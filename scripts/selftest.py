#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端自测：不依赖任何系统字体、不依赖网络。

    python3.12 scripts/selftest.py        # 期望最后打印 ALL PASS，退出码 0

覆盖：
  1. 造一个只含几个汉字的极小测试字体
  2. 造一个假项目（js / wxml / json / 内联字体变量）
  3. subset_cjk.py --mode file  → 出 woff2
  4. check_cmap.py --fonts 该 woff2 → 0 缺字，退出码 0
  5. 往项目里加一个字 → check_cmap.py 必须报缺字并退出码 1（防「检查器永远通过」）
  6. subset_cjk.py --mode css   → 出 @font-face
  7. subset_cjk.py --mode inject → 改写 var ZH，且改完复验 0 缺字
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

fails = []


def run(args):
    p = subprocess.run([PY] + args, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def ok(name, cond, detail=""):
    if cond:
        print("  ✓ %s" % name)
    else:
        print("  ✗ %s   %s" % (name, detail.strip()[:400]))
        fails.append(name)


def write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main():
    tmp = tempfile.mkdtemp(prefix="cjkfont_")
    try:
        font = os.path.join(tmp, "test.ttf")
        rc, out = run([os.path.join(HERE, "make_test_font.py"), font, "--chars", "甲乙丙丁戊"])
        ok("造出测试字体", rc == 0 and os.path.exists(font), out)

        proj = os.path.join(tmp, "app")
        write(os.path.join(proj, "app.js"),
              "// 注释里的戊会进重建口径\nconst label = '甲';\n/* 块注释 己 */\n")
        write(os.path.join(proj, "pages", "index.wxml"), "<view>乙</view>\n")
        write(os.path.join(proj, "app.json"), '{"navigationBarTitleText":"丙"}\n')
        # 内联字体变量（初版只含「甲」）
        only_jia = os.path.join(tmp, "only_jia.woff2")
        rc, out = run([os.path.join(HERE, "subset_cjk.py"), proj,
                       "--src", font, "--no-safety", "--dry-run"])
        ok("dry-run 正常退出", rc == 0, out)
        ok("dry-run 报出字表", "会显示的文字" in out, out)

        # 4) file 模式
        rc, out = run([os.path.join(HERE, "subset_cjk.py"), proj, "--src", font, "--mode", "file"])
        woff = os.path.join(proj, ".font-dist", "zh-subset.woff2")
        ok("file 模式出 woff2", rc == 0 and os.path.exists(woff) and os.path.getsize(woff) > 0, out)

        rc, out = run([os.path.join(HERE, "check_cmap.py"), proj, "--fonts", woff])
        ok("子集后复验 0 缺字", rc == 0 and "真实缺字: 0" in out, out)

        # 5) 反证：检查器必须真的会红
        write(os.path.join(proj, "pages", "index.wxml"), "<view>乙丁</view>\n")
        rc, out = run([os.path.join(HERE, "check_cmap.py"), proj, "--fonts", woff])
        ok("漏字时退出码 1", rc == 1, out)
        ok("漏字时点名「丁」", "缺「丁」" in out, out)
        ok("漏字时给出文件:行号", re.search(r"index\.wxml:\d+", out) is not None, out)

        # 6) css 模式
        rc, out = run([os.path.join(HERE, "subset_cjk.py"), proj, "--src", font,
                       "--mode", "css", "--family", "TestCJK"])
        css = os.path.join(proj, ".font-dist", "zh-subset.css")
        body = open(css, encoding="utf-8").read() if os.path.exists(css) else ""
        ok("css 模式出 @font-face", rc == 0 and "@font-face" in body, out)
        ok("css 里带 base64", "data:font/woff2;base64," in body, body[:200])
        ok("css 里带 family 名", "TestCJK" in body, body[:200])

        # 7) inject 模式：项目里先放一份「缺字」的旧子集，再回写
        fonts_js = os.path.join(proj, "data", "fonts.js")
        shutil.copyfile(woff, only_jia)
        import base64
        b64 = base64.b64encode(open(only_jia, "rb").read()).decode()
        write(fonts_js, "// 旧子集\nvar ZH = 'data:font/woff2;base64,%s';\nvar SG5 = 'keep-me';\n" % b64)

        rc, out = run([os.path.join(HERE, "check_cmap.py"), proj, "--fonts", fonts_js, "--var", "ZH"])
        ok("内联旧子集先报缺字", rc == 1, out)

        rc, out = run([os.path.join(HERE, "subset_cjk.py"), proj, "--src", font,
                       "--mode", "inject", "--target", fonts_js, "--var", "ZH"])
        ok("inject 回写成功", rc == 0, out)
        after = open(fonts_js, encoding="utf-8").read()
        ok("inject 只改了 ZH，SG5 未动", "keep-me" in after, after[-200:])

        rc, out = run([os.path.join(HERE, "check_cmap.py"), proj, "--fonts", fonts_js, "--var", "ZH"])
        ok("回写后复验 0 缺字", rc == 0 and "真实缺字: 0" in out, out)

        print()
        if fails:
            print("有 %d 项失败：%s" % (len(fails), ", ".join(fails)))
            return 1
        print("ALL PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
