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

- `models/elks_bulletin_issue.py` — `elks.bulletin.issue` (mail.thread): name,
  issue_date, page_size, template_id, state, body_arch/body_html/mailing_model_id,
  FRS related fields, computed volume/issue_number/issue_ref/charter_missing,
  create() template-copy, action_mark_final/reset_draft.
- `models/elks_bulletin_template.py` — `elks.bulletin.template` (name, is_default,
  same body trio).
- `data/bulletin_template_data.xml` — seeds default "Lodge Newsletter" template.
- `views/snippets/elks_bulletin_snippets.xml` — **8 Lodge blocks** in a new
  "Lodge" category: Masthead, Section Bar, Exalted Ruler Message (2/3+1/3),
  In Memoriam, Lodge Officers, Two-Thirds+One-Third, Three Columns, Continued.
- `views/elks_bulletin_views.xml` — issue + template forms (mass_mailing_html
  editor), lists, actions. `views/elks_bulletin_menus.xml` — Newsletter app menu.
- `security/ir.model.access.csv`, `static/description/icon.png` (+ icon.svg).
- Every file uses the **HUMAN / AI AGENT comment banner** standard.

## Deploy (local dev)
```
cd /Users/dannyadmin/Documents/odoo/odoo19
python3 odoo-bin -d <your_db> -u elksbulletin --stop-after-init
```
then restart the server. (Model/view/snippet changes need `-u`; controller-only
changes just need a restart.)

## Open work (task board)

1. **Print/PDF export sized to page** (Letter/Legal) + pagination + Continue-to-
   page splitting + page-number footer + no content bleed. (The mockups
   `clms/Lodge_Newsletter_Mockup_v3.html` show the target print look.)
2. **Dynamic New Members + Calendar blocks** — auto-fill from lodge Odoo.
   **BLOCKED:** need the GitHub module folder name(s) for (1) members / new
   members and (2) events / calendar. Read-only; other threads own those modules.
3. **Builder option plugins** — per-block Style-panel toggles for size
   (1/3, 2/3, 3/3, invalid sizes disabled per block) and framing (box / no box).
   Currently shipped as fixed layout variants.
4. **Masthead auto-fill** — real `logo_lodge` + computed Volume/No. injected at
   render time (currently branded static placeholders in the snippet).
5. Optional: scope Lodge blocks to the newsletter editor only (JS patch).

## Reference mockups (in clms/)
`Lodge_Newsletter_Mockup_v3.html` (target print look), `FRS_Charter_Date_Prompt.md`
(the FRS field hand-off — already done by the elksfrs thread).

## Companion modules (other threads own these — read-only here)
- `elksfrs` — lodge settings/logo/charter (field already added).
- `elksattendance` — unrelated (attendance), also in this workspace.
