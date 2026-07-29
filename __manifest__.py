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
    "version": "19.0.1.16.0",
    "category": "Marketing",
    "summary": "Drag-and-drop, print-ready lodge newsletter in Grand Lodge style.",
    "description": """
Elks Bulletin — v19.0.1.16.0
============================
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
* Layout controls: a Spacer block (preset or custom px height) to open vertical
  space, and a "Pin to page bottom" toggle that drops a block (e.g. the Calendar)
  to the bottom of the page it lands on, measured at print by the two-pass layout.
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
19.0.1.16.0 — The editor masthead now tracks the Issue Date. Changing the date
rewrites the date-driven masthead markers (month + "Volume X, No. Y", plus
city/state and lodge number) right in the editing canvas, so it stops showing the
month the template was originally built for — no need to Preview to see the right
month. Only text markers change; images and the editor-owned lodge title are left
alone, and the markers are preserved so Print/Preview still re-resolves them.

19.0.1.15.0 — Templates apply after create. Previously a template only populated
an issue at create time, so picking a template on an existing (blank) issue did
nothing. Now: choosing a template auto-loads its content WHEN the newsletter is
still empty (never clobbers an issue you've already built), and a new "Load
Template" button (with a confirm) fills/resets an issue from the selected template
on demand. Empty detection ignores whitespace / empty wrapper tags.

19.0.1.14.0 — Fix: the Calendar/Leaderboard "Month shown" setting had no effect.
The Style-panel option writes its class/attribute onto the snippet ROOT, but the
resolver handed the builder the inner data-elks-block element, which didn't carry
it — so the setting was silently ignored (also affected the Leaderboard month +
"Stack boards"). The month/flag lookups now walk up through ancestors to find the
setting. Simplified the "Month shown" choices to Issue month / Next month / Last
month (dropped "Two months back") on both blocks.

19.0.1.13.0 — The Lodge Calendar now has the same Style-panel "Month shown"
control as the Leaderboard: pick Issue month / Previous / Two months back / Next
(a relative offset that tracks the issue date), or type an exact YYYY-MM — so you
can send the newsletter out early and still show next month's calendar. The
month-offset helper is now shared by both blocks (_block_ref_date), each with its
own independent setting.

19.0.1.12.0 — Fast "Preview (data)" button. Opens the newsletter as a plain HTML
page with every dynamic block filled from real lodge data in a fraction of a
second — no PDF, no WeasyPrint — so you can check the data while editing and just
refresh after changes. Served by a new GET /elksbulletin/preview/<id> controller
(auth=user, check_access("read")) that renders the SAME QWeb report as HTML via
_render_qweb_html, so it's a faithful data preview (only true page breaks /
continuation bars differ, since those need the PDF engine). The existing Preview
PDF / Print buttons are unchanged.

19.0.1.11.0 — In Memoriam now prints each member's date of death under their name
(full month, e.g. "January 5, 2026"), from x_date_of_death on the member record,
above the existing membership-tenure / Life-Member line.

19.0.1.10.0 — Leaderboard layout + month controls. The Volunteer Leaderboard now
has a Style-panel "Month shown" picker (Issue month / Previous / Two months back
/ Next — a relative offset that tracks the issue date each month) plus an exact
"YYYY-MM" override for one-off months, so you can prepare next month's issue and
feature the right month. A new FULL-WIDTH Leaderboard section block spans the
whole page (alongside the existing drop-in-a-column version), and a "Stack boards"
toggle switches the two boards (This Month / This Lodge Year) between side-by-side
and stacked full-width. The dynamic-block resolver now passes each block's element
to its builder so these per-block options can be read at print.

19.0.1.9.0 — New Volunteer Hours Leaderboard dynamic block. Ranks the Elks who
logged the most charity hours, as two boards (This Month + This Lodge Year) with
the top volunteer featured large and places 2–10 below, plus a note on our duty
to serve. Numbers come from the shared elks.charity.leaderboard model in the
Elks Charity module (all submitted hours, Elks only, current lodge year), the
same source the public website leaderboard uses — so the two never disagree.
Requires elkscharity 19.0.6.0+.

19.0.1.8.0 — Layout controls. New Spacer block: an empty, resizable vertical gap
(Style-panel Height — presets Small/Medium/Large/Extra-Large or a custom px
value, written as the section's inline height so editor and PDF match). New "Pin
to page bottom" Style-panel toggle on full-width blocks: at print the report's
existing two-pass WeasyPrint layout measures where the block lands and inserts a
filler above it so its bottom edge sits on the page's bottom margin — reusing the
continuation pass's single extra render (no added render cost). The editor canvas
now shows the Spacer (dashed outline + label) and badges a pinned block, and the
printed-page boundary line on the canvas is drawn more boldly so page ends are
easy to see while editing (the dashed printable-area margin box was already
drawn). Report CSS hides the Spacer's editor label and keeps the Spacer / pinned
block from splitting across pages.

19.0.1.7.0 — Housekeeping / best-practice pass (no behaviour change). Removed
stale compiled bytecode (__pycache__/*.pyc, including a cpython-310 build) that
was accidentally tracked in git — it never belonged in the repo and risked stale
bytecode on pull. The emoji wrapper now logs "wrapped N emoji run(s)" per print
so a live build can be confirmed from the log. Tightened the report url_fetcher:
the /web/image/<model>/<id>/<field> branch now only serves genuine Binary fields
(trust boundary documented in-code). Corrected a mis-placed method comment
(_officer_label vs _officer_byline_html). Refreshed HANDOFF.md to match the live
Vultr deployment (systemd odona-lewistonelks896.com, Python 3.13, WeasyPrint 69),
the current feature set, and the emoji/restart gotchas.

19.0.1.6.0 — Emoji printing made self-contained and reliable. The module
AUTO-INSTALLS the free monochrome Noto Emoji font on install and on every -u:
it downloads the font and stores it as an ir.attachment (the module folder is
often root-owned while Odoo runs non-root, so a file write there fails — the
filestore is always writable); the report url_fetcher serves the @font-face
'Elks Emoji' request from that attachment (or from static/fonts/ if a copy is
committed). Emoji runs are also wrapped at print in a span that NAMES that font,
so WeasyPrint draws the monochrome glyphs instead of falling back to a system
COLOR emoji font whose bitmap glyphs render blank/tiny. A system-parameter
(elksbulletin.pdf_engine) can force wkhtmltopdf for A/B diagnosis, and each
print logs which engine rendered it.

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
printing the whole event page. (Emoji font auto-install + monochrome wrapping
were finalized in 19.0.1.6.0 — see above.)

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
        "data/emoji_font_install.xml",  # LAST: self-installs the emoji font
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
