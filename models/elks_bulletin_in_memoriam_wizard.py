# -*- coding: utf-8 -*-
# =============================================================================
# === HUMAN ===
# The "Choose Who Appears" dialogs for the New Members and In Memoriam blocks.
# Both blocks fill automatically by date; these pop-ups (opened by header
# buttons on the newsletter) let the receptionist fine-tune WHO shows —
# deselect anyone the automatic fill picked, or add someone it missed. They open
# pre-loaded with the current automatic result, so the default is still fully
# automatic; only when you Apply a change does the block switch to your curated
# list. "Reset to Automatic" returns to the pure date-based fill.
#
# === AI AGENT ===
# Two TransientModel wizards. Each is seeded (by the issue's
# action_select_* method) from the block's EFFECTIVE list, edited, then on Apply
# it sets the issue's <block>_manual flag and stores partner_ids; Reset clears
# both. Partner domains/contexts restrict + reveal the right contacts (members
# for New Members; deceased, incl. archived, for In Memoriam).
# =============================================================================
from odoo import fields, models


class ElksBulletinNewMemberWizard(models.TransientModel):
    _name = "elks.bulletin.new.member.wizard"
    _description = "Choose New Members to Show"

    issue_id = fields.Many2one(
        "elks.bulletin.issue", string="Newsletter",
        required=True, ondelete="cascade")
    partner_ids = fields.Many2many(
        "res.partner", "elks_bulletin_nm_wiz_rel", "wiz_id", "partner_id",
        string="Members to show",
        domain=[("x_is_member", "=", True)],
        help="Exactly the members the New Members block will show. Seeded with "
             "the automatic date fill — remove anyone you don't want, or add "
             "others.")

    def action_apply(self):
        """Take the block manual: store the chosen members and flag the issue
        so the block shows exactly this list (see _effective_new_members)."""
        self.ensure_one()
        self.issue_id.write({
            "new_member_manual": True,
            "new_member_partner_ids": [(6, 0, self.partner_ids.ids)],
        })
        return {"type": "ir.actions.act_window_close"}

    def action_reset_auto(self):
        """Back to automatic: clear the flag and the curated list so the block
        reverts to the date-based fill."""
        self.ensure_one()
        self.issue_id.write({
            "new_member_manual": False,
            "new_member_partner_ids": [(5, 0, 0)],
        })
        return {"type": "ir.actions.act_window_close"}


class ElksBulletinInMemoriamWizard(models.TransientModel):
    _name = "elks.bulletin.in.memoriam.wizard"
    _description = "Choose In Memoriam Members to Show"

    issue_id = fields.Many2one(
        "elks.bulletin.issue", string="Newsletter",
        required=True, ondelete="cascade")
    partner_ids = fields.Many2many(
        "res.partner", "elks_bulletin_im_wiz_rel", "wiz_id", "partner_id",
        string="Members to show",
        domain=[("x_drop_reason", "=", "deceased")],
        context={"active_test": False},
        help="Exactly the deceased members the In Memoriam block will show. "
             "Seeded with the automatic month fill — remove anyone, or add "
             "others (e.g. a late-reported death).")

    def action_apply(self):
        """Take the block manual: store the chosen members and flag the issue
        so In Memoriam shows exactly this list (see
        _effective_in_memoriam_members). NB the storage field is still named
        in_memoriam_extra_partner_ids for historical reasons — it now holds the
        full curated list, not just extras."""
        self.ensure_one()
        self.issue_id.write({
            "in_memoriam_manual": True,
            "in_memoriam_extra_partner_ids": [(6, 0, self.partner_ids.ids)],
        })
        return {"type": "ir.actions.act_window_close"}

    def action_reset_auto(self):
        """Back to automatic: clear the flag and the curated list so the block
        reverts to the month-window fill."""
        self.ensure_one()
        self.issue_id.write({
            "in_memoriam_manual": False,
            "in_memoriam_extra_partner_ids": [(5, 0, 0)],
        })
        return {"type": "ir.actions.act_window_close"}
