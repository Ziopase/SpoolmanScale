#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  SpoolmanScale - Localization (i18n)
#  lang_it.py - the Italian column: working file, checks, emitter
# ============================================================
#
# Italian is the fourth column of src/lang.cpp. It works like the French one
# (tools/lang_fr.py, whose parser, signatures and width engine this reuses):
# the source of truth is tools/lang_it.jsonl, and src/lang.cpp is rebuilt from
# it by `emit`. lang_fr.py keeps owning the French and passes the Italian cell
# through untouched, so the two tools can run in either order.
#
#   python tools/lang_it.py apply FILE.tsv   lines "STR_X<TAB>italiano"
#   python tools/lang_it.py coverage         fails while a row has no Italian
#   python tools/lang_it.py check            every rule below
#   python tools/lang_it.py emit             write the fourth column
#
# A line break inside a string is written \n, as in the C source.
#
# What `check` holds every Italian text to, against the German it comes from:
#   - the printf conversions, the same and in the same order (a swap crashes);
#   - %% as often, browser markers {n} the same and never twice;
#   - leading LV_SYMBOL icons and the gap after them, \n count, HTML tags;
#   - no bare & in a web string, no unescaped double quote;
#   - the destination buffer, in bytes (tools/lang_fr.jsonl "bmax");
#   - every glyph present in the display fonts;
#   - the hard widths of tools/ui_budgets.tsv;
#   - and, where no budget names the widget, not wider than the widest of
#     German, English and French at any font size. French was checked on the
#     device line by line, so the envelope of the three is a width the screens
#     are known to take.
# ============================================================
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import lang_fr as fr                               # noqa: E402

WORK = ROOT / "tools" / "lang_it.jsonl"
WIDE = ROOT / "tools" / "lang_it_wide.txt"


def read_wide():
    if not WIDE.exists():
        return set()
    return {l.split()[0] for l in WIDE.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")}
COLUMN = 3                                         # de, en, fr, it
WRAPS_PAST = 440                                   # px: no single line is this wide


def load_work():
    out = {}
    if WORK.exists():
        for line in WORK.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["id"]] = r
    return out


