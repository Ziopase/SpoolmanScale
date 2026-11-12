#pragma once
// Ricerca di un server Spoolman nella rete locale.
//
// Prova tutti gli indirizzi della /24 in cui si trova il dispositivo sulla
// porta indicata (connessioni non bloccanti, a gruppi), poi chiede
// /api/v1/health a chi ha risposto e tiene solo chi dice "healthy".
// Blocca per qualche secondo (circa 10 al massimo): da chiamare in un task.
#include <Arduino.h>

#define SM_DISCOVER_MAX 6

struct SmFound {
  char host[24];   // "192.168.0.161:7912"
};

// Ritorna quanti server ha trovato (0..max). `port` 0 = 7912.
int spoolmanDiscover(uint16_t port, SmFound* out, int max);
