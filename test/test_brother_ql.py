"""Compile the production Brother QL stream builder and compare it, byte for
byte, with what the brother_ql library writes for the same picture.

Needs: pip install brother_ql pillow   (skipped when they are missing)
"""
import random
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
    from brother_ql.conversion import convert
    from brother_ql.raster import BrotherQLRaster
except ImportError:
    print("brother_ql / pillow not installed: skipped")
    sys.exit(0)

root = Path(__file__).parents[1]
source = r'''
#include "services/brother_ql.h"
#include <cstdio>
#include <vector>

static bool sink(void*, const uint8_t* d, size_t n) { return fwrite(d, 1, n, stdout) == n; }

int main(int argc, char** argv) {
  FILE* f = fopen(argv[1], "rb");
  unsigned w, h, cut, mw, ml;
  if (fscanf(f, "%u %u %u %u %u\n", &w, &h, &cut, &mw, &ml) != 5) return 2;
  const BrotherQlMedia* m = brotherQlMedia((uint8_t)mw, (uint8_t)ml);
  if (!m) return 4;
  // The renderer's placement, checked against the library's below.
  fprintf(stderr, "x=%u w=%u\n", (unsigned)brotherQlContentX(*m), (unsigned)m->printable_w);
  std::vector<uint8_t> px((w / 8) * h);
  if (fread(px.data(), 1, px.size(), f) != px.size()) return 3;
  LabelRaster r{};
  r.width = w; r.height = h; r.row_bytes = w / 8; r.pixels = px.data();
  r.length = px.size(); r.content_width = w;
  return brotherQlStream(r, *m, cut != 0, sink, nullptr) ? 0 : 1;
}
'''

from brother_ql.labels import ALL_LABELS
LABELS = {l.identifier: l for l in ALL_LABELS}


def case(tmp, exe, ident, media, height, cut, seed):
    """One label: `ident` names brother_ql's roll, `media` is (width, length)
    as the scale names it, `height` the lines (a die-cut label: its own)."""
    lab = LABELS[ident]
    width = lab.dots_printable[0]
    x = 720 - width - lab.offset_r
    rnd = random.Random(seed)
    img = Image.new("1", (width, height), 1)               # 1 = white in PIL
    for _ in range(width * height // 6):
        img.putpixel((rnd.randrange(width), rnd.randrange(height)), 0)
    # Ours: the 720-dot row, black = 1, MSB first, the label where brother_ql puts it.
    row = Image.new("1", (720, height), 1)
    row.paste(img, (x, 0))
    mine = bytearray()
    for y in range(height):
        bits = [1 - row.getpixel((xx, y)) for xx in range(720)]
        for i in range(0, 720, 8):
            v = 0
            for b in bits[i:i + 8]:
                v = (v << 1) | b
            mine.append(v)
    raw = tmp / f"in{seed}.bin"
    raw.write_bytes(f"720 {height} {int(cut)} {media[0]} {media[1]}\n".encode() + bytes(mine))
    run = subprocess.run([str(exe), str(raw)], check=True, capture_output=True)
    got = run.stdout
    assert run.stderr.decode().strip() == f"x={x} w={width}", run.stderr

    qlr = BrotherQLRaster("QL-700")
    qlr.exception_on_warning = True
    convert(qlr, [img.convert("L")], ident, cut=cut, dither=False, compress=False,
            rotate=0, hq=True, red=False)
    want = qlr.data.replace(b"\x1b\x69\x53", b"", 1)       # the status request: we never read an answer
    assert got == want, f"{ident} seed {seed}: {len(got)} bytes vs {len(want)}; first diff at " \
        f"{next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))}"

with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    cpp = tmp / "t.cpp"
    cpp.write_text(source)
    exe = tmp / "t"
    subprocess.run(["g++", "-std=c++17", "-I", str(root / "src"), str(cpp),
                    str(root / "src/services/brother_ql.cpp"), "-o", str(exe)], check=True)
    case(tmp, exe, "62", (62, 30), 354, True, 1)       # DK-22205, 62 x 30 mm, cut
    case(tmp, exe, "62", (62, 30), 354, False, 2)      # no cut
    case(tmp, exe, "62", (62, 30), 17, True, 4)        # not a multiple of the 8-line write
    case(tmp, exe, "38", (38, 40), 472, True, 5)       # DK-22225, 38 x 40 mm
    case(tmp, exe, "23x23", (23, 23), 202, True, 6)    # DK-11221, 23 x 23 die-cut
print("brother_ql stream matches the library byte for byte")
