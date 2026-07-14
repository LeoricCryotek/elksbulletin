/** @odoo-module */
// =============================================================================
// === HUMAN ===
// Editor-side behavior for Lodge blocks — three things:
//   • Width (Style panel) — on the two structural blocks that can still sit
//     side by side (Lodge Officers, In Memoriam): Full / Two-Thirds / Half /
//     One-Third. The dynamic data blocks no longer need it — they're inner
//     content sized by whichever column you drop them into.
//   • Officer (Style panel) — on the Message Block, pick whose message it is
//     (Exalted Ruler, Leading Knight, ...); the photo, name and title then
//     auto-fill from that officer at print.
//   • Spacer height (Style panel) — on the Spacer block, set a preset or custom
//     vertical gap; use it to push a block (e.g. the Calendar) down the page.
//   • Pin to page bottom (Style panel) — on any full-width block, drop it to the
//     bottom of the page it lands on (the report's two-pass layout does the push).
//   • Page-turn preview — content after a Page Break is pushed down to the
//     next red page-boundary line on the canvas, so the editor shows the page
//     turn the way the PDF will print it.
//
// === AI AGENT ===
// html_builder option components (BaseOptionComponent + static selector) and a
// Plugin, registered into the "mass_mailing-plugins" registry. The XML
// templates use the declarative builder widgets (BuilderRow / BuilderSelect /
// BuilderSelectItem). Width uses classAction (o_elks_w_* classes, styled in
// the report + editor CSS); its selector covers ONLY blocks that remain
// structural sections — legacy documents with old sized sections keep
// rendering, they just don't get the panel. Officer uses classAction
// o_elks_officer_<pos>; a class (not data-attribute) because classes reliably
// survive the email inliner, and elks.bulletin.issue._render_print_body reads
// it to fill the title + byline. The PageBreakPreview plugin is documented at
// its definition below. Loaded in mass_mailing.assets_builder. Needs a server
// restart (JS asset) to take effect.
// =============================================================================
import { BaseOptionComponent } from "@html_builder/core/utils";
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";

