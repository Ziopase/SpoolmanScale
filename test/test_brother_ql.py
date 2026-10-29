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
  unsigned w, h, cut, tape;
  if (fscanf(f, "%u %u %u %u\n", &w, &h, &cut, &tape) != 4) return 2;
  std::vector<uint8_t> px((w / 8) * h);
  if (fread(px.data(), 1, px.size(), f) != px.size()) return 3;
  LabelRaster r{};
  r.width = w; r.height = h; r.row_bytes = w / 8; r.pixels = px.data();
  r.length = px.size(); r.content_width = w;
  return brotherQlStream(r, (uint8_t)tape, cut != 0, sink, nullptr) ? 0 : 1;
}
'''

def case(tmp, exe, width, height, cut, seed):
    rnd = random.Random(seed)
    img = Image.new("1", (width, height), 1)               # 1 = white in PIL
    for _ in range(width * height // 6):
        img.putpixel((rnd.randrange(width), rnd.randrange(height)), 0)
    # Ours: the 720-dot row, black = 1, MSB first, the 696 dots 12 in.
    row = Image.new("1", (720, height), 1)
    row.paste(img, (12, 0))
    mine = bytearray()
    for y in range(height):
        bits = [1 - row.getpixel((x, y)) for x in range(720)]
        for i in range(0, 720, 8):
            v = 0
            for b in bits[i:i + 8]:
                v = (v << 1) | b
            mine.append(v)
    raw = tmp / f"in{seed}.bin"
    raw.write_bytes(f"720 {height} {int(cut)} 62\n".encode() + bytes(mine))
    got = subprocess.run([str(exe), str(raw)], check=True, capture_output=True).stdout

    qlr = BrotherQLRaster("QL-700")
    qlr.exception_on_warning = True
    convert(qlr, [img.convert("L")], "62", cut=cut, dither=False, compress=False,
            rotate=0, hq=True, red=False)
    want = qlr.data.replace(b"\x1b\x69\x53", b"", 1)       # the status request: we never read an answer
    assert got == want, f"seed {seed}: {len(got)} bytes vs {len(want)}; first diff at " \
        f"{next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))}"

with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    cpp = tmp / "t.cpp"
    cpp.write_text(source)
    exe = tmp / "t"
    subprocess.run(["g++", "-std=c++17", "-I", str(root / "src"), str(cpp),
                    str(root / "src/services/brother_ql.cpp"), "-o", str(exe)], check=True)
    case(tmp, exe, 696, 354, True, 1)      # 62 x 30 mm, cut
    case(tmp, exe, 696, 354, False, 2)     # no cut
    case(tmp, exe, 696, 150, True, 3)      # the shortest label
    case(tmp, exe, 696, 17, True, 4)       # not a multiple of the 8-line write
print("brother_ql stream matches the library byte for byte")
