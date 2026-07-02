# -*- coding: utf-8 -*-
# =============================================================================
# === HUMAN ===
# Prints the Lodge Newsletter with a modern print engine (WeasyPrint) instead of
# Odoo's default wkhtmltopdf, so blocks never bleed across page cuts, the layout
# can flow in real newspaper columns, and page sizing / page numbers are exact.
# Only the newsletter reports use this; every other report in the system prints
# normally. If WeasyPrint isn't installed on the server, it quietly falls back to
# the standard engine so nothing breaks.
#
# === AI AGENT ===
# Overrides ir.actions.report._render_qweb_pdf. For our two report_names it
# renders the QWeb to HTML (_render_qweb_html) and pipes it through WeasyPrint,
# which has real CSS paged-media support (break-inside: avoid, CSS multicol +
# column-span, @page size/margins + @bottom margin boxes with counter(page)).
# A url_fetcher resolves /web/image and /web/content URLs via the ORM so member
# photos / dragged images render without an authenticated HTTP round-trip;
# data: URIs (masthead logo, computed photos) need no fetch. WeasyPrint is a
# SOFT dependency: missing import or any render error -> super() (wkhtmltopdf),
# so the module installs and runs either way. Model/report changes need
# -u elksbulletin; this controller-style Python needs a server restart.
# =============================================================================
import base64
import logging
from collections import defaultdict

from lxml import etree, html as lxml_html

from odoo import models

_logger = logging.getLogger(__name__)

try:
    import weasyprint
except ImportError:  # pragma: no cover - optional dependency
    weasyprint = None

