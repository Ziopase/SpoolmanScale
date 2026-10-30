# Italian translation

Italian is the fourth language of SpoolmanScale, on the display and in the web
interface. It is built exactly like the French one (see
[FRENCH_TRANSLATION.md](FRENCH_TRANSLATION.md)): a fourth column in
`src/lang.cpp`, kept in a working file and written into the table by a tool.

## What changed

| File | Change |
|---|---|
| `src/lang.h` | `LANG_IT = 3`, `STRINGS[][4]` |
| `src/lang.cpp` | the fourth column, 1464 rows |
| `src/ui/language_screen.cpp`, `src/ui/setup_welcome_screen.cpp` | four language buttons, 110 px each, instead of three of 148 |
| `src/services/time_service.cpp` | Italian defaults to the CET time zone, like German and French |
| `src/web/web_portal.cpp` | `<html lang="it">` on the setup portal |
| `STR_BTN_LANG_SUB` | "Deutsch / English / Français / Italiano" in every language |
| `scripts/check.sh` | rule 10b: Italian coverage and check |
| `scripts/conventions_baseline.json` | `label_literal_captions` 14 -> 16: the two "Italiano" buttons, written as literals on purpose like "Deutsch", "English" and "Français" (a language's own name is not translated) |

No font work was needed: the French supplement fonts already carry every
Italian letter (à è é ì ò ù and their capitals).

## The tools

| File | What it is |
|---|---|
| `tools/lang_it.jsonl` | the source of truth for Italian, one JSON line per text |
| `tools/lang_it.py` | `apply FILE.tsv` (lines `STR_X<TAB>testo`), `coverage`, `check`, `emit` |
| `tools/lang_it_wide.txt` | the few rows allowed past the width envelope, each with the widget that proves the room |

`lang_fr.py` reads and writes the four-column table too and passes the Italian
cell through untouched, so the two tools can run in either order. After taking
upstream's `lang.cpp` during a rebase:

    python3 tools/lang_fr.py seed && python3 tools/lang_fr.py emit
    python3 tools/lang_it.py emit
    python3 tools/lang_it.py check

## What `check` holds every Italian text to

The same rules as the French: printf conversions identical and in the same
order as the German, `%%`, browser markers, leading icons, `\n` count, HTML
tags, buffer sizes in bytes, glyphs present in the fonts, and the hard widths
of `tools/ui_budgets.tsv`. Where no budget names the widget, a line may not be
wider than the widest of German, English and French at any font size - French
was checked on the device, so that envelope is a width the screens are known
to take. Lines that every other language already runs past 440 px with are
skipped: such a widget wraps or scrolls.

Not yet looked at on a real display, screen by screen.
