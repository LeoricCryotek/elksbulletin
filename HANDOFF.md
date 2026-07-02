# elksbulletin — project handoff (paste this into the new thread)

**What this is:** an Odoo 19 module that builds a **print-ready lodge newsletter**
(Grand Lodge house style) using a **drag-and-drop block editor**, then outputs a
page-sized document (US Letter / Legal). It does NOT send email.

**Module path:** `/Users/dannyadmin/Documents/Cluade_odoo/clms/elksbulletin`
**Local Odoo 19 source (read-only ref):** `/Users/dannyadmin/Documents/odoo/odoo19`
**Local dev DB:** runs at `localhost:8069` (ask user for the db name for `-u`).

---

## Key decisions (already made — don't re-litigate)

- **Editor = the mass_mailing "email designer"** (drag-drop blocks like Email
  Marketing, but never sent). The field widget is `mass_mailing_html`, wired on
  a **field trio**: `body_arch` (edited), `body_html` (inlined output the widget
  maintains), `mailing_model_id` (read by the widget's theme/dynamic picker —
  defaulted to `res.partner`, vestigial). Depends on module **`mass_mailing`**.
- **Snippets register** by inheriting `mass_mailing.email_designer_snippets`
  (the `snippetsName` is hardcoded in
  `addons/mass_mailing/static/src/iframe/mass_mailing_iframe.js`). Each snippet is
  a `<template>` whose root `<section>` has class `o_mail_snippet_general`.
  Side effect: our Lodge blocks also show in the Email Marketing designer
  (shared template) — accepted for now; can scope with a JS patch later.
- **Styling is inline** on snippet markup so it survives the email-inliner into
  `body_html` (used for print). Palette: purple `#5b3b8c` / deep `#3f2566` /
  gold `#c9a227` / pale `#e9e1f5`.
- **FRS integration:** reads singleton **`elks.lodge.settings`** (from module
  `elksfrs`) via related fields: `lodge_charter_date`, `logo_lodge` (masthead
  logo), `name`, `lodge_number`. **Masthead numbering:** Volume = years since
  charter (`relativedelta(issue_date, charter).years or 1`), No. = issue month.
  Lewiston #896 charter = **Feb 1, 1906** → a 2026 issue is **Volume 120**.
- **Page size** field on the issue: Letter (default) / Legal.
- **New issues copy the default template** (`elks.bulletin.template`,
  is_default) `body_arch` into the issue on create.

## Current state (built + compiles clean)

**Models**
- `models/elks_bulletin_issue.py` — `elks.bulletin.issue` (mail.thread). Fields:
  name, issue_date, page_size, template_id, state, body_arch/body_html/
  mailing_model_id, new_member_month/new_member_photos (dynamic-block settings),
  FRS related fields (lodge_name/number/logo/charter, computed city_state),
  computed volume/issue_number/issue_ref/charter_missing. Actions: print/preview
  PDF, mark final/reset. **Render-time resolver** `_render_print_body()` (guarded)
  fills dynamic blocks + masthead fields + officer bylines, flattens the email
  wrapper table, and tags the section flow. All built HTML is escaped via `_e()`.
- `models/ir_actions_report.py` — inherits `ir.actions.report`; renders the two
  bulletin reports with **WeasyPrint** (real CSS paged media: `@page`, page
  numbers, `break-inside: avoid`, per-block width). Falls back to wkhtmltopdf
  only if WeasyPrint isn't installed (errors surface, not silently masked).
- `models/elks_bulletin_template.py` — `elks.bulletin.template` (name, is_default,
  body trio). New issues copy the default template's body.

**Dynamic blocks (auto-fill at print, `data-elks-block` / class markers):**
New Members (name/age/init/vet flag), Project Dollars (FRS FY from elkssecretary),
Dues (aggregate counts), Charity (elkscharity totals + reminder), Lodge Calendar
(renders the elks_calendar_publisher calendar, scaled to fit), Upcoming Events
(approved elksevent project.tasks), Events (Odoo event.event), Officer Roster
(elks.officer.term), Message Block (officer byline auto-fill; Style-panel Officer
picker), plus static Masthead / Section Bar / In Memoriam / Mailing Panel /
layout blocks / Page Break / Continued.

**Editor**
- `static/src/js/elks_builder_options.js` + `.xml` — Style-panel options: Width
  (Full/⅔/½/⅓ via `o_elks_w_*` classes) and Officer (via `o_elks_officer_*`).
- `static/src/scss/newsletter_paper_canvas.scss` — paper-size editing canvas +
  printable-area overlay + width classes (loaded in the mass_mailing iframe).
- `static/src/img/snippets_thumbs/*.svg` — block icons.

**Views / security / data**
- `views/*` — issue + template forms, lists, menus (scoped to the groups below).
- `security/elks_bulletin_groups.xml` — **Editor** and **Publisher** groups;
  `ir.model.access.csv` (Editor: no delete; Publisher: full).
- `data/bulletin_template_data.xml` — branded starter template.
- Every production file uses the **HUMAN / AI AGENT comment banner** standard.

## Deploy (local dev)
```
# WeasyPrint must be installed in the SAME python that runs Odoo:
#   brew install pango ; <odoo-python> -m pip install weasyprint
cd /Users/dannyadmin/Documents/odoo/odoo19
python3 odoo-bin -c odoo/odoo.conf -u elksbulletin
```
Python changes need a **process restart** (`-u` from the CLI restarts); XML/SCSS-
only changes can use the Apps > Upgrade button. Editing is done in **Chrome**
(the mass_mailing editor's block-preview iframe hangs in Firefox).

## Open work (task board)

1. **Free-form grid layout** (chosen next): enable Odoo's html_builder `gridLayout`
   in the newsletter by registering a `LayoutOption`-named option on the layout
   blocks, injecting the grid CSS into the editor iframe + WeasyPrint report, and
   printing from `body_arch` (raw grid markup) instead of the email-inlined
   `body_html`. Large, editor-JS heavy, only testable live in Chrome.
2. **Scope Lodge blocks to this editor only** (they also show in Email Marketing).
   Deferred: a separate snippet set collides in the builder; needs a filter/patch.
3. Automated tests.

## Companion modules (read-only from here; other threads own them)
- `elksfrs` — lodge settings/logo/charter/fiscal-year.
- `elkscontacts` — members (new-member/dues/veteran), `elks.officer.term`.
- `elkssecretary` — `elks.meeting.money` (Project Dollars).
- `elkscharity` — `elks.charity.contribution`.
- `elksevent` — `project.task` events; `elks_calendar_publisher` — the calendar.
- Note: a `%(xmlid)d`-in-context bug in elksevent's actions was fixed here (it
  broke the web client in Odoo 19).
