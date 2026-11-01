"""
csv_service.py — Scraper + parser untuk log Canon iR2870/iR4570.

Mesin menyimpan 2 jenis log:
  • Copy Job  : /jlc.cgi  (fotocopy pakai scanner mesin)
  • Print Job : /jlp.cgi  (cetak dari komputer/USB)

Cookie 'iR=<nilai>' wajib ada — mesin mengembalikan halaman kosong tanpa cookie.
Nilai cookie didapat otomatis saat request pertama ke /common.cgi.

Kolom HTML yang perlu diparsing khusus (pakai JavaScript document.write):
  • Result      : log_rslt(1) → OK, log_rslt(0) → NG
  • Device Name : job_t(0, "iR2870") → "Local Copy"
  • Sheet x Copies : document.write("1"); document.write(" x "); document.write("2")
"""

import re
import time
import csv
import io
import requests
from bs4 import BeautifulSoup
from datetime import datetime


# ── Konfigurasi ───────────────────────────────────────────────────────────────

TIMEOUT  = 10
HEADERS  = {
    "User-Agent":      ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/149.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection":      "keep-alive",
    "Cache-Control":   "no-cache",
    "Pragma":          "no-cache",
}

_sessions: dict = {}


def _dummy() -> str:
    return str(int(time.time() * 1000))


# ── Session & Cookie ──────────────────────────────────────────────────────────

def _get_session(ip: str) -> requests.Session:
    """
    Buat session dengan cookie 'iR' yang valid.
    Mesin Canon iR memerlukan kunjungan ke /common.cgi dulu untuk mendapat cookie.
    Cookie akan tersimpan otomatis di session.
    """
    if ip in _sessions:
        sess = _sessions[ip]
        # Cek apakah cookie iR masih ada
        if sess.cookies.get("iR"):
            return sess
        # Cookie hilang, reset
        _sessions.pop(ip, None)

    session = requests.Session()
    session.headers.update(HEADERS)

    # Kunjungi halaman utama untuk mendapatkan cookie iR
    try:
        r = session.get(
            f"http://{ip}/common.cgi",
            params={"PageFlag": "j_lps.tpl", "Dummy": _dummy()},
            timeout=TIMEOUT,
        )
        r.raise_for_status()

        cookie_val = session.cookies.get("iR")
        if cookie_val:
            print(f"[scraper] Cookie iR={cookie_val} untuk {ip}")
        else:
            # Mesin kadang tidak set cookie via Set-Cookie header,
            # tapi nilai cookie terlihat di URL redirect atau HTML
            # Coba ekstrak dari response HTML
            m = re.search(r"iR[=\s]+(\d+)", r.text)
            if m:
                session.cookies.set("iR", m.group(1), domain=ip)
                print(f"[scraper] Cookie iR={m.group(1)} dari HTML untuk {ip}")
            else:
                # Fallback: coba tanpa cookie (beberapa versi firmware tidak perlu)
                print(f"[scraper] Tidak dapat cookie iR dari {ip}, coba tanpa cookie")

        _sessions[ip] = session
        return session

    except requests.RequestException as e:
        print(f"[scraper] Gagal inisialisasi session {ip}: {e}")
        raise


def _reset_session(ip: str):
    _sessions.pop(ip, None)


# ── Fetch dari mesin ──────────────────────────────────────────────────────────