def save_work(work):
    ids = [i for i, _ in fr.enum_ids()]
    rows = [work[i] for i in ids if i in work]
    fr.write_lf(WORK, "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                              for r in rows))


def apply(paths):
    work = load_work()
    ids = set(i for i, _ in fr.enum_ids())
    n, bad = 0, 0
    for p in paths:
        for ln, line in enumerate(pathlib.Path(p).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip() or line.startswith("#"):
                continue
            if "\t" not in line:
                print("  %s:%d no tab" % (p, ln)); bad += 1; continue
            sid, text = line.split("\t", 1)
            sid = sid.strip()
            if sid not in ids:
                print("  %s:%d unknown id %s" % (p, ln, sid)); bad += 1; continue
            rec = work.get(sid, {"id": sid})
            rec["it"] = text
            rec["st"] = "ok"
            work[sid] = rec
            n += 1
    save_work(work)
    print("%d row(s) applied, %d problem(s) - %d of %d translated"
          % (n, bad, sum(1 for r in work.values() if r.get("it")), len(ids)))
    return bad == 0


def coverage():
    work = load_work()
    ids = [i for i, _ in fr.enum_ids()]
    missing = [i for i in ids if not work.get(i, {}).get("it")]
    for i in missing[:40]:
        print("  E %-34s no Italian" % i)
    print("\n  %d rows, %d without Italian" % (len(ids), len(missing)))
    return not missing


def check():
    _, _, _, _, rows = fr.load_table()
    work = load_work()
    frw = fr.load_work()
    import fit_check
    budgets = {}
    for b in fit_check.read_budgets():
        budgets.setdefault(b["id"], []).append(b)
    if not fr.symbol_chars():
        print("  E LVGL is not unpacked - build the firmware once, icons cannot be measured")
        return False
    errors = warnings = 0
    wide = read_wide()

    def err(sid, msg):
        nonlocal errors
        errors += 1
        print("  E %-34s %s" % (sid, msg))

    def warn(sid, msg):
        nonlocal warnings
        warnings += 1
        print("  w %-34s %s" % (sid, msg))

    for r in rows:
        sid = r["id"]
        it = work.get(sid, {}).get("it")
        if not it:
            err(sid, "no Italian")
            continue
        have = r["vals"][COLUMN] if len(r["vals"]) > COLUMN else None
        if have is not None and have != it:
            err(sid, "src/lang.cpp is out of date - run emit")
        de, en = r["vals"][0], r["vals"][1]
        frt = r["vals"][2] if len(r["vals"]) > 2 else en
        sd, si = fr.signature(de), fr.signature(it)
        if sd["conv"] != si["conv"]:
            err(sid, "printf conversions differ: %s vs %s" % (sd["conv"], si["conv"]))
        if de.count("%%") != it.count("%%"):
            err(sid, "literal %% count differs")
        if sd["brace"] != si["brace"]:
            err(sid, "browser markers differ: %s vs %s" % (sd["brace"], si["brace"]))
        for b in set(si["brace"]):
            if it.count(b) > 1:
                err(sid, "marker %s repeated" % b)
        if sd["symbols"] != si["symbols"]:
            err(sid, "leading LV_SYMBOL differs: %s vs %s" % (sd["symbols"], si["symbols"]))
        elif sd["symbol_gaps"] != si["symbol_gaps"]:
            err(sid, "spaces after the icon: %s, German %s" % (si["symbol_gaps"], sd["symbol_gaps"]))
        if sd["newlines"] != si["newlines"]:
            fn = fr.signature(frt)["newlines"]
            if fn == si["newlines"]:
                warn(sid, "\\n count %d like French, German %d" % (si["newlines"], sd["newlines"]))
            else:
                err(sid, "\\n count %d, German %d" % (si["newlines"], sd["newlines"]))
        if sd["tags"] != si["tags"]:
            err(sid, "HTML differs: %s vs %s" % (sd["tags"], si["tags"]))
        elif fr.crossed_tags(it) and not fr.crossed_tags(de):
            err(sid, "HTML tags do not nest")
        if fr.reaches_innerhtml(sid) and "&" in re.sub(fr.ENTITY, "", it):
            err(sid, "bare & in a web string - write \"e\"")
        if '"' in it.replace('\\"', ""):
            err(sid, "unescaped double quote")
        if re.search(r"\\(?![n\"\\])", it):
            err(sid, "a backslash that is not \\n, \\\" or \\\\")
        bmax = frw.get(sid, {}).get("bmax")
        if bmax:
            n = len(fr.resolved(it).encode("utf-8"))
            if n > bmax:
                err(sid, "%d bytes > %d in the buffer" % (n, bmax))
        web_only = sid.startswith("STR_W_")
        rows_b = [b for b in budgets.get(sid, []) if b["mode"] == "NEVER"]
        size = rows_b[0]["font"] if rows_b else 16
        if not web_only:
            for seg in it.split("\\n"):
                _, miss = fit_check.width(fr.probe_text(seg), size)
                if miss:
                    err(sid, "no glyph for %s" % " ".join(sorted(set(miss))))
        if web_only:
            continue
        segs = {k: v.split("\\n") for k, v in (("de", de), ("en", en), ("fr", frt))}
        sites = frw.get(sid, {}).get("sites") or []
        for i, seg in enumerate(it.split("\\n")):
            for b in rows_b:
                w, _ = fit_check.width(fr.probe_text(seg), b["font"])
                if w > b["budget"]:
                    err(sid, "line %d is %d px, the widget holds %d px (f%d) %s"
                        % (i + 1, w, b["budget"], b["font"], b["site"]))
            if rows_b and len(sites) <= len(rows_b):
                continue
            if sid in wide:
                continue
            sizes = (size,) if rows_b else fit_check.SIZES
            worst = None
            for s in sizes:
                w, _ = fit_check.width(fr.probe_text(seg), s)
                room = max(fit_check.width(fr.probe_text(v[i] if i < len(v) else ""), s)[0]
                           for v in segs.values())
                # The panel is 480 px wide: where German, English and French
                # already run past it, the widget wraps or scrolls, and the
                # envelope says nothing about it.
                if room > WRAPS_PAST:
                    continue
                if w - room > 0 and (worst is None or w - room > worst[0]):
                    worst = (w - room, w, room, s)
            if worst:
                err(sid, "line %d is %d px, wider than German, English and French "
                         "(%d px, f%d)" % (i + 1, worst[1], worst[2], worst[3]))
    print("\n  %d rows, %d error(s), %d warning(s)" % (len(rows), errors, warnings))
    return errors == 0


def emit():
    src, prefix, items, suffix, rows = fr.load_table()
    work = load_work()
    if fr.OPEN3 not in prefix and fr.OPEN4 not in prefix:
        print("emit expects the three-column table: run tools/lang_fr.py emit first")
        return False
    out = []
    for kind, it in items:
        if kind == "raw":
            out.append(it)
            continue
        text = (work.get(it["id"], {}).get("it")
                or (it["vals"][1] if len(it["vals"]) > 1 else ""))
        lit = fr.c_literal(text)
        row = it["text"]
        end = fr.match_brace(row, 0)
        inner, tail = row[1:end - 1], row[end:]
        cells = fr.split_cells(inner)
        if len(cells) < 3:
            print("%s has no French cell - run tools/lang_fr.py emit first" % it["id"])
            return False
        head = ",".join(cells[:3]).rstrip()
        if "\n" in head:
            body = "{%s,\n    %s }" % (head, lit)
        else:
            one = "{%s, %s }" % (head, lit)
            body = one if len(one) + len(tail) + 2 <= fr.LINE_MAX else "{%s,\n    %s }" % (head, lit)
        out.append(body + tail)
    new = prefix.replace(fr.OPEN3, fr.OPEN4) + "".join(out) + suffix
    new = new.replace('// Format: { "Deutsch", "English", "Francais" }',
                      '// Format: { "Deutsch", "English", "Francais", "Italiano" }')
    new = new.replace("//  lang.cpp - String table DE / EN / FR\n",
                      "//  lang.cpp - String table DE / EN / FR / IT\n")
    fr.write_lf(fr.LANG_CPP, new)
    _, _, _, _, again = fr.load_table()
    moved = [a["id"] for a, b in zip(again, rows) if a["vals"][:3] != b["vals"][:3]]
    if moved:
        print("EMIT CHANGED German, English or French on %d row(s): %s"
              % (len(moved), ", ".join(moved[:5])))
        return False
    print("emitted %d rows with an Italian column; German, English and French "
          "verified unchanged" % len(again))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("apply", "coverage", "check", "emit"))
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    if a.cmd == "apply":
        return 0 if apply(a.files) else 1
    return 0 if {"coverage": coverage, "check": check, "emit": emit}[a.cmd]() else 1


if __name__ == "__main__":
    sys.exit(main())
