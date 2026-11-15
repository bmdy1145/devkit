[中文](SECURITY.md) | [English](SECURITY.en.md)

# Security Policy

## Supported Versions

Security fixes are provided only for the **latest version of each project**. Historical
versions are kept frozen for reference and rollback only.

| Project | Current version | Supported |
|---------|-----------------|-----------|
| DevKit · AI developer toolkit | `A1_V_Φ10` (Refactor, single Premium theme) | ✅ |
| Writer · Novel editor | `A1_I_Φ6` (8 skins) | ✅ |
| Persona · Character-profile editor | `A1_II_Φ15` (8 skins) | ✅ |
| DirCleaner · Directory cleaner | `A1_II_Φ9` (8 themes) | ✅ |
| SubMerge Pro · Bilingual subtitle tool | `A1_II_Φ11` (9 standalone themes + all-in-one) | ✅ |
| All earlier versions of the above | — | ❌ |

## Reporting a Vulnerability

Please do **not** disclose security issues through public Issues. Available channels:

1. The repository's **Security** tab → **Report a vulnerability** (private vulnerability reporting; the feature must be enabled for the repository);
2. If the entry point above is unavailable, contact the maintainer using the contact details given in the copyright notice in the source code.

A good report includes: a description of the issue, reproduction steps, impact, and a suggested fix if you have one; a PoC is welcome.

Maintainers will confirm and respond as soon as possible. Credit will be given in the version notes once a fix ships — let us know if you prefer to stay anonymous.

## Common Ground

All five projects are **static, single-file HTML applications**: no server, no build
pipeline, and no package manager (the only external resource is Google Fonts CSS, loaded
directly by the browser). All code ships inside the file, and nothing passes through a
server we control.

Unlike a traditional web application, the realistic attack surface is therefore the
browser's local capabilities: file access, clipboard, local storage, and content the user
pastes or imports.

## Attack Surface per Project

### DevKit · `A1_V_Φ10`

**Storage**: **not persisted.** Projects, tabs and settings live in memory only and are
discarded when the page closes; persistence relies on manually exporting a JSON config.
The only `localStorage` key is `devkit_first_run` (first-run flag, no user content).

**Network**: AI interaction happens in **external sites** opened via "Go to AI"; the app
itself makes no network requests.

**Risks**:

- **Imported configuration (JSON)**: reads a local JSON file, involving field type validation and prototype-pollution protection;
- **Clipboard**: paste buttons read clipboard contents, involving user awareness and length limits;
- **File system access**: quick file rename uses the directory picker API and performs file read, download and delete;
- **Local file import**: extension and MIME validation when dragging or uploading files.

### Writer · `A1_I_Φ6`

**Storage**: **persisted.** Manuscripts and reference material live in browser IndexedDB
(database `writer_db`), with a `localStorage` fallback key. Clearing site data loses drafts.

**Network**: optional AI streaming connects directly to an OpenAI-compatible endpoint the
user configures (e.g. `api.openai.com`, `api.anthropic.com`, `api.deepseek.com`), using the
user's own key.

**Risks**:

- API keys are stored locally; clear them on shared machines;
- Field validation when importing JSON backups;
- Exported files contain full manuscript text — mind who you share them with.

### Persona · `A1_II_Φ15`

**Storage**: **persisted.** Profiles, parallel worlds, memories and snapshots live in
browser IndexedDB (database `persona_db`), with a `localStorage` fallback key.

**Network**: as with Writer, AI calls go directly to the user-configured endpoint and the
key is stored locally.

**Risks**:

- Share images and full backups render or write every selected item — confirm the scope before exporting;
- Ownership checks when restoring snapshots and importing backups;
- Conflict handling for concurrent writes from multiple tabs.

### DirCleaner · `A1_II_Φ9`

**Storage**: **persisted.** Operation records live in IndexedDB; preferences use
`localStorage`.

**Network**: no requests beyond Google Fonts; deletion happens entirely on the local machine.

**Risks** (highest in this repository, because deletion is **irreversible**):

- **Directory picker**: uses the File System Access API (`showDirectoryPicker`) to read and write the user-selected directory;
- **Irreversible operation**: recursively empties a directory, with a confirmation flow and a second confirmation for critical directories and executables;
- Always back up first and double-check the target directory.

### SubMerge Pro · `A1_II_Φ11`

**Storage**: **not persisted.** Subtitle results live in memory and are discarded when the
page closes.

**Network**: the eight themed builds load UI fonts from Google Fonts and fall back to system
fonts offline; subtitle content is never uploaded.

**Risks**:

- Parsing and field validation when importing subtitle files;
- Exported files contain subtitle text — mind who you share them with.

## Shared Technical Measures

- **Content-Security-Policy**: every application file declares a CSP with `default-src 'self'`,
  `object-src 'none'` and `base-uri 'self'`; scripts and styles are limited to the file itself and inline;
- **Font sources**: limited per project to `data:` (embedded) or `https://fonts.gstatic.com`;
- **AI endpoints**: projects that need network access allow the user-configured endpoint via `connect-src`;
- **URL allow-list**: protocols are checked before opening AI sites, rejecting `javascript:`, `data:` and similar;
- **Import validation**: JSON imports are validated field by field against an allow-list of names and types; unknown fields are rejected.

## Out of Scope

- Vulnerabilities in the browser itself or in its File System APIs;
- Problems caused by third-party code or data that users paste or import themselves;
- Availability, privacy or billing of third-party AI services the user configures;
- Misbehaviour caused by outdated browsers (the latest Chrome / Edge is recommended).

## Security Recommendations

- Download files directly from this repository or its Releases; avoid copies of unknown origin;
- When handling sensitive code or manuscripts, remember that clipboard reads and exported files may contain personal information;
- Back up browser-local data regularly (Writer / Persona / DirCleaner data is lost when site data is cleared);
- On shared machines, clear any locally stored API keys after using AI features;
- These tools never upload content to a server we control. If you observe unexpected network requests, report them immediately.
