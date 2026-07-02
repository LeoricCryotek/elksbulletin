# Bundled fonts for the printed newsletter

Fonts here are **bundled inside the module** and referenced by `@font-face` in
`report/elks_bulletin_report.xml`, so the printed PDF renders the same on ANY
server that installs `elksbulletin` — no system font install, no `apt`, no root,
works on hosted Odoo. The report's WeasyPrint `url_fetcher` serves these files
straight off disk.

Two font files go in this folder. Both are free to redistribute. Fetch them once
(then commit them to the repo, or drop them onto the server's module copy),
then `-u elksbulletin` + restart Odoo.

## 1. Masthead script — `GreatVibes-Regular.ttf`

Elegant script for the masthead lodge name + tagline. SIL Open Font License 1.1.

    curl -L -o GreatVibes-Regular.ttf \
      https://github.com/google/fonts/raw/main/ofl/greatvibes/GreatVibes-Regular.ttf

## 2. Emoji — `NotoEmoji-Regular.ttf`  (makes the emoji print)

Emoji only render in the PDF if an emoji font is available. Bundling one here
means every install gets it. **Monochrome Noto Emoji** is the recommended file:
it's a single static TTF that renders on every WeasyPrint version (color-bitmap
emoji fonts like "Noto Color Emoji" are large and fail to render on some
WeasyPrint builds). Emoji print as clean black-and-white glyphs — ideal for a
print newsletter. SIL Open Font License 1.1.

    curl -L -o NotoEmoji-Regular.ttf \
      "https://github.com/google/fonts/raw/main/ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf"

(That file is a variable font; WeasyPrint renders it at its default weight. Any
static NotoEmoji regular file works too — keep the filename.)

### Want COLOR emoji instead?

If your WeasyPrint build renders color emoji, drop a color font in place of the
monochrome one — keep the filename `NotoEmoji-Regular.ttf` (the `@font-face`
family is `Elks Emoji`, so the filename is the only contract):

    curl -L -o NotoEmoji-Regular.ttf \
      https://github.com/googlefonts/noto-emoji/raw/main/fonts/NotoColorEmoji.ttf

### Test after install (same Python Odoo uses)

    python3 -c "import weasyprint; weasyprint.HTML(string='<p style=\"font-family:Elks Emoji;font-size:48px\">A B C heart spade</p>').write_pdf('/tmp/emoji_test.pdf')"

Open `/tmp/emoji_test.pdf` — if the emoji show, the newsletter will show them too.

## Changing a font

To swap either font, drop a replacement `.ttf` here **using the same filename**.
To rename the `@font-face` family or add a weight, edit
`report/elks_bulletin_report.xml` (and, for the masthead, the masthead SCSS).
