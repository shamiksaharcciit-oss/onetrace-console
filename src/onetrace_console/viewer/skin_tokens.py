"""The onetrace Console Skin v1's token block, byte for byte, held in a module of its own (console 0.8.0):
every colour, size and space the pages use, named once. `tokens.css_block()` checks this block's sha256
before it is used.
"""

BLOCK = """:root{
  --page:#f5f6f8; --surface:#ffffff; --surface-sunk:#fbfcfd; --surface-alt:#f9fafb;
  --ink:#16202e; --ink-soft:#3a4556; --ink-muted:#4a5566; --ink-faint:#667185;
  --line:#dde2ea; --line-soft:#eef1f5; --line-node:#c9d0db; --line-strong:#8a96a8;
  --accent:#1f3a5f; --accent-ink:#ffffff;
  --nav-bg:#0f1b2d; --nav-ink:#c9d3e0; --nav-ink-faint:#8fa0b8; --nav-on-bg:#1f3a5f; --nav-on-ink:#ffffff;
  --ok-bg:#e6f4ea;  --ok-ink:#17663a;
  --cc-bg:#fdf3dc;  --cc-ink:#7a4f00;  --hl:#fdf3dc;
  --bad-bg:#fdeaea; --bad-ink:#a4161a;
  --neu-bg:#eef1f5; --neu-ink:#3a4556;
  --font-sans:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif;
  --font-mono:'IBM Plex Mono',ui-monospace,'Cascadia Mono',Consolas,monospace;
  --fs-small:12px; --fs-body:13px; --fs-nav:14px; --fs-h1:26px; --fs-kpi:30px;
  --r-card:8px; --r-ctl:6px; --r-pill:4px; --r-num:13px;
  --nav-width:232px;
}
"""
