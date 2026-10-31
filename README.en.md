[中文](README.md) | [English](README.en.md)

# AI DevKit (DevKit · Chinese Edition)

Live preview: https://bmdy1145.github.io/devkit/
Repository: https://github.com/bmdy1145/devkit

## Overview

DevKit is a **single-file, pure HTML** local developer utility. Open it in any modern browser and it just works: no installation, no build step, no backend dependency. All data lives in browser memory only — nothing is sent anywhere, nothing is uploaded.

The tool organises collaboration around **workflow steps**: for each step you write your inspiration (the requirement) and paste your current code; DevKit combines the step's built-in prompt template with your input into one complete instruction that you can copy in a single click and paste into any AI chat tool.

## Features

- **Workflow tabs**: 22 built-in prompt templates — Version Planning, Requirements Analysis, Security Audit, Performance Audit, Refactoring, Unit Testing, Integration Testing, Version Number Derivation, i18n Adaptation, Deployment & Operations, Performance Monitoring, Data Analysis, Accessibility Audit, Architecture Design, Security Compliance, Full Rewrite — plus a blank tab
- **Multiple projects**: project tab bar with create / switch / close; each project keeps its own tabs and editor state
- **Inspiration sync**: sync the inspiration field across tabs within a project; when turned off, other tabs are cleared
- **Combined preview**: live preview of the full instruction that will be sent to the AI, with copy, copy-requirement-only, and download-and-copy actions
- **Spec prompt**: the project's own *Specification Prompt*, copyable as a whole
- **Code editor**: synchronised line numbers, paste, copy, clear, upload / drag-and-drop import, export code (multiple extensions), and an "Evolve" action that loads DevKit's own source
- **AI result area**: paste what the AI returns and overwrite the code area in one click
- **Version history**: collapsible tree, milestone nodes expanded by default, with expand-all / collapse-all that preserve scroll position
- **Full-site visual skins**: the nine skins share identical functional logic and differ only in the visual layer — see "Visual skins" below
- **Theme switching**: the switcher sits in the top-left; chosen once in the first-run guide and remembered afterwards. Which dimensions are available depends on the skin
- **Performance mode**: lowers preview refresh frequency (from once per second to on demand)
- **Config import / export**: export `devkit_config.json`; import supports full overwrite restore
- **Quick file rename**: pick a directory and rename files to `Deepseek_ + your text + original extension`
- **Keyboard shortcut**: `Esc` closes the topmost dialog

## Visual skins

The same functional code ships with nine skins. Each is an independent single-file version; they do not affect one another:

| Version | Skin | Theme dimensions |
|---------|------|------------------|
| `A1_V_Φ9_Clean_Fix_CN` | Clean: Roboto / Poppins / Inconsolata, 8pt baseline grid, 6/8px corners, restrained soft shadows | Clean dark / Clean light / Follow system |
| `A1_V_Φ9_Material_Fix_CN` | Material Design (MD3): Roboto + Fira Code, five levels of tinted surfaces, tonal palette, state layers, elevation 1–5, corners 4/8/12/28px | Dark / Light / Follow system |
| `A1_V_Φ9_Minimal_Fix_CN` | Minimal: Open Sans / Inter / Inconsolata, near-monochrome with a single indigo accent, no shadows, whitespace and 1px dividers | Minimal dark / Minimal light / Follow system |
| `A1_V_Φ9_Premium_Fix_CN` | Premium: Inter + JetBrains Mono, precise spacing rhythm, soft layered shadows, refined letter-spacing and line-height | Premium dark / Premium light / Follow system |
| `A1_V_Φ9_Shadcn_Fix_CN` | Shadcn: Geist + Fira Code, monochrome greys with `hsl()` semantic tokens, 1px border layering, flat (no shadows) | Shadcn dark / Shadcn light / Follow system |
| `A1_V_Φ9_Mono_Fix_CN` | Full-site monospace: Space Mono + JetBrains Mono, no glow, 1px hard borders, tight corners | Light/dark (dark / light / auto) × accent (matrix green / cold white / amber) — 6 palettes |
| `A1_V_Φ9_Neon_Fix_CN` | Electric neon: near-opaque panels, coloured borders, layered outer glow, no backdrop blur | Dark neon / Light neon / Follow system |
| `A1_V_Φ9_Glass_Fix_CN` | Glassmorphism: translucent layers, background blur, luminous borders | Dark glass / Light glass / Follow system |
| `A1_V_Φ9_Fix_CN` | Baseline skin (no skin; numeric theme system) | Original `theme` system |

