# -*- coding: utf-8 -*-
# =============================================================================
# === HUMAN ===
# A reusable starting layout for a newsletter. "Lodge Newsletter" is the default
# one — when you create a new issue it copies this template's content so you
# start from the branded masthead + blocks instead of a blank page.
#
# === AI AGENT ===
# elks.bulletin.template: name + is_default flag + body_html (the snippet
# canvas markup). body_html is unsanitized so editor snippet markup survives.
# One record is seeded in data/bulletin_template_data.xml. is_default picks the
# template used by new issues (see elks.bulletin.issue._default_template).
# =============================================================================
from odoo import fields, models


class ElksBulletinTemplate(models.Model):
    _name = "elks.bulletin.template"
    _description = "Lodge Newsletter Template"
    _order = "is_default desc, name"

    name = fields.Char(required=True)
    is_default = fields.Boolean(
        "Default Template",
        help="New newsletters start from the default template.")
    # Same field trio as an issue so the template is edited with the same
    # block builder. body_arch = edited layout; body_html = inlined output;
    # mailing_model_id is read by the editor widget (never sent).
    body_arch = fields.Html("Layout", sanitize=False)
    body_html = fields.Html("Layout (inlined)", sanitize=False)
    mailing_model_id = fields.Many2one(
        "ir.model", string="Editor Data Model",
        default=lambda self: self.env["ir.model"]._get_id("res.partner"))
