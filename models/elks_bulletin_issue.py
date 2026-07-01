# -*- coding: utf-8 -*-
# =============================================================================
# === HUMAN ===
# One newsletter issue (e.g. "Lodge Newsletter — July 2026"). It knows its page
# size (Letter or Legal), holds the drag-and-drop page content, and figures out
# the masthead's Volume / No. and the lodge logo by reading the FRS lodge
# settings. Creating a new issue starts from the default template.
#
# === AI AGENT ===
# elks.bulletin.issue (mail.thread). body_html = the editor canvas (unsanitized).
# Lodge data is pulled from elksfrs' singleton elks.lodge.settings via related
# fields (lodge_settings_id -> logo/charter/name/address). Numbering:
#   volume = relativedelta(issue_date, charter).years or 1 ; number = month.
# If the charter date isn't set in FRS, charter_missing flags a form banner.
# New records copy the default template body into body_html (create override).
# =============================================================================
import calendar as _calmod
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from lxml import html as lxml_html
from markupsafe import Markup

from odoo import api, fields, models, _

# Month selection for the "New Members" block source window.
NEW_MEMBER_MONTHS = [
    ("fy", "Fiscal Year to Date"),
    ("01", "January"), ("02", "February"), ("03", "March"),
    ("04", "April"), ("05", "May"), ("06", "June"),
    ("07", "July"), ("08", "August"), ("09", "September"),
    ("10", "October"), ("11", "November"), ("12", "December"),
]


