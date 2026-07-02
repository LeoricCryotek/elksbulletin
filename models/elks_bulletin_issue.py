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
import base64
import calendar as _calmod
import logging
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from lxml import etree, html as lxml_html
from markupsafe import Markup, escape as markup_escape

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

# Month selection for the "New Members" block source window.
NEW_MEMBER_MONTHS = [
    ("fy", "Fiscal Year to Date"),
    ("01", "January"), ("02", "February"), ("03", "March"),
    ("04", "April"), ("05", "May"), ("06", "June"),
    ("07", "July"), ("08", "August"), ("09", "September"),
    ("10", "October"), ("11", "November"), ("12", "December"),
]

# Display order for the Lodge Officers roster (elks.officer.term positions).
OFFICER_ORDER = [
    "exalted_ruler", "leading_knight", "loyal_knight", "lecturing_knight",
    "secretary", "treasurer", "tiler", "esquire", "chaplain", "inner_guard",
    "organist", "pianist", "sergeant_at_arms", "presiding_justice",
    "boardchair", "trustee1y", "trustee2y", "trustee3y", "trustee4y",
    "trustee5y", "assistant_secretary", "assistant_treasurer", "house_chair",
    "activities_chair", "membership_chair", "lodge_advisor",
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
        help="Include member photos in the New Members block, pulled from each "
             "member's CONTACT photo (members without one get a monogram). "
             "Looks best when the block is placed at full width (3/3).\n"
             "If photos are taken at initiation and emailed to you instead of "
             "stored on the contact, leave this off and use the 'Member Photo "
             "Grid' block in the editor: drop it under New Members, then "
             "double-click each placeholder and upload the emailed photo. That "
             "grid is hand-edited content and is never overwritten at print.")

    # --- lodge settings (from elksfrs) -----------------------------------
    lodge_settings_id = fields.Many2one(
        "elks.lodge.settings", string="Lodge Settings",
        default=lambda self: self.env["elks.lodge.settings"].sudo().search([], limit=1),
        readonly=True)
    lodge_charter_date = fields.Date(
        related="lodge_settings_id.lodge_charter_date", readonly=True)
    lodge_logo = fields.Binary(
        related="lodge_settings_id.logo_lodge", readonly=True)
    # Grand-Lodge-style banner assets (all from FRS lodge settings):
    #   logo_lodge_bw       -> monochrome lodge logo (banner, left)
    #   lodge_building_entry-> photo of the lodge (banner, right)
    #   lodge_website       -> public URL shown across the banner's top bar
    lodge_logo_bw = fields.Binary(
        related="lodge_settings_id.logo_lodge_bw", readonly=True)
    lodge_building = fields.Binary(
        related="lodge_settings_id.lodge_building_entry", readonly=True)
    lodge_website = fields.Char(
        related="lodge_settings_id.lodge_website", readonly=True)
    lodge_name = fields.Char(
        related="lodge_settings_id.name", readonly=True)
    lodge_number = fields.Char(
        related="lodge_settings_id.lodge_number", readonly=True)
    city_state = fields.Char(
        "City / State", compute="_compute_city_state",
        help="Lodge city and state for the masthead, from FRS lodge settings.")

    # === AI AGENT ===
    # "City, State" for the masthead, built from FRS lodge_city + the label of the
    # lodge_state selection. Falls back to Lewiston, Idaho if settings are unset.
    @api.depends("lodge_settings_id.lodge_city", "lodge_settings_id.lodge_state")
    def _compute_city_state(self):
        for rec in self:
            city = state = ""
            s = rec.lodge_settings_id
            if s:
                city = s.lodge_city or ""
                if s.lodge_state and "lodge_state" in s._fields:
                    sel = dict(s._fields["lodge_state"].selection or [])
                    state = sel.get(s.lodge_state, s.lodge_state)
            rec.city_state = ", ".join(
                p for p in (city, state) if p) or "Lewiston, Idaho"

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

    # === HUMAN ===
    # "Preview" opens the finished newsletter PDF in a new browser tab (inline)
    # so you can see exactly how it breaks across pages before you download it.
    # === AI AGENT ===
    # Renders the same report (WeasyPrint via the ir.actions.report override),
    # stores it as an attachment, and returns an act_url with download=false so
    # the browser shows the PDF inline rather than downloading it. Prior preview
    # attachments for this issue are removed first so they don't accumulate.
    PREVIEW_ATTACHMENT_TAG = "elksbulletin_preview"

    def action_preview_pdf(self):
        self.ensure_one()
        xmlid = ("elksbulletin.action_report_bulletin_legal"
                 if self.page_size == "legal"
                 else "elksbulletin.action_report_bulletin_letter")
        report = self.env.ref(xmlid)
        pdf_content, _type = report._render_qweb_pdf(
            report.report_name, self.ids)
        Attachment = self.env["ir.attachment"].sudo()
        # Drop any earlier preview for this issue to avoid pile-up.
        Attachment.search([
            ("res_model", "=", self._name),
            ("res_id", "=", self.id),
            ("description", "=", self.PREVIEW_ATTACHMENT_TAG),
        ]).unlink()
        attachment = Attachment.create({
            "name": f"{self.name or 'Newsletter'} (preview).pdf",
            "type": "binary",
            "datas": base64.b64encode(pdf_content),
            "res_model": self._name,
            "res_id": self.id,
            "description": self.PREVIEW_ATTACHMENT_TAG,
            "mimetype": "application/pdf",
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=false",
            "target": "new",
        }

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
    # Produces the print-ready page: takes the drag-and-drop layout, swaps each
    # "dynamic" block (New Members, Project Dollars, Dues, Charity, Calendar,
    # Events, Officers) for the live numbers from the lodge modules, fills the
    # masthead and Officer's Message from lodge data, and fixes up the layout
    # so Page Breaks actually break and side-by-side blocks never get split
    # across pages. Used by the PDF so the newsletter is always current when
    # you print it. Hand-edited Message titles are respected — only the default
    # "Officer's Message" placeholder is auto-filled.
    # === AI AGENT ===
    # PRINTS body_arch (the clean editor markup), NOT body_html. Rationale
    # (19.0.1.2.0): body_html is the mass_mailing EMAIL-inliner output — built
    # for Outlook, it table-izes the Bootstrap grid and locks the whole mailing
    # to a narrow email width, which made the PDF render at ~half page width.
    # We never email this document; WeasyPrint renders real CSS (flex grid,
    # break-inside) directly, so the un-inlined body_arch prints full page width
    # with proper side-by-side columns (the report stylesheet supplies the
    # .row/.col-md-* grid). body_html is kept only as a fallback. Because the
    # source is now un-inlined, the wrapper-table flatten (step 2) and the
    # page-break table-hoist (step 3) are usually no-ops — harmless; they still
    # guard any legacy inlined body_html that flows through the fallback.
    # Parses that body and runs the resolver pipeline:
    #   1  data-elks-block markers  -> computed HTML (tag + attrs preserved)
    #   1b data-elks-field markers  -> masthead values (month, Volume/No.,
    #      lodge name/number/city, logo as data: URI)
    #   1c o_elks_officer_<pos> sections -> title (default placeholder only;
    #      curly/straight apostrophes normalized) + byline photo/name/title
    #   2  flatten the mass_mailing wrapper table (o_mail_wrapper_td) into a
    #      block-level div (.o_mail_print_wrapper)
    #   3  Page Breaks (both variants): hoist out of the inliner's table cells
    #      (_hoist_to) and REPLACE with a bare break-after div — no PDF engine
    #      honors a forced break inside a td, and wkhtmltopdf also ignores
    #      page-break props on <table> elements
    #   4  tag the section holder .o_elks_print_flow (print stylesheet hook)
    #   4b wrap consecutive sized siblings (o_elks_w_*) in a shared
    #      break-inside:avoid row so a page cut can't split a row
    #   5  assign elks-flow-N ids to story-flow children (skipping page-break
    #      elements) for the report's auto-continuation pass
    # Returns Markup. No markers -> body returned unchanged. Data reads use
    # sudo(); any failure degrades to a notice / the raw body rather than
    # breaking the whole render.
    def _render_print_body(self):
        self.ensure_one()
        # Prefer body_arch (clean, un-inlined markup): full-width, real CSS grid
        # for WeasyPrint. body_html (email-inliner output) only as a fallback.
        html = self.body_arch or self.body_html or ""
        if not html.strip():
            return Markup("")
        # Guard: a resolver error must never take down the whole PDF/report.
        try:
            return self._render_print_body_inner(html)
        except Exception:
            _logger.warning(
                "elksbulletin: print body render failed; using raw body.",
                exc_info=True)
            return Markup(html)

    def _render_print_body_inner(self, html):
        frag = lxml_html.fragment_fromstring(html, create_parent="div")

        # 1) Fill dynamic blocks (data-elks-block markers).
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

        # 1b) Fill masthead dynamic fields (data-elks-field markers) so the
        #     masthead / Grand-Lodge-style banner reflects THIS issue (month,
        #     website, Volume/No., lodge name, logos and building photo)
        #     instead of the static placeholder.
        field_values = {
            "lodge_name": getattr(self, "lodge_name", "") or "",
            "lodge_number": getattr(self, "lodge_number", "") or "",
            "city_state": getattr(self, "city_state", "") or "",
            "issue_ref": getattr(self, "issue_ref", "") or "",
            "lodge_website": getattr(self, "lodge_website", "") or "",
            "issue_month_year": (self.issue_date.strftime("%B %Y")
                                 if self.issue_date else ""),
        }
        # Image markers -> the binary field to source, with graceful fallback.
        # The B&W banner logo falls back to the colour lodge logo if unset.
        image_fields = {
            "logo_lodge": ("lodge_logo",),
            "logo_lodge_bw": ("lodge_logo_bw", "lodge_logo"),
            "lodge_building_entry": ("lodge_building",),
        }
        for el in frag.xpath(".//*[@data-elks-field]"):
            key = el.get("data-elks-field")
            if key in image_fields:
                data = next((getattr(self, f, False)
                             for f in image_fields[key]
                             if getattr(self, f, False)), False)
                if data:
                    el.set("src", "data:image/png;base64," + data.decode())
                    el.set("style", (el.get("style") or "").replace(
                        "display:none", "").replace("display: none", ""))
                elif el.getparent() is not None:
                    # No image on file: drop the placeholder rather than print
                    # a broken-image / grey box.
                    el.getparent().remove(el)
                continue
            if key in field_values:
                for child in list(el):
                    el.remove(child)
                el.text = field_values[key]

        # 1c) Message Blocks: a section carrying an o_elks_officer_<position>
        #     class (set by the Style-panel Officer dropdown) gets its title set
        #     and its byline (photo/name/title) filled from that officer for this
        #     lodge year. A class is used (not a data-attribute) because classes
        #     reliably survive the email inliner. The message body stays editable.
        msg_t = ("contains(concat(' ', normalize-space(@class), ' '),"
                 " ' s_elks_msg_title ')")
        msg_b = ("contains(concat(' ', normalize-space(@class), ' '),"
                 " ' s_elks_msg_byline ')")
        for sec in frag.xpath(".//*[contains(@class, 'o_elks_officer_')]"):
            position = next(
                (c[len("o_elks_officer_"):]
                 for c in (sec.get("class") or "").split()
                 if c.startswith("o_elks_officer_")),
                "exalted_ruler")
            for title in sec.xpath(f".//*[{msg_t}]"):
                # Respect hand-edited titles (e.g. "Exalted Ruler's Message
                # Continued"): only auto-fill when the title is still the
                # snippet's default placeholder. Curly apostrophes (\u2019)
                # are normalized — the editor may substitute them for the
                # template's straight quote.
                current = " ".join(title.text_content().split()).lower()
                current = current.replace("\u2019", "'")
                # Only auto-fill an UNTOUCHED default (or empty) title; any edit
                # means the user wrote their own title, so print it verbatim.
                if current not in ("", "officer's message"):
                    continue
                for c in list(title):
                    title.remove(c)
                title.text = f"Message from the {self._officer_label(position)}"
            for byl in sec.xpath(f".//*[{msg_b}]"):
                inner = self._officer_byline_html(position)
                for c in list(byl):
                    byl.remove(c)
                byl.text = None
                try:
                    nodes = lxml_html.fragments_fromstring(inner)
                except Exception:
                    nodes = [inner]
                for node in nodes:
                    if isinstance(node, str):
                        byl.text = (byl.text or "") + node
                    else:
                        byl.append(node)

        # 1d) Bake the Style-panel border into LITERAL inline CSS. The panel
        #     stores the chosen width/radius as CSS custom properties
        #     (--box-border-width / --box-border-radius); the rule that turns
        #     those into a real border only exists in an editor/website
        #     stylesheet, and PDF engines are unreliable with var() (WeasyPrint
        #     only supports it in single-value props in some versions; the
        #     wkhtmltopdf fallback not at all). So resolve them here to plain
        #     border-width / border-radius / border-style on the element — the
        #     one fix that prints on BOTH engines. (Advice confirmed by an
        #     external review; see HANDOFF.) border-color/-style are already
        #     inline, so they're left as-is.
        for el in frag.xpath(".//*[contains(@style, '--box-border')]"):
            self._bake_box_border(el)

        # 2) Flatten the mass_mailing wrapper table into a plain div. All the
        #    sections normally live in ONE <td class="o_mail_wrapper_td">, and
        #    wkhtmltopdf ignores page-break CSS inside a table cell. Moving them
        #    to a block-level div makes page-breaks work. No-op if absent.
        td_xpath = (".//*[contains(concat(' ', normalize-space(@class), ' '),"
                    " ' o_mail_wrapper_td ')]")
        for td in frag.xpath(td_xpath):
            table = td
            while table is not None and table.tag != "table":
                table = table.getparent()
            if table is None or table.getparent() is None:
                continue
            holder = etree.Element("div")
            holder.set("class", "o_mail_print_wrapper")
            for child in list(td):
                holder.append(child)
            table.getparent().replace(table, holder)

        # 3) Force the manual "Page Break" blocks (both variants). Two parts:
        #    (a) HOIST: the mass_mailing inliner (addTables/bootstrapToTable)
        #        wraps every section in table>tr>td, and BOTH WeasyPrint and
        #        wkhtmltopdf ignore a forced page break inside a table cell.
        #        This is exactly why the July 2026 preview didn't break: the
        #        break sat inside the inliner's table cells. So each break is
        #        bubbled up to be a direct, block-level child of the flattened
        #        print wrapper (splitting every ancestor around it; content
        #        order preserved — see _hoist_to).
        #    (b) STYLE: inline break-after (modern) + page-break-after (the
        #        only spelling wkhtmltopdf's Qt WebKit understands).
        token = ("contains(concat(' ', normalize-space(@class), ' '),"
                 " ' %s ')")
        pb_xpath = (".//*[" + (token % "s_elks_page_break") + " or "
                    + (token % "s_elks_page_break_inline") + "]")
        wrappers = frag.xpath(
            ".//*[contains(concat(' ', normalize-space(@class), ' '),"
            " ' o_mail_print_wrapper ')]")
        hoist_stop = wrappers[0] if wrappers else frag
        for pb in frag.xpath(pb_xpath):
            self._hoist_to(pb, hoist_stop)
            # Replace the break element with a bare, empty <div>. Post-inliner
            # the break is a <table> (addTables moves the section's attributes
            # onto a table), and wkhtmltopdf's Qt WebKit ignores page-break
            # properties on table elements — a div is honored by both engines.
            # Dropping the children also guarantees the editor's dashed line
            # can never leak into the PDF, independent of the hide CSS.
            div = etree.Element("div")
            if pb.get("class"):
                div.set("class", pb.get("class"))
            div.set("style",
                    "break-after:page;page-break-after:always;"
                    "display:block;height:0;")
            parent = pb.getparent()
            if parent is not None:
                parent.replace(pb, div)

        # 4) Tag the element that directly holds the snippet sections so the
        #    print stylesheet can flow it in newspaper columns (full-width
        #    blocks opt out via column-span:all).
        sects = frag.xpath(
            ".//*[contains(concat(' ', normalize-space(@class), ' '),"
            " ' o_mail_snippet_general ')]")
        if sects:
            parent = sects[0].getparent()
            if parent is not None:
                cls = (parent.get("class") or "").strip()
                parent.set("class", (cls + " o_elks_print_flow").strip())

        # 4b) Group consecutive same-row SIZED siblings (o_elks_w_23/_12/_13)
        #     into a shared break-inside:avoid wrapper. Without this, WeasyPrint
        #     can push one sibling in a side-by-side row to the next page while
        #     its row-partner stays behind (break-inside:avoid is only ever set
        #     per-block, never on the row as a unit), splitting the row across
        #     the page boundary. Row membership is approximated the same way
        #     inline-block actually wraps: sum declared widths and start a new
        #     row once the running total would exceed 100%. Full-width /
        #     unsized blocks are never inline-block, so they always reset the run.
        ROW_WIDTH_PCT = {"o_elks_w_23": 66, "o_elks_w_12": 49.6, "o_elks_w_13": 33}
        if sects:
            parent = sects[0].getparent()
            if parent is not None:
                children = list(parent)
                i = 0
                while i < len(children):
                    el = children[i]
                    width_cls = next(
                        (c for c in (el.get("class") or "").split()
                         if c in ROW_WIDTH_PCT), None)
                    if width_cls is None:
                        i += 1
                        continue
                    run = [el]
                    running = ROW_WIDTH_PCT[width_cls]
                    j = i + 1
                    while j < len(children):
                        nxt = children[j]
                        nxt_cls = next(
                            (c for c in (nxt.get("class") or "").split()
                             if c in ROW_WIDTH_PCT), None)
                        if nxt_cls is None or running + ROW_WIDTH_PCT[nxt_cls] > 100.5:
                            break
                        run.append(nxt)
                        running += ROW_WIDTH_PCT[nxt_cls]
                        j += 1
                    if len(run) > 1:
                        wrapper = etree.Element(
                            "div", style="break-inside:avoid;"
                                          "page-break-inside:avoid;")
                        run[0].addprevious(wrapper)
                        for node in run:
                            wrapper.append(node)
                    i = j

        # 5) Mark "story" flow text (Message Block / Two-Thirds+One-Third /
        #    Three Columns body columns, tagged .s_elks_story_flow in the
        #    snippets) with stable per-child ids. The report's second WeasyPrint
        #    pass (ir_actions_report._bulletin_insert_continuation_markers) uses
        #    these ids to find exactly which child landed on which printed page,
        #    so it can auto-insert "Continued on page #" / "(Continued from
        #    page #)" bars at the real break point instead of a guess.
        flow_xpath = (".//*[contains(concat(' ', normalize-space(@class), ' '),"
                      " ' s_elks_story_flow ')]")
        flow_counter = 0
        for flow in frag.xpath(flow_xpath):
            for child in flow:
                if not isinstance(child.tag, str):
                    continue  # skip comments/PIs
                if "s_elks_page_break" in (child.get("class") or ""):
                    # Deliberate breaks (incl. s_elks_page_break_inline) are not
                    # flow text. Leaving them un-id'd makes the marker pass pair
                    # the paragraphs AROUND the break, so "Continued on page #"
                    # is spliced after the last paragraph BEFORE the break
                    # (bottom of the earlier page) rather than after the break
                    # element itself (top of the new page).
                    continue
                if not child.get("id"):
                    child.set("id", f"elks-flow-{flow_counter}")
                    flow_counter += 1

        return Markup(
            "".join(lxml_html.tostring(c, encoding="unicode")
                    for c in frag)
        )

    # === HUMAN ===
    # Pulls a Page Break up and out of the email-style table wrapping so the
    # PDF engines actually honor it — the reason breaks used to be silently
    # ignored. Content order is preserved; anything after the break simply
    # continues in a copy of its old wrapper.
    # === AI AGENT ===
    # Bubble `el` up to become a direct child of `stop` by splitting each
    # ancestor around it: preceding siblings stay in the ancestor, `el` moves
    # up beside the ancestor, and any following siblings move into a shallow
    # attribute-preserving clone (ids dropped to keep them unique) inserted
    # right after `el`. Transiently odd positions (e.g. a div between <tr>s)
    # exist only inside the loop; the final resting place is block context.
    # Purpose: forced page breaks must escape the email-inliner's table cells,
    # where no PDF engine honors them.
    @staticmethod
    def _hoist_to(el, stop):
        while True:
            parent = el.getparent()
            if parent is None or parent is stop:
                return
            siblings = list(parent)
            tail = siblings[siblings.index(el) + 1:]
            parent.addnext(el)
            if tail:
                clone = etree.Element(parent.tag)
                for k, v in parent.attrib.items():
                    if k != "id":
                        clone.set(k, v)
                el.addnext(clone)
                for node in tail:
                    clone.append(node)

    # === AI AGENT ===
    # Resolve the Style-panel border CSS variables on one element into literal
    # inline CSS (border-radius / border-width / border-style), so the border
    # prints without relying on var() (unreliable in WeasyPrint's older versions
    # and unsupported by the wkhtmltopdf fallback). Only fills a property we can
    # derive AND that isn't already set literally, so a hand-authored inline
    # border-radius/-width is never clobbered. border-color stays as authored.
    @staticmethod
    def _bake_box_border(el):
        style = el.get("style") or ""
        decls = {}
        for part in style.split(";"):
            if ":" in part:
                k, v = part.split(":", 1)
                decls[k.strip().lower()] = v.strip()
        add = []
        main_r = decls.get("--box-border-radius")
        corners = [decls.get("--box-border-%s-radius" % c) or main_r
                   for c in ("top-left", "top-right",
                             "bottom-right", "bottom-left")]
        if any(corners) and "border-radius" not in decls:
            vals = [c or "0" for c in corners]
            r = vals[0] if len(set(vals)) == 1 else " ".join(vals)
            add.append("border-radius:%s" % r)
            add.append("-webkit-border-radius:%s" % r)
        main_w = decls.get("--box-border-width")
        sides = [decls.get("--box-border-%s-width" % s) or main_w
                 for s in ("top", "right", "bottom", "left")]
        if any(sides) and "border-width" not in decls:
            vals = [s or "0" for s in sides]
            w = vals[0] if len(set(vals)) == 1 else " ".join(vals)
            add.append("border-width:%s" % w)
            if "border-style" not in decls:
                add.append("border-style:solid")
        if add:
            base = style.rstrip("; ").strip()
            el.set("style", (base + ";" if base else "") + ";".join(add) + ";")

    # === AI AGENT ===
    # Dispatch by block key. Wrapped so a data error never breaks the PDF.
    def _dynamic_block_html(self, key):
        builders = {
            "new_members": self._html_new_members,
            "project_dollars": self._html_project_dollars,
            "delinquents": self._html_delinquents,
            "charity": self._html_charity,
            "calendar": self._html_calendar,
            "upcoming_events": self._html_upcoming_events,
            "events": self._html_events,
            "officers": self._html_officers,
            "in_memoriam": self._html_in_memoriam,
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

    @staticmethod
    def _e(value):
        """HTML-escape a dynamic value before injecting it into the HTML the
        resolver builds. Lodge data (member names, event titles, descriptions)
        can contain '&', '<', quotes, etc.; escaping keeps the markup valid so a
        stray character can't break the render or inject markup."""
        return str(markup_escape("" if value is None else value))

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
    # In Memoriam: members flagged deceased (x_drop_reason == 'deceased') whose
    # Date of Death (x_date_of_death) falls in the CALENDAR MONTH BEFORE the
    # issue date. Deceased members are archived once the Secretary processes the
    # death in CLMS, so the search runs with active_test=False to include them.
    # Each member is a small centered card: name (+ a US flag for veterans,
    # x_is_veteran) with membership tenure and a Life-Member badge below.
    # Tenure is computed AT DEATH from x_date_initiated -> x_date_of_death minus
    # x_lost_years (NOT x_member_years, which is relative to today and keeps
    # counting after death). Life status: x_is_honorary_life_member ->
    # "Honorary Life Member", else x_is_life_member -> "Life Member". The gold
    # frame, header and fraternal quote are static in the snippet.
    def _html_in_memoriam(self):
        issue_d = self.issue_date or fields.Date.context_today(self)
        prev_month_end = issue_d.replace(day=1) - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        members = self.env["res.partner"].sudo().with_context(
            active_test=False).search([
                ("x_drop_reason", "=", "deceased"),
                ("x_date_of_death", ">=", prev_month_start),
                ("x_date_of_death", "<=", prev_month_end),
            ], order="x_date_of_death asc, name asc")
        if not members:
            return ('<p style="font-family:Arial,sans-serif;font-size:11px;'
                    'color:#555555;font-style:italic;margin:6px 0 0;">'
                    'No members reported this month.</p>')
        # Compact, self-arranging layout: each member is an inline-block card
        # (name on top; membership years + Life-Member badge below; a small US
        # flag next to the name for veterans). Cards flow and wrap to fill the
        # width — several sit on one row, a long list wraps to more rows —
        # instead of one tall single-column stack.
        entries = []
        for mbr in members:
            dod = getattr(mbr, "x_date_of_death", False)
            init = getattr(mbr, "x_date_initiated", False)
            lost = getattr(mbr, "x_lost_years", 0) or 0
            # Membership tenure AT DEATH (x_member_years is relative to today,
            # so it keeps counting after death — compute from the dates here).
            meta_parts = []
            if init and dod:
                my = dod.year - init.year - (
                    1 if (dod.month, dod.day) < (init.month, init.day) else 0)
                my = max(0, my - lost)
                meta_parts.append("Member %d year%s" % (my, "" if my == 1 else "s"))
            if getattr(mbr, "x_is_honorary_life_member", False):
                meta_parts.append("Honorary Life Member")
            elif getattr(mbr, "x_is_life_member", False):
                meta_parts.append("Life Member")
            meta = " &#183; ".join(self._e(p) for p in meta_parts)
            entries.append(
                '<span style="display:inline-block;vertical-align:top;'
                'margin:4px 16px;text-align:center;font-family:Georgia,serif;'
                'line-height:1.25;">'
                f'<span style="font-weight:bold;color:{self._PURPLE_DEEP};'
                f'font-size:14px;">{self._e(mbr.name)}</span>{self._vet_flag(mbr)}'
                + (('<br/><span style="color:#555555;font-size:10.5px;'
                    'font-family:Arial,sans-serif;">'
                    f'{meta}</span>') if meta else "")
                + '</span>'
            )
        return ('<div style="text-align:center;margin:6px 0 2px;">'
                + "".join(entries) + '</div>')

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
                f'<b>{self._e(mbr.name)}</b>{self._vet_flag(mbr)}</td>'
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
                f'font-size:13px;margin-top:4px;">{self._e(mbr.name)}'
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
    # Upcoming APPROVED Project Events (elksevent project.task): board-approved
    # events dated today or later. Shows Title, Description, Date.
    def _html_upcoming_events(self):
        today = fields.Date.context_today(self)
        events = self.env["project.task"].sudo().search([
            ("x_is_event", "=", True),
            ("x_approval_state", "=", "approved"),
            ("x_event_date", ">=", today),
        ], order="x_event_date asc")
        if not events:
            return ('<p style="font-style:italic;color:#666;">'
                    'No upcoming approved events.</p>')
        rows = []
        for evt in events:
            # x_event_description is a plain Text field -> escape it.
            desc = self._e((evt.x_event_description or "").strip())
            desc_html = (
                f'<div style="font-family:Arial,sans-serif;font-size:11px;'
                f'color:#555;margin-top:1px;">{desc}</div>' if desc else "")
            rows.append(
                '<div style="margin:0 0 6px;padding-bottom:5px;'
                'border-bottom:1px solid #e5dff0;">'
                '<div><b style="font-family:Georgia,serif;font-size:13px;">'
                f'{self._e(evt.name)}</b>'
                f'<span style="float:right;font-family:Arial,sans-serif;'
                f'font-size:11px;font-weight:bold;color:{self._PURPLE_DEEP};">'
                f'{self._fmt_date(evt.x_event_date)}</span></div>'
                f'{desc_html}</div>'
            )
        return "".join(rows)

    # === AI AGENT ===
    # The lodge's actual events from Odoo's Events app (event.event): upcoming
    # events (start today or later). Shows name, date, and description (Html).
    def _html_events(self):
        now = fields.Datetime.now()
        events = self.env["event.event"].sudo().search([
            ("date_begin", ">=", now),
        ], order="date_begin asc")
        if not events:
            return ('<p style="font-style:italic;color:#666;">'
                    'No upcoming lodge events scheduled.</p>')
        rows = []
        for evt in events:
            when = self._fmt_date(evt.date_begin.date()) if evt.date_begin else ""
            # description is a rich-text Html field, so render it as-is (authored
            # by lodge staff); only the plain-text name is escaped.
            desc = (evt.description or "").strip() if evt.description else ""
            desc_html = (
                f'<div style="font-family:Arial,sans-serif;font-size:11px;'
                f'color:#555;margin-top:1px;">{desc}</div>' if desc else "")
            rows.append(
                '<div style="margin:0 0 6px;padding-bottom:5px;'
                'border-bottom:1px solid #e5dff0;">'
                '<div><b style="font-family:Georgia,serif;font-size:13px;">'
                f'{self._e(evt.name)}</b>'
                f'<span style="float:right;font-family:Arial,sans-serif;'
                f'font-size:11px;font-weight:bold;color:{self._PURPLE_DEEP};">'
                f'{when}</span></div>{desc_html}</div>'
            )
        return "".join(rows)

    # === HUMAN ===
    # The Lodge Calendar block renders the SAME calendar the website publishes
    # (elks_calendar_publisher), so the newsletter matches the website — theme,
    # colors, emojis, event styling and all.
    # === AI AGENT ===
    # Prefer an existing elks.calendar.publication for the issue month/year and
    # render its report_calendar_body template (exact website output). If none
    # exists, render a throwaway new() publication with a stock theme. Any
    # failure falls back to the simple built-in grid. Depends on
    # elks_calendar_publisher (month/year are string selections '1'..'12'/'2026').
    def _html_calendar(self):
        d = self.issue_date or fields.Date.context_today(self)
        month, year = str(d.month), str(d.year)
        try:
            Pub = self.env["elks.calendar.publication"].sudo()
            pub = Pub.search(
                [("month", "=", month), ("year", "=", year)], limit=1)
            body = None
            if pub:
                # Reuse the published calendar's own rendered HTML (same output
                # as the website preview) — the proven path.
                body = pub.preview_html
            else:
                Theme = self.env["elks.calendar.theme"].sudo()
                theme = (Theme.search([("is_stock", "=", True)], limit=1)
                         or Theme.search([], limit=1))
                if theme:
                    tmp = Pub.new({"month": month, "year": year,
                                   "theme_id": theme.id})
                    body = self.env["ir.qweb"]._render(
                        "elks_calendar_publisher.report_calendar_body",
                        {"pub": tmp})
            body = str(body or "")
            if body.strip() and "Preview unavailable" not in body:
                # The publisher template wraps content in <main class="elks-cal">.
                # A nested <main> inside the report's <main> is invalid HTML and
                # can make WeasyPrint throw, so swap it for a <div> (keeping the
                # class so the scoped styles still apply).
                body = (body.replace('<main class="elks-cal">',
                                     '<div class="elks-cal">')
                            .replace("</main>", "</div>"))
                return body
        except Exception:
            _logger.warning(
                "elksbulletin: publisher calendar render failed; "
                "using simple grid.", exc_info=True)
        return self._html_calendar_simple()

    # === AI AGENT ===
    # Fallback month grid from calendar.event, used only if the publisher
    # render is unavailable.
    def _html_calendar_simple(self):
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
                by_day.setdefault(sd.day, []).append(self._e(evt.name or "Event"))
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

    # === AI AGENT ===
    # Byline (photo + name + title) for the officer holding <position> in this
    # issue's lodge year, used by the Message Block. Photo from the officer term,
    # else the member's avatar, else a grey placeholder.
    def _officer_label(self, position):
        Term = self.env["elks.officer.term"].sudo()
        return dict(Term._fields["position"].selection).get(position, position)

    def _officer_byline_html(self, position):
        d = self.issue_date or fields.Date.context_today(self)
        y, m = d.year, d.month
        lodge_year = f"{y}-{y + 1}" if m >= 4 else f"{y - 1}-{y}"
        Term = self.env["elks.officer.term"].sudo()
        label = self._officer_label(position)
        term = Term.search([
            ("position", "=", position),
            ("lodge_year", "=", lodge_year),
            ("active", "=", True),
        ], limit=1)
        name, img = "", False
        if term:
            name = term.partner_id.name or ""
            img = term.image_1920 or (
                term.partner_id.image_512 or term.partner_id.image_1920
                if term.partner_id else False)
        if img:
            photo = (f'<img src="data:image/png;base64,{img.decode()}" '
                     f'style="width:100%;max-width:150px;object-fit:cover;'
                     f'border:1px solid #555555;"/>')
        else:
            photo = ('<div style="width:100%;max-width:150px;height:150px;'
                     'background:#8b8b8b;border:1px solid #555555;'
                     'margin:0 auto;"></div>')
        return (
            f'<div style="text-align:center;">{photo}'
            f'<p style="font-family:Arial,sans-serif;font-weight:bold;'
            f'color:#000000;margin-top:6px;">{self._e(name)}<br/>'
            f'<span style="font-weight:normal;font-style:italic;'
            f'color:#3f2566;">{self._e(label)}</span></p></div>'
        )

    # === AI AGENT ===
    # Lodge Officers roster from elks.officer.term for THIS issue's lodge year
    # (Apr–Mar), ordered by office, rendered as a two-column list.
    def _html_officers(self):
        d = self.issue_date or fields.Date.context_today(self)
        y, m = d.year, d.month
        lodge_year = f"{y}-{y + 1}" if m >= 4 else f"{y - 1}-{y}"
        Term = self.env["elks.officer.term"].sudo()
        terms = Term.search([
            ("lodge_year", "=", lodge_year),
            ("active", "=", True),
        ])
        if not terms:
            return ('<p style="font-style:italic;color:#666;">'
                    f'Officer roster for {lodge_year} is not set yet.</p>')
        pos_labels = dict(Term._fields["position"].selection)
        order = {p: i for i, p in enumerate(OFFICER_ORDER)}
        terms = terms.sorted(key=lambda t: order.get(t.position, 999))
        cells = [
            f'<b>{self._e(pos_labels.get(t.position, t.position))}</b> — '
            f'{self._e(t.partner_id.name)}'
            for t in terms
        ]
        half = (len(cells) + 1) // 2
        left, right = cells[:half], cells[half:]
        rows = []
        for i in range(half):
            lft = left[i] if i < len(left) else ""
            rgt = right[i] if i < len(right) else ""
            rows.append(
                '<tr>'
                f'<td style="padding:1px 8px;font-family:Arial,sans-serif;'
                f'font-size:12px;width:50%;">{lft}</td>'
                f'<td style="padding:1px 8px;font-family:Arial,sans-serif;'
                f'font-size:12px;width:50%;">{rgt}</td></tr>'
            )
        return ('<table style="width:100%;border-collapse:collapse;">'
                + "".join(rows) + "</table>")
