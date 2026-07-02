# -*- coding: utf-8 -*-
# =============================================================================
# === HUMAN ===
# Prints the Lodge Newsletter with a modern print engine (WeasyPrint) instead of
# Odoo's default wkhtmltopdf, so blocks never bleed across page cuts, page
# sizing / page numbers are exact, and long stories automatically get
# "Continued on page #" / "(Continued from page #)" bars exactly where they
# break. Only the newsletter reports use this; every other report in the system
# prints normally. If WeasyPrint isn't installed on the server, printing falls
# back to the standard engine (page breaks still work; the auto "Continued"
# bars and page-number footer don't) and a warning names what's missing.
#
# === AI AGENT ===
# Overrides ir.actions.report._render_qweb_pdf. For our two report_names it
# renders the QWeb to HTML (_render_qweb_html), runs the two-pass
# auto-continuation marker insertion (_bulletin_insert_continuation_markers),
# and pipes the result through WeasyPrint, which has real CSS paged-media
# support (break-inside: avoid, @page size/margins + @bottom margin boxes with
# counter(page)). A url_fetcher resolves /web/image and /web/content URLs via
# the ORM so member photos / dragged images render without an authenticated
# HTTP round-trip, and serves /<module>/static/* assets straight off disk (the
# calendar's bundled Font Awesome CSS + font); data: URIs (masthead logo,
# computed photos) need no fetch.
# WeasyPrint is a SOFT dependency with two distinct behaviors:
#   * absent/unloadable -> super() (wkhtmltopdf) + a WARNING naming the cause.
#     The import guard catches Exception, NOT just ImportError: on macOS a
#     missing native lib raises OSError from cffi's dlopen at import time, and
#     that once took down the whole registry at server start.
#   * present but a render error -> the error SURFACES (no silent fallback
#     that would mask layout bugs).
# Model/report changes need -u elksbulletin; this controller-style Python
# needs a server restart.
# =============================================================================
import base64
import logging
import mimetypes
import os
import re
import urllib.request
from collections import defaultdict

from lxml import etree, html as lxml_html

from odoo import api, models
from odoo.modules.module import get_module_path
from odoo.tools import file_path as _odoo_file_path

# Emoji font auto-install (see _elks_ensure_emoji_font). Monochrome Noto Emoji
# (OFL) — one static TTF that renders on every WeasyPrint version.
EMOJI_FONT_URL = ("https://raw.githubusercontent.com/google/fonts/main/"
                  "ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf")
EMOJI_FONT_REL = "static/fonts/NotoEmoji-Regular.ttf"
# sfnt / web-font magic numbers used to sanity-check the download is a real font
# and not an HTML error page.
_FONT_MAGIC = (b"\x00\x01\x00\x00", b"true", b"ttcf", b"OTTO", b"wOFF", b"wOF2")

_logger = logging.getLogger(__name__)

try:
    import weasyprint
except Exception as _wp_err:  # pragma: no cover - optional dependency
    # NOT just ImportError: on macOS, WeasyPrint raises OSError from cffi's
    # dlopen at import time when the native Pango/GObject libraries are
    # missing or not on the loader path (needs `brew install pango` +
    # DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib in the environment that
    # launches Odoo). A soft dependency must never prevent the module — let
    # alone the whole registry — from loading; an uncaught OSError here once
    # took down server startup entirely.
    weasyprint = None
    logging.getLogger(__name__).warning(
        "elksbulletin: WeasyPrint unavailable (%s); newsletter PDFs will "
        "fall back to wkhtmltopdf until it is installed.", _wp_err)

