#include "spoolman_discover.h"

#include <HTTPClient.h>
#include <WiFi.h>
#include <errno.h>
#include <fcntl.h>
#include <lwip/sockets.h>

#define DISC_BATCH   8      // socket aperti insieme (lwip ne ha pochi)
#define DISC_WAIT_MS 350    // attesa per gruppo

static bool askHealth(const char* host) {
  HTTPClient h;
  h.setTimeout(2000);
  h.setConnectTimeout(1500);
  if (!h.begin(String("http://") + host + "/api/v1/health")) return false;
  const int code = h.GET();
  const bool ok = code == 200 && h.getString().indexOf("healthy") >= 0;
  h.end();
  return ok;
}

int spoolmanDiscover(uint16_t port, SmFound* out, int max) {
  if (WiFi.status() != WL_CONNECTED || max <= 0) return 0;
  if (!port) port = 7912;
  const IPAddress me = WiFi.localIP();
  int found = 0;

  for (int first = 1; first < 255 && found < max; first += DISC_BATCH) {
    int fds[DISC_BATCH];
    int last[DISC_BATCH];
    int n = 0;
    for (int h = first; h < first + DISC_BATCH && h < 255; h++) {
      if (h == me[3]) continue;
      const int s = lwip_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
      if (s < 0) break;
      lwip_fcntl(s, F_SETFL, lwip_fcntl(s, F_GETFL, 0) | O_NONBLOCK);
      sockaddr_in a = {};
      a.sin_family = AF_INET;
      a.sin_port = htons(port);
      a.sin_addr.s_addr = (uint32_t)IPAddress(me[0], me[1], me[2], h);
      const int r = lwip_connect(s, (sockaddr*)&a, sizeof(a));
      if (r < 0 && errno != EINPROGRESS) { lwip_close(s); continue; }
      fds[n] = s;
      last[n] = h;
      n++;
    }
    const unsigned long t0 = millis();
    bool done[DISC_BATCH] = {};
    int open_left = n;
    while (open_left > 0 && millis() - t0 < DISC_WAIT_MS) {
      fd_set wr;
      FD_ZERO(&wr);
      int maxfd = -1;
      for (int i = 0; i < n; i++)
        if (!done[i]) { FD_SET(fds[i], &wr); if (fds[i] > maxfd) maxfd = fds[i]; }
      timeval tv = {0, 50 * 1000};
      if (lwip_select(maxfd + 1, nullptr, &wr, nullptr, &tv) <= 0) continue;
      for (int i = 0; i < n; i++) {
        if (done[i] || !FD_ISSET(fds[i], &wr)) continue;
        done[i] = true;
        open_left--;
        int err = 0;
        socklen_t len = sizeof(err);
        lwip_getsockopt(fds[i], SOL_SOCKET, SO_ERROR, &err, &len);
        if (err == 0 && found < max) {
          char host[24];
          snprintf(host, sizeof(host), "%u.%u.%u.%d:%u", me[0], me[1], me[2], last[i], port);
          lwip_close(fds[i]);
          fds[i] = -1;
          if (askHealth(host)) {
            snprintf(out[found].host, sizeof(out[found].host), "%s", host);
            found++;
          }
        }
      }
    }
    for (int i = 0; i < n; i++) if (fds[i] >= 0) lwip_close(fds[i]);
    delay(1);
  }
  return found;
}
