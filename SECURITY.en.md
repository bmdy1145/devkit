[中文](SECURITY.md) | [English](SECURITY.en.md)

# Security Policy

## Supported Versions

Security fixes are provided only for the latest version in this repository.

| Version | Supported |
|---------|-----------|
| A1_V_Φ9_CN (current latest) | ✅ |
| Earlier versions | ❌ |

## Reporting a Vulnerability

Please do **not** disclose security issues through public Issues. Available channels:

1. The repository's **Security** tab → **Report a vulnerability** (private vulnerability reporting; the feature must be enabled for the repository);
2. If the entry point above is unavailable, contact the maintainer using the contact details given in the copyright notice in the source code.

A good report includes: a description of the issue, reproduction steps, impact, and a suggested fix if you have one; a PoC is welcome.

Maintainers will confirm and respond as soon as possible. Credit will be given in the version notes once a fix ships — let us know if you prefer to stay anonymous.

## Scope and Attack Surface

DevKit is a **static, single-file HTML application**: no server, no build pipeline, no third-party scripts (only Google Fonts loaded from a CDN). At runtime all data stays in browser memory and is discarded when the page is closed.

So, unlike a traditional web application, the realistic attack surface is limited to:

- **Imported configuration files (JSON)**: the *Import config* feature reads a local JSON file, which involves field validation and prototype-pollution protection;
- **Clipboard reading**: the *Paste* buttons request clipboard contents, which involves user awareness and length limits;
- **File system access**: *Quick file rename* uses the directory picker API and performs file read, download and delete operations;
- **Local file import**: extension and MIME validation when dragging/uploading files;
- **CSP and external resources**: the page sets a Content-Security-Policy that allows only its own scripts and Google Fonts;
- **Data embedded in the page**: the source contains copyright and contact information, which is public information.

## Out of Scope

- Vulnerabilities in the browser itself or in its File System APIs;
- Problems caused by third-party code or data that users paste or import themselves;
- Misbehaviour caused by outdated browsers (the latest Chrome / Edge is recommended).

## Security Recommendations

- Download the file directly from this repository; avoid copies of unknown origin;
- When handling sensitive code, remember that clipboard reads and exported configuration files may contain personal information;
- This tool never uploads anything on its own. If you observe unexpected network requests, report them immediately.