def _fetch_html(ip: str, url: str, referer: str, extra_params: dict | None = None) -> str:
    """Fetch halaman HTML log dari mesin."""
    for attempt in range(3):
        try:
            session = _get_session(ip)
            params = {"Flag": "Html_Data", "Dummy": _dummy()}
            if extra_params:
                params.update(extra_params)
            r = session.get(
                url,
                params=params,
                headers={"Referer": referer,
                         "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            if len(r.text) > 200:
                return r.text
            # Halaman terlalu pendek → cookie expired, reset
            print(f"[scraper] Response terlalu pendek ({len(r.text)} char), reset session")
            _reset_session(ip)
        except requests.RequestException as e:
            print(f"[scraper] Error attempt {attempt+1}: {e}")
            _reset_session(ip)
            time.sleep(1)
    return ""


def fetch_copy_history(ip: str) -> list[dict]:
    """Ambil Copy Job Log dari mesin (fotocopy pakai scanner)."""
    referer = f"http://{ip}/common.cgi?PageFlag=j_lcs.tpl&Dummy={_dummy()}"
    html    = _fetch_html(ip, f"http://{ip}/jlc.cgi", referer)
    if not html:
        return []
    jobs = _parse_html_log(html, job_type="copy")
    print(f"[scraper] {len(jobs)} copy job dari {ip}")
    return jobs


def fetch_print_history(ip: str) -> list[dict]:
    """Ambil Print Job Log dari mesin (cetak dari PC/USB)."""
    referer = f"http://{ip}/common.cgi?PageFlag=j_lps.tpl&Dummy={_dummy()}"
    # LogType=0 wajib disertakan -- tanpa ini mesin mengembalikan
    # halaman log kosong (0 job), sesuai request asli browser ke jlp.cgi.
    html    = _fetch_html(ip, f"http://{ip}/jlp.cgi", referer, extra_params={"LogType": "0"})
    if not html:
        return []
    jobs = _parse_html_log(html, job_type="print")
    print(f"[scraper] {len(jobs)} print job dari {ip}")
    return jobs


def fetch_all_history(ip: str) -> list[dict]:
    """Ambil Copy + Print Job sekaligus, return digabung."""
    copy_jobs  = fetch_copy_history(ip)
    print_jobs = fetch_print_history(ip)
    all_jobs   = copy_jobs + print_jobs
    # Urutkan dari terlama ke terbaru
    all_jobs.sort(key=lambda j: j.get("start_time") or datetime.min)
    return all_jobs


# ── Parser HTML log ───────────────────────────────────────────────────────────

def _parse_html_log(html: str, job_type: str = "copy") -> list[dict]:
    """
    Parse halaman HTML log Canon iR.

    Kolom yang terdapat dalam JavaScript perlu diekstrak via regex:
      - Result: log_rslt(1) → OK, log_rslt(0) → NG
      - Sheet x Copies: document.write("N") ... document.write("M")
      - Job Name (print): langsung di <td>
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr")
    jobs = []

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 8:
            continue

        # Kolom 0: Job Number — harus angka
        job_no_text = cells[0].get_text(strip=True)
        if not job_no_text.isdigit():
            continue
        job_no = int(job_no_text)

        # Kolom 1: Result (via JavaScript log_rslt)
        result_html = str(cells[1])
        result_match = re.search(r"log_rslt\((\d)\)", result_html)
        result = "OK" if (result_match and result_match.group(1) == "1") else "NG"

        # Kolom 2: Device Name (copy) / Job Name (print)
        # Copy job tidak punya nama dokumen asli — kolom ini cuma nama device
        # scanner ("Local Copy" dll), jadi TIDAK dipakai sebagai job_name.
        if job_type == "copy":
            job_name = None
        else:
            job_name = cells[2].get_text(strip=True).replace("\xa0", " ").strip('"').strip()

        # Kolom 3: User
        username = cells[3].get_text(strip=True).replace("\xa0", " ")

        # Kolom 5: Start Time
        start_time = _parse_datetime(cells[5].get_text(strip=True))
        if not start_time:
            continue

        # Kolom 6: End Time
        end_time = _parse_datetime(cells[6].get_text(strip=True))

        # Kolom 7: Sheet x Copies — ada di dalam document.write()
        sheet_html = str(cells[7])
        nums = re.findall(r'document\.write\("(\d+)"\)', sheet_html)
        if len(nums) >= 2:
            sheets = int(nums[0])
            copies = int(nums[1])
        elif len(nums) == 1:
            sheets = int(nums[0]); copies = 1
        else:
            # PrintJob langsung di text: "1 X 5"
            sheet_text = cells[7].get_text(strip=True).upper()
            sheets, copies = _parse_sheet_copies(sheet_text)

        total_sheets = sheets * copies

        # Kolom 8: End Code
        end_code = cells[8].get_text(strip=True).upper() if len(cells) > 8 else ""

        # Tentukan status akhir
        if end_code == "STOP":
            status = "STOP"
        elif result == "NG":
            status = "NG"
        else:
            status = "OK"

        jobs.append({
            "job_number":   job_no,
            "job_type":     job_type,
            "job_name":     job_name,  # None untuk copy job -> ditampilkan "-" di web
            "username":     username,
            "start_time":   start_time,
            "end_time":     end_time,
            "sheets":       sheets,
            "copies":       copies,
            "total_sheets": total_sheets,
            "paper_size":   "A4",
            "status":       status,
        })

    return jobs


# ── Parse CSV (untuk fitur Import CSV manual) ─────────────────────────────────

def parse_csv_content(content: str) -> list[dict]:
    """
    Parse isi CSV dari mesin Canon iR (untuk upload manual).

    Ada 2 format header, otomatis dideteksi:
      • Print log: Job Number, Result, Job Name, User, Department ID,
                    Start Time, End Time, Sheet x Copies, End Code
      • Copy log : Job Number, Result, Device Name, User, Department ID,
                    Start Time, End Time, Sheet x Copies, End Code
    """
    rows  = []
    content = content.lstrip("\ufeff").strip()
    if not content:
        return rows

    # Cek apakah ini HTML (untuk backward compat jika user upload HTML)
    if content.lstrip().startswith("<"):
        return _parse_html_log(content, job_type="print")

    try:
        reader = csv.DictReader(io.StringIO(content))
        fieldnames = [f.strip() for f in (reader.fieldnames or [])]

        # Auto-detect tipe log dari header kolom ke-3
        if "Device Name" in fieldnames:
            job_type = "copy"
        else:
            job_type = "print"

        for row in reader:
            row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
            parsed = _parse_csv_row(row, job_type)
            if parsed:
                rows.append(parsed)
    except Exception as e:
        print(f"[csv_service] Error parse CSV: {e}")

    return rows


def _parse_csv_row(row: dict, job_type: str = "print") -> dict | None:
    try:
        sheet_col = (row.get("Sheet x Copies") or row.get("Sheet X Copies") or "0 X 0")
        sheets, copies = _parse_sheet_copies(sheet_col)

        result   = row.get("Result",   "").strip().upper()
        end_code = row.get("End Code", "").strip().upper()
        if end_code == "STOP":
            status = "STOP"
        elif result == "NG":
            status = "NG"
        else:
            status = "OK"

        start = _parse_datetime(row.get("Start Time", ""))
        end   = _parse_datetime(row.get("End Time",   ""))
        if not start:
            return None

        # Copy job tidak punya nama dokumen asli (kolom "Device Name" bukan
        # nama file) -> job_name dikosongkan, ditampilkan "-" di web.
        job_name = row.get("Job Name", "") if job_type == "print" else None

        return {
            "job_number":   _safe_int(row.get("Job Number", "0")),
            "job_type":     job_type,
            "job_name":     job_name,
            "username":     row.get("User", ""),
            "start_time":   start,
            "end_time":     end,
            "sheets":       sheets,
            "copies":       copies,
            "total_sheets": sheets * copies,
            "paper_size":   "A4",
            "status":       status,
        }
    except Exception as e:
        print(f"[csv_service] Skip baris: {e}")
        return None


# ── Helper ────────────────────────────────────────────────────────────────────

def _parse_sheet_copies(value: str) -> tuple[int, int]:
    value = value.strip().upper()
    for sep in ["X", "x"]:
        if sep in value:
            parts = [p.strip() for p in value.split(sep, 1)]
            return _safe_int(parts[0]), _safe_int(parts[1]) if len(parts) > 1 else 1
    return _safe_int(value), 1


def _parse_datetime(value: str) -> datetime | None:
    if not value or not value.strip():
        return None
    value = value.strip()
    for fmt in ["%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
                "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    print(f"[csv_service] Format tanggal tidak dikenal: '{value}'")
    return None


def _safe_int(value) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


# ── Cek duplikat ──────────────────────────────────────────────────────────────

def is_duplicate(job: dict, existing: list[dict]) -> bool:
    job_no = job.get("job_number")
    if job_no is None:
        return False

    job_type = job.get("job_type")

    for ex in existing:
        # Bug lama: "if job['job_number']" salah karena 0 dianggap falsy,
        # jadi job dengan nomor 0 tidak pernah kecocok -> numpuk terus.
        if ex.get("job_number") != job_no:
            continue

        # Copy job dan Print job punya penomoran sendiri-sendiri di mesin,
        # jadi nomor yang sama bisa saja dua job yang beda jenis.
        ex_type = ex.get("job_type")
        if job_type and ex_type and job_type != ex_type:
            continue

        ex_start = ex.get("start_time")
        if isinstance(ex_start, str):
            ex_start = _parse_datetime(ex_start)
        if ex_start and job["start_time"]:
            if abs((job["start_time"] - ex_start).total_seconds()) < 60:
                return True
    return False