All nine belong to main line `A1_V_Φ9`; the current iteration layer is **Fix**. The incremental change in Φ9 is a **Pages site-home link added to the “About DevKit” dialog** (opened by clicking the DevKit wordmark in the top-left corner), plus a site change on the project page: a new “nine skins — open directly” section at the top brings opening the app from the site home page down from three clicks to two.

Φ9_Fix **fixes 43 defects** (a fourth-layer `Fix` tag on Φ9, with the Φ number unchanged), shipped across all nine skins: 12 functional (first-run theme buttons had no handler, full export omitted `version`, copy failures reported success, the context menu never closed and could act on the wrong project, the rename tool could never delete the original file, touch devices could accidentally close a project, cycle-extension version numbers were misjudged, `window.open` lost the user gesture, imported AI sites did not refresh, and the editor was not saved before import), 8 visual (Shadcn wrapped an already-complete `hsl()` foreground in `hsl()` again, making text nearly invisible; active states were overridden by hover/hidden-text rules; several contrast failures), 5 accessibility (keyboard reachability, focus trap and focus restoration, ARIA state), and 18 robustness items (import field and tab-type validation, async races, false-positive unsaved prompts, mutually exclusive menus, context-menu viewport clamping). The unfixed Φ9 originals are archived under `projects/devkit/code/A1_V_Φ9_fix-archive/`.

Φ9_Fix_Fix **fixes a ReDoS in version parsing**: the old single-pattern regex backtracks exponentially on inputs like `A1` + many `_A` segments + an illegal trailing character (measured: 63 characters froze the page for 126 s). It now splits on `_` and validates each segment linearly. Behaviour is equivalent to the old regex (verified against 17 version strings), shipped across all nine skins.

The incremental change in Φ8 was **full-site responsive, multi-ratio and touch adaptation**: `viewport-fit=cover`, `100dvh` height with `env(safe-area-inset-*)` safe areas, width breakpoints at ≥1800 / ≤1024 / ≤820 / ≤560 plus a ≤520 height breakpoint, vertical stacking and horizontally scrolling step lists on narrow screens, enlarged touch targets on coarse pointers, and drag handles switched from mouse to pointer events. All nine skins share the same adaptation layer.

Eight of the nine skins (all but the baseline) unify on a three-state `themePref` — dark / light / follow system — chosen once in the first-run guide and remembered in `devkit_theme_pref`, with `auto` tracking the system colour scheme live. The baseline skin keeps the original numeric `theme` system.

In the version string, `Glass` / `Neon` / `Mono` / `Clean` / `Material` / `Minimal` / `Premium` / `Shadcn` are **variant markers** (they occupy no layer).

The previous generation `A1_V_Φ8` is available **in parallel** with Φ9 under `projects/devkit/code/A1_V_Φ8/`, with nine skins at the `Fix_Fix` iteration layer. The earlier `A1_V_Φ7` (four skins), `A1_V_Φ5` (two versions) and `A1_V_Φ4` (one version) are also kept under `projects/devkit/code/` for historical reference — skins only arrived with Φ7, so Φ5 and Φ4 have none.

## Usage

1. **Easiest: grab a Release.** Every update to `main` is published automatically, packaged per main line with all of that generation's skins attached — one click, no browsing. See https://github.com/bmdy1145/devkit/releases
2. **Read online:** open https://bmdy1145.github.io/devkit/projects/devkit/ and click any skin under “nine skins — open directly”; or download `projects/devkit/code/A1_V_Φ9_Fix_Fix/deepseek_A1_V_Φ9_Clean_Fix_Fix_CN.html` directly
3. Double-click to open it in a browser (Chrome / Edge or any modern browser)
4. Pick a step under "Workflow Steps" → fill in the inspiration and paste your code → click "Copy" → paste into your AI chat tool

