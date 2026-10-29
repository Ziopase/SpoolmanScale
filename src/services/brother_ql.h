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

// The QL head: 90 bytes, 720 dots at 300 dpi. 62 mm continuous tape (DK-22205)
// prints 696 of them, 12 dots in from either edge of the row.
#define BQL_ROW_DOTS   720
#define BQL_ROW_BYTES  (BQL_ROW_DOTS / 8)
#define BQL_PORT       9100

// Takes the bytes of the job in pieces; false stops the stream.
typedef bool (*BrotherQlSink)(void* ctx, const uint8_t* data, size_t len);

// The whole job for a raster BQL_ROW_DOTS wide (labelRasterValid()) on
// continuous tape `tape_mm` wide: invalidate, initialise, media, cut, margin,
// every raster line, print. Pure: no network, no LVGL. False when the raster
// is not the head's width or the sink refused.
bool brotherQlStream(const LabelRaster& image, uint8_t tape_mm, bool cut,
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
                               uint8_t tape_mm, bool cut, BrotherQlProgressFn progress);
