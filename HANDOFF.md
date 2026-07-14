# elksbulletin — project handoff (paste this into a new thread)

**What this is:** an Odoo 19 module that builds a **print-ready lodge newsletter**
(Grand Lodge house style) using a **drag-and-drop block editor**, then outputs a
page-sized PDF (US Letter / Legal) via WeasyPrint. It does NOT send email.

**Repo:** `github.com/LeoricCryotek/elksbulletin`
**Local working copy:** `~/Documents/GitHub/elksbulletin`
**Local Odoo 19 source (read-only ref):** `~/Documents/odoo/odoo19`
**Companion modules live in:** `~/Documents/Cluade_odoo/clms` (elksfrs, elkscontacts, …)

---

## Live deployment (Lewiston Elks #896)

- **Server:** `root@vultr`, module at
  `/var/odoo/lewistonelks896.com/extra-addons/elksbulletin`
- **Service (systemd):** `odona-lewistonelks896.com`
- **Runtime:** Python 3.13, WeasyPrint 69.0
- **Redeploy sequence** (from the module dir on the server):
  ```bash
  git pull
  # XML/SCSS/CSV-only change → Apps > Upgrade button is enough
  # PYTHON change → MUST restart the workers (Upgrade button/-u do NOT reload .py):
  find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
  systemctl restart odona-lewistonelks896.com
  ```
  **This is the #1 gotcha:** the Apps *Upgrade* button and `-u … --stop-after-init`
  re-run the module's XML/data against the *already-running* workers; only a full
  `systemctl restart` loads changed Python.

## Key decisions (already made — don't re-litigate)

- **Editor = the mass_mailing "email designer"** (drag-drop blocks like Email
  Marketing, but never sent). Field trio on the issue: `body_arch` (edited),
  `body_html` (email-inlined output the widget maintains), `mailing_model_id`
  (read by the widget, defaulted to `res.partner`, vestigial). Depends on
  **`mass_mailing`**.
- **Print from `body_arch`, not `body_html`.** The email inliner locks a narrow
  mailing width and mangles the free-form grid; printing the clean `body_arch`
  (plus grid CSS re-declared in the report) is what fixed the half-width output.
- **Snippets register** by inheriting `mass_mailing.email_designer_snippets`.
  Each snippet is a `<template>` whose root `<section>` has class
  `o_mail_snippet_general`. Side effect: Lodge blocks also appear in the Email
  Marketing designer (shared template) — accepted for now.
- **Styling is inline** on snippet markup so it survives into the print body.
  Masthead banner palette: `#8f78bd` (banner) with a purple gradient, deep
  `#3f2566` accents, gold `#c9a227`, pale `#e9e1f5`.
- **FRS integration:** reads singleton **`elks.lodge.settings`** (module
  `elksfrs`) via related fields: `lodge_charter_date`, `logo_lodge`,
  `logo_lodge_bw`, `lodge_building_entry`, `lodge_website`, `name`,
  `lodge_number`, `lodge_city`, `lodge_state`. **Masthead numbering:**
  Volume = years since charter (`relativedelta(issue, charter).years or 1`),
  No. = issue month. Lewiston #896 charter = **Feb 1, 1906** → 2026 issue is
  **Volume 120**.
- **Fonts are BUNDLED, not system-installed**, so print is identical on any
  server: masthead script = **Great Vibes** (`static/fonts/GreatVibes-Regular.ttf`),
  emoji = **monochrome Noto Emoji**. Both are `@font-face`'d in the report and
  served by the report's WeasyPrint `url_fetcher` (off disk, or from an
  ir.attachment when the module dir is root-owned). See "Emoji" below.

## Current state (built + compiles clean)

**Models**
- `models/elks_bulletin_issue.py` — `elks.bulletin.issue` (mail.thread). Fields:
  name, issue_date, page_size, template_id, state, body trio, new-member block
  settings, FRS related fields, computed volume/issue_number/issue_ref/
  charter_missing/city_state. Actions: print/preview PDF, mark final/reset.
  **Render-time resolver** `_render_print_body()` (guarded) fills dynamic blocks
  + masthead + officer bylines, bakes Style-panel borders to literal CSS,
  hoists page breaks out of the inliner table, re-grids the layout, and wraps
  emoji onto the bundled font. All built HTML escaped via `_e()`.
- `models/ir_actions_report.py` — inherits `ir.actions.report`; renders the
  bulletin reports with **WeasyPrint** (real paged media: `@page`, page numbers,
  `break-inside: avoid`, per-block width, continuation bars). Custom
  `url_fetcher` serves bundled static assets + editor images. Emoji-font
  auto-installer (`_elks_ensure_emoji_font`). Falls back to wkhtmltopdf only if
  WeasyPrint isn't importable; a system param `elksbulletin.pdf_engine` can force
  wkhtmltopdf for A/B diagnosis, and every render logs which engine ran.
- `models/elks_bulletin_template.py` — `elks.bulletin.template` (name,
  is_default, body trio). New issues copy the default template's body.

**Dynamic blocks (auto-fill at print, `data-elks-block` / class markers):**
New Members, Project Dollars (elkssecretary FY), Dues (aggregate counts),
Charity (elkscharity totals + reminder), Lodge Calendar (renders the
elks_calendar_publisher calendar), Upcoming Events (approved elksevent
project.tasks), Events (Odoo `event.event` — PUBLISHED only, teaser: title bar +
date + first line + a link to the lodge `/event` page), Officer Roster
(elks.officer.term), Message Block (officer byline auto-fill; Style-panel Officer
picker — hand-edited titles are preserved), In Memoriam (members who passed the
month before the issue, with membership tenure computed at death, a veteran flag,
and a Life/Honorary-Life-Member badge; inner-content block that drops inside a
column), plus static Masthead banner / Section Bar / Mailing Panel / layout
blocks / Page Break / Continued.