> Note: directory selection and original-file deletion rely on the browser's File System Access API (best supported on Chromium-based browsers).

## Version Naming Scheme

The project uses a "four base layers + cyclic extension" version scheme:

| Layer | Identifier | Description |
|-------|-----------|-------------|
| 1st | Branch code (A1, A2) | Specified by the user |
| 2nd | Roman numerals (I, II, III…) | Incremented on a rewrite or major upgrade; lower layers reset |
| 3rd | Φ + number (Φ1, Φ2…) | Incremental changes on the same Roman-numeral version |
| 4th | English tag (Fix, Perf, Doc…) | Minor tweaks; appended when the change is below incremental scale, without bumping Φ. **Skin names do not belong to this layer** — see the variant-marker note below |

Beyond the 4th layer the scheme cycles as `B1 → I → Ψ1 → English tag → C1 …`, e.g. `A1_I_Φ1_Fix_B1_I_Ψ1_Fix_C1`.

**Variant markers occupy no layer**: skin names (Glass / Neon / Mono / Clean / Material / Minimal / Premium / Shadcn) denote "parallel skins of the same version". They are variant markers rather than iteration layers, and sit after the Φ layer and before the language suffix. So in `A1_V_Φ8_Glass_Fix_CN`, `Glass` is the variant marker and `Fix` is the actual 4th-layer English tag — the version string is valid; `A1_V_Φ9_Glass_Fix_CN` is valid for the same reason. Variant markers must not be used to express iteration (e.g. `Glass2`).

The project maintains two language variants in parallel. They share the same main-line version number and differ only by a trailing suffix: `_CN` (Chinese edition) and `_GLOBAL` (multilingual edition). This repository is the **Chinese edition**.

## Repository Layout

