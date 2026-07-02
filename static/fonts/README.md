# Masthead script font

The masthead lodge name + tagline use **Great Vibes** (an elegant script),
bundled here so the printed newsletter and the on-screen editor render the
SAME font regardless of what is installed on the server or the editor's
computer.

Great Vibes is licensed under the **SIL Open Font License 1.1** (free to bundle
and redistribute). Only one file is needed:

    GreatVibes-Regular.ttf

## How to add it

Fetch the file into this folder (run on your machine, then commit, OR run
directly on the server's module copy):

    curl -L -o GreatVibes-Regular.ttf \
      https://github.com/google/fonts/raw/main/ofl/greatvibes/GreatVibes-Regular.ttf

Then upgrade the module (`-u elksbulletin`) and restart Odoo so the new asset
and the print `@font-face` pick it up.

To swap in a different script (e.g. Dancing Script, Tangerine), drop that
`.ttf` here as `GreatVibes-Regular.ttf` (keep the filename) — or tell the
developer to change the `@font-face` family name in
`report/elks_bulletin_report.xml` and `static/src/scss/elks_masthead_font.scss`.