BULLETIN_REPORTS = (
    "elksbulletin.report_bulletin_letter",
    "elksbulletin.report_bulletin_legal",
)


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        if report.report_name in BULLETIN_REPORTS:
            if weasyprint:
                # Do NOT silently swallow WeasyPrint errors into a wkhtmltopdf
                # fallback: that masks layout problems (page breaks / block
                # sizing don't work under wkhtmltopdf). Let errors surface so
                # they can be fixed. Only fall back when WeasyPrint is absent.
                return self._render_bulletin_weasyprint(report_ref, res_ids, data)
            _logger.warning(
                "elksbulletin: WeasyPrint is not installed; printing via "
                "wkhtmltopdf. Page breaks and per-block sizing require "
                "WeasyPrint (pip install weasyprint + Pango/Cairo).")
        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

    # === AI AGENT ===
    # Render the newsletter HTML and convert with WeasyPrint. Returns the same
    # (bytes, 'pdf') contract as the core method.
    def _render_bulletin_weasyprint(self, report_ref, res_ids, data):
        html, _type = self._render_qweb_html(report_ref, res_ids, data=data)
        if isinstance(html, bytes):
            html = html.decode("utf-8")
        base_url = self.env["ir.config_parameter"].sudo().get_param(
            "web.base.url"
        ) or ""
        fetcher = self._bulletin_url_fetcher(base_url)
        html = self._bulletin_insert_continuation_markers(html, base_url, fetcher)
        document = weasyprint.HTML(
            string=html,
            base_url=base_url,
            url_fetcher=fetcher,
        )
        return document.write_pdf(), "pdf"

    # === HUMAN ===
    # If a story (Message Block / Two-Thirds+One-Third / Three Columns body
    # text) runs long enough to spill onto the next page, this automatically
    # drops in a "Continued on page #" bar right where it breaks, and a
    # "(Continued from page #)" bar at the top of where it picks back up —
    # instead of you having to guess where a story will break and manually place
    # a Continued block there.
    #
    # === AI AGENT ===
    # Two-pass. (1) Render the HTML once with WeasyPrint's render() (not
    # write_pdf()) to get the real page layout, then walk its box tree: every
    # box WeasyPrint generates keeps box.element pointing back at the source
    # lxml element (this is how WeasyPrint implements bookmarks/hyperlinks
    # internally), so for each "elks-flow-N" id (assigned to direct children of
    # .s_elks_story_flow containers by elks.bulletin.issue._render_print_body_inner
    # step 5) we can read which printed page(s) it actually landed on — real
    # layout, not a guess. (2) Wherever two consecutive flow children land on
    # different pages, splice a Continued/Continued-from bar in at that exact
    # boundary (styled by .s_elks_continued_auto / .s_elks_continued_from_auto
    # in the report CSS) and return the modified HTML for the real render.
    # This relies on WeasyPrint's internal box tree (box.element / page._page_box),
    # which is NOT documented/stable public API — guarded end-to-end so a future
    # WeasyPrint upgrade that changes it degrades to a no-op (original html
    # unchanged) rather than breaking the report, same soft-dependency posture
    # as the rest of this file. Only one extra render pass is done: the markers'
    # own height can nudge later page breaks by a line or two, an accepted
    # tradeoff rather than looping to a fixed point.
    def _bulletin_insert_continuation_markers(self, html, base_url, fetcher):
        try:
            return self._bulletin_insert_continuation_markers_inner(
                html, base_url, fetcher)
        except Exception:
            _logger.warning(
                "elksbulletin: auto-continuation pass failed; printing "
                "without auto-inserted 'Continued on page #' markers.",
                exc_info=True)
            return html

    def _bulletin_insert_continuation_markers_inner(self, html, base_url, fetcher):
        frag = lxml_html.fromstring(html)
        flow_xpath = (".//*[contains(concat(' ', normalize-space(@class), ' '),"
                      " ' s_elks_story_flow ')]")
        flow_containers = frag.xpath(flow_xpath)
        if not flow_containers:
            return html  # nothing to check

        # --- pass 1: find which page each "elks-flow-N" child lands on -----
        document = weasyprint.HTML(
            string=html, base_url=base_url, url_fetcher=fetcher,
        ).render()

        element_pages = defaultdict(set)

        def walk(box, page_idx):
            el = getattr(box, "element", None)
            if el is not None:
                eid = el.get("id")
                if eid and eid.startswith("elks-flow-"):
                    element_pages[eid].add(page_idx)
            for child in getattr(box, "children", None) or []:
                walk(child, page_idx)

        for page_idx, page in enumerate(document.pages):
            walk(page._page_box, page_idx)

        # --- pass 2: splice continuation markers at the real page boundary --
        inserted = False
        for flow in flow_containers:
            children = [c for c in flow if isinstance(c.tag, str) and c.get("id")]
            primary_page = {}
            for child in children:
                pages = element_pages.get(child.get("id"))
                if pages:
                    primary_page[child.get("id")] = min(pages)
            for idx in range(len(children) - 1):
                cur, nxt = children[idx], children[idx + 1]
                cur_page = primary_page.get(cur.get("id"))
                nxt_page = primary_page.get(nxt.get("id"))
                if cur_page is None or nxt_page is None or nxt_page <= cur_page:
                    continue
                continued_bar = etree.Element(
                    "div", **{"class": "s_elks_continued_auto"})
                continued_bar.text = f"Continued on page {nxt_page + 1}"
                cur.addnext(continued_bar)
                from_bar = etree.Element(
                    "div", **{"class": "s_elks_continued_from_auto"})
                from_bar.text = f"(Continued from page {cur_page + 1})"
                nxt.addprevious(from_bar)
                inserted = True

        if not inserted:
            return html
        return lxml_html.tostring(frag, encoding="unicode")

    # === AI AGENT ===
    # Resolve Odoo image/content URLs through the ORM so they render regardless
    # of auth. Anything else (incl. data: URIs) uses WeasyPrint's default fetcher.
    def _bulletin_url_fetcher(self, base_url):
        env = self.env

        def fetcher(url):
            try:
                path = url
                if base_url and path.startswith(base_url):
                    path = path[len(base_url):]
                if path.startswith("/web/image") or path.startswith("/web/content"):
                    seg = [p for p in path.split("?")[0].strip("/").split("/")]
                    rest = seg[2:]  # drop 'web','image'|'content'
                    raw, mime = None, "image/png"
                    if len(rest) >= 3 and not rest[0].isdigit():
                        # /web/image/<model>/<id>/<field>
                        model, rid, field = rest[0], int(rest[1]), rest[2]
                        rec = env[model].sudo().browse(rid)
                        val = rec[field] if field in rec._fields else False
                        raw = base64.b64decode(val) if val else b""
                    elif rest and rest[0].isdigit():
                        # /web/image/<attachment_id>[/filename]
                        att = env["ir.attachment"].sudo().browse(int(rest[0]))
                        raw = att.raw or b""
                        mime = att.mimetype or mime
                    if raw is not None:
                        return {"string": raw, "mime_type": mime}
            except Exception:  # pragma: no cover - fall back to default
                _logger.debug("elksbulletin url_fetcher fallback for %s", url)
            return weasyprint.default_url_fetcher(url)

        return fetcher