class ElksBulletinIssue(models.Model):
    _name = "elks.bulletin.issue"
    _description = "Lodge Newsletter Issue"
    _inherit = ["mail.thread"]
    _order = "issue_date desc, id desc"

    # --- identity ---------------------------------------------------------
    name = fields.Char(required=True, default=lambda self: self._default_name(),
                       tracking=True)
    issue_date = fields.Date(
        required=True, default=fields.Date.context_today, tracking=True,
        help="Date of this issue. Drives the masthead month and No.")
    page_size = fields.Selection(
        [("letter", "US Letter — 8.5 × 11 in"),
         ("legal", "US Legal — 8.5 × 14 in")],
        default="letter", required=True,
        help="Document/print size. The canvas and PDF are sized to this.")
    template_id = fields.Many2one(
        "elks.bulletin.template", string="Template",
        default=lambda self: self._default_template())
    state = fields.Selection(
        [("draft", "Draft"), ("final", "Final")],
        default="draft", required=True, tracking=True)

    # --- the drag-and-drop canvas (mass_mailing "email designer") --------
    # body_arch is what you edit with the block builder; body_html is the
    # inlined output the widget maintains alongside it (used for rendering /
    # PDF). mailing_model_id is read by the editor's dynamic-field + theme
    # picker — the newsletter is NOT sent; this just satisfies the widget.
    body_arch = fields.Html("Newsletter", sanitize=False)
    body_html = fields.Html("Newsletter (inlined)", sanitize=False)
    mailing_model_id = fields.Many2one(
        "ir.model", string="Editor Data Model",
        default=lambda self: self.env["ir.model"]._get_id("res.partner"))

    # --- dynamic-block settings (read by the render-time resolver) --------
    # These configure the auto-filled Lodge blocks. Kept on the issue (not the
    # block) so no editor-side option JS is needed; one setting per issue.
    new_member_month = fields.Selection(
        NEW_MEMBER_MONTHS, string="New Members Source",
        default="fy",
        help="Which initiations the New Members block features: a single "
             "calendar month (of this issue's year) or all of the fiscal year.")
    new_member_photos = fields.Boolean(
        "Show New Member Photos", default=False,
        help="Include member photos in the New Members block. Looks best when "
             "the block is placed at full width (3/3).")

    # --- lodge settings (from elksfrs) -----------------------------------
    lodge_settings_id = fields.Many2one(
        "elks.lodge.settings", string="Lodge Settings",
        default=lambda self: self.env["elks.lodge.settings"].sudo().search([], limit=1),
        readonly=True)
    lodge_charter_date = fields.Date(
        related="lodge_settings_id.lodge_charter_date", readonly=True)
    lodge_logo = fields.Binary(
        related="lodge_settings_id.logo_lodge", readonly=True)
    lodge_name = fields.Char(
        related="lodge_settings_id.name", readonly=True)
    lodge_number = fields.Char(
        related="lodge_settings_id.lodge_number", readonly=True)

    # --- computed masthead numbering -------------------------------------
    # NOTE: Odoo 19 warns if one compute method feeds both stored and
    # non-stored fields (different default compute_sudo + recompute coupling).
    # So the STORED numbers and the NON-STORED display/flag use separate
    # methods; the display method depends on the stored values.
    volume = fields.Integer(compute="_compute_issue_numbers", store=True)
    issue_number = fields.Integer(compute="_compute_issue_numbers", store=True)
    issue_ref = fields.Char("Issue Ref", compute="_compute_issue_ref")
    charter_missing = fields.Boolean(compute="_compute_issue_ref")

    # ------------------------------------------------------------------
    # === HUMAN ===
    # A friendly default title based on this month, e.g. "Lodge Newsletter —
    # July 2026". You can rename it.
    # === AI AGENT ===
    # Instance-safe default (self may be empty recordset); uses context today.
    def _default_name(self):
        today = fields.Date.context_today(self)
        return _("Lodge Newsletter — %s") % today.strftime("%B %Y")

    # === HUMAN ===
    # Which template a brand-new newsletter starts from (the default one).
    # === AI AGENT ===
    # Prefers is_default; falls back to any template. Returns empty if none seeded.
    def _default_template(self):
        Template = self.env["elks.bulletin.template"]
        return (Template.search([("is_default", "=", True)], limit=1)
                or Template.search([], limit=1))

    # === HUMAN ===
    # Works out the masthead numbers from the lodge charter date and this issue's
    # date. Volume counts years since the lodge was chartered; No. is the month
    # (1–12). These are stored so they're searchable.
    # === AI AGENT ===
    # STORED-ONLY compute. relativedelta(...).years or 1 avoids "Volume 0" in a
    # charter year. Kept separate from the display/flag compute below so Odoo 19
    # doesn't warn about mixing stored + non-stored fields in one method.
    @api.depends("issue_date", "lodge_charter_date")
    def _compute_issue_numbers(self):
        for rec in self:
            idt = rec.issue_date
            cd = rec.lodge_charter_date
            rec.issue_number = idt.month if idt else 0
            if cd and idt:
                rec.volume = relativedelta(idt, cd).years or 1
            else:
                rec.volume = 0

    # === HUMAN ===
    # Builds the "Volume X, No. Y" label for the masthead and flags when the
    # charter date is missing (drives the form banner).
    # === AI AGENT ===
    # NON-STORED compute; depends on the stored numbers so it re-runs when they
    # change. charter_missing -> form banner.
    @api.depends("issue_date", "lodge_charter_date", "volume", "issue_number")
    def _compute_issue_ref(self):
        for rec in self:
            if rec.lodge_charter_date and rec.issue_date:
                rec.issue_ref = _("Volume %(v)s, No. %(n)s",
                                  v=rec.volume, n=rec.issue_number)
                rec.charter_missing = False
            else:
                rec.issue_ref = _("Volume — , No. %(n)s",
                                  n=rec.issue_number or "—")
                rec.charter_missing = True

    # === HUMAN ===
    # When you create a newsletter, start it from the template's layout so it's
    # not a blank page.
    # === AI AGENT ===
    # Copies BOTH the template's body_arch (edited canvas) and body_html (inlined
    # output used by the PDF) into an empty issue at create time, so a brand-new
    # issue can be printed before it's ever opened in the editor. Respects an
    # explicitly provided body (e.g. duplicate). @api.model_create_multi.
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("body_arch"):
                continue
            tmpl = self.env["elks.bulletin.template"].browse(
                vals.get("template_id")) if vals.get("template_id") \
                else self._default_template()
            if tmpl and tmpl.body_arch:
                vals["body_arch"] = tmpl.body_arch
                # Carry the inlined output too; fall back to body_arch so the
                # print path is never empty even if the template was never
                # inlined by the editor.
                if not vals.get("body_html"):
                    vals["body_html"] = tmpl.body_html or tmpl.body_arch
        return super().create(vals_list)

    # === HUMAN ===
    # Lock the issue as Final (kept editable-in-place is fine; this just marks it).
    # === AI AGENT ===
    # Simple state toggle.
    def action_mark_final(self):
        self.write({"state": "final"})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    # === HUMAN ===
    # The "Print / Download PDF" button. Produces a page-sized PDF that matches
    # the page size you picked (US Letter or US Legal), with a page-number footer.
    # === AI AGENT ===
    # Two report actions share one QWeb template but carry different paperformats
    # (Letter vs Legal); pick the matching one by page_size so the PDF is sized
    # correctly. ensure_one() -> single-issue export.
    def action_print_pdf(self):
        self.ensure_one()
        xmlid = ("elksbulletin.action_report_bulletin_legal"
                 if self.page_size == "legal"
                 else "elksbulletin.action_report_bulletin_letter")
        return self.env.ref(xmlid).report_action(self)

    # ==================================================================
    # Dynamic content — filled in at render time
    # ==================================================================
    # === HUMAN ===
    # The fiscal year window for THIS issue, using the lodge's FRS settings
    # (Fiscal Year Start Month/Day; defaults to April 1). Everything dynamic
    # (Project Dollars, new members, charity totals) is measured across this
    # window.
    # === AI AGENT ===
    # Returns (start, end) dates. FY start = the most recent (month, day) on or
    # before the issue date; end = one year later minus a day. Falls back to
    # Apr 1 if settings are unset.
    def _fiscal_year_range(self):
        self.ensure_one()
        settings = self.lodge_settings_id
        m = (settings.fiscal_year_start_month or 4) if settings else 4
        d = (settings.fiscal_year_start_day or 1) if settings else 1
        ref = self.issue_date or fields.Date.context_today(self)
        try:
            start = date(ref.year, m, d)
        except ValueError:
            start = date(ref.year, m, 1)
        if start > ref:
            start = date(ref.year - 1, m, d if d <= 28 else 1)
        end = start + relativedelta(years=1) - timedelta(days=1)
        return start, end

    # === HUMAN ===
    # Produces the print-ready page: takes the drag-and-drop layout and swaps
    # each "dynamic" block (New Members, Project Dollars, Delinquent list,
    # Charity totals) for the live numbers from the lodge modules. Used by the
    # PDF so the newsletter is always current when you print it.
    # === AI AGENT ===
    # Parses body_html (fallback body_arch), finds elements carrying
    # data-elks-block="<key>", and replaces their inner content with computed
    # HTML (tag + attributes preserved). Returns Markup. If there are no markers
    # the body is returned unchanged. Data reads use sudo(); a failure in one
    # block degrades to a small notice rather than breaking the whole render.
    def _render_print_body(self):
        self.ensure_one()
        html = self.body_html or self.body_arch or ""
        if not html or "data-elks-block" not in html:
            return Markup(html or "")
        try:
            frag = lxml_html.fragment_fromstring(html, create_parent="div")
        except Exception:
            return Markup(html)
        for el in frag.xpath('.//*[@data-elks-block]'):
            key = el.get("data-elks-block")
            inner = self._dynamic_block_html(key)
            for child in list(el):
                el.remove(child)
            el.text = None
            try:
                nodes = lxml_html.fragments_fromstring(inner)
            except Exception:
                nodes = [inner]
            for node in nodes:
                if isinstance(node, str):
                    el.text = (el.text or "") + node
                else:
                    el.append(node)
        return Markup(
            "".join(lxml_html.tostring(c, encoding="unicode")
                    for c in frag)
        )

    # === AI AGENT ===
    # Dispatch by block key. Wrapped so a data error never breaks the PDF.
    def _dynamic_block_html(self, key):
        builders = {
            "new_members": self._html_new_members,
            "project_dollars": self._html_project_dollars,
            "delinquents": self._html_delinquents,
            "charity": self._html_charity,
            "calendar": self._html_calendar,
        }
        builder = builders.get(key)
        if not builder:
            return ""
        try:
            return builder()
        except Exception:  # pragma: no cover - defensive
            return ('<p style="color:#a00;font-style:italic;">'
                    'This section could not be generated from lodge data.</p>')

    # --- shared styling helpers --------------------------------------
    _PURPLE = "#5b3b8c"
    _PURPLE_DEEP = "#3f2566"
    _GOLD = "#c9a227"

    # Small US flag (inline SVG) shown next to veteran members. SVG renders in
    # wkhtmltopdf, unlike color emoji.
    _VET_FLAG = (
        '<svg width="19" height="12" viewBox="0 0 19 12"'
        ' style="vertical-align:middle;margin-left:6px;"'
        ' xmlns="http://www.w3.org/2000/svg">'
        '<rect width="19" height="12" fill="#b22234"/>'
        '<rect width="19" height="1.85" y="1.85" fill="#ffffff"/>'
        '<rect width="19" height="1.85" y="5.55" fill="#ffffff"/>'
        '<rect width="19" height="1.85" y="9.25" fill="#ffffff"/>'
        '<rect width="8.4" height="6.46" fill="#3c3b6e"/></svg>'
    )

    def _vet_flag(self, member):
        return self._VET_FLAG if getattr(member, "x_is_veteran", False) else ""

    def _dyn_table_open(self, headers):
        ths = "".join(
            f'<th style="text-align:left;border-bottom:2px solid '
            f'{self._PURPLE_DEEP};padding:3px 6px;font-family:Arial,sans-serif;'
            f'font-size:11px;">{h}</th>' for h in headers
        )
        return (
            '<table style="width:100%;border-collapse:collapse;'
            'font-family:Georgia,serif;font-size:12px;">'
            f'<tr>{ths}</tr>'
        )

    @staticmethod
    def _fmt_date(d):
        """'Jun 22, 2026' without platform-specific strftime codes."""
        return f"{d.strftime('%b')} {d.day}, {d.year}" if d else ""

    # === AI AGENT ===
    # New members for the configured window (a single month of the issue year,
    # or fiscal-year-to-date). Renders a compact name/age/date table, or photo
    # cards when Show New Member Photos is on.
    def _html_new_members(self):
        d = self.issue_date or fields.Date.context_today(self)
        if self.new_member_month and self.new_member_month != "fy":
            y, m = d.year, int(self.new_member_month)
            _, last = _calmod.monthrange(y, m)
            start, end = date(y, m, 1), date(y, m, last)
        else:
            start, end = self._fiscal_year_range()
        Partner = self.env["res.partner"].sudo()
        members = Partner.search([
            ("x_is_member", "=", True),
            ("x_date_initiated", ">=", start),
            ("x_date_initiated", "<=", end),
        ], order="x_date_initiated asc, name asc")
        if not members:
            return ('<p style="font-style:italic;color:#666;">'
                    'No new members were initiated in this period.</p>')
        if self.new_member_photos:
            return self._html_new_members_photos(members)
        rows = []
        for mbr in members:
            age = int(mbr.x_age) if mbr.x_age else ""
            rows.append(
                f'<tr><td style="padding:2px 6px;border-bottom:1px solid #ddd;">'
                f'<b>{mbr.name or ""}</b>{self._vet_flag(mbr)}</td>'
                f'<td style="padding:2px 6px;border-bottom:1px solid #ddd;">'
                f'{age}</td>'
                f'<td style="padding:2px 6px;border-bottom:1px solid #ddd;">'
                f'{self._fmt_date(mbr.x_date_initiated)}</td></tr>'
            )
        return (self._dyn_table_open(["Name", "Age", "Initiated"])
                + "".join(rows) + "</table>")

    # === AI AGENT ===
    # Photo-card layout for new members (3 per row; fills the block width so it
    # looks best at 3/3). Missing photos show an initial monogram.
    def _html_new_members_photos(self, members):
        cards = []
        for mbr in members:
            img = mbr.image_512 or mbr.image_1920
            if img:
                photo = (
                    f'<img src="data:image/png;base64,{img.decode()}" '
                    f'style="width:88px;height:88px;border-radius:50%;'
                    f'object-fit:cover;border:2px solid {self._PURPLE_DEEP};"/>'
                )
            else:
                initial = (mbr.name or "?").strip()[:1].upper()
                photo = (
                    f'<div style="width:88px;height:88px;border-radius:50%;'
                    f'background:{self._PURPLE};color:#fff;display:inline-block;'
                    f'line-height:88px;font-family:Georgia,serif;font-size:34px;'
                    f'font-weight:bold;">{initial}</div>'
                )
            age = int(mbr.x_age) if mbr.x_age else ""
            meta = " · ".join(filter(None, [
                (f"Age {age}" if age else ""),
                self._fmt_date(mbr.x_date_initiated),
            ]))
            cards.append(
                f'<td style="width:33%;text-align:center;vertical-align:top;'
                f'padding:8px 4px;">{photo}'
                f'<div style="font-family:Georgia,serif;font-weight:bold;'
                f'font-size:13px;margin-top:4px;">{mbr.name or ""}'
                f'{self._vet_flag(mbr)}</div>'
                f'<div style="font-family:Arial,sans-serif;font-size:11px;'
                f'color:#555;">{meta}</div></td>'
            )
        # 3 cards per row
        rows = []
        for i in range(0, len(cards), 3):
            rows.append("<tr>" + "".join(cards[i:i + 3]) + "</tr>")
        return ('<table style="width:100%;border-collapse:collapse;">'
                + "".join(rows) + "</table>")

    # === AI AGENT ===
    # Project Dollars taken in for the fiscal year — sum of the Trustees' cup
    # collections (elkssecretary meeting money) dated within the FY window.
    def _html_project_dollars(self):
        fy_start, fy_end = self._fiscal_year_range()
        MM = self.env["elks.meeting.money"].sudo()
        recs = MM.search([
            ("meeting_date", ">=", fy_start),
            ("meeting_date", "<=", fy_end),
        ])
        total = sum(recs.mapped("project_dollars_amount"))
        meetings = len(recs)
        fy_label = f"{fy_start.strftime('%b %Y')} – {fy_end.strftime('%b %Y')}"
        return (
            f'<div style="text-align:center;padding:6px 0;">'
            f'<div style="font-family:Arial,sans-serif;font-size:12px;'
            f'color:#555;">Project Dollars raised · {fy_label}</div>'
            f'<div style="font-family:Georgia,serif;font-weight:bold;'
            f'font-size:38px;color:{self._PURPLE_DEEP};line-height:1.1;">'
            f'${total:,.2f}</div>'
            f'<div style="font-family:Arial,sans-serif;font-size:11px;'
            f'color:#777;">across {meetings} meeting'
            f'{"s" if meetings != 1 else ""} this fiscal year</div></div>'
        )

    # === AI AGENT ===
    # Dues standing — AGGREGATE COUNTS ONLY (no names): total members and the
    # number delinquent. Compact enough for a 1/3 block.
    def _html_delinquents(self):
        Partner = self.env["res.partner"].sudo()
        total = Partner.search_count([("x_is_member", "=", True)])
        delinq = Partner.search_count([
            ("x_is_member", "=", True),
            ("x_is_dues_paid", "=", False),
        ])
        return (
            '<table style="width:100%;border-collapse:collapse;'
            'font-family:Georgia,serif;font-size:13px;">'
            f'<tr><td style="padding:3px 6px;border-bottom:1px solid #d9cbe8;">'
            f'Total Members</td>'
            f'<td style="padding:3px 6px;text-align:right;font-weight:bold;'
            f'border-bottom:1px solid #d9cbe8;">{total:,}</td></tr>'
            f'<tr><td style="padding:3px 6px;">Members Delinquent</td>'
            f'<td style="padding:3px 6px;text-align:right;font-weight:bold;'
            f'color:{self._PURPLE_DEEP};">{delinq:,}</td></tr>'
            '</table>'
            '<p style="font-family:Arial,sans-serif;font-size:10px;'
            'font-style:italic;color:#777;margin:6px 0 0;text-align:center;">'
            'Past due? Please contact the lodge office.</p>'
        )

    # === AI AGENT ===
    # Month calendar grid for the issue month, populated from calendar.event —
    # the SAME source as elks_calendar_publisher (the real lodge calendar), so it
    # matches the published calendar. Inline-styled so it survives the email
    # inliner into the print body.
    def _html_calendar(self):
        d = self.issue_date or fields.Date.context_today(self)
        y, m = d.year, d.month
        _, last = _calmod.monthrange(y, m)
        Event = self.env["calendar.event"].sudo()
        events = Event.search([
            ("start", ">=", date(y, m, 1)),
            ("start", "<=", date(y, m, last)),
        ], order="start asc")
        by_day = {}
        for evt in events:
            sd = evt.start.date() if evt.start else False
            if sd and sd.year == y and sd.month == m:
                by_day.setdefault(sd.day, []).append(evt.name or "Event")
        dow = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        head = "".join(
            f'<th style="border:1px solid {self._PURPLE_DEEP};'
            f'background:{self._PURPLE};color:#fff;font-family:Arial,sans-serif;'
            f'font-size:10px;padding:2px;text-align:center;">{d0}</th>'
            for d0 in dow)
        weeks = _calmod.Calendar(firstweekday=6).monthdayscalendar(y, m)
        body = []
        for wk in weeks:
            cells = []
            for day in wk:
                if day == 0:
                    cells.append(
                        f'<td style="border:1px solid {self._PURPLE_DEEP};'
                        f'background:#f2f2f2;height:52px;"></td>')
                    continue
                evs = "".join(
                    f'<div style="font-size:8px;line-height:1.1;'
                    f'border-top:1px solid #ddd;margin-top:1px;">{e}</div>'
                    for e in by_day.get(day, []))
                cells.append(
                    f'<td style="border:1px solid {self._PURPLE_DEEP};'
                    f'height:52px;vertical-align:top;padding:1px 2px;">'
                    f'<div style="font-weight:bold;font-size:10px;">{day}</div>'
                    f'{evs}</td>')
            body.append("<tr>" + "".join(cells) + "</tr>")
        return (
            f'<table style="width:100%;border-collapse:collapse;'
            f'table-layout:fixed;font-family:Georgia,serif;">'
            f'<tr>{head}</tr>{"".join(body)}</table>'
        )

    # === AI AGENT ===
    # Charity totals for the fiscal year plus the "report it or it didn't happen"
    # reminder driving volunteers to submit hours to the Secretary.
    def _html_charity(self):
        fy_start, fy_end = self._fiscal_year_range()
        Contrib = self.env["elks.charity.contribution"].sudo()
        recs = Contrib.search([
            ("contribution_date", ">=", fy_start),
            ("contribution_date", "<=", fy_end),
        ])
        hours = sum(recs.mapped("elks_hours")) + sum(recs.mapped("helper_hours"))
        cash = sum(recs.mapped("cash_value"))
        noncash = sum(recs.mapped("non_cash_value"))
        totals = (
            self._dyn_table_open(["Charity Totals (Fiscal Year)", ""])
            + f'<tr><td style="padding:2px 6px;border-bottom:1px solid #ddd;">'
              f'Volunteer Hours</td><td style="padding:2px 6px;text-align:right;'
              f'border-bottom:1px solid #ddd;"><b>{hours:,.0f}</b></td></tr>'
            + f'<tr><td style="padding:2px 6px;border-bottom:1px solid #ddd;">'
              f'Cash Donations</td><td style="padding:2px 6px;text-align:right;'
              f'border-bottom:1px solid #ddd;"><b>${cash:,.2f}</b></td></tr>'
            + f'<tr><td style="padding:2px 6px;">Non-Cash Donations</td>'
              f'<td style="padding:2px 6px;text-align:right;">'
              f'<b>${noncash:,.2f}</b></td></tr></table>'
        )
        reminder = (
            f'<div style="margin-top:8px;border:2px solid {self._GOLD};'
            f'background:#f7efd6;border-radius:6px;padding:8px 10px;'
            f'font-family:Arial,sans-serif;font-size:11px;color:{self._PURPLE_DEEP};">'
            f'<b>Report it, or it didn\'t happen!</b> Volunteer hours only count '
            f'toward our lodge\'s charity report when they\'re turned in. Please '
            f'get your hours and donations to the <b>Secretary\'s office</b> so '
            f'your good work is recorded.</div>'
        )
        return totals + reminder
