# -*- coding: utf-8 -*-
# =============================================================================
# === HUMAN ===
# The module label: name/version, the apps it needs, and the ordered list of
# data files. This module is the Lodge Newsletter builder — a drag-and-drop,
# print-ready bulletin styled after the Grand Lodge newsletter. The description
# below is what members see on the Apps page, including the version history.
#
# === AI AGENT ===
# Standard Odoo 19 manifest. depends: mass_mailing (provides the "email
# designer" drag-drop block builder — the mass_mailing_html field widget and
# its snippet/theme assets; we reuse it to build the newsletter but never send
# it), mail (chatter), elksfrs (elks.lodge.settings: charter date + lodge logo
# for the masthead), and the lodge data modules feeding the dynamic blocks.
# 'data' order: security before views; seed template data before the views
# that reference it. Assets: two bundles —
#   * mass_mailing.assets_inside_builder_iframe (SCSS only): paper-sheet
#     canvas, side rulers, page-boundary lines.
#   * mass_mailing.assets_builder (JS/XML): Style-panel Width + Officer
#     options and the PageBreakPreview plugin (canvas page-turn spacers).
# WeasyPrint is a SOFT runtime dependency (see models/ir_actions_report.py),
# deliberately NOT in external_dependencies so install never blocks on it.
# Python/JS changes need a server restart; XML data needs -u elksbulletin.
# =============================================================================
{
    "name": "Elks Bulletin — Lodge Newsletter Builder",
    "version": "19.0.1.5.0",
    "category": "Marketing",
    "summary": "Drag-and-drop, print-ready lodge newsletter in Grand Lodge style.",
    "description": """
Elks Bulletin — v19.0.1.2.0
===========================
A lodge newsletter builder that works like Odoo's email-marketing editor
(a side panel of drag-in content blocks) but produces a print-ready,
page-sized document (US Letter / Legal) instead of an email.

Features
--------
* Content blocks (snippets) with per-block column size (1/3, 2/3, 3/3) and
  framing (box / no box), plus a Style-panel Officer picker for Message Blocks.
* Dynamic blocks that auto-update from lodge data at print time: New Members
  (with optional contact-photo mode), Lodge Calendar (renders the published
  website calendar), Project Dollars, Dues Reminder, Charity Report, Upcoming
  Events, Events, Lodge Officers, In Memoriam (members who passed in the
  month before the issue).
* Member Photo Grid: hand-editable photo cards for photos emailed to the
  editor (never overwritten at print).
* Grand-Lodge-style masthead banner pulling the lodge name, B&W logo,
  building photo and website URL from the FRS module (``elks.lodge.settings``)
  — Volume = years since charter, No. = issue month.
* Page Break blocks — Full Width (between sections) and Inline (mid-story) —
  hoisted out of the email-inliner's table markup at print so both PDF
  engines honor them.
* Auto "Continued on page #" / "(Continued from page #)" bars inserted at the
  real page boundary (WeasyPrint two-pass layout detection), plus a manual
  Continued bar for one-off placement.
* Compact "Grand Lodge" print typography (measured from the GL newsletter:
  ~11pt body on tight leading) for newspaper-density output.
* Editing canvas framed as a true paper sheet with side rulers, page-boundary
  guides, and live page-turn preview at forced breaks.
* PDF via WeasyPrint when installed (page-number footer, real paged-media
  CSS); graceful wkhtmltopdf fallback otherwise.

Version history
---------------
19.0.1.5.0 — Masthead title now prints exactly what the editor holds (no longer
overwritten by the FRS lodge name) and uses a BUNDLED elegant script font
(Great Vibes, static/fonts) @font-face'd in both the editor and the report, so
the printed masthead matches the screen regardless of server-installed fonts.
Footer names the lodge from FRS (elks.lodge.settings.name) without duplicating
the number. Bullet/numbered list markers are re-declared for WeasyPrint (they
had vanished when printing the un-inlined body). Font Awesome is imported from
both known Odoo paths so icons load whichever this build serves. (Lodge Calendar
that renders blank with KeyError: 'top' means elks_calendar_publisher is stale
on the server — upgrade it so its template matches the grid builder. Calendar
emoji need a system emoji font: apt install fonts-noto-color-emoji.)

19.0.1.2.0 — Masthead rebuilt as a Grand-Lodge-style banner (date | website |
volume top bar; B&W lodge logo, script lodge name + NEWSLETTER, lodge building
photo; "Elks Care - Elks Share"), all dynamic from FRS (logo_lodge_bw,
lodge_building_entry, lodge_website). In Memoriam is now dynamic — members
flagged deceased whose Date of Death falls in the calendar month before the
issue. PDF now prints from body_arch (clean markup) instead of the email-inlined
body_html, fixing the ~half-page-width output (the email inliner locked a narrow
mailing width); report stylesheet gained a light flex grid so Bootstrap columns
still sit side by side at full page width. "Bulletin" newsletter font added to
the Design-tab font picker (and the text toolbar) and set as the default face;
body text uses a literal 5px between-line leading (calc(1em + 5px)) kept
identical in the editor and the PDF. Content and inner blocks ship frameless
(no baked-in border) — add framing via the Style panel. Print fidelity fixes:
Style-panel Round Corners now render in the PDF (the --box-border-radius
variable is re-applied in the report); the print grid covers every Bootstrap
breakpoint (col-/sm/md/lg/xl/xxl) so image/ad Columns stay side by side at
their set size instead of collapsing full-width; and the Lodge Calendar's Font
Awesome event icons render (the bundled FA stylesheet + font are pulled into
the report and served off disk by the url_fetcher). Unicode emoji in the
calendar still require a system emoji font on the Odoo server. Fixed content
dropping out of the PDF: free-form grid blocks (.o_grid_mode) are now rendered
as a real CSS grid in print (core only enables the grid at >=lg screen width,
so on paper the items had collapsed) and the print column widths are ordered by
breakpoint so "col-md-x col-12" columns no longer all fall to full width and
drop; uploaded / related images (the /web/image/<id>-<unique> URL form, e.g.
the banner logo) are now fetched off disk too; the banner carries a solid
background-color fallback for WeasyPrint builds without CSS-gradient support.
Style-panel border WIDTH (px) now prints (like Round Corners, it is written as
a --box-border-* CSS variable that an editor-only stylesheet used to apply;
re-applied in the report). Border style/colour already print (written inline).
Calendar theme icons: Font Awesome event graphics render via the bundled FA
stylesheet; Unicode emoji banner symbols + the seasonal header strip still need
a system emoji font on the Odoo server (fonts-noto-color-emoji, or fonts-symbola
for monochrome). Editor now shows the canvas at true page width: the newsletter
form is widened (web.assets_backend) and the canvas padding matches the print
@page margin (0.42in), so text wraps in the editor where it wraps in the PDF.
In Memoriam is now an inner-content block (drops inside a column) and lists
multiple names in a compact self-wrapping row instead of a tall stack. PDF
engine is selectable for diagnosis via the system parameter
elksbulletin.pdf_engine ("wkhtmltopdf" to force the legacy engine); every
newsletter print logs which engine actually rendered it. Style-panel borders
are now baked to LITERAL inline CSS at print (the --box-border-* variables are
resolved to real border-width/border-radius/border-style), so rounded corners
and widths print on BOTH WeasyPrint and wkhtmltopdf instead of relying on
var(). Officer's Message title only auto-fills when left at the default — any
edit now prints verbatim. In Memoriam entries show membership tenure (computed
at death), a veteran flag, and a Life-Member / Honorary-Life-Member badge. The
Events block (event.event) is now a teaser — PUBLISHED upcoming events only,
showing the title in a bar + date + the first line of the description, plus one
notice linking the lodge website's /event page (FRS lodge_website) instead of
printing the whole event page.

19.0.1.1.0 — Page breaks hoisted out of inliner tables (works in both PDF
engines); inline Page Break variant; auto continuation markers; compact GL
print density; Member Photo Grid; row-grouping so side-by-side blocks never
split across pages; canvas rulers + page-turn preview; hand-edited Message
titles preserved; WeasyPrint soft-dependency hardened (macOS OSError no
longer blocks server start).

19.0.1.0.0 — Initial release: block-based editor, dynamic lodge blocks,
FRS-driven masthead, Letter/Legal PDF export.
""",
    "author": "Danny Santiago",
    "website": "https://dannysantiago.info",
    "license": "LGPL-3",
    "depends": [
        "mass_mailing",
        "mail",
        "elksfrs",        # lodge settings: logo, charter, fiscal-year start
        "elkscontacts",   # members: new-member + delinquent-dues blocks
        "elkssecretary",  # meeting money: Project Dollars totals
        "elkscharity",    # charity contributions: charity-report totals
        "elksevent",      # project.task events: Upcoming Events (approved)
        "calendar",       # calendar.event: Lodge Calendar fallback source
        "elks_calendar_publisher",  # Lodge Calendar block = the published calendar
        "event",          # event.event: Events block (Odoo Events app)
    ],
    "data": [
        "security/elks_bulletin_groups.xml",
        "security/ir.model.access.csv",
        "data/bulletin_template_data.xml",
        "report/elks_bulletin_report.xml",
        "views/snippets/elks_bulletin_snippets.xml",
        "views/elks_bulletin_views.xml",
        "views/elks_bulletin_menus.xml",
    ],
    "assets": {
        # Backend (web client, OUTSIDE the builder iframe): widen the newsletter
        # editor form so the canvas can show true page width, matching print.
        "web.assets_backend": [
            "elksbulletin/static/src/scss/newsletter_form_backend.scss",
            "elksbulletin/static/src/scss/elks_masthead_font.scss",
        ],
        # Paper-size editing canvas: frames the newsletter content at true page
        # width inside the mass_mailing editing iframe. Scoped to .o_elksbulletin
        # so only this module's editor is affected.
        "mass_mailing.assets_inside_builder_iframe": [
            "elksbulletin/static/src/scss/newsletter_paper_canvas.scss",
            "elksbulletin/static/src/scss/elks_masthead_font.scss",
        ],
        # Style-panel option controls (Width + Officer) for Lodge blocks, the
        # PageBreakPreview plugin, and the "Bulletin" font-dropdown entry.
        "mass_mailing.assets_builder": [
            "elksbulletin/static/src/js/elks_builder_options.js",
            "elksbulletin/static/src/js/elks_builder_options.xml",
            "elksbulletin/static/src/js/elks_editor_font.js",
        ],
    },
    "installable": True,
    "application": True,
}
