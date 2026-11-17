const base = location.pathname.replace(/\/$/, "");
const jobsEl = document.querySelector("#jobs");
const msg = document.querySelector("#message");
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[character]);
const headers = (extra = {}) => extra;

function progressInfo(job) {
  if (job.status === "completed") return { value: 100, label: "100%" };
  const match = String(job.progress || "").match(/(\d+(?:\.\d+)?)%/);
  if (!match) return { value: null, label: "กำลังทำงาน" };
  const value = Math.min(100, Math.max(0, Number(match[1])));
  return { value, label: `${Math.round(value)}%` };
}

function renderJobs(jobs) {
  if (!jobs.length) { jobsEl.innerHTML = "<p>ไม่พบงานตามตัวกรอง</p>"; return; }
  jobsEl.innerHTML = jobs.map((job) => {
    const info = progressInfo(job);
    const attrs = info.value === null ? "" : `aria-valuenow="${info.value}"`;
    const bar = info.value === null ? '<em class="indeterminate"></em>' : `<em style="width:${info.value}%"></em>`;
    const retry = ["failed", "interrupted", "cancelled"].includes(job.status) ? `<button class="ghost retry" data-job="${esc(job.id)}">ลองใหม่</button>` : "";
    const cancel = ["queued", "downloading", "converting", "transcribing"].includes(job.status) ? `<button class="ghost cancel-job" data-job="${esc(job.id)}">ยกเลิกงาน</button>` : "";
    const files = job.files.map((file) => `<button class="ghost file" data-job="${esc(job.id)}" data-file="${esc(file)}">ดาวน์โหลด ${esc(file)}</button>`).join("");
    return `<article class="job"><div class="job-head"><strong>${esc(job.title || "ใช้ชื่อคลิปอัตโนมัติ")}</strong><span class="status">${esc(job.status)}</span></div><p class="url">${esc(job.platform || "")} · ${esc(job.url)}</p><div class="job-progress"><span><b>สถานะงาน</b><i>${esc(info.label)}</i></span><div role="progressbar" aria-valuemin="0" aria-valuemax="100" ${attrs}>${bar}</div></div><p>${esc(job.progress)}</p>${job.error ? `<p class="error">${esc(job.error)}</p>` : ""}<div class="files">${files}${retry}${cancel}</div></article>`;
  }).join("");
}

function updateStats(jobs) {
  const running = new Set(["preparing", "downloading", "converting", "transcribing", "exporting"]);
  document.querySelector("#stat-waiting").textContent = jobs.filter((job) => job.status === "queued").length;
  document.querySelector("#stat-running").textContent = jobs.filter((job) => running.has(job.status)).length;
  document.querySelector("#stat-completed").textContent = jobs.filter((job) => job.status === "completed").length;
  document.querySelector("#stat-failed").textContent = jobs.filter((job) => ["failed", "interrupted"].includes(job.status)).length;
}

function filterQuery() {
  const params = new URLSearchParams();
  [["search", "#filter-search"], ["status", "#filter-status"], ["media_type", "#filter-media"]].forEach(([name, selector]) => {
    const value = document.querySelector(selector).value.trim();
    if (value) params.set(name, value);
  });
  return params.toString();
}

async function load() {
  const query = filterQuery();
  const [response, allResponse] = await Promise.all([
    fetch(`${base}/api/jobs${query ? `?${query}` : ""}`, { headers: headers() }),
    fetch(`${base}/api/jobs`, { headers: headers() }),
  ]);
  if (!response.ok || !allResponse.ok) { jobsEl.innerHTML = '<p class="error">เชื่อมต่อระบบไม่ได้</p>'; return; }
  renderJobs(await response.json());
  updateStats(await allResponse.json());
}

document.querySelector("#submit").onclick = async () => {
  const urls = document.querySelector("#urls").value.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
  if (!urls.length) { msg.textContent = "กรุณาใส่ URL"; return; }
  msg.textContent = "กำลังเพิ่มงาน…";
  const response = await fetch(`${base}/api/jobs`, {
    method: "POST", headers: headers({ "content-type": "application/json" }),
    body: JSON.stringify({ urls, title: document.querySelector("#title").value || null, transcribe: document.querySelector("#transcribe").checked, language: document.querySelector("#language").value, media_mode: document.querySelector("#media-mode").value, output_format: document.querySelector("#output-format").value, quality: document.querySelector("#quality").value, embed_cover: document.querySelector("#embed-cover").checked }),
  });
  msg.textContent = response.ok ? "เพิ่มงานแล้ว" : `เกิดข้อผิดพลาด: ${await response.text()}`;
  if (response.ok) { document.querySelector("#urls").value = ""; load(); }
};

