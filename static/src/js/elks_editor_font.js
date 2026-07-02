/** @odoo-module */
// =============================================================================
// === HUMAN ===
// Adds a "Bulletin" choice to the text editor's font dropdown. It's the house
// newsletter font (a compact serif) and it's what every new bulletin uses by
// default — the tight, newspaper-style line spacing (about 5 px between lines)
// is set on the page itself (see newsletter_paper_canvas.scss for the editor
// and the report stylesheet for the PDF), so text reads tight the moment you
// start typing. Picking "Bulletin" again from the dropdown re-applies the font
// to any text whose font was changed.
//
// === AI AGENT ===
// The font control the user actually sees in the mailing editor is the DESIGN
// TAB font picker (mass_mailing/builder/fontfamily_picker.js), NOT the html
// text-toolbar font-family dropdown. That picker renders an exported plain
// object `FONT_FAMILIES` {Label: "css,stack"}; adding a key adds a choice.
// This is the primary registration. We give "Bulletin" a stack that leads with
// Georgia (matches the report `body { font-family: Georgia, ... }` so editor
// and PDF agree) but is a DISTINCT string from the built-in "Georgia" entry so
// the picker shows "Bulletin" (not "Georgia") when selected — BuilderSelect
// matches the active item by value.
// We ALSO add the same face to html_editor's toolbar list `fontFamilyItems`
// (font_family_plugin.js) for the per-selection font control, in case it is
// enabled. Both lists are shared singletons read when an editor opens, so
// mutating them once at module load is enough; guarded against double-add.
// IMPORTANT — a font-family choice only writes `font-family`; it cannot carry
// line-height. The "5 px between lines" is the page default in CSS
// (`.o_elksbulletin` -> line-height: calc(1em + 5px)) in both the editor canvas
// SCSS and the report template — which is also why newsletters are tight by
// default without selecting anything. Loaded in mass_mailing.assets_builder;
// needs a server restart to take effect (JS asset).
// =============================================================================
import { FONT_FAMILIES } from "@mass_mailing/builder/fontfamily_picker";
import { fontFamilyItems } from "@html_editor/main/font/font_family_plugin";

// The Grand Lodge body face. Distinct stack string from the built-in "Georgia"
// so the Design-tab picker labels the active choice "Bulletin".
const BULLETIN_STACK = "Georgia,'Times New Roman',Times,serif";

// (1) Design-tab picker (the visible control).
if (!("Bulletin" in FONT_FAMILIES)) {
    FONT_FAMILIES.Bulletin = BULLETIN_STACK;
}

// (2) Text-toolbar font-family dropdown (if shown).
if (!fontFamilyItems.some((item) => item.nameShort === "Bulletin")) {
    fontFamilyItems.push({
        name: "Bulletin",
        nameShort: "Bulletin",
        fontFamily: BULLETIN_STACK,
    });
}
