# -*- coding: utf-8 -*-
# =============================================================================
# === HUMAN ===
# The "Preview (data)" fast preview. Renders the newsletter as a plain HTML page
# with all the dynamic blocks (New Members, Charity, Leaderboard, In Memoriam,
# Calendar, ...) filled in with real lodge data — in a fraction of a second,
# with NO PDF and no WeasyPrint. Open it in a browser tab while editing to see
# exactly what data will appear, then refresh after each change. The final PDF
# still uses the same resolver, so this is a faithful data preview (only true
# page breaks / continuation bars differ, since those need the PDF engine).
#
# === AI AGENT ===
# GET /elksbulletin/preview/<id>, auth="user". Reuses the QWeb report template
# via report._render_qweb_html (the same template the PDF path renders, which
# calls elks.bulletin.issue._render_print_body) and returns it as text/html so
# the browser renders it inline (a /web/content attachment would be served as a
# download for .html). Access is enforced with record.check_access("read") so a
# user can only preview issues they may read. NOTE: the emoji @font-face points
# at an ir.attachment served by the PDF url_fetcher, which isn't used for this
# HTML view — the browser just falls back to its own emoji rendering, which is
# fine for a data preview. Great Vibes + images load over normal HTTP.
# =============================================================================
from odoo import http
from odoo.http import request


class ElksBulletinPreview(http.Controller):

    @http.route(
        "/elksbulletin/preview/<int:issue_id>",
        type="http",
        auth="user",
        website=False,
        sitemap=False,
        methods=["GET"],
    )
    def preview_html(self, issue_id, **kw):
        issue = request.env["elks.bulletin.issue"].browse(issue_id).exists()
        if not issue:
            return request.not_found()
        # Only render issues the current user is allowed to read.
        issue.check_access("read")

        xmlid = ("elksbulletin.action_report_bulletin_legal"
                 if issue.page_size == "legal"
                 else "elksbulletin.action_report_bulletin_letter")
        report = request.env.ref(xmlid)
        html, _type = report.sudo()._render_qweb_html(
            report.report_name, issue.ids)
        if isinstance(html, bytes):
            html = html.decode("utf-8")

        # Screen-only CSS so the preview looks like a real sheet of paper
        # (Letter width, page margins, centered on a grey desk) instead of
        # flowing at full browser width. Targets ".article" — Odoo's guaranteed
        # report wrapper — and is injected at the END of <body> so it beats the
        # report's own in-body <style>. The PDF is unaffected (WeasyPrint sizes
        # by @page, ignoring @media screen). Legal issues just show a slightly
        # narrower sheet than their true 8.5in — fine for a data preview.
        page_w = "8.5in"
        # Preview-only paper CSS. Two things to note:
        #   1. `.article` is pinned to 8.5in wide and centered so the
        #      browser shows a true-size sheet (not scaled to viewport).
        #   2. Images MUST get max-width:100% + height:auto or a large
        #      image (like the "Volunteers Needed" flyer) renders at its
        #      native pixel size and pushes its column past the 8.5in
        #      article, giving the false impression that the preview is
        #      "scaling" — the article is fine, one runaway <img> is
        #      just overflowing it. `object-fit:contain` keeps aspect
        #      ratio inside the constraint.
        # Constrain the whole <body> (always present, unlike an inner wrapper
        # class) to a centered Letter-width sheet. Targeting body is bulletproof;
        # .article-based attempts didn't take because the report's own in-body
        # styles / structure won out. Images and tables are clamped to the sheet
        # width so a large flyer can't overflow and make it look like the page is
        # "scaling".
        # Plain concatenation, NOT %-formatting: this CSS contains literal '%'
        # (max-width:100%) that %-formatting would misread as format specifiers
        # (that once 500'd the whole preview). page_w is the only variable.
        paper_css = (
            "<style>@media screen{"
            "html{background:#dfdce6 !important;}"
            "body{width:" + page_w + " !important;max-width:" + page_w
            + " !important;"
            "margin:18px auto !important;"
            "padding:0.42in 0.42in 0.58in 0.42in !important;"
            "background:#ffffff !important;box-sizing:border-box !important;"
            "overflow-x:hidden !important;"
            "box-shadow:0 0 0 1px #cfcfcf,0 6px 24px rgba(0,0,0,.25) !important;}"
            "body .container,body .container-fluid{"
            "width:100% !important;max-width:100% !important;}"
            "body img{max-width:100% !important;height:auto !important;"
            "max-height:9in !important;}"
            "body table{max-width:100% !important;}"
            "}</style>"
        )
        if "</body>" in html:
            html = html.replace("</body>", paper_css + "</body>", 1)
        else:
            html = html + paper_css
        return request.make_response(
            html, headers=[("Content-Type", "text/html; charset=utf-8")])
