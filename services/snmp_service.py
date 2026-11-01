"""
SNMP Service – Canon iR2870 / iR4570
OID telah diverifikasi dari SNMP walk nyata pada mesin (OID.xml).
"""
import asyncio
import re
from datetime import datetime

COMMUNITY = "public"
PORT      = 161
TIMEOUT   = 3

OID = {
    "sys_descr":        "1.3.6.1.2.1.1.1.0",
    "sys_name":         "1.3.6.1.2.1.1.5.0",
    "sys_location":     "1.3.6.1.2.1.1.6.0",
    "sys_uptime":       "1.3.6.1.2.1.1.3.0",
    "printer_status":   "1.3.6.1.2.1.25.3.5.1.1.1",
    "counter_lifetime": "1.3.6.1.2.1.43.10.2.1.4.1.1",
    "toner_level":      "1.3.6.1.2.1.43.11.1.1.9.1.1",
    "toner_max":        "1.3.6.1.2.1.43.11.1.1.8.1.1",
    "waste_level":      "1.3.6.1.2.1.43.11.1.1.9.1.2",
    "waste_max":        "1.3.6.1.2.1.43.11.1.1.8.1.2",
    "tray_bypass":      "1.3.6.1.2.1.43.8.2.1.10.1.1",
    "tray_1":           "1.3.6.1.2.1.43.8.2.1.10.1.2",
    "tray_2":           "1.3.6.1.2.1.43.8.2.1.10.1.3",
    "tray_3":           "1.3.6.1.2.1.43.8.2.1.10.1.4",
    "tray_4":           "1.3.6.1.2.1.43.8.2.1.10.1.5",
}

PRINTER_STATUS_MAP = {1: "other", 2: "unknown", 3: "idle", 4: "printing", 5: "warmup"}
INVALID_IPS = {"0.0.0.0", "", "127.0.0.1", None}


def _is_valid_ip(ip: str) -> bool:
    if not ip or ip in INVALID_IPS:
        return False
    if ip.startswith("0.") or ip.startswith("127."):
        return False
    return True


def _to_str(val) -> str:
    """Konversi OctetString / bytes / apapun ke str bersih."""
    if val is None:
        return ""
    # bytes langsung
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace").strip()
    # puresnmp v2+ mengembalikan objek dengan .pythonize()
    if hasattr(val, "pythonize"):
        raw = val.pythonize()
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace").strip()
        return str(raw).strip()
    s = str(val)
    # Buang wrapper "OctetString(b'...')" jika masih muncul
    m = re.match(r"[A-Za-z]+\(b['\"](.+)['\"]\)\s*$", s)
    if m:
        return m.group(1).strip()
    return s.strip()


def _to_int(val) -> int | None:
    try:
        # puresnmp bisa kembalikan Integer objek
        if hasattr(val, "pythonize"):
            return int(val.pythonize())
        return int(val)
    except (TypeError, ValueError):
        return None


def _pct(current, maximum) -> int:
    try:
        c, m = _to_int(current) or 0, _to_int(maximum) or 0
        if m <= 0 or c < 0:
            return 0
        return max(0, min(100, round(c / m * 100)))
    except Exception:
        return 0


def _tray(val) -> int | None:
    v = _to_int(val)
    return None if v is None or v < 0 else v


async def _async_get(ip: str, oids: list) -> dict:
    from puresnmp import Client, V2C, ObjectIdentifier
    client   = Client(ip, V2C(COMMUNITY), port=PORT)
    oid_objs = [ObjectIdentifier(o) for o in oids]
    results  = await asyncio.wait_for(client.multiget(oid_objs), timeout=TIMEOUT)
    return dict(zip(oids, results))


def _get_snmp(ip: str, oids: list) -> dict:
    try:
        loop   = asyncio.new_event_loop()
        result = loop.run_until_complete(_async_get(ip, oids))
        loop.close()
        return result
    except Exception as e:
        raise ConnectionError(f"SNMP error [{ip}]: {e}")


def poll_snmp(ip: str) -> dict:
    if not _is_valid_ip(ip):
        return {"polled_at": datetime.now(), "is_online": False}
    try:
        data = _get_snmp(ip, list(OID.values()))

        def v(key):
            return data.get(OID[key])

        status_raw     = _to_int(v("printer_status")) or 1
        printer_status = PRINTER_STATUS_MAP.get(status_raw, "other")
        toner_pct      = _pct(v("toner_level"), v("toner_max"))
        waste_pct      = _pct(v("waste_level"), v("waste_max"))
        uptime_raw     = _to_int(v("sys_uptime")) or 0
        uptime_sec     = uptime_raw // 100

        return {
            "polled_at":         datetime.now(),
            "is_online":         True,
            "printer_status":    printer_status,
            "toner_level":       toner_pct,
            "waste_toner_level": waste_pct,
            "tray_bypass":       _tray(v("tray_bypass")),
            "tray_1":            _tray(v("tray_1")),
            "tray_2":            _tray(v("tray_2")),
            "tray_3":            _tray(v("tray_3")),
            "tray_4":            _tray(v("tray_4")),
            "counter_lifetime":  _to_int(v("counter_lifetime")),
            "uptime_seconds":    uptime_sec,
        }
    except Exception as e:
        print(f"[snmp_service] Gagal poll {ip}: {e}")
        return {"polled_at": datetime.now(), "is_online": False}


def scan_device(ip: str) -> dict | None:
    if not _is_valid_ip(ip):
        return None
    try:
        scan_oids = [OID["sys_descr"], OID["sys_name"], OID["sys_location"]]
        data      = _get_snmp(ip, scan_oids)

        descr    = _to_str(data.get(OID["sys_descr"]))
        hostname = _to_str(data.get(OID["sys_name"]))
        location = _to_str(data.get(OID["sys_location"]))

        if not descr and not hostname:
            return None

        return {
            "ip_address": ip,
            "model":      descr or hostname,
            "hostname":   hostname,
            "location":   location,
        }
    except Exception:
        return None


def scan_network(subnet: str, concurrency: int = 30) -> list[dict]:
    import concurrent.futures
    parts = subnet.strip().split(".")
    base  = ".".join(parts[:3]) if len(parts) >= 3 else subnet.strip()
    ips   = [f"{base}.{i}" for i in range(1, 255)]

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {ex.submit(scan_device, ip): ip for ip in ips}
        for fut in concurrent.futures.as_completed(futures):
            info = fut.result()
            if info:
                results.append(info)

    results.sort(key=lambda d: list(map(int, d["ip_address"].split("."))))
    return results