```
devkit/                              # Repo root (GitHub Pages publish folder)
├── README.md / README.en.md        # Documentation (must stay at root for GitHub to render it)
├── SECURITY.md / SECURITY.en.md    # Security policy (must stay at root for the Security tab)
├── LICENSE                          # Full text of the GPLv3 license (must stay at root)
├── index.html                       # GitHub Pages landing page (project picker)
├── 404.html                         # Fallback for pre-migration /code/** paths
├── .nojekyll                        # Disables Jekyll processing (plain static site)
├── .github/                         # PR template, CODEOWNERS, workflows, Dependabot
│   ├── workflows/                   # version guard, repo checks, auto release, branch cleanup, PR labels
│   └── scripts/                     # check scripts called by the workflows; runnable locally
├── docs/                            # Repo-level conventions (shared across projects)
│   ├── .gitkeep                     # Placeholder only (git cannot track empty folders)
│   ├── branching.md                 # Branching & PR policy (imported by CLAUDE.md via @)
│   └── github-settings.md           # GitHub repo settings manual (branch protection, Actions)
├── projects/                        # One directory per project, each with its own landing page
│   ├── index.html                   # Index for /projects/
│   ├── devkit/                      # Project: AI 开发快捷工具箱
│   │   ├── index.html               # Project landing page (skin shortcuts + download + branches)
│   │   └── code/
│   │       ├── index.html                   # Index for the branch directory
│   │       ├── A1_V_Φ9_Fix_Fix/             # Current main line (Fix_Fix layer, ReDoS fix)
│   │       ├── A1_V_Φ9/                     # Previous iteration layer (Fix)
│   │       │   ├── index.html                              # Version list for this branch
│   │       │   ├── deepseek_A1_V_Φ9_Clean_Fix_CN.html          # Clean
│   │       │   ├── deepseek_A1_V_Φ9_Material_Fix_CN.html       # Material Design (MD3)
│   │       │   ├── deepseek_A1_V_Φ9_Minimal_Fix_CN.html        # Minimal
│   │       │   ├── deepseek_A1_V_Φ9_Premium_Fix_CN.html        # Premium
│   │       │   ├── deepseek_A1_V_Φ9_Shadcn_Fix_CN.html         # Shadcn
│   │       │   ├── deepseek_A1_V_Φ9_Mono_Fix_CN.html           # Monospace + two-axis themes
│   │       │   ├── deepseek_A1_V_Φ9_Neon_Fix_CN.html           # Electric neon
│   │       │   ├── deepseek_A1_V_Φ9_Glass_Fix_CN.html          # Glassmorphism
│   │       │   └── deepseek_A1_V_Φ9_Fix_CN.html                # Baseline skin
│   │       ├── A1_V_Φ9_fix-archive/         # Archived unfixed Φ9 builds (nine)
│   │       │   └── index.html
│   │       ├── A1_V_Φ8/                     # Previous main line (parallel with Φ9)
│   │       │   ├── index.html                              # Version list for this branch
│   │       │   ├── deepseek_A1_V_Φ8_Clean_Fix_Fix_CN.html      # Clean
│   │       │   ├── deepseek_A1_V_Φ8_Material_Fix_Fix_CN.html   # Material Design (MD3)
│   │       │   ├── deepseek_A1_V_Φ8_Minimal_Fix_Fix_CN.html    # Minimal
│   │       │   ├── deepseek_A1_V_Φ8_Premium_Fix_Fix_CN.html    # Premium
│   │       │   ├── deepseek_A1_V_Φ8_Shadcn_Fix_Fix_CN.html     # Shadcn
│   │       │   ├── deepseek_A1_V_Φ8_Mono_Fix_Fix_CN.html       # Monospace + two-axis themes
│   │       │   ├── deepseek_A1_V_Φ8_Neon_Fix_Fix_CN.html       # Electric neon
│   │       │   ├── deepseek_A1_V_Φ8_Glass_Fix_Fix_CN.html      # Glassmorphism
│   │       │   └── deepseek_A1_V_Φ8_Fix_Fix_CN.html            # Baseline skin
│   │       ├── A1_V_Φ8_fix-archive/         # Historical archive of Φ8's Fix layer
│   │       │   └── index.html                              # Archive page (nine Fix builds)
│   │       ├── A1_V_Φ7/                     # Earlier historical main line
│   │       │   ├── index.html
│   │       │   ├── deepseek_A1_V_Φ7_Mono_CN.html
│   │       │   ├── deepseek_A1_V_Φ7_Neon_CN.html
│   │       │   ├── deepseek_A1_V_Φ7_Glass_CN.html
│   │       │   └── deepseek_A1_V_Φ7_CN.html
│   │       ├── A1_V_Φ5/                     # Early main line (historical reference)
│   │       │   ├── index.html
│   │       │   ├── deepseek_A1_V_Φ5_Fix_CN.html          # Icon font embedded locally + spec red lines
│   │       │   └── deepseek_A1_V_Φ5_CN.html              # Fixes 9 inherited defects + 4 review amendments
│   │       └── A1_V_Φ4/                     # Early main line (historical reference)
│   │           ├── index.html
│   │           └── deepseek_A1_V_Φ4_CN.html              # Fixes 15 defects
│   ├── submerge-pro/                # Project: bilingual subtitle translation/splitting
│   │   ├── index.html
│   │   └── code/
│   │       ├── index.html
│   │       └── A1_II_Φ10/
│   │           ├── index.html
│   │           ├── deepseek_html_20260705_d1ca99.html     # Original archive
│   │           └── deepseek_html_20261006_d1ca99_Fix.html # Safe filename rendering fix
│   ├── dircleaner/                  # Project: empty a user-selected directory
│   │   ├── index.html
│   │   └── code/
│   │       ├── index.html
│   │       └── A1_II_Φ8/
│   │           ├── index.html
│   │           └── deepseek_html_20261005_ada08c.html
│   └── writer/                      # Project: novel editor
│       ├── index.html               # Landing page (open link + data-safety notice)
│       └── code/
│           ├── index.html           # Code / branch index
│           ├── A1_I_Φ6/             # Current version (writing stats & layout)
│           │   ├── index.html
│           │   └── deepseek_A1_I_Φ6_CN.html
│           ├── A1_I_Φ5/             # POV converter
│           │   ├── index.html
│           │   └── deepseek_A1_I_Φ5_CN.html
│           ├── A1_I_Φ4/             # Data safety & concurrency fixes
│           │   ├── index.html
│           │   └── deepseek_A1_I_Φ4_CN.html
│           ├── A1_I_Φ3/             # Logic & robustness fixes
│           │   ├── index.html
│           │   └── deepseek_A1_I_Φ3_CN.html
│           ├── A1_I_Φ2/             # Layout rework (single left column, four tabs)
│           │   ├── index.html
│           │   └── deepseek_A1_I_Φ2_CN.html
│           └── A1_I_Φ1/             # First release (historical reference)
│               ├── index.html
│               └── deepseek_A1_I_Φ1_CN.html
│   └── persona/                     # Project: character-profile editor
│       ├── index.html               # Landing page (open entry + data-safety notice)
│       └── code/
│           ├── index.html           # Code / branch index
│           ├── A1_II_Φ8/            # Current version (persona/worldview switch)
│           │   ├── index.html
│           │   └── deepseek_A1_II_Φ8_CN.html
│           ├── A1_II_Φ7/            # Worldview in sidebar
│           │   ├── index.html
│           │   └── deepseek_A1_II_Φ7_CN.html
│           ├── A1_II_Φ6/            # UI
│           │   ├── index.html
│           │   └── deepseek_A1_II_Φ6_CN.html
│           ├── A1_II_Φ5/            # Export
│           │   ├── index.html
│           │   └── deepseek_A1_II_Φ5_CN.html
│           ├── A1_II_Φ4/            # Parallel worlds & worldviews
│           │   ├── index.html
│           │   └── deepseek_A1_II_Φ4_CN.html
│           ├── A1_II_Φ3/            # Responsive layout
│           │   ├── index.html
│           │   └── deepseek_A1_II_Φ3_CN.html
│           ├── A1_II_Φ2/            # Interview mode
│           │   ├── index.html
│           │   └── deepseek_A1_II_Φ2_CN.html
│           └── A1_II_Φ1/            # First release
│               ├── index.html
│               └── deepseek_A1_II_Φ1_CN.html
└── .claude/skills/devkit-spec/      # Claude Code skill (version & collaboration spec + version templates)
```

