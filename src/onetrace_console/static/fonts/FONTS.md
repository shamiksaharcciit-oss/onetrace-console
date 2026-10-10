# The console's fonts: IBM Plex, bundled

The console serves these files itself, at `/static/fonts/<name>`; no page loads
a font from another host. The free viewer file uses system fonts instead.

**Upstream releases** (npm), each tarball checked against the registry's own sha512 integrity before
anything was taken from it:

| Package | Version | Integrity |
|---|---|---|
| `@ibm/plex-sans` 1.1.0 | 1.1.0 | `sha512-WPgvO6Yfj2w5YbhyAr1tv95RUz4LRJlqN+CmYvBglabXteufP1D1E9BABMde+ZIKdRbFJDoKF5eQzfhpnbgZcQ==` |
| `@ibm/plex-mono` 2.5.0 | 2.5.0 | `sha512-STBJIPxPomOYPmBMO7z5TKPJUotAF9u3gAUumTqVgwgrAO+K4FRNh0MlhsoJjKhJKsMbBJR10/bk4inkj/wc1w==` |

Taken from each package's `fonts/complete/woff2/`: Sans Regular, Medium and SemiBold (400, 500, 600)
and Mono Regular and Medium (400, 500), the weights the v6 boards use. `OFL.txt` is the packages'
`LICENSE.txt` (identical in both): the SIL Open Font License, Version 1.1, Copyright 2017 IBM Corp.,
Reserved Font Name "Plex".

**Files**, sha256 written by tooling (`tests/test_fonts.py` pins the same values):

| File | sha256 | Bytes |
|---|---|---|
| `IBMPlexMono-Medium.woff2` | `33faf307fa6031fb4062276d7320a6d632de890cbb347576fd80cfa01077bc25` | 50,400 |
| `IBMPlexMono-Regular.woff2` | `ba204497f16b6d334cee9d1e963a831b73e3a56e1d6300a8489d18df7214b350` | 49,248 |
| `IBMPlexSans-Medium.woff2` | `5660f8a658f8bb50dbc005232f885eadffd2bc1c235c4f6fbb63469d1f9cde6d` | 66,740 |
| `IBMPlexSans-Regular.woff2` | `ba711a3085ff9f27440b6b9c4550cfc47c97bf36591d5da958b975bb3add8c1a` | 63,020 |
| `IBMPlexSans-SemiBold.woff2` | `f78048030eab62e860efa39a0df79e2e5581bf122eb95b9bc42c0b8a4988d205` | 67,060 |
| `OFL.txt` | `7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da` | 4,456 |
