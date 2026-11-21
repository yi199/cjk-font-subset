# cjk-font-subset

**Subset huge CJK fonts down to a tiny woff2, and CI-check that no glyph is missing.** An Agent Skill (SKILL.md) with portable, dependency-light Python scripts for WeChat Mini Programs, H5, Electron, PWA and any web project that ships Chinese text.

A real project using 995 Chinese characters:

```
Noto Sans SC variable font (full)   16.9 MB
└─ subsetted woff2                    275 KB   (≈ 367 KB after base64 inlining)
```

**~98% smaller**, self-contained in the bundle — no CDN, no external font request, no cross-origin or privacy dependency.

## Why subsetting alone is not enough

Subsetting keeps only the glyphs your project actually uses. But every copy change, imported spreadsheet column, or even a Chinese code comment can introduce a character the subset does not contain — which renders as a hollow box (tofu) in production and is easy to miss in review.

So this skill ships **two tools with intentionally different strictness**:

| Script | Role | Strictness |
|---|---|---|
| `subset_cjk.py` | Rebuild the subset; supports `file` / `css` / `inject` output | Lenient — trailing comments still contribute glyphs, better to carry a few extra than miss one |
| `check_cmap.py` | Verify every used glyph exists in the font's cmap; reports `file:line` | Strict — strips all comments; false positives only cost a glance, a miss is an incident |

`check_cmap.py` exits `0` when complete and `1` on any missing glyph, so it plugs straight into CI / pre-commit. Counting glyphs is **not** a valid check ("871 used / 878 in font ✓" can still show 7 tofu boxes) — only cmap-level per-character comparison is reliable.

## Quick start

```bash
# Two dependencies: fonttools reads/writes fonts, brotli handles woff2
python -m pip install fonttools brotli

# Offline self-test: builds a tiny synthetic TTF, no system fonts or network needed
python scripts/selftest.py          # expect: ALL PASS

# Preview missing glyphs without writing anything
python scripts/subset_cjk.py ./app --src <path-to-source-font.ttf> --dry-run

# Emit a woff2 file (H5 / Electron)
python scripts/subset_cjk.py ./app --src <path-to-source-font.ttf> --mode file

# Emit a self-contained @font-face CSS with base64
python scripts/subset_cjk.py ./app --src <path-to-source-font.ttf> --mode css --family MyCJK

# Update an existing fonts.js in place (var ZH = 'data:font/woff2;base64,…')
python scripts/subset_cjk.py ./app --src <path-to-source-font.ttf> \
    --mode inject --target app/data/fonts.js --var ZH

# The authoritative "will anything render as tofu?" check
python scripts/check_cmap.py ./app --fonts app/data/fonts.js --var ZH
```

## Source fonts

- **Noto Sans SC / Source Han Sans** (SIL OFL 1.1) — free for commercial use and redistribution, the common default.
- Variable fonts are supported: point `--src` at the `-VF` file and used axes are preserved automatically.
- Never bundle a "free font" with an unclear license into a commercial product.

## Scope and limits

- Handles **Han / CJK Unified Ideographs** only (including Extension A and compatibility blocks). Kana and Hangul are out of scope.
- Covers glyph coverage and size, not type design (weight pairing, line height, letter spacing).
- `check_cmap.py` recognizes string literals; dynamically concatenated Chinese (e.g. `'第' + n + '组'`) can only be caught for the literal parts — enumerate possible values in an assertion or an explicit safety glyph list.

## Repository layout

```
SKILL.md                      Agent Skill definition (Chinese; the skill body loaded by AI agents)
scripts/subset_cjk.py         Extract glyphs + subset, three output modes
scripts/check_cmap.py         Strict missing-glyph check, CI-friendly exit codes
scripts/make_test_font.py     Build a minimal TTF for offline testing
scripts/selftest.py           End-to-end self-test (15 assertions, incl. negative cases)
references/cjk-font-ops.md    Operational details, real failure log, CI wiring, type-scale guidance
```

## License

MIT — see [LICENSE](LICENSE).
