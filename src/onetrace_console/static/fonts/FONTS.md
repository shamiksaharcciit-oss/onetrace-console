# The console's fonts: IBM Plex, bundled

The console serves these files itself, at `/static/fonts/<name>`; no page loads
a font from another host. The free viewer file uses system fonts instead.

**Upstream releases** (npm), each tarball checked against the registry's own sha512 integrity before
anything was taken from it:

| Package | Version | Integrity |
|---|---|---|
| `@ibm/plex-sans` 1.1.0 | 1.1.0 | `sha512-WPgvO6Yfj2w5YbhyAr1tv95RUz4LRJlqN+CmYvBglabXteufP1D1E9BABMde+ZIKdRbFJDoKF5eQzfhpnbgZcQ==` |
| `@ibm/plex-mono` 2.5.0 | 2.5.0 | `sha512-STBJIPxPomOYPmBMO7z5TKPJUotAF9u3gAUumTqVgwgrAO+K4FRNh0MlhsoJjKhJKsMbBJR10/bk4inkj/wc1w==` |

Taken from each package's `fonts/split/woff2/`, IBM Plex's own split of each weight into character
sets: for Sans Regular, Medium and SemiBold (400, 500, 600) and Mono Regular and Medium (400, 500),
the `Latin1` file and the `Pi` file (arrows and other symbols). Every character the console's own
words use is in one of the two: the Latin1 files hold all but `→` (U+2192), which the Pi files hold.
A record's own words in other scripts are drawn in the reader's system font, character by character.
`OFL.txt` is the packages' `LICENSE.txt` (identical in both): the SIL Open Font License, Version 1.1,
Copyright 2017 IBM Corp., Reserved Font Name "Plex".

Until 0.2.0 the console shipped each package's `fonts/complete/woff2/` files, one per weight:
296,468 bytes for the five. These ten files are 151,456 bytes.

**Files**, sha256 written by tooling (`tests/test_fonts.py` pins the same values):

| File | In the package | sha256 | Bytes |
|---|---|---|---|
| `IBMPlexMono-Medium-Latin1.woff2` | `fonts/split/woff2/IBMPlexMono-Medium-Latin1.woff2` | `41201b658a328b9d00368215c2f1102770f80b15952ab82631e4006255e6365d` | 17,868 |
| `IBMPlexMono-Medium-Pi.woff2` | `fonts/split/woff2/IBMPlexMono-Medium-Pi.woff2` | `92bd18415e8c43a2569f615e4e84a94b1b1c4e0377ba9d8f4d894bbf6ffcc39d` | 13,968 |
| `IBMPlexMono-Regular-Latin1.woff2` | `fonts/split/woff2/IBMPlexMono-Regular-Latin1.woff2` | `e8993d946649b9d01abb1ed06d574b19d8ea3e66b5c3948602db335c44c18e56` | 17,544 |
| `IBMPlexMono-Regular-Pi.woff2` | `fonts/split/woff2/IBMPlexMono-Regular-Pi.woff2` | `b8002770aa636f544ba43e124da6a227301769754f295eae26e16475b469c767` | 13,780 |
| `IBMPlexSans-Medium-Latin1.woff2` | `fonts/split/woff2/IBMPlexSans-Medium-Latin1.woff2` | `b5610af04d0d4b5a14a621d96d974b993e945a065db1a8861918f69ef9321934` | 21,960 |
| `IBMPlexSans-Medium-Pi.woff2` | `fonts/split/woff2/IBMPlexSans-Medium-Pi.woff2` | `bf05f10c977353cfb5a5c11e8973adf77c2b93a4798da3aa0dd8ba5088e12515` | 7,768 |
| `IBMPlexSans-Regular-Latin1.woff2` | `fonts/split/woff2/IBMPlexSans-Regular-Latin1.woff2` | `b5ad7bd39f996144915f0ad9849a90183b27d8c28ad97ed98af5b1bebc51f6b1` | 20,984 |
| `IBMPlexSans-Regular-Pi.woff2` | `fonts/split/woff2/IBMPlexSans-Regular-Pi.woff2` | `1487059829a180f975627e473acc81ff22c2c0faf1da09b314c27eeb41b7f2e4` | 7,500 |
| `IBMPlexSans-SemiBold-Latin1.woff2` | `fonts/split/woff2/IBMPlexSans-SemiBold-Latin1.woff2` | `fff0ab3a88b0b4aa0b693e4f0201359a15183b08e3fa5696d1918d8f0ade8ad5` | 22,260 |
| `IBMPlexSans-SemiBold-Pi.woff2` | `fonts/split/woff2/IBMPlexSans-SemiBold-Pi.woff2` | `768421433d850d3a30118dddf05972625d99ee49bc32c5a8fd26bbe020c4d0f9` | 7,824 |
| `OFL.txt` | `LICENSE.txt` | `7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da` | 4,456 |

**Characters each file holds**, as the stylesheet's `unicode-range` names them, read from each file's
own character map with fontTools 4.55.3 (a tool run once, not shipped):

