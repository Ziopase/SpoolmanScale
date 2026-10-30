#include "services/brother_ql.h"

#include <string.h>

// One byte of the print row, turned around: the QL takes a row from its right
// end, so the row's last byte comes first with its bits reversed.
static uint8_t reverseBits(uint8_t b) {
  b = (uint8_t)((b & 0xF0) >> 4 | (b & 0x0F) << 4);
  b = (uint8_t)((b & 0xCC) >> 2 | (b & 0x33) << 2);
  b = (uint8_t)((b & 0xAA) >> 1 | (b & 0x55) << 1);
  return b;
}

// brother_ql's labels '62', '38' and '23x23'. Continuous tape keeps a 35 dot
// feed margin, a die-cut label none (its gap is the margin).
static const BrotherQlMedia MEDIA[] = {
  { 62, 30, false, 696,   0, 12 },
  { 38, 40, false, 413,   0, 12 },
  { 23, 23, true,  202, 202, 42 },
};

const BrotherQlMedia* brotherQlMedia(uint8_t width_mm, uint8_t length_mm) {
  for (const BrotherQlMedia& m : MEDIA)
    if (m.width_mm == width_mm && m.length_mm == length_mm) return &m;
  return nullptr;
}

bool brotherQlStream(const LabelRaster& image, const BrotherQlMedia& media, bool cut,
                     BrotherQlSink sink, void* ctx) {
  if (!sink || !image.pixels || image.width != BQL_ROW_DOTS ||
      image.row_bytes != BQL_ROW_BYTES || image.height == 0 ||
      image.length != size_t(image.row_bytes) * image.height) return false;

  // Invalidate: 200 zero bytes clear whatever a broken job left in the buffer.
  uint8_t head[200];
  memset(head, 0, sizeof(head));
  if (!sink(ctx, head, sizeof(head))) return false;

  uint8_t cmd[32];
  size_t n = 0;
  cmd[n++] = 0x1B; cmd[n++] = 0x40;                       // ESC @  initialise
  // ESC i z  media and quality: kind, width and length valid, high quality.
  // 0x0A continuous tape, length 0: the line count sets the label. 0x0B a
  // die-cut label of its own length.
  cmd[n++] = 0x1B; cmd[n++] = 0x69; cmd[n++] = 0x7A;
  cmd[n++] = 0xCE;
  cmd[n++] = media.die_cut ? 0x0B : 0x0A;
  cmd[n++] = media.width_mm;
  cmd[n++] = media.die_cut ? media.length_mm : 0x00;
  const uint32_t lines = image.height;
  cmd[n++] = (uint8_t)(lines);       cmd[n++] = (uint8_t)(lines >> 8);
  cmd[n++] = (uint8_t)(lines >> 16); cmd[n++] = (uint8_t)(lines >> 24);
  cmd[n++] = 0x00; cmd[n++] = 0x00;                       // first page
  if (cut) {
    cmd[n++] = 0x1B; cmd[n++] = 0x69; cmd[n++] = 0x4D; cmd[n++] = 0x40;   // ESC i M  auto cut
    cmd[n++] = 0x1B; cmd[n++] = 0x69; cmd[n++] = 0x41; cmd[n++] = 0x01;   // ESC i A  every label
  }
  cmd[n++] = 0x1B; cmd[n++] = 0x69; cmd[n++] = 0x4B;      // ESC i K  expanded mode
  cmd[n++] = cut ? 0x08 : 0x00;                           // cut at the end
  cmd[n++] = 0x1B; cmd[n++] = 0x69; cmd[n++] = 0x64;      // ESC i d  feed margin
  cmd[n++] = media.die_cut ? 0x00 : 0x23; cmd[n++] = 0x00;  // 35 dots, none on die-cut
  if (!sink(ctx, cmd, n)) return false;

  // The raster lines, a few to a write so a socket is not fed byte by byte.
  // QL-700: no compression, so every line is 0x67 0x00 0x5A and 90 bytes.
  enum { PER_WRITE = 8, LINE = 3 + BQL_ROW_BYTES };
  uint8_t buf[PER_WRITE * LINE];
  size_t fill = 0;
  for (uint16_t y = 0; y < image.height; ++y) {
    const uint8_t* row = image.pixels + size_t(y) * image.row_bytes;
    uint8_t* out = buf + fill;
    out[0] = 0x67; out[1] = 0x00; out[2] = BQL_ROW_BYTES;
    for (int i = 0; i < BQL_ROW_BYTES; ++i)
      out[3 + i] = reverseBits(row[BQL_ROW_BYTES - 1 - i]);
    fill += LINE;
    if (fill == sizeof(buf)) {
      if (!sink(ctx, buf, fill)) return false;
      fill = 0;
    }
  }
  if (fill && !sink(ctx, buf, fill)) return false;

  const uint8_t print = 0x1A;                             // print and feed
  return sink(ctx, &print, 1);
}

#ifdef ARDUINO
#include <Arduino.h>
#include <WiFi.h>

#include "hardware/sd_logger.h"
#include "services/wifi_manager.h"

namespace {
struct NetSink {
  WiFiClient* client;
  BrotherQlProgressFn progress;
};

// Gives the socket every byte, waiting while its buffer is full; a socket that
// takes nothing for 3 s has gone.
bool netWrite(void* ctx, const uint8_t* data, size_t len) {
  NetSink* s = static_cast<NetSink*>(ctx);
  uint32_t last_move = millis();
  size_t sent = 0;
  while (sent < len) {
    if (!s->client->connected()) return false;
    const size_t w = s->client->write(data + sent, len - sent);
    if (w > 0) { sent += w; last_move = millis(); }
    else if (millis() - last_move > 3000) return false;
    else delay(5);
    if (s->progress) s->progress();
  }
  return true;
}
}  // namespace

BrotherQlResult brotherQlPrint(const char* host, uint16_t port, const LabelRaster& image,
                               const BrotherQlMedia& media, bool cut,
                               BrotherQlProgressFn progress) {
  if (!image.pixels || image.width != BQL_ROW_DOTS) return BQL_BAD_RASTER;
  if (!wifiManagerIsConnected()) return BQL_NO_WIFI;
  IPAddress ip;
  if (!host || !ip.fromString(host)) return BQL_CONNECT;

  WiFiClient client;
  client.setTimeout(3);
  if (progress) progress();
  if (!client.connect(ip, port, 3000)) {
    logSDf("Printer: QL connect %s:%u failed", host, (unsigned)port);
    return BQL_CONNECT;
  }
  client.setNoDelay(true);
  NetSink sink{&client, progress};
  const bool ok = brotherQlStream(image, media, cut, netWrite, &sink);
  if (ok) {
    // Let the last bytes leave before the socket closes: a close with data
    // still queued can drop the print command.
    client.flush();
    const uint32_t t = millis();
    while (millis() - t < 300) { if (progress) progress(); delay(20); }
  }
  client.stop();
  logSDf("Printer: QL %s:%u %u lines %s", host, (unsigned)port, (unsigned)image.height,
         ok ? "sent" : "FAILED");
  return ok ? BQL_OK : BQL_WRITE;
}
#endif