> Only the contents of `projects/<name>/` are project artifacts. The three root documents, `index.html`, `404.html`, `docs/`, `.claude/` and `.github/` are all **repo-level** — they belong to no project's version scheme and carry no project version number.

### Multi-project layout

This repository is organised as `projects/<name>/`, one directory per project:

- Each project ships its own `index.html` as its landing page. The internal directory structure and version-numbering rules are **up to each project** — the repo imposes no shared convention on them.
- The root `index.html` is a **project picker**; it only lists entries to the projects.
- `docs/` (conventions) and `.github/` (automation) are **shared across projects**. `version_guard.py` covers DevKit, Writer and Persona; `size_guard.py` and `smoke_test.py` auto-discover `projects/*/code/*/deepseek_*.html`, so a new project needs no registration. `auto_release.py` discovers projects and main lines automatically and prefixes tags with the project name for non-DevKit projects.
- The repository currently hosts five projects: `devkit`, `submerge-pro`, `dircleaner`, `writer` and `persona`. Add future projects under `projects/<name>/` and update the root project picker and `projects/index.html`.

### Pages deployment note

The site entry is the **root-level** `index.html`, a **project picker**; each project then has its own version picker. The site is browsable level by level:

| Path | Content |
|------|---------|
| `/` | Project picker: every project hosted in this repository |
| `/projects/` | Index for the projects directory |
| `/projects/devkit/` | DevKit landing page: nine-skin shortcuts + download + branch cards |
| `/projects/devkit/code/` | DevKit branch index (Φ9 / Φ8 / Φ7 / Φ5 / Φ4) |
| `/projects/devkit/code/A1_V_Φ9/` | Version list for the current main line (nine skins, Fix layer) |
| `/projects/devkit/code/A1_V_Φ9_fix-archive/` | Archived unfixed Φ9 builds (nine, for comparison and rollback) |
| `/projects/devkit/code/A1_V_Φ8/` | Version list for the previous main line (nine skins, Fix_Fix, parallel with Φ9) |
| `/projects/devkit/code/A1_V_Φ8_fix-archive/` | Historical archive of Φ8's Fix layer (nine builds) |
| `/projects/devkit/code/A1_V_Φ7/` | Version list for the earlier main line (four skins) |
| `/projects/devkit/code/A1_V_Φ5/` | Early main line (two versions, historical reference) |
| `/projects/devkit/code/A1_V_Φ4/` | Early main line (one version, historical reference) |
| `/projects/submerge-pro/` | SubMerge Pro project page |
| `/projects/submerge-pro/code/` | SubMerge Pro branch index |
| `/projects/submerge-pro/code/A1_II_Φ10/` | Original archive and A1_II_Φ10_Fix security revision |
| `/projects/dircleaner/` | DirCleaner project page |
| `/projects/dircleaner/code/` | DirCleaner branch index |
| `/projects/dircleaner/code/A1_II_Φ8/` | A1_II_Φ8 application file |
| `/projects/writer/` | Writer novel-editor project page |
| `/projects/writer/code/` | Writer code/branch index |
| `/projects/writer/code/A1_I_Φ6/` | A1_I_Φ6 application file (current · writing stats & layout) |
| `/projects/writer/code/A1_I_Φ5/` | A1_I_Φ5 application file (POV converter) |
| `/projects/writer/code/A1_I_Φ4/` | A1_I_Φ4 application file (data safety fixes) |
| `/projects/writer/code/A1_I_Φ3/` | A1_I_Φ3 application file (logic & robustness fixes) |
| `/projects/writer/code/A1_I_Φ2/` | A1_I_Φ2 application file (layout rework) |
| `/projects/writer/code/A1_I_Φ1/` | A1_I_Φ1 application file (historical reference) |
| `/projects/persona/` | Persona character-profile editor project page |
| `/projects/persona/code/` | Persona code/branch index |
| `/projects/persona/code/A1_II_Φ8/` | A1_II_Φ8 application file (current · persona/worldview switch) |
| `/projects/persona/code/A1_II_Φ7/` | A1_II_Φ7 application file (worldview in sidebar) |
| `/projects/persona/code/A1_II_Φ6/` | A1_II_Φ6 application file (UI) |
| `/projects/persona/code/A1_II_Φ5/` | A1_II_Φ5 application file (export) |
| `/projects/persona/code/A1_II_Φ4/` | A1_II_Φ4 application file (parallel worlds & worldviews) |
| `/projects/persona/code/A1_II_Φ3/` | A1_II_Φ3 application file (responsive layout) |
| `/projects/persona/code/A1_II_Φ2/` | A1_II_Φ2 application file (interview mode) |
| `/projects/persona/code/A1_II_Φ1/` | A1_II_Φ1 application file (first release) |

