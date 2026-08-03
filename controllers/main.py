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
        # (Letter/Legal width, page margins, centered on a grey desk) instead of
        # flowing at full browser width. This makes the data preview reflect the
        # printed layout — text wraps and images size as they will on paper —
        # without affecting the PDF (WeasyPrint uses @page, not this).
        page_w = "8.5in"
        pad = "0.42in 0.42in 0.58in 0.42in"
        paper_css = (
            "<style>@media screen{"
            "html,body{background:#dfdce6!important;margin:0!important;}"
            ".article{padding:18px 0!important;}"
            ".o_elksbulletin{width:%s!important;max-width:%s!important;"
            "margin:0 auto!important;padding:%s!important;background:#fff!important;"
            "box-sizing:border-box!important;"
            "box-shadow:0 0 0 1px #cfcfcf,0 6px 24px rgba(0,0,0,.25)!important;}"
            ".o_elksbulletin img{max-height:9in;}"
            "}</style>" % (page_w, page_w, pad)
        )
        if "</head>" in html:
            html = html.replace("</head>", paper_css + "</head>", 1)
        else:
            html = paper_css + html
        return request.make_response(
            html, headers=[("Content-Type", "text/html; charset=utf-8")])