**Editor**
- `static/src/js/elks_builder_options.{js,xml}` — Style-panel Width
  (Full/⅔/½/⅓), Officer, **Spacer Height** (preset + custom px), and **Pin to
  page bottom** options; the PageBreakPreview canvas plugin.
- **Layout controls (19.0.1.8.0):** the **Spacer** block (structure list) opens
  an adjustable vertical gap; **Pin to page bottom** drops a full-width block to
  the bottom of its page. Pin is done at PRINT by
  `ir_actions_report._bulletin_insert_continuation_markers_inner`, which reuses
  the continuation two-pass render: it reads each pinned block's box geometry
  (`position_y + border_height() + margin_bottom`) and inserts an
  `.s_elks_pin_filler` div of the exact remaining height above it. The editing
  canvas draws continuous page-boundary lines + a dashed printable-area margin
  box (`newsletter_paper_canvas.scss`).
- `static/src/js/elks_editor_font.js` — adds the "Bulletin" default font to the
  Design-tab picker (and the toolbar list).
- `static/src/scss/newsletter_paper_canvas.scss` — paper-size editing canvas at
  true page width (padding matches the `@page` 0.42in margin).
- `static/src/scss/newsletter_form_backend.scss` — widens the newsletter form so
  the canvas shows full page width.
- `static/src/scss/elks_masthead_font.scss` — Great Vibes `@font-face` for the
  editor.

**Views / security / data**
- `views/*` — issue + template forms, lists, menus (scoped to the groups below).
- `security/elks_bulletin_groups.xml` — Odoo 19 `res.groups.privilege` +
  **Editor** and **Publisher** groups; `ir.model.access.csv` (Editor: no
  unlink; Publisher: full). Admin seeded into Publisher.
- `data/bulletin_template_data.xml` — branded starter template.
- `data/emoji_font_install.xml` — runs the emoji-font installer on every -u
  (loaded LAST).
- Every production file uses the **HUMAN / AI AGENT comment banner** standard.

## Emoji rendering (the long-running issue)

Emoji must print as **monochrome** glyphs. WeasyPrint's automatic fallback tends
to grab a system COLOR emoji font (`Noto-Color-Emoji`, CBDT bitmap) whose glyphs
render blank/tiny in the PDF. The fix has two halves, both in place:
1. **Bundle + serve a monochrome font.** `_elks_ensure_emoji_font` downloads Noto
   Emoji and stores it as an ir.attachment (the module dir is root-owned, so a
   file write there fails); the `url_fetcher` serves the `@font-face 'Elks Emoji'`
   request from that attachment.
2. **Pin emoji to that font.** `_wrap_emoji_fonts` wraps every emoji run at print
   in `<span style="font-family:'Elks Emoji'…">` so WeasyPrint uses the
   monochrome glyphs instead of falling back to the color font. It logs
   `elksbulletin: wrapped N emoji run(s)` on every print — **if that line is
   absent from the log, the running workers don't have this Python** (needs the
   `systemctl restart` above). Verify the embedded font with
   `pdffonts issue.pdf` — you want the monochrome NotoEmoji, NOT Noto-Color-Emoji.

If a build renders color emoji fine, drop a color font in as
`static/fonts/NotoEmoji-Regular.ttf` (same filename) — see `static/fonts/README.md`.

## Deploy (local dev)
```bash
# WeasyPrint must be in the SAME python that runs Odoo:
#   brew install pango ; <odoo-python> -m pip install weasyprint
cd ~/Documents/odoo/odoo19
python3 odoo-bin -c odoo/odoo.conf -u elksbulletin   # -u from CLI restarts
```
Edit in **Chrome** (the mass_mailing block-preview iframe hangs in Firefox).

## Open work (task board)

1. **Emoji in PDF** — code is committed (wrap + monochrome font auto-install);
   confirm it's live on the server via the `wrapped N emoji` log line after a
   full restart. If live and still color: strip the FE0F presentation selector
   and/or override the color `@font-face` so the fetcher can't reach it.
2. **Scope Lodge blocks to this editor only** (they also show in Email
   Marketing). Deferred: needs a builder filter/JS patch.
3. **Deferred cosmetics:** render speed (~50s — trim the pulled-in
   `web.report_assets_common` CSS, silence the "Odoo Unicode Support Noto"
   font warning); a theme `o_cc` colour box printing white (report strips the
   theme colour class); blank-page gaps from tall image blocks with
   `break-inside:avoid`.
4. Automated tests.

## Known review notes (best-practice backlog, non-blocking)
- `url_fetcher` `/web/image` branch runs `sudo().browse()` on ids from body HTML;
  acceptable because authors are trusted Editor/Publisher officers, and the
  `<model>/<id>/<field>` branch is now restricted to Binary fields. Allowlist
  models/fields if the trust boundary ever widens.
- Several dynamic-block strings and month names are hardcoded English (rest of
  the module uses `_()`); wrap for i18n if the lodge ever needs localisation.
- The font-download URL points at the mutable `main` branch and validates only
  "is a font"; pin to a commit / vendor the file for supply-chain safety.

## Companion modules (read-only from here; other threads own them)
- `elksfrs` — lodge settings/logo/charter/fiscal-year/building/website.
- `elkscontacts` — members (new-member/dues/veteran/deceased), `elks.officer.term`.
- `elkssecretary` — `elks.meeting.money` (Project Dollars).
- `elkscharity` — `elks.charity.contribution`.
- `elksevent` — `project.task` events; `elks_calendar_publisher` — the calendar.