BULLETIN_REPORTS = (
    "elksbulletin.report_bulletin_letter",
    "elksbulletin.report_bulletin_legal",
)


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    # === HUMAN ===
    # The traffic cop: newsletter reports go to WeasyPrint when it's available;
    # everything else (and the newsletter too, when WeasyPrint is missing) goes
    # to Odoo's normal print engine, with a log warning naming what to install.
    # DIAGNOSTIC: to test the legacy engine, set the system parameter
    # elksbulletin.pdf_engine = "wkhtmltopdf" (unset it to go back). Every
    # newsletter print logs which engine actually rendered it.
    # === AI AGENT ===
    # Engine dispatch. Only BULLETIN_REPORTS are affected. WeasyPrint present ->
    # our renderer, and its errors surface (a silent wkhtmltopdf fallback would
    # mask layout problems). WeasyPrint absent -> warn + super().
    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        if report.report_name in BULLETIN_REPORTS:
            # Engine toggle for diagnosis. Set the system parameter
            # `elksbulletin.pdf_engine` = "wkhtmltopdf" (Settings > Technical >
            # System Parameters) to force the legacy engine and compare output;
            # unset it or set "weasyprint" for the default. Either way the INFO
            # line below records which engine actually ran, so you can confirm
            # whether WeasyPrint is really active (rounded corners / gradients /
            # page-number footer only work under WeasyPrint).
            engine = (self.env["ir.config_parameter"].sudo().get_param(
                "elksbulletin.pdf_engine", "weasyprint") or "weasyprint")
            engine = engine.strip().lower()
            if weasyprint and engine != "wkhtmltopdf":
                # Do NOT silently swallow WeasyPrint errors into a wkhtmltopdf
                # fallback: that masks layout problems (page breaks / block
                # sizing don't work under wkhtmltopdf). Let errors surface so
                # they can be fixed. Only fall back when WeasyPrint is absent.
                _logger.info(
                    "elksbulletin: rendering %s with WeasyPrint %s",
                    report.report_name, weasyprint.__version__)
                return self._render_bulletin_weasyprint(report_ref, res_ids, data)
            if engine == "wkhtmltopdf":
                _logger.info(
                    "elksbulletin: rendering %s with wkhtmltopdf (forced by "
                    "system parameter elksbulletin.pdf_engine)",
                    report.report_name)
            else:
                _logger.warning(
                    "elksbulletin: WeasyPrint is not installed/loadable; "
                    "printing via wkhtmltopdf. Page breaks, per-block sizing, "
                    "rounded corners, gradients and the page-number footer all "
                    "require WeasyPrint (pip install weasyprint + Pango/Cairo).")
        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

    # === HUMAN ===
    # Builds the actual PDF: renders the finished newsletter page, adds the
    # automatic "Continued on page #" bars where stories really break, and
    # converts it with WeasyPrint at the exact paper size.
    # === AI AGENT ===
    # Render the newsletter HTML, insert continuation markers (two-pass layout
    # detection), and convert with WeasyPrint. Returns the same (bytes, 'pdf')
    # contract as the core method. Deliberately skips core's
    # _pre_render_qweb_pdf plumbing (attachment_use caching, test-mode HTML
    # fallback) — single-record newsletters don't benefit, tradeoff documented.
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
                # Static assets (e.g. the bundled Font Awesome CSS + font used by
                # the Lodge Calendar icons): serve straight off disk so they load
                # without an authenticated HTTP round-trip / correct base_url.
                # URL form: /<module>/static/<path-in-module> (?query stripped).
                clean = path.split("?")[0]
                if "/static/" in clean:
                    try:
                        rel = clean.lstrip("/")
                        abs_path = _odoo_file_path(
                            rel, filter_ext=(
                                ".css", ".woff2", ".woff", ".ttf", ".otf",
                                ".eot", ".svg", ".png", ".jpg", ".jpeg", ".gif"))
                        with open(abs_path, "rb") as fh:
                            raw = fh.read()
                        mime = (mimetypes.guess_type(abs_path)[0]
                                or "application/octet-stream")
                        return {"string": raw, "mime_type": mime}
                    except Exception:
                        _logger.debug(
                            "elksbulletin url_fetcher: static miss for %s", clean)
                if path.startswith("/web/image") or path.startswith("/web/content"):
                    seg = [p for p in path.split("?")[0].strip("/").split("/")]
                    rest = seg[2:]  # drop 'web','image'|'content'
                    raw, mime = None, "image/png"
                    first = rest[0] if rest else ""
                    lead = re.match(r"^(\d+)", first)
                    if lead and not first[:1].isalpha():
                        # /web/image/<id>[-<unique>][/<w>x<h>][/<filename>] — the
                        # form the editor writes for uploaded / related images
                        # (ir.attachment). Take the leading integer id; ignore any
                        # -unique suffix or trailing size/filename segments.
                        att = env["ir.attachment"].sudo().browse(int(lead.group(1)))
                        raw = att.raw or b""
                        mime = att.mimetype or mime
                    elif len(rest) >= 3:
                        # /web/image/<model>/<id>/<field>[/<filename>]
                        model, rid, field = rest[0], int(rest[1]), rest[2]
                        rec = env[model].sudo().browse(rid)
                        val = rec[field] if field in rec._fields else False
                        raw = base64.b64decode(val) if val else b""
                    if raw is not None:
                        return {"string": raw, "mime_type": mime}
            except Exception:  # pragma: no cover - fall back to default
                _logger.debug("elksbulletin url_fetcher fallback for %s", url)
            return weasyprint.default_url_fetcher(url)

        return fetcher

    # === HUMAN ===
    # So a fresh install "just works" with emoji: on install AND every module
    # upgrade this fetches the (free, OFL) Noto Emoji font into the module's
    # static/fonts/ folder if it isn't already there. That's the one file the
    # printed newsletter needs to show emoji, and it's what was 404'ing before.
    # Runs once (skips if the file is already present); never blocks install.
    # === AI AGENT ===
    # Called by data/emoji_font_install.xml's <function> on load (install + -u).
    # Downloads EMOJI_FONT_URL to <module>/static/fonts/NotoEmoji-Regular.ttf
    # (the path the report @font-face 'Elks Emoji' + url_fetcher expect).
    # Idempotent (size check), validates the bytes are a real font (not an HTML
    # error page), writes atomically, and swallows every error (offline server,
    # read-only module dir, etc.) with a clear warning pointing at the manual
    # fallback in static/fonts/README.md. Network I/O at load is deliberate and
    # bounded (30s timeout) — the lodge asked for a self-installing module.
    @api.model
    def _elks_ensure_emoji_font(self):
        try:
            base = get_module_path("elksbulletin")
            if not base:
                return False
            target = os.path.join(base, EMOJI_FONT_REL)
            if os.path.exists(target) and os.path.getsize(target) > 50000:
                return True  # already installed
            os.makedirs(os.path.dirname(target), exist_ok=True)
            req = urllib.request.Request(
                EMOJI_FONT_URL, headers={"User-Agent": "elksbulletin"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if not data or data[:4] not in _FONT_MAGIC:
                _logger.warning(
                    "elksbulletin: emoji-font download was not a font (%d bytes);"
                    " emoji will not print until static/fonts/NotoEmoji-Regular"
                    ".ttf is added manually (see that folder's README).",
                    len(data or b""))
                return False
            tmp = target + ".part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, target)
            _logger.info(
                "elksbulletin: emoji font installed (%d bytes) at %s",
                len(data), target)
            return True
        except Exception as err:
            _logger.warning(
                "elksbulletin: could not auto-install the emoji font (%s). "
                "Emoji will print once static/fonts/NotoEmoji-Regular.ttf is "
                "added (see that folder's README.md).", err)
            return False
