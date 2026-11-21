---
name: cjk-font-subset
slug: cjk-font-subset
version: 1.0.0
displayName: 中文字体子集化 + 缺字校验
description: 把项目里会显示的汉字抽出来，从源字体生成极小的 woff2（16.9MB → 275KB），并给出能挂 CI 的缺字检查（按字体 cmap 实测、报文件:行号）。支持 file / css 内联 / 回写 fonts.js 三种落地。
tags: 中文字体,字体子集,woff2,fonttools,@font-face,base64,缺字检查,小程序,H5,体积优化
license: MIT
---

# 中文字体子集化 + 缺字校验

中文字体动辄 10–20 MB，不可能整份发到前端。业界标准做法是**子集化**：只把项目里真正用到的
汉字切出来，其余丢掉。一个 995 个汉字的项目实测：

```
Noto Sans SC 可变字体全量  16.9 MB  →  子集 woff2  275 KB（base64 内联后约 367 KB）
```

体积降 98%，而且不再依赖任何 CDN（内联在包里，无外链、无跨域、无隐私风险）。

但**光有子集化会翻车**：改了一句文案、灌进一张表格的中文、甚至写了一句中文注释，
都可能引入字表里没有的字 —— 线上表现是**一小部分字显示成方框**，很难自查。
所以这套东西必须是两件套：**重建（subset）+ 实测检查（check）**，检查能挂 CI。

## 什么时候用

- 前端项目里要放中文字体（小程序 / H5 / Electron / PWA / 单页内联）
- 改完中文文案后要确认「没有字变成方框」
- 想把「缺字」变成 CI 上的一条红/绿，而不是上线后靠人眼发现
- 项目里已经有一份 `var ZH = 'data:font/woff2;base64,…'`，改文案后需要原地更新

## 30 秒上手

```bash
# 依赖（只这两个：fonttools 读/写字体，brotli 读写 woff2）
python3.12 -m pip install fonttools brotli

# 0) 先自测：不需要任何系统字体、不联网，造一个只含几个汉字的测试字体跑全链路
python3.12 scripts/selftest.py          # 期望最后打印 ALL PASS

# 1) 只看缺多少字，不写文件
python3.12 scripts/subset_cjk.py ./app --src C:/Windows/Fonts/NotoSansSC-VF.ttf --dry-run

# 2) 出 woff2 文件（H5 / Electron）
python3.12 scripts/subset_cjk.py ./app --src <源字体> --mode file

# 3) 出 @font-face + base64 的 CSS（单文件自包含）
python3.12 scripts/subset_cjk.py ./app --src <源字体> --mode css --family MyCJK

# 4) 回写项目已有的 fonts.js
python3.12 scripts/subset_cjk.py ./app --src <源字体> --mode inject \
    --target app/data/fonts.js --var ZH

# 5) 复验（另一个脚本，口径更严格）—— 这一步才是「有没有方框」的判据
python3.12 scripts/check_cmap.py ./app --fonts app/data/fonts.js --var ZH
```

`check_cmap.py` 的退出码：**0 = 没有缺字，1 = 有缺字**（可直接挂进 CI / pre-commit）。

## 为什么是两个脚本、两套口径

| 脚本 | 口径 | 为什么这么定 |
|---|---|---|
| `subset_cjk.py` | **重建口径**：只跳过「整行」`//` 与块注释；行尾注释里的中文**照样进字表** | 重建要**宁可多带字**，少一个大不了多几 KB，少一个就是线上方框 |
| `check_cmap.py` | **严格口径**：`//` 与 `/* */` 全去（保留字符串字面量里的中文，别把 `'https://…'` 截断） | 检查要**宁可报严**，误报只是让你多看一眼，漏报就是事故 |

⚠️ **只比数量一定漏**。最常见的假绿灯是「代码用到 871 个汉字 / 字表 878 个 ✓ 没有缺字」——
数量够 ≠ 字够。真实翻车：数量检查全过，真机仍有 7 个字是方框（全部来自刚合进来的两个新页面）。
唯一可靠判据是 `check_cmap.py` 那样**按字体 cmap 逐字比对**。

## 六个坑（都踩过）