document.querySelector("#preview").onclick = async () => {
  const url = document.querySelector("#urls").value.split(/\r?\n/).map((value) => value.trim()).find(Boolean);
  const card = document.querySelector("#preview-card");
  if (!url) { msg.textContent = "กรุณาใส่ URL ก่อน"; return; }
  msg.textContent = "กำลังตรวจสอบข้อมูลคลิป…";
  const response = await fetch(`${base}/api/preview`, { method: "POST", headers: headers({ "content-type": "application/json" }), body: JSON.stringify({ url }) });
  if (!response.ok) { msg.textContent = `Preview ไม่สำเร็จ: ${await response.text()}`; return; }
  const data = await response.json();
  const duration = Number.isFinite(data.duration) ? `${Math.floor(data.duration / 60)}:${String(Math.round(data.duration % 60)).padStart(2, "0")} นาที` : "ไม่ทราบ";
  card.innerHTML = `${data.thumbnail ? `<img src="${esc(data.thumbnail)}" alt="ภาพปก">` : ""}<div><h3>${esc(data.title || "ไม่พบชื่อ")}</h3><p>${esc(data.platform)} · ${esc(data.uploader || "ไม่ทราบผู้เผยแพร่")}</p><p>ระยะเวลา ${esc(duration)} · พบ ${data.formats.length} รูปแบบ</p></div>`;
  card.hidden = false; msg.textContent = "ตรวจสอบข้อมูลแล้ว";
};

document.querySelector("#media-mode").onchange = (event) => {
  const video = event.target.value === "video";
  document.querySelector("#output-format").value = video ? "mp4" : "mp3";
  document.querySelector("#quality").value = video ? "best" : "v0";
  document.querySelector("#embed-cover").disabled = video;
};

async function upload(endpoint, fileSelector, messageSelector, extra) {
  const fileInput = document.querySelector(fileSelector); const output = document.querySelector(messageSelector); const file = fileInput.files[0];
  if (!file) { output.textContent = "กรุณาเลือกไฟล์"; return; }
  const data = new FormData(); data.append("file", file); Object.entries(extra).forEach(([key, value]) => data.append(key, value));
  output.textContent = "กำลังอัปโหลด…";
  const response = await fetch(`${base}${endpoint}`, { method: "POST", headers: headers(), body: data });
  output.textContent = response.ok ? "เพิ่มงานเข้าคิวแล้ว" : `เกิดข้อผิดพลาด: ${await response.text()}`;
  if (response.ok) { fileInput.value = ""; load(); }
}

document.querySelector("#upload").onclick = () => upload("/api/uploads", "#media", "#upload-message", { title: document.querySelector("#title").value || "", language: document.querySelector("#language").value });
document.querySelector("#convert-submit").onclick = () => upload("/api/conversions", "#convert-media", "#convert-message", { output_format: document.querySelector("#convert-format").value, bitrate: document.querySelector("#convert-bitrate").value, resolution: document.querySelector("#convert-resolution").value, title: document.querySelector("#title").value || "" });

jobsEl.onclick = async (event) => {
  const fileButton = event.target.closest(".file");
  if (fileButton) {
    const url = `${base}/api/jobs/${encodeURIComponent(fileButton.dataset.job)}/files/${encodeURIComponent(fileButton.dataset.file)}`;
    if (!window.showSaveFilePicker) { const link = document.createElement("a"); link.href = url; link.download = fileButton.dataset.file; link.click(); return; }
    let handle;
    try { handle = await window.showSaveFilePicker({ suggestedName: fileButton.dataset.file }); }
    catch (error) { if (error.name === "AbortError") return; const link = document.createElement("a"); link.href = url; link.download = fileButton.dataset.file; link.click(); return; }
    fileButton.disabled = true; fileButton.textContent = "กำลังบันทึก…";
    try { const response = await fetch(url, { headers: headers() }); if (!response.ok || !response.body) throw Error("ดาวน์โหลดไม่สำเร็จ"); const writable = await handle.createWritable(); await response.body.pipeTo(writable); fileButton.textContent = "บันทึกแล้ว ✓"; }
    catch (error) { fileButton.textContent = error.message; }
    finally { fileButton.disabled = false; }
    return;
  }
  const action = event.target.closest(".retry,.cancel-job"); if (!action) return;
  action.disabled = true;
  const endpoint = action.classList.contains("retry") ? "retry" : "cancel";
  const response = await fetch(`${base}/api/jobs/${encodeURIComponent(action.dataset.job)}/${endpoint}`, { method: "POST", headers: headers() });
  if (!response.ok) alert(await response.text()); await load();
};

document.querySelector("#refresh").onclick = load;
document.querySelectorAll("#filter-search,#filter-status,#filter-media").forEach((control) => control.addEventListener("input", load));
load();
setInterval(load, 4000);
