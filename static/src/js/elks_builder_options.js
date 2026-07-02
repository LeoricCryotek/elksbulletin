/** @odoo-module */
// =============================================================================
// === HUMAN ===
// Adds two controls to the editor's Style panel for Lodge blocks:
//   • Width — set a data block to Full / Two-Thirds / Half / One-Third so blocks
//     can sit side by side instead of always full width.
//   • Officer — on the Message Block, pick whose message it is (Exalted Ruler,
//     Leading Knight, ...); the photo, name and title then auto-fill from that
//     officer at print.
//
// === AI AGENT ===
// html_builder option components (BaseOptionComponent + static selector),
// registered via a Plugin into the "mass_mailing-plugins" registry. The XML
// templates use the declarative builder widgets (BuilderRow / BuilderSelect /
// BuilderSelectItem). Width uses classAction (o_elks_w_* classes, styled in the
// report + editor CSS). Officer uses dataAttributeAction="elksOfficer" ->
// data-elks-officer, which elks.bulletin.issue._render_print_body reads to fill
// the title + byline. Loaded in mass_mailing.assets_builder. Needs a server
// restart (JS asset) to take effect.
// =============================================================================
import { BaseOptionComponent } from "@html_builder/core/utils";
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";

const SIZE_SELECTOR = [
    ".s_elks_new_members", ".s_elks_project_dollars", ".s_elks_delinquents",
    ".s_elks_charity", ".s_elks_calendar", ".s_elks_upcoming_events",
    ".s_elks_events", ".s_elks_officers", ".s_elks_in_memoriam",
].join(", ");

export class ElksSizeOption extends BaseOptionComponent {
    static template = "elksbulletin.SizeOption";
    static selector = SIZE_SELECTOR;
    static groups = ["base.group_user"];
}

export class ElksMessageOption extends BaseOptionComponent {
    static template = "elksbulletin.MessageOption";
    static selector = ".s_elks_message";
    static groups = ["base.group_user"];
}

class ElksBulletinOptionsPlugin extends Plugin {
    static id = "elksbulletin.Options";
    resources = {
        builder_options: [ElksSizeOption, ElksMessageOption],
    };
}

registry
    .category("mass_mailing-plugins")
    .add(ElksBulletinOptionsPlugin.id, ElksBulletinOptionsPlugin);
