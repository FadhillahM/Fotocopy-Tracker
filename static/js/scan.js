// ── Scan ulang dari sidebar ──────────────────────────────────────────────
function scanUlang() {
  document.getElementById("modal-scan").style.display = "flex";
  document.getElementById("scan-sub").textContent = "Menghubungi mesin di IP tersimpan...";
  document.getElementById("scan-footer").style.display = "none";
  document.getElementById("scan-body").innerHTML =
    '<div class="alert-info"><i class="ti ti-loader spin"></i> Scanning...</div>';

  fetch("/api/scan-ulang", { method: "POST" })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        document.getElementById("scan-sub").textContent = "Terhubung";
        document.getElementById("scan-body").innerHTML =
          `<div class="alert-success">
            <i class="ti ti-check"></i>
            Mesin ditemukan di <strong>${data.ip}</strong> — ${data.model || ""}
           </div>`;
        setTimeout(() => location.reload(), 1500);
      } else {
        document.getElementById("scan-sub").textContent = "Gagal";
        document.getElementById("scan-body").innerHTML =
          `<div class="alert-danger">
            <i class="ti ti-wifi-off"></i> ${data.error}
           </div>
           <div style="margin-top:10px;">
             <label>Coba IP lain:</label>
             <div style="display:flex;gap:6px;margin-top:4px;">
               <input type="text" id="ip-alt" placeholder="192.168.1.X"
                      style="font-family:var(--mono);" />
               <button class="btn btn-primary" onclick="scanIP()">Scan</button>
             </div>
           </div>`;
        document.getElementById("scan-footer").style.display = "flex";
      }
    })
    .catch(() => {
      document.getElementById("scan-body").innerHTML =
        '<div class="alert-danger"><i class="ti ti-x"></i> Tidak dapat menghubungi server.</div>';
      document.getElementById("scan-footer").style.display = "flex";
    });
}

function scanIP() {
  const ip = document.getElementById("ip-alt").value.trim();
  if (!ip) return;
  document.getElementById("scan-body").innerHTML =
    `<div class="alert-info"><i class="ti ti-loader spin"></i> Scanning ${ip}...</div>`;

  fetch("/api/scan", { method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ ip }) })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        document.getElementById("scan-body").innerHTML =
          `<div class="alert-success">
            <i class="ti ti-check"></i> Device ditemukan di <strong>${ip}</strong>
           </div>
           <p style="font-size:12px;margin-top:8px;color:var(--text2);">
             Model: ${data.device.model || "-"}</p>
           <div style="margin-top:10px;">
             <button class="btn btn-success" onclick="saveDevice(${JSON.stringify(data.device).replace(/"/g,'&quot;')})">
               <i class="ti ti-plug-connected"></i> Sambungkan
             </button>
           </div>`;
      } else {
        document.getElementById("scan-body").innerHTML =
          `<div class="alert-danger"><i class="ti ti-x"></i> ${data.error}</div>`;
      }
    });
}

function saveDevice(device) {
  fetch("/api/device/save", { method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(device) })
    .then(r => r.json())
    .then(data => { if (data.ok) location.href = "/dashboard"; });
}

function closeScanModal() {
  document.getElementById("modal-scan").style.display = "none";
}

// ── Modal hapus data ─────────────────────────────────────────────────────
function showDeleteModal() {
  document.getElementById("cb-riwayat").checked = false;
  document.getElementById("cb-device").checked  = false;
  document.getElementById("warn-reset").style.display = "none";
  updateDeleteBtn();
  document.getElementById("modal-delete").style.display = "flex";
}

function closeDeleteModal() {
  document.getElementById("modal-delete").style.display = "none";
}

function updateDeleteBtn() {
  const r = document.getElementById("cb-riwayat").checked;
  const d = document.getElementById("cb-device").checked;
  const btn   = document.getElementById("btn-delete");
  const label = document.getElementById("delete-label");
  const warn  = document.getElementById("warn-reset");

  btn.disabled = !(r || d);
  warn.style.display = (r && d) ? "block" : "none";
  if (!r && !d) label.textContent = "Hapus";
  else if (r && d) label.textContent = "Reset total";
  else if (r) label.textContent = "Hapus riwayat";
  else label.textContent = "Hapus device";
}

function doDelete() {
  const r = document.getElementById("cb-riwayat").checked;
  const d = document.getElementById("cb-device").checked;
  fetch("/api/settings/delete", { method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ history: r, device: d }) })
    .then(res => res.json())
    .then(data => {
      if (data.ok) {
        closeDeleteModal();
        location.href = d ? "/" : "/dashboard";
      }
    });
}
