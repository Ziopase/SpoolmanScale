#pragma once

#include <stddef.h>
#include <stdint.h>

#include "services/label_raster.h"

// ============================================================
//  BROTHER QL OVER THE NETWORK
//
//  The QL raster protocol (QL-700 and its family) sent over a
//  plain TCP socket, port 9100 as the QL-710W/720NW/810W/820NWB
//  take it. A QL-700 has only USB: a Raspberry Pi or any Linux
//  box with the printer on USB forwards the socket to it, e.g.
//      socat TCP-LISTEN:9100,fork,reuseaddr FILE:/dev/usb/lp0
//  The bytes are the ones the brother_ql library writes for the
//  same picture (checked bit for bit, see test/).
//
//  One way only: the printer is never asked for its status, so
//  a job that was sent is "sent", not "printed".
// ============================================================

// The QL head: 90 bytes, 720 dots at 300 dpi, whatever roll is loaded.
#define BQL_ROW_DOTS   720
#define BQL_ROW_BYTES  (BQL_ROW_DOTS / 8)
#define BQL_PORT       9100

// One Brother DK roll as the QL takes it, from brother_ql's label table. The
// printer reads the roll's chip and refuses a job for another roll (red lamp),
// so the kind and the size sent must be the roll's own.
//   printable_w: the dots across the 720 dot row it prints
//   printable_h: the dots along the feed of a die-cut label; 0 on continuous
//   offset_r:    dots from the right end of the row (before the row is turned
//                around) to the printable area
struct BrotherQlMedia {
  uint8_t  width_mm, length_mm;   // length 0: continuous, cut where the job ends
  bool     die_cut;
  uint16_t printable_w, printable_h;
  uint16_t offset_r;
};

// The rolls the scale knows, by the label size it offers for them: 62 x 30 on
// DK-22205 (62 mm continuous), 38 x 40 on DK-22225 (38 mm continuous),
// 23 x 23 on DK-11221 (die-cut square). nullptr for any other size.
const BrotherQlMedia* brotherQlMedia(uint8_t width_mm, uint8_t length_mm);
// The first dot of the printable area in the row as the renderer draws it.
inline uint16_t brotherQlContentX(const BrotherQlMedia& m) {
  return (uint16_t)(BQL_ROW_DOTS - m.printable_w - m.offset_r);
}

// Takes the bytes of the job in pieces; false stops the stream.
typedef bool (*BrotherQlSink)(void* ctx, const uint8_t* data, size_t len);

// The whole job for a raster BQL_ROW_DOTS wide (labelRasterValid()) on the
// roll `media`: invalidate, initialise, media, cut, margin, every raster line,
// print. Pure: no network, no LVGL. False when the raster is not the head's
// width or the sink refused.
bool brotherQlStream(const LabelRaster& image, const BrotherQlMedia& media, bool cut,
                     BrotherQlSink sink, void* ctx);

enum BrotherQlResult : uint8_t {
  BQL_OK = 0,
  BQL_BAD_RASTER,   // not the head's width, or no pixels
  BQL_NO_WIFI,
  BQL_CONNECT,      // nothing answered on the address
  BQL_WRITE,        // the socket stopped taking bytes
};

typedef void (*BrotherQlProgressFn)();

// Opens host:port, streams the job, closes. Blocking: from appLoop() only.
// `host` is a dotted IPv4 address. Not built into the host-side test.
BrotherQlResult brotherQlPrint(const char* host, uint16_t port, const LabelRaster& image,
                               const BrotherQlMedia& media, bool cut,
                               BrotherQlProgressFn progress);
