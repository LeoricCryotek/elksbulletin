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
import re
import urllib.request
from collections import defaultdict

from lxml import etree, html as lxml_html

from odoo import api, models
from odoo.tools import file_path as _odoo_file_path

# Emoji font auto-install (see _elks_ensure_emoji_font). Monochrome Noto Emoji
# (OFL) — one static TTF that renders on every WeasyPrint version.
EMOJI_FONT_URL = ("https://raw.githubusercontent.com/google/fonts/main/"
                  "ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf")
EMOJI_FONT_REL = "static/fonts/NotoEmoji-Regular.ttf"
# The font is stored as an ir.attachment under this name when it can't be
# written into the module folder (the common case: module dir owned by root,
# Odoo runs as a non-root user). The report url_fetcher serves it from here.
EMOJI_FONT_ATTACH = "elksbulletin_NotoEmoji-Regular.ttf"
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
            # Engine selection. DEFAULT is now wkhtmltopdf (WebKit): it renders
            # the newsletter the way a browser does — which paginates this
            # layout correctly, whereas WeasyPrint could halt on tall/flex blocks
            # and drop everything after them. Set the system parameter
            # `elksbulletin.pdf_engine` = "weasyprint" to opt back into the
            # WeasyPrint pipeline (nicer CSS: gradients, CSS grid, @page
            # page-number footer, bundled monochrome emoji — but the pagination
            # fragility). The INFO line records which engine actually ran.
            engine = (self.env["ir.config_parameter"].sudo().get_param(
                "elksbulletin.pdf_engine", "wkhtmltopdf") or "wkhtmltopdf")
            engine = engine.strip().lower()
            if weasyprint and engine == "weasyprint":
                # Errors surface (no silent fallback) so layout problems can be
                # fixed rather than masked.
                _logger.info(
                    "elksbulletin: rendering %s with WeasyPrint %s (forced by "
                    "system parameter elksbulletin.pdf_engine)",
                    report.report_name, weasyprint.__version__)
                return self._render_bulletin_weasyprint(report_ref, res_ids, data)
            if engine == "chromium":
                # Headless Chromium (Blink) renders the newsletter exactly like a
                # browser: correct pagination on this flex/tall-block layout AND
                # full-colour emoji from the platform emoji font — the one engine
                # that gives us both. If Chromium/Playwright isn't available or
                # the render fails, we fall through to wkhtmltopdf rather than
                # error the print (graceful degrade), with a warning naming why.
                try:
                    _logger.info(
                        "elksbulletin: rendering %s with headless Chromium "
                        "(elksbulletin.pdf_engine=chromium)", report.report_name)
                    return self._render_bulletin_chromium(
                        report_ref, res_ids, data)
                except Exception:
                    _logger.warning(
                        "elksbulletin: Chromium render failed; falling back to "
                        "wkhtmltopdf. Install a chromium/chrome binary (or the "
                        "Playwright chromium) on the server to use this engine.",
                        exc_info=True)
            else:
                _logger.info(
                    "elksbulletin: rendering %s with wkhtmltopdf (default engine; "
                    "set elksbulletin.pdf_engine=weasyprint or =chromium to "
                    "change)", report.report_name)
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
    # Builds the PDF with headless Chromium (a real browser engine). Chromium
    # paginates this newsletter the same way the on-screen Preview does, and — the
    # whole reason to use it — prints the emoji in full colour straight from the
    # system emoji font, so the printed PDF matches what you see in the editor.
    # The lodge/page-number/date footer is drawn by Chromium's own print footer.
    # === AI AGENT ===
    # Render the newsletter HTML, INLINE every external resource (images, the
    # Great Vibes masthead font) into data: URIs via the same ORM url_fetcher the
    # WeasyPrint path uses — so Chromium renders fully offline with no auth round
    # trip — then convert with Chromium. Two backends, tried in order:
    #   1. Playwright (page.pdf): honours @page size/margins via
    #      prefer_css_page_size, prints backgrounds, and draws a footer_template
    #      that reproduces the WeasyPrint @bottom-* page-number footer.
    #   2. A system chromium/chrome binary via `--headless --print-to-pdf`
    #      (no custom footer; --no-pdf-header-footer). Path can be pinned with
    #      the system parameter elksbulletin.chromium_path.
    # Any failure raises to the dispatcher, which degrades to wkhtmltopdf.
    def _render_bulletin_chromium(self, report_ref, res_ids, data):
        report = self._get_report(report_ref)
        html, _type = self._render_qweb_html(report_ref, res_ids, data=data)
        if isinstance(html, bytes):
            html = html.decode("utf-8")
        icp = self.env["ir.config_parameter"].sudo()
        base_url = icp.get_param("web.base.url") or ""
        fetcher = self._bulletin_url_fetcher(base_url)
        html = self._bulletin_inline_resources(html, base_url, fetcher)
        # Make Chromium honour our background colours/gradients (the masthead
        # bar, leaderboard shading) even on the CLI path where there's no
        # print_background flag: print-color-adjust:exact forces them to print.
        inject = ("<style>*{-webkit-print-color-adjust:exact !important;"
                  "print-color-adjust:exact !important;}</style>")
        # A <base> so any resource we DIDN'T inline (e.g. the calendar's
        # FontAwesome <link> stylesheet + its font) still resolves — Chromium
        # fetches those public /web/static assets over HTTP from the live site.
        # Images and the masthead font are already inlined as data: URIs, so no
        # authenticated URLs are fetched this way.
        if base_url:
            inject = '<base href="%s/">' % base_url.rstrip("/") + inject
        if "<head>" in html:
            html = html.replace("<head>", "<head>" + inject, 1)
        elif "</head>" in html:
            html = html.replace("</head>", inject + "</head>", 1)
        else:
            html = inject + html
        doc = None
        if res_ids:
            doc = self.env[report.model].sudo().browse(res_ids[0]).exists()
        pdf = self._bulletin_chromium_pdf(html, doc)
        if not pdf:
            raise RuntimeError("Chromium produced no PDF output")
        return pdf, "pdf"

    # === AI AGENT ===
    # Rewrite <img src> and CSS font url()s into self-contained data: URIs using
    # `fetcher` (the ORM resolver). Leaves anything it can't resolve untouched.
    # This is what lets Chromium render without hitting the Odoo HTTP stack.
    def _bulletin_inline_resources(self, html, base_url, fetcher):
        try:
            frag = lxml_html.fromstring(html)
        except Exception:
            return html

        def to_data_uri(url):
            if not url or url.startswith("data:"):
                return None
            try:
                res = fetcher(url)
            except Exception:
                return None
            if not res or not res.get("string"):
                return None
            raw = res["string"]
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
            mime = res.get("mime_type") or "application/octet-stream"
            return "data:%s;base64,%s" % (
                mime, base64.b64encode(raw).decode("ascii"))

        for img in frag.xpath("//img[@src]"):
            du = to_data_uri(img.get("src"))
            if du:
                img.set("src", du)

        url_re = re.compile(
            r"url\(\s*['\"]?([^'\")]+\.(?:ttf|otf|woff2?|eot))(?:\?[^'\")]*)?"
            r"['\"]?\s*\)", re.I)

        def repl(m):
            du = to_data_uri(m.group(1))
            return "url('%s')" % du if du else m.group(0)

        for style_el in frag.xpath("//style"):
            css = style_el.text or ""
            if "url(" in css:
                style_el.text = url_re.sub(repl, css)
        return lxml_html.tostring(frag, encoding="unicode")

    # === AI AGENT ===
    # HTML -> PDF bytes via Chromium. Prefers Playwright (better control + a real
    # page-number footer); falls back to a system chrome binary on the CLI.
    def _bulletin_chromium_pdf(self, html, doc):
        legal = bool(doc) and getattr(doc, "page_size", "") == "legal"
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return self._bulletin_chromium_pdf_cli(html, legal)
        footer = self._bulletin_chromium_footer(doc)
        # Reuse a system-installed chromium/chrome so the server only needs the
        # small `playwright` Python package — NOT Playwright's ~300MB bundled
        # browser download (which also needs `playwright install`). Prefer an
        # explicit elksbulletin.chromium_path, else AUTO-DETECT a binary on PATH.
        # Without this, Playwright looks for its own un-downloaded browser and
        # fails ("Executable doesn't exist ..."). On Debian the binary is
        # /usr/bin/chromium (apt package `chromium`, not `chromium-browser`).
        # Browser selection. DEFAULT is Playwright's OWN bundled browser build
        # (install it with `playwright install chromium`), because Playwright
        # pins its driver to a specific browser revision — pointing it at a
        # much newer SYSTEM chromium (e.g. Debian's 151) makes the CDP pipe
        # handshake fail and the browser dies on launch with SIGTRAP /
        # "Target ... has been closed". Only use a system binary when the admin
        # explicitly opts in via elksbulletin.chromium_path (and accepts the
        # version-match caveat).
        exe = self.env["ir.config_parameter"].sudo().get_param(
            "elksbulletin.chromium_path")
        launch_kwargs = {"args": ["--no-sandbox"]}
        if exe:
            launch_kwargs["executable_path"] = exe
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                page.emulate_media(media="print")
                pdf = page.pdf(
                    prefer_css_page_size=True,   # honour the report's @page size
                    print_background=True,
                    display_header_footer=True,
                    header_template="<span></span>",
                    footer_template=footer,
                )
            finally:
                browser.close()
        return pdf

    # === AI AGENT ===
    # Chromium print footer that reproduces the WeasyPrint @bottom-* boxes:
    # lodge name (left), "Page N of M" (centre), issue month (right). Chromium
    # substitutes .pageNumber / .totalPages; font-size must be set inline or the
    # footer renders microscopic.
    def _bulletin_chromium_footer(self, doc):
        from markupsafe import escape as _esc
        lodge = str(_esc(getattr(doc, "lodge_name", "") or "")) if doc else ""
        month = ""
        if doc and getattr(doc, "issue_date", False):
            month = str(_esc(doc.issue_date.strftime("%B %Y")))
        # NB: plain concatenation, not %-formatting — the CSS contains literal
        # '%' (width:100%) that would be misread as format specifiers.
        return (
            '<div style="width:100%;font:8.5pt Arial,sans-serif;color:#3f2566;'
            'padding:0 0.42in;box-sizing:border-box;">'
            '<span style="float:left;">' + lodge + ' · B.P.O.E.</span>'
            '<span style="float:right;">' + month + '</span>'
            '<span style="display:block;text-align:center;font-weight:bold;">'
            'Page <span class="pageNumber"></span> of '
            '<span class="totalPages"></span></span></div>')

    # === AI AGENT ===
    # CLI fallback: find a chromium/chrome binary and print via
    # --headless --print-to-pdf. No custom footer (Chrome's default is
    # suppressed with --no-pdf-header-footer). @page size/margins come from CSS.
    def _bulletin_chromium_pdf_cli(self, html, legal):
        import os
        import shutil
        import subprocess
        import tempfile
        icp = self.env["ir.config_parameter"].sudo()
        binary = (icp.get_param("elksbulletin.chromium_path")
                  or shutil.which("chromium")
                  or shutil.which("chromium-browser")
                  or shutil.which("google-chrome")
                  or shutil.which("google-chrome-stable")
                  or shutil.which("chrome"))
        if not binary:
            raise RuntimeError(
                "no chromium/chrome binary found (set elksbulletin.chromium_path "
                "or install chromium)")
        with tempfile.TemporaryDirectory() as d:
            hp = os.path.join(d, "bulletin.html")
            op = os.path.join(d, "bulletin.pdf")
            with open(hp, "w", encoding="utf-8") as fh:
                fh.write(html)
            cmd = [
                binary, "--headless=new", "--no-sandbox", "--disable-gpu",
                "--no-pdf-header-footer",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=10000",
                "--print-to-pdf=" + op, "file://" + hp,
            ]
            proc = subprocess.run(
                cmd, timeout=120, capture_output=True)
            if not os.path.exists(op):
                raise RuntimeError(
                    "chromium --print-to-pdf produced no file (%s)"
                    % (proc.stderr[-400:].decode("utf-8", "replace")))
            with open(op, "rb") as fh:
                return fh.read()

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
        # The continuation + pin-to-bottom two-pass is now OPT-IN and OFF by
        # default: it re-renders and rewrites the whole document, and a bad
        # measurement (a pinned block, or a story boundary) could insert a filler
        # that halts pagination and drops content — a much worse failure than
        # simply not drawing the auto "Continued on page #" bars. Enable it only
        # once it's proven safe on a lodge's real content: system parameter
        # elksbulletin.enable_layout_pass = 1. (The old
        # elksbulletin.disable_layout_pass is still honored as a hard off.)
        cfg = self.env["ir.config_parameter"].sudo()
        if (not cfg.get_param("elksbulletin.enable_layout_pass")
                or cfg.get_param("elksbulletin.disable_layout_pass")):
            return html
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
        # Blocks the editor flagged "Pin to page bottom" (Style panel) — pushed
        # down to sit at the bottom of the page they land on (see below).
        pin_xpath = (".//*[contains(concat(' ', normalize-space(@class), ' '),"
                     " ' o_elks_pin_bottom ')]")
        pinned = frag.xpath(pin_xpath)
        if not flow_containers and not pinned:
            return html  # nothing to check

        # --- pass 1: render once; read the REAL page layout ---------------
        document = weasyprint.HTML(
            string=html, base_url=base_url, url_fetcher=fetcher,
        ).render()
        # Diagnostic: how many pages the PLAIN resolved body produced, before we
        # add any continuation markers or pin fillers. If this is already 1 while
        # the newsletter clearly has more content, the collapse is in the content
        # itself (e.g. an unbreakable box taller than the page), NOT this pass.
        _logger.info(
            "elksbulletin: layout pass 1 = %d page(s); %d story flow(s), "
            "%d pinned block(s).",
            len(document.pages), len(flow_containers), len(pinned))

        element_pages = defaultdict(set)
        # For pinned blocks we need the geometry of their principal box, keyed
        # by the box's source element identity (stable within this one render).
        pin_geom = {}          # id(element) -> (page_idx, box_top, box_height)
        page_bottoms = {}      # page_idx    -> usable content-area bottom (px)

        def _has_cls(el, cls):
            return (" " + (el.get("class") or "") + " ").find(" " + cls + " ") >= 0

        def walk(box, page_idx):
            el = getattr(box, "element", None)
            if el is not None:
                eid = el.get("id")
                if eid and eid.startswith("elks-flow-"):
                    element_pages[eid].add(page_idx)
                if _has_cls(el, "o_elks_pin_bottom"):
                    key = id(el)
                    if key not in pin_geom:  # keep the first (principal) box
                        # Bottom margin edge = border-box top (position_y) +
                        # border_height (border+padding+content) + margin_bottom.
                        # box.height alone is CONTENT height and undershoots.
                        try:
                            outer_bottom = (box.position_y
                                            + box.border_height()
                                            + getattr(box, "margin_bottom", 0.0))
                        except Exception:
                            outer_bottom = (getattr(box, "position_y", 0.0)
                                            + (getattr(box, "height", 0.0) or 0.0))
                        pin_geom[key] = (page_idx, outer_bottom)
            for child in getattr(box, "children", None) or []:
                walk(child, page_idx)

        for page_idx, page in enumerate(document.pages):
            pb = page._page_box
            # Usable bottom of the printable area = top margin + content height.
            page_bottoms[page_idx] = (getattr(pb, "margin_top", 0.0)
                                      + (getattr(pb, "height", 0.0) or 0.0))
            walk(pb, page_idx)

        # --- pin-to-bottom: insert a filler above each pinned block so its
        #     bottom edge lands on the page's bottom margin. Geometry came from
        #     the render above, so the filler height is exact; because it goes
        #     directly before the block, everything above is undisturbed and the
        #     block simply drops to the bottom of the SAME page. Matched in
        #     document order (render order == frag order). Guarded per-block.
        pinned_changed = False
        geoms = list(pin_geom.values())  # document order (pages then DFS)
        for elem, geom in zip(pinned, geoms):
            try:
                page_idx, outer_bottom = geom
                usable_bottom = page_bottoms.get(page_idx)
                if not usable_bottom:
                    continue
                gap = usable_bottom - outer_bottom - 4  # 4px safety
                # Safety clamp: never insert a filler taller than the remaining
                # page. A bad/zero measurement could otherwise inject a giant
                # empty box that itself overflows the page and breaks pagination.
                if gap < 8 or gap >= usable_bottom:
                    continue  # already near the bottom, or measurement is off
                filler = etree.Element(
                    "div", **{"class": "s_elks_pin_filler"})
                filler.set("style", "height:%dpx;" % int(gap))
                elem.addprevious(filler)
                pinned_changed = True
            except Exception:
                continue

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

        if not inserted and not pinned_changed:
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
                        # The emoji font may live in an ir.attachment instead of
                        # on disk (module dir read-only) — serve it from there.
                        if clean.endswith(EMOJI_FONT_REL):
                            att = env["ir.attachment"].sudo().search(
                                [("name", "=", EMOJI_FONT_ATTACH)], limit=1)
                            if att and att.raw:
                                return {"string": att.raw,
                                        "mime_type": "font/ttf"}
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
                        # Trust boundary: these URLs come from newsletter body
                        # HTML authored by Editor/Publisher-group officers (a
                        # trusted role) and the bytes are only composited into
                        # that same officer's PDF. We still restrict this branch
                        # to genuine BINARY fields so a stray/mistyped src can't
                        # pull a non-image field's value into the render.
                        model, rid, field = rest[0], int(rest[1]), rest[2]
                        rec = env[model].sudo().browse(rid)
                        f = rec._fields.get(field)
                        val = rec[field] if (f and f.type == "binary") else False
                        raw = base64.b64decode(val) if val else b""
                    if raw is not None:
                        return {"string": raw, "mime_type": mime}
            except Exception:  # pragma: no cover - fall back to default
                _logger.debug("elksbulletin url_fetcher fallback for %s", url)
            return weasyprint.default_url_fetcher(url)

        return fetcher

    # === HUMAN ===
    # So a fresh install "just works" with emoji: on install AND every module
    # upgrade this fetches the (free, OFL) Noto Emoji font and stores it where
    # the printed newsletter can find it. That's the one file emoji need, and
    # it's what was 404'ing before. Runs once (skips if already present); never
    # blocks install.
    # === AI AGENT ===
    # Called by data/emoji_font_install.xml's <function> on load (install + -u).
    # Downloads EMOJI_FONT_URL and stores it as an ir.attachment named
    # EMOJI_FONT_ATTACH. Attachment (not the module folder) because the module
    # dir is typically root-owned while Odoo runs non-root, so writing the file
    # there fails with PermissionError; the filestore is always writable. The
    # report url_fetcher serves the @font-face 'Elks Emoji' request
    # (/elksbulletin/static/fonts/NotoEmoji-Regular.ttf) from disk if a committed
    # copy exists, else from this attachment. Idempotent, validates the bytes are
    # a real font (not an HTML error page), 30s-bounded network I/O, and swallows
    # every error with a clear warning (manual fallback: static/fonts/README.md).
    @api.model
    def _elks_ensure_emoji_font(self):
        try:
            # Already committed on disk? Then nothing to do.
            try:
                _odoo_file_path("elksbulletin/" + EMOJI_FONT_REL)
                return True
            except Exception:
                pass
            Att = self.env["ir.attachment"].sudo()
            existing = Att.search([("name", "=", EMOJI_FONT_ATTACH)], limit=1)
            if existing and existing.raw and len(existing.raw) > 50000:
                return True  # already stored
            req = urllib.request.Request(
                EMOJI_FONT_URL, headers={"User-Agent": "elksbulletin"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if not data or data[:4] not in _FONT_MAGIC:
                _logger.warning(
                    "elksbulletin: emoji-font download was not a font (%d bytes);"
                    " emoji will not print until the font is added manually "
                    "(see static/fonts/README.md).", len(data or b""))
                return False
            vals = {
                "name": EMOJI_FONT_ATTACH, "type": "binary",
                "raw": data, "mimetype": "font/ttf",
            }
            (existing.write(vals) if existing else Att.create(vals))
            _logger.info(
                "elksbulletin: emoji font stored as attachment '%s' (%d bytes)",
                EMOJI_FONT_ATTACH, len(data))
            return True
        except Exception as err:
            _logger.warning(
                "elksbulletin: could not auto-install the emoji font (%s). "
                "Emoji will print once the font is added (see "
                "static/fonts/README.md).", err)
            return False
