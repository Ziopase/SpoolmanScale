#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ams_to_spoolman.py - fills Spoolman with the Bambu spools sitting in the AMS.

Reads every AMS / external tray that Home Assistant's Bambu Lab integration
(ha-bambulab) reports, and for each Bambu spool with an RFID serial:

  1. creates the filament in Spoolman (vendor "Bambu Lab", material, colour),
     unless an identical one exists;
  2. creates the spool, with the weight left estimated from the AMS percentage
     and the serial (tray_uuid) in extra.tag - the field SpoolmanSync,
     OpenSpoolman and SpoolmanScale all match a Bambu spool by;
  3. asks SpoolmanSync, through Home Assistant's rest_command, to assign the
     spool to the tray it is in, exactly as if it had just been inserted.

A spool whose serial is already in Spoolman is not created again, only
assigned. Spools without a serial (third-party, zeros) are listed and skipped:
assign them by hand in SpoolmanSync.

Python 3 standard library only. Runs anywhere that reaches both servers.

    python3 ams_to_spoolman.py --ha http://homeassistant.local:8123 \
        --token <long-lived token> --spoolman http://192.168.0.161:7912
    ... the same with --apply to actually write.

Without --apply nothing is written: it prints what it would do.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

VENDOR = "Bambu Lab"
DIAMETER = 1.75
DEFAULT_WEIGHT = 1000.0          # g of filament on a Bambu spool
DENSITY = {                      # g/cm3, by the material's family
    "PLA": 1.24, "PETG": 1.27, "PET": 1.27, "ABS": 1.04, "ASA": 1.07,
    "TPU": 1.21, "PA": 1.14, "PAHT": 1.14, "PC": 1.20, "PVA": 1.23,
    "HIPS": 1.04, "PPS": 1.35, "PET-CF": 1.29, "PA6": 1.14,
}
TRAY_CHANGE = "rest_command/spoolmansync_tray_change"


