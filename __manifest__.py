# -*- coding: utf-8 -*-
# =============================================================================
# === HUMAN ===
# The module label: name/version, the apps it needs, and the ordered list of
# data files. This module is the Lodge Newsletter builder — a drag-and-drop,
# print-ready bulletin styled after the Grand Lodge newsletter.
#
# === AI AGENT ===
# Standard Odoo 19 manifest. depends: mass_mailing (provides the "email
# designer" drag-drop block builder — the mass_mailing_html field widget and
# its snippet/theme assets; we reuse it to build the newsletter but never send
# it), mail (chatter), and elksfrs (reads elks.lodge.settings for the charter
# date + lodge logo used in the masthead). 'data' order: security
# before views; seed template data before the views that reference it. The
# drag-drop snippet assets bundle is added in the editor phase.
# =============================================================================
{
    "name": "Elks Bulletin — Lodge Newsletter Builder",
    "version": "19.0.1.0.0",
    "category": "Marketing",
    "summary": "Drag-and-drop, print-ready lodge newsletter in Grand Lodge style.",
    "description": """
Elks Bulletin
=============
A lodge newsletter builder that works like Odoo's email-marketing editor
(a side panel of drag-in content blocks) but produces a print-ready,
page-sized document (US Letter / Legal) instead of an email.

* Content blocks (snippets) with per-block column size (1/3, 2/3, 3/3) and
  framing (box / no box).
* Dynamic blocks that auto-update from lodge data (New Members, Calendar,
  Exalted Ruler's message, In Memoriam).
* Masthead pulls the lodge logo and charter date from the FRS module
  (``elks.lodge.settings``) — Volume = years since charter, No. = issue month.
* Continue-to-page control flows long sections onto later pages.
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
        # Paper-size editing canvas: frames the newsletter content at true page
        # width inside the mass_mailing editing iframe. Scoped to .o_elksbulletin
        # so only this module's editor is affected.
        "mass_mailing.assets_inside_builder_iframe": [
            "elksbulletin/static/src/scss/newsletter_paper_canvas.scss",
        ],
        # Style-panel option controls (Width + Officer) for Lodge blocks.
        "mass_mailing.assets_builder": [
            "elksbulletin/static/src/js/elks_builder_options.js",
            "elksbulletin/static/src/js/elks_builder_options.xml",
        ],
    },
    "installable": True,
    "application": True,
}