| # | 坑 | 说明 |
|---|---|---|
| 1 | **行尾注释照样进字表** | 「改注释不必重做子集」只对**独占一行**的注释成立。在两行代码后补一句 `// … 不显示重量栏`，`栏`/`省` 立刻被报缺字。新注释写成独立一行，或避开生僻字 |
| 2 | **测试断言里的中文也算字** | `ok('… 精简 / 命中 / 齐')` 这种断言文案会被算进字表。改断言时顺手避开表外的字（`精简`→`现在`）比为了三个字重建子集划算。但**UI 文案缺字必须重建**，不能靠换字糊过去 |
| 3 | **灌入外部表格数据 = 改文案** | 把动作库表的肌群/器材列灌进详情页，`股四头肌 / 肱二头肌 / 腘绳肌 / 菱形肌 / 药球` 一次报缺 15 字。数据文件单独一份，别为了展示字段改主字典结构 |
| 4 | **顺序铁律：字体 PR 最后合** | 字体子集是全局生成物，依赖**全部**文案。所有改文案的 PR 合完之后，最后单独合字体 PR。否则每合一个就要重建一次（实测：先合字体修 7 字，再合 storage 又带进 3 字，白做一轮） |
| 5 | **`fonts.js` 是生成物，别手改** | 它是一次 base64 几十万字符的单行；手改几乎必然弄坏。要改就重跑；判断缺字是不是你引入的：`git stash -q && <check> ; git stash pop -q`，改前就红说明是前人留下的 |
| 6 | **小程序不能引外部字体文件** | `@font-face` 的 `src` 只认 `https://`（合法域名白名单）或 base64。离线可用 + 不依赖 CDN 就得内联；内联后体积 ≈ woff2 × 4/3（base64 编码膨胀），275 KB 的 woff2 内联后约 367 KB |

## 源字体怎么选

- **Noto Sans SC / 思源黑体**：SIL OFL 1.1，可商用、可再分发（最常见的选择）
- **可变字体 vs 静态字重**：可变字体（`-VF`）一份含多个字重，`--src` 指它就行；子集化会自动保留用到的轴
- 别用来路不明的「免费字体」：license 不清的字体装进商业项目，是真实的法律风险
- 检查本机有没有 Noto Sans SC：`python3.12 -c "import os;print(os.path.exists('C:/Windows/Fonts/NotoSansSC-VF.ttf'))"`；
  没有就去 Google Fonts 或 `github.com/notofonts/noto-cjk` 取

## 字号体系（附赠：子集化之后最容易犯的错）

子集化只解决「字有没有」，不解决「看得清不清」。真实用户反馈「字太小」时的正确做法：

- **字号只从一套 token 来**（如 `--fs-1 … --fs-8` 八档），页面里不写裸 `font-size: 26rpx`
- **中文正文字号有下限**：移动端正文不小于 `32rpx`（约 16px @375 宽），说明文字不小于 `24rpx`
- **调大字号后必须检查卡片标题折行**：字号 +1 档常常让「动作名 + 单位」这一行挤成两行，卡片高度跳变
- 调完拿真机最小屏（如 375×667）过一遍：宽屏好看不算好看

细节清单见 `references/cjk-font-ops.md`。

## 文件

- `scripts/subset_cjk.py` —— 抽字 + 子集化 + 三种落地（file / css / inject）
- `scripts/check_cmap.py` —— 严格口径缺字检查，`exit 1` 可直接挂 CI
- `scripts/make_test_font.py` —— 造一个只含指定汉字的极小 TTF（离线自测用）
- `scripts/selftest.py` —— 端到端自测，15 项断言，含「检查器必须真的会红」的反证
- `references/cjk-font-ops.md` —— 口径细节、真实翻车记录、CI 接法、字号体系

## 边界

- 只处理**汉字/中日韩统一表意文字**（含扩展 A、兼容区）。日文假名、韩文不在此列
- 不管字体设计（字重搭配、行高、字间距），只管「有没有这个字 + 体积」
- `check_cmap.py` 靠扩展名判定，动态拼接出来的中文（如 `'第' + n + '组'`）只能认出字面量部分——
  拼接出来的字要么加进 `--no-safety` 之外的保险字表，要么写个断言把可能值列出来