// Width applies only to blocks that are still STRUCTURAL sections; the
// dynamic data blocks are true inner content as of 19.0.1.1.0 — dropped inside
// a layout column, which is what sizes them — so a per-block Width would be
// meaningless (and o_elks_w_* CSS is scoped to sections). Legacy documents
// with old sized sections keep rendering fine; they just don't get the panel.
const SIZE_SELECTOR = [
    ".s_elks_officers",
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

// Spacer height (Style panel): the Spacer block is an empty section whose only
// job is vertical space. Height is written as an inline style on the section
// (BuilderNumberInput/SelectItem styleAction="height"), so the same value drives
// the editor canvas AND the printed PDF — no class round-tripping needed.
export class ElksSpacerOption extends BaseOptionComponent {
    static template = "elksbulletin.SpacerOption";
    static selector = ".s_elks_spacer";
    static groups = ["base.group_user"];
}

// Pin to page bottom (Style panel): a simple class toggle on a full-width
// section. The class does nothing on its own in print — at render the report's
// two-pass layout (ir_actions_report._bulletin_insert_continuation_markers_inner)
// measures where the block lands and inserts a filler above it so its bottom
// edge sits on the page's bottom margin. Excluded from utility blocks (Page
// Break, Spacer) where pinning is meaningless.
export class ElksPinBottomOption extends BaseOptionComponent {
    static template = "elksbulletin.PinBottomOption";
    static selector =
        "section.o_mail_snippet_general:not(.s_elks_page_break):not(.s_elks_spacer)";
    static groups = ["base.group_user"];
}

class ElksBulletinOptionsPlugin extends Plugin {
    static id = "elksbulletin.Options";
    resources = {
        builder_options: [
            ElksSizeOption, ElksMessageOption,
            ElksSpacerOption, ElksPinBottomOption,
        ],
    };
}

// =============================================================================
// === HUMAN ===
// Makes the editing canvas actually SHOW the page turn: content after a Page
// Break block is pushed down to the next red page-boundary line, the same way
// the PDF will start it on a new page — instead of the dashed line just sitting
// in the middle of continuously flowing content.
//
// === AI AGENT ===
// The iframe asset bundle (mass_mailing.assets_inside_builder_iframe) is
// SCSS-only in core, and CSS alone cannot compute "distance to the next
// multiple of --elks-page-h" — so this runs as a builder Plugin in the top
// frame (mass_mailing.assets_builder, same bundle as the options above), which
// owns the iframe via this.document / this.editable.
// DESIGN CONSTRAINT — never write into the editable DOM: inline styles or
// attributes set here would (a) be recorded by the editor's mutation history
// (polluting undo), (b) be SAVED into body_arch/body_html, and (c) then leak a
// giant margin-bottom into the printed PDF. Instead, spacer margins live in a
// <style> element injected into the IFRAME HEAD (never serialized into the
// field value), and rules target each break via a structural
// ".o_elksbulletin > :nth-child(k) > ..." path computed on the fly.
// Breaks are processed in document order, applying each rule before measuring
// the next, because an earlier spacer shifts everything after it.
// Recompute is debounced on editable mutations + iframe resize; writes go only
// to the head style element, which the observer does not watch — no feedback
// loop. Fully guarded: any failure clears to a no-op canvas (accurate print is
// unaffected either way; the PDF pipeline never sees any of this).
// =============================================================================
class ElksPageBreakPreviewPlugin extends Plugin {
    static id = "elksbulletin.PageBreakPreview";

    setup() {
        this._styleEl = this.document.createElement("style");
        this._styleEl.setAttribute("data-elks", "page-break-preview");
        this.document.head.appendChild(this._styleEl);
        this._cleanups.push(() => this._styleEl.remove());

        const schedule = () => {
            clearTimeout(this._timer);
            this._timer = setTimeout(() => this._recompute(), 200);
        };
        this._observer = new MutationObserver(schedule);
        this._observer.observe(this.editable, {
            childList: true, subtree: true,
            attributes: true, characterData: true,
        });
        this._cleanups.push(() => {
            this._observer.disconnect();
            clearTimeout(this._timer);
        });
        if (this.window) {
            this.addDomListener(this.window, "resize", schedule, false, true);
        }
        schedule();
    }

    _recompute() {
        try {
            this._recomputeInner();
        } catch {
            // Visual aid only — never let it break the editor.
            this._styleEl.textContent = "";
        }
    }

    _recomputeInner() {
        const wrapper = this.editable.querySelector(".o_elksbulletin");
        if (!wrapper) {
            this._styleEl.textContent = "";
            return; // not a Lodge Newsletter (e.g. regular Email Marketing)
        }
        // --elks-page-h (printable page height) in px, via a probe element so
        // the browser does the in->px conversion for us.
        const probe = this.document.createElement("div");
        probe.style.cssText =
            "position:absolute;visibility:hidden;height:var(--elks-page-h);";
        wrapper.appendChild(probe);
        const pageH = probe.getBoundingClientRect().height;
        probe.remove();
        if (!pageH || pageH <= 0) {
            this._styleEl.textContent = "";
            return;
        }
        const padTop = parseFloat(
            this.window.getComputedStyle(wrapper).paddingTop) || 0;
        const breaks = wrapper.querySelectorAll(
            ".s_elks_page_break, .s_elks_page_break_inline");
        const rules = [];
        for (const el of breaks) {
            // Apply spacers computed so far before measuring the next break —
            // each spacer shifts everything below it.
            this._styleEl.textContent = rules.join("\n");
            void wrapper.offsetHeight; // force reflow before measuring
            const contentTop = wrapper.getBoundingClientRect().top + padTop;
            const dist = el.getBoundingClientRect().bottom - contentTop;
            if (dist <= 0) {
                continue;
            }
            const remainder = dist % pageH;
            const gap = remainder < 1 ? 0 : pageH - remainder;
            if (gap < 1) {
                continue;
            }
            const path = this._cssPath(el, wrapper);
            if (path) {
                rules.push(`${path}{margin-bottom:${Math.round(gap)}px !important;}`);
            }
        }
        this._styleEl.textContent = rules.join("\n");
    }

    // Structural selector from .o_elksbulletin down to el, using only
    // > :nth-child(k) steps — no ids/attributes written to the content.
    _cssPath(el, wrapper) {
        const steps = [];
        let node = el;
        while (node && node !== wrapper) {
            const parent = node.parentElement;
            if (!parent) {
                return null;
            }
            const k = Array.prototype.indexOf.call(parent.children, node) + 1;
            steps.unshift(`> :nth-child(${k})`);
            node = parent;
        }
        return node === wrapper ? `.o_elksbulletin ${steps.join(" ")}` : null;
    }
}

registry
    .category("mass_mailing-plugins")
    .add(ElksBulletinOptionsPlugin.id, ElksBulletinOptionsPlugin)
    .add(ElksPageBreakPreviewPlugin.id, ElksPageBreakPreviewPlugin);