Beyond Pages there is a **download entry point**: the repository's Releases page (`/releases`), maintained automatically by `.github/workflows/release-on-main.yml` — every update to `main` packages that main line's artifacts and attaches them. Downloading is easiest there; reading online is what Pages is for.

GitHub Pages must therefore publish from **`/ (root)`**:

> Settings → Pages → Deploy from a branch → Branch: `main` → folder **`/ (root)`** → Save

Do **not** set the publish folder to `/docs`: with `/docs`, GitHub Pages only publishes files inside the `docs/` directory, so neither the root `index.html` nor `projects/` would go live, and the site would return 404.

> Note 1: GitHub Pages does **not** generate directory listings. A directory without an `index.html` returns 404, which is why `/projects/`, `/projects/devkit/`, `/projects/devkit/code/` and each main-line directory contain an explicit `index.html`.

> Note 2: **Fallback for old links.** Before the project layer was introduced on 2026-10-03, DevKit lived directly under the repo-level `code/`; those addresses stopped working after the move. The root `404.html` redirects `/devkit/code/**` to `/devkit/projects/devkit/code/**`, covering any depth (including deep links to individual files) in one go. If the repository is ever renamed, update the `BASE` constant in that file.

## License

AI DevKit  Copyright (C) 2026-present  北冥的鱼, DeepSeek

This program is free software, released under GPLv3, with no warranty. You should have received a copy of the GNU General Public License.