| File | Face | unicode-range |
|---|---|---|
| `IBMPlexMono-Medium-Latin1.woff2` | IBM Plex Mono 500 | `U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2013-2014,U+2018-201A,U+201C-201E,U+2020-2022,U+2026,U+2030,U+2039-203A,U+2044,U+20AC,U+2122,U+2212,U+FB01-FB02` |
| `IBMPlexMono-Medium-Pi.woff2` | IBM Plex Mono 500 | `U+03C0,U+0E3F,U+2000-200D,U+2010-2012,U+2015,U+2028-2029,U+202F,U+2032-2033,U+203E,U+205F,U+2070,U+2074-2079,U+2080-2089,U+2113,U+2116,U+2126,U+212E,U+2150-2151,U+2153-215E,U+2190-2199,U+21A9-21AA,U+21B0-21B3,U+21B6-21B7,U+21BA-21BB,U+21C4,U+21C6,U+2202,U+2206,U+220F,U+2211,U+2215,U+2219-221A,U+221E,U+222B,U+2236,U+2248,U+2260,U+2264-2265,U+2400-2421,U+2500-259F,U+25CA,U+2713,U+274C,U+2B0E-2B11,U+3000,U+FEFF,U+FFFD` |
| `IBMPlexMono-Regular-Latin1.woff2` | IBM Plex Mono 400 | `U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2013-2014,U+2018-201A,U+201C-201E,U+2020-2022,U+2026,U+2030,U+2039-203A,U+2044,U+20AC,U+2122,U+2212,U+FB01-FB02` |
| `IBMPlexMono-Regular-Pi.woff2` | IBM Plex Mono 400 | `U+03C0,U+0E3F,U+2000-200D,U+2010-2012,U+2015,U+2028-2029,U+202F,U+2032-2033,U+203E,U+205F,U+2070,U+2074-2079,U+2080-2089,U+2113,U+2116,U+2126,U+212E,U+2150-2151,U+2153-215E,U+2190-2199,U+21A9-21AA,U+21B0-21B3,U+21B6-21B7,U+21BA-21BB,U+21C4,U+21C6,U+2202,U+2206,U+220F,U+2211,U+2215,U+2219-221A,U+221E,U+222B,U+2236,U+2248,U+2260,U+2264-2265,U+2400-2421,U+2500-259F,U+25CA,U+2713,U+274C,U+2B0E-2B11,U+3000,U+FEFF,U+FFFD` |
| `IBMPlexSans-Medium-Latin1.woff2` | IBM Plex Sans 500 | `U+0000,U+000D,U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2013-2014,U+2018-201A,U+201C-201E,U+2020-2022,U+2026,U+2030,U+2039-203A,U+2044,U+20AC,U+2122,U+2212,U+FB01-FB02` |
| `IBMPlexSans-Medium-Pi.woff2` | IBM Plex Sans 500 | `U+0E3F,U+2000-200D,U+2015,U+2028-2029,U+202F,U+2032-2033,U+2070,U+2074-2079,U+2080-2089,U+2113,U+2116,U+2126,U+212E,U+2150-2151,U+2153-215E,U+2190-2199,U+21A9-21AA,U+21B0-21B3,U+21B6-21B7,U+21BA-21BB,U+21C4,U+21C6,U+2202,U+2206,U+220F,U+2211,U+2215,U+221A,U+221E,U+222B,U+2248,U+2260,U+2264-2265,U+25CA,U+2713,U+274C,U+2B0E-2B11,U+ECE0,U+EFCC,U+FEFF,U+FFFD` |
| `IBMPlexSans-Regular-Latin1.woff2` | IBM Plex Sans 400 | `U+0000,U+000D,U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2013-2014,U+2018-201A,U+201C-201E,U+2020-2022,U+2026,U+2030,U+2039-203A,U+2044,U+20AC,U+2122,U+2212,U+FB01-FB02` |
| `IBMPlexSans-Regular-Pi.woff2` | IBM Plex Sans 400 | `U+0E3F,U+2000-200D,U+2015,U+2028-2029,U+202F,U+2032-2033,U+2070,U+2074-2079,U+2080-2089,U+2113,U+2116,U+2126,U+212E,U+2150-2151,U+2153-215E,U+2190-2199,U+21A9-21AA,U+21B0-21B3,U+21B6-21B7,U+21BA-21BB,U+21C4,U+21C6,U+2202,U+2206,U+220F,U+2211,U+2215,U+221A,U+221E,U+222B,U+2248,U+2260,U+2264-2265,U+25CA,U+2713,U+274C,U+2B0E-2B11,U+ECE0,U+EFCC,U+FEFF,U+FFFD` |
| `IBMPlexSans-SemiBold-Latin1.woff2` | IBM Plex Sans 600 | `U+0000,U+000D,U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2013-2014,U+2018-201A,U+201C-201E,U+2020-2022,U+2026,U+2030,U+2039-203A,U+2044,U+20AC,U+2122,U+2212,U+FB01-FB02` |
| `IBMPlexSans-SemiBold-Pi.woff2` | IBM Plex Sans 600 | `U+0E3F,U+2000-200D,U+2015,U+2028-2029,U+202F,U+2032-2033,U+2070,U+2074-2079,U+2080-2089,U+2113,U+2116,U+2126,U+212E,U+2150-2151,U+2153-215E,U+2190-2199,U+21A9-21AA,U+21B0-21B3,U+21B6-21B7,U+21BA-21BB,U+21C4,U+21C6,U+2202,U+2206,U+220F,U+2211,U+2215,U+221A,U+221E,U+222B,U+2248,U+2260,U+2264-2265,U+25CA,U+2713,U+274C,U+2B0E-2B11,U+ECE0,U+EFCC,U+FEFF,U+FFFD` |