def request(method, url, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        sys.exit("%s %s -> HTTP %d: %s" % (method, url, e.code, e.read().decode(errors="replace")[:300]))
    except urllib.error.URLError as e:
        sys.exit("%s %s -> %s" % (method, url, e.reason))


def norm_tag(v):
    if not v:
        return ""
    try:
        p = json.loads(v)
        if isinstance(p, str):
            v = p
    except (ValueError, TypeError):
        pass
    return str(v).strip().lower()


def valid_uuid(u):
    return bool(u) and u not in ("unknown", "unavailable") and u.replace("0", "") != ""


def density_for(material):
    m = (material or "").upper()
    if m in DENSITY:
        return DENSITY[m]
    for k in sorted(DENSITY, key=len, reverse=True):
        if m.startswith(k):
            return DENSITY[k]
    return 1.24


def hex6(color):
    h = "".join(c for c in (color or "") if c in "0123456789abcdefABCDEF")
    return h[:6].upper() if len(h) >= 6 else None


def filament_name(name, material):
    n = (name or "").strip()
    if n.lower().startswith("bambu "):
        n = n[6:].strip()
    return n or material or "Filament"


def trays_from_ha(ha, token):
    out = []
    for s in request("GET", ha + "/api/states", token):
        a = s.get("attributes") or {}
        if "tray_uuid" not in a or not s["entity_id"].startswith("sensor."):
            continue
        # The "active tray" sensor mirrors whichever tray is printing: the
        # same spool a second time, under an entity SpoolmanSync assigns nothing to.
        label = (a.get("friendly_name") or "").lower()
        if "active_tray" in s["entity_id"] or "active tray" in label or "piatto attivo" in label:
            continue
        out.append({
            "entity_id": s["entity_id"],
            "label": a.get("friendly_name") or s["entity_id"],
            "uuid": (a.get("tray_uuid") or "").strip(),
            "name": a.get("name") or "",
            "material": a.get("type") or "",
            "color": a.get("color") or "",
            "remain": a.get("remain"),
            "empty": bool(a.get("empty")) or (a.get("name") or "").lower() in ("", "empty"),
        })
    return sorted(out, key=lambda t: t["entity_id"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ha", required=True, help="Home Assistant, e.g. http://homeassistant.local:8123")
    ap.add_argument("--token", required=True, help="Home Assistant long-lived access token")
    ap.add_argument("--spoolman", required=True, help="Spoolman, e.g. http://192.168.0.161:7912")
    ap.add_argument("--apply", action="store_true", help="write; without it only shows what it would do")
    ap.add_argument("--no-assign", action="store_true", help="create the spools, do not ask SpoolmanSync to assign")
    a = ap.parse_args()
    ha, sm = a.ha.rstrip("/"), a.spoolman.rstrip("/") + "/api/v1"

    trays = trays_from_ha(ha, a.token)
    if not trays:
        sys.exit("Home Assistant reports no AMS tray with a tray_uuid: is ha-bambulab set up?")

    spools = request("GET", sm + "/spool")
    by_tag = {norm_tag((s.get("extra") or {}).get("tag")): s for s in spools}
    by_tag.pop("", None)
    filaments = request("GET", sm + "/filament")
    vendors = request("GET", sm + "/vendor")
    vendor = next((v for v in vendors if v["name"].lower() == VENDOR.lower()), None)
    fields = {f["key"] for f in request("GET", sm + "/field/spool")}

    print("%s\n" % ("WRITING" if a.apply else "DRY RUN - nothing is written, add --apply"))
    if a.apply:
        for key in ("tag", "active_tray"):
            if key not in fields:
                request("POST", sm + "/field/spool/" + key, body={"name": key, "field_type": "text"})
                print("  extra field %s created in Spoolman" % key)

    created = assigned = skipped = 0
    seen = set()
    for t in trays:
        head = "%-45s" % t["label"][:45]
        if t["empty"]:
            print(head, "empty")
            continue
        if not valid_uuid(t["uuid"]):
            print(head, "no Bambu serial (%s %s) - assign by hand in SpoolmanSync" % (t["material"], t["name"]))
            skipped += 1
            continue
        key = t["uuid"].lower()
        if key in seen:
            print(head, "same serial as another tray, skipped")
            continue
        seen.add(key)

        spool = by_tag.get(key)
        if spool:
            print(head, "already in Spoolman: spool #%d" % spool["id"])
        else:
            fname = filament_name(t["name"], t["material"])
            color = hex6(t["color"])
            fil = next((f for f in filaments
                        if f.get("vendor") and f["vendor"]["name"].lower() == VENDOR.lower()
                        and f.get("name") == fname and (f.get("color_hex") or "").upper() == (color or "")), None)
            remain = t["remain"]
            weight = None
            if isinstance(remain, (int, float)) and 0 <= remain <= 100:
                weight = round(DEFAULT_WEIGHT * remain / 100.0, 1)
            what = "new spool %s %s #%s, %s" % (VENDOR, fname, color or "-",
                                                 ("%.0f g (AMS %s%%)" % (weight, remain)) if weight is not None else "full")
            if not a.apply:
                print(head, what + ("" if fil else " + new filament"))
                created += 1
                continue
            if not vendor:
                vendor = request("POST", sm + "/vendor", body={"name": VENDOR})
            if not fil:
                body = {"name": fname, "vendor_id": vendor["id"], "material": t["material"] or None,
                        "density": density_for(t["material"]), "diameter": DIAMETER,
                        "weight": DEFAULT_WEIGHT}
                if color:
                    body["color_hex"] = color
                fil = request("POST", sm + "/filament", body=body)
                filaments.append(fil)
            body = {"filament_id": fil["id"],
                    "comment": "Created from %s by ams_to_spoolman.py; weight estimated by the AMS" % t["label"],
                    "extra": {"tag": json.dumps(t["uuid"])}}
            if weight is not None:
                body["remaining_weight"] = weight
            spool = request("POST", sm + "/spool", body=body)
            by_tag[key] = spool
            created += 1
            print(head, what.replace("new spool", "created spool #%d" % spool["id"]))

        if a.apply and not a.no_assign:
            request("POST", ha + "/api/services/" + TRAY_CHANGE, a.token, body={
                "tray_entity_id": t["entity_id"], "tray_uuid": t["uuid"], "name": t["name"],
                "material": t["material"], "color": t["color"], "current_print_state": "unknown"})
            assigned += 1

    print("\n%d spool(s) %s, %d assignment(s) sent to SpoolmanSync, %d tray(s) without a serial"
          % (created, "created" if a.apply else "to create", assigned, skipped))


if __name__ == "__main__":
    main()
