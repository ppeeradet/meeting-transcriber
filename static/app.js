const base = location.pathname.replace(/\/$/, "");
const jobsEl = document.querySelector("#jobs");
const msg = document.querySelector("#message");
const jobsById = new Map();
let editorJob = null;
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

function formatBytes(value) {
  if (!Number.isFinite(value)) return "";
  const units = ["B", "KB", "MB", "GB"];
  let size = value; let unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
  return `${size.toFixed(unit ? 1 : 0)} ${units[unit]}`;
}

function renderJobs(jobs) {
  jobsById.clear();
  jobs.forEach((job) => jobsById.set(job.id, job));
  if (!jobs.length) { jobsEl.innerHTML = "<p>ไม่พบงานตามตัวกรอง</p>"; return; }
  jobsEl.innerHTML = jobs.map((job) => {
    const info = progressInfo(job);
    const attrs = info.value === null ? "" : `aria-valuenow="${info.value}"`;
    const bar = info.value === null ? '<em class="indeterminate"></em>' : `<em style="width:${info.value}%"></em>`;
    const retry = ["failed", "interrupted", "cancelled"].includes(job.status) ? `<button class="ghost retry" data-job="${esc(job.id)}">ลองใหม่</button>` : "";
    const cancel = ["queued", "downloading", "converting", "transcribing"].includes(job.status) ? `<button class="ghost cancel-job" data-job="${esc(job.id)}">ยกเลิกงาน</button>` : "";
    const close = job.archived
      ? `<button class="ghost restore-job" data-job="${esc(job.id)}">เปิดงานกลับ</button>`
      : (["completed", "failed", "cancelled", "interrupted", "queued"].includes(job.status) ? `<button class="archive-job" data-job="${esc(job.id)}">${job.status === "queued" ? "ยกเลิกและปิดงานนี้" : "ปิดงานนี้"}</button>` : "");
    const files = job.files.map((file) => {
      const transcribe = /\.(mp3|mp4|m4a|wav|webm|mov|mkv|aac|flac|ogg|opus|mpeg|mpg)$/i.test(file)
        ? `<button class="ghost transcribe-file" data-job="${esc(job.id)}" data-file="${esc(file)}">ถอดเสียงไฟล์นี้</button>` : "";
      const mediaActions = transcribe ? `<button class="ghost play-media" data-job="${esc(job.id)}" data-file="${esc(file)}">เล่น</button><button class="ghost convert-file" data-job="${esc(job.id)}" data-file="${esc(file)}">แปลงไฟล์นี้</button>` : "";
      const manage = `<button class="ghost copy-managed-file" data-job="${esc(job.id)}" data-file="${esc(file)}">คัดลอก</button><button class="ghost move-managed-file" data-job="${esc(job.id)}" data-file="${esc(file)}">ย้าย</button><button class="ghost delete-managed-file" data-job="${esc(job.id)}" data-file="${esc(file)}">ลบไฟล์</button>`;
      return `<div class="managed-file"><b>${esc(file)}</b><button class="ghost file" data-job="${esc(job.id)}" data-file="${esc(file)}">ดาวน์โหลด</button>${mediaActions}${transcribe}${manage}</div>`;
    }).join("");
    const edit = job.files.includes("transcript.json") ? `<button class="ghost edit-transcript" data-job="${esc(job.id)}">แก้ไขถอดเสียง</button>` : "";
    const sizes = job.source_size_bytes ? `<p class="media-sizes">ต้นฉบับ ${formatBytes(job.source_size_bytes)}${job.result_size_bytes ? ` · ผลลัพธ์ ${formatBytes(job.result_size_bytes)}` : ""}</p>` : "";
    const missing = job.missing_files?.length ? `<p class="error">ไฟล์ถูกย้ายหรือลบจากภายนอก ${job.missing_files.length} รายการ</p>` : "";
    const empty = !job.files.length ? '<p class="error">ไม่พบไฟล์จริงของงานนี้บน Dell</p>' : "";
    const removeRecord = !job.files.length && !["queued", "preparing", "downloading", "converting", "transcribing", "exporting"].includes(job.status) ? `<button class="delete-job-record" data-job="${esc(job.id)}">ลบรายการงาน</button>` : "";
    return `<article class="job"><div class="job-head"><strong>${esc(job.title || "ใช้ชื่อคลิปอัตโนมัติ")}</strong><div class="job-head-actions"><span class="status">${job.archived ? "ปิดแล้ว · " : ""}${esc(job.status)}</span>${close}</div></div><p class="url">${esc(job.platform || "")} · ${esc(job.url)}</p>${sizes}${missing}${empty}<div class="job-progress"><span><b>สถานะงาน</b><i>${esc(info.label)}</i></span><div role="progressbar" aria-valuemin="0" aria-valuemax="100" ${attrs}>${bar}</div></div><p>${esc(job.progress)}</p>${job.error ? `<p class="error">${esc(job.error)}</p>` : ""}<div class="files">${edit}${files}${retry}${cancel}${removeRecord}</div></article>`;
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
  [["search", "#filter-search"], ["status", "#filter-status"], ["media_type", "#filter-media"], ["archived", "#filter-archived"]].forEach(([name, selector]) => {
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
    body: JSON.stringify({ urls, title: document.querySelector("#title").value || null, transcribe: document.querySelector("#transcribe").checked, language: document.querySelector("#language").value, model_profile: document.querySelector("#model-profile").value, media_mode: document.querySelector("#media-mode").value, output_format: document.querySelector("#output-format").value, quality: document.querySelector("#quality").value, embed_cover: document.querySelector("#embed-cover").checked }),
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

document.querySelector("#upload").onclick = () => upload("/api/uploads", "#media", "#upload-message", { title: document.querySelector("#title").value || "", language: document.querySelector("#language").value, model_profile: document.querySelector("#model-profile").value });
document.querySelector("#convert-submit").onclick = () => upload("/api/conversions", "#convert-media", "#convert-message", { output_format: document.querySelector("#convert-format").value, bitrate: document.querySelector("#convert-bitrate").value, resolution: document.querySelector("#convert-resolution").value, title: document.querySelector("#title").value || "" });

function formatEditorTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  const remainder = (seconds % 60).toFixed(1).padStart(4, "0");
  return `${minutes}:${remainder}`;
}

async function openTranscript(job) {
  const response = await fetch(`${base}/api/jobs/${encodeURIComponent(job.id)}/transcript`, { headers: headers() });
  if (!response.ok) { alert(await response.text()); return; }
  const data = await response.json();
  editorJob = { ...job, language: data.language || job.language };
  document.querySelector("#editor-title").textContent = job.title || "ตรวจสอบผลถอดเสียง";
  document.querySelector("#editor-segments").innerHTML = data.segments.map((segment, index) => `<article class="editor-segment" data-index="${index}" data-start="${Number(segment.start)}" data-end="${Number(segment.end)}"><button class="ghost seek" type="button">▶ ${formatEditorTime(Number(segment.start))}</button><textarea aria-label="ข้อความช่วงที่ ${index + 1}">${esc(segment.text)}</textarea></article>`).join("");
  const audioFile = job.files.find((file) => /\.(mp3|m4a|wav|flac|ogg|opus|mp4|webm)$/i.test(file));
  const audio = document.querySelector("#editor-audio");
  audio.hidden = !audioFile;
  audio.src = audioFile ? `${base}/api/jobs/${encodeURIComponent(job.id)}/files/${encodeURIComponent(audioFile)}` : "";
  document.querySelector("#editor-message").textContent = "";
  document.querySelector("#transcript-editor").hidden = false;
  document.querySelector("#transcript-editor").scrollIntoView({ behavior: "smooth" });
}

document.querySelector("#editor-segments").onclick = (event) => {
  const seek = event.target.closest(".seek");
  if (!seek) return;
  const audio = document.querySelector("#editor-audio");
  audio.currentTime = Number(seek.closest(".editor-segment").dataset.start);
  audio.play();
};
document.querySelector("#editor-search").oninput = (event) => {
  const needle = event.target.value.trim().toLocaleLowerCase("th");
  document.querySelectorAll(".editor-segment").forEach((row) => { row.hidden = needle && !row.querySelector("textarea").value.toLocaleLowerCase("th").includes(needle); });
};
document.querySelector("#editor-copy").onclick = async () => {
  const text = [...document.querySelectorAll(".editor-segment textarea")].map((field) => field.value).join("\n");
  await navigator.clipboard.writeText(text);
  document.querySelector("#editor-message").textContent = "คัดลอกข้อความแล้ว";
};
document.querySelector("#editor-save").onclick = async () => {
  if (!editorJob) return;
  const segments = [...document.querySelectorAll(".editor-segment")].map((row) => ({ start: Number(row.dataset.start), end: Number(row.dataset.end), text: row.querySelector("textarea").value }));
  const output = document.querySelector("#editor-message");
  output.textContent = "กำลังบันทึกและสร้างเอกสาร…";
  const response = await fetch(`${base}/api/jobs/${encodeURIComponent(editorJob.id)}/transcript`, { method: "PUT", headers: headers({ "content-type": "application/json" }), body: JSON.stringify({ language: editorJob.language, segments }) });
  output.textContent = response.ok ? "บันทึกและสร้างไฟล์ TXT, SRT, VTT, JSON, Markdown และ DOCX แล้ว" : `บันทึกไม่สำเร็จ: ${await response.text()}`;
  if (response.ok) load();
};
document.querySelector("#editor-close").onclick = () => { document.querySelector("#transcript-editor").hidden = true; document.querySelector("#editor-audio").pause(); };

jobsEl.onclick = async (event) => {
  const managedFile = event.target.closest(".copy-managed-file,.move-managed-file,.delete-managed-file");
  if (managedFile) {
    const deleting = managedFile.classList.contains("delete-managed-file");
    const moving = managedFile.classList.contains("move-managed-file");
    if (deleting && !confirm(`ลบไฟล์ ${managedFile.dataset.file} ถาวร?`)) return;
    if (moving && !confirm(`ย้ายไฟล์ ${managedFile.dataset.file} ออกจากโฟลเดอร์งาน?`)) return;
    managedFile.disabled = true;
    const endpoint = deleting ? "" : moving ? "/move" : "/copy";
    const options = deleting ? { method: "DELETE", headers: headers() } : {
      method: "POST", headers: headers({ "content-type": "application/json" }),
      body: JSON.stringify({ destination: document.querySelector("#file-destination").value }),
    };
    const response = await fetch(`${base}/api/jobs/${encodeURIComponent(managedFile.dataset.job)}/files/${encodeURIComponent(managedFile.dataset.file)}${endpoint}`, options);
    if (!response.ok) alert(await response.text());
    else { const result = await response.json(); alert(result.destination ? `สำเร็จ: ${result.destination}` : "ลบไฟล์แล้ว"); }
    await load(); return;
  }
  const deleteRecord = event.target.closest(".delete-job-record");
  if (deleteRecord) {
    if (!confirm("ลบเฉพาะรายการงานนี้ออกจากประวัติ? การดำเนินการนี้ใช้เมื่องานไม่มีไฟล์เหลือแล้ว")) return;
    deleteRecord.disabled = true;
    const response = await fetch(`${base}/api/jobs/${encodeURIComponent(deleteRecord.dataset.job)}`, { method: "DELETE", headers: headers() });
    if (!response.ok) alert(await response.text());
    await load(); return;
  }
  const editButton = event.target.closest(".edit-transcript");
  if (editButton) { await openTranscript(jobsById.get(editButton.dataset.job)); return; }
  const playButton = event.target.closest(".play-media");
  if (playButton) {
    const url = `${base}/api/jobs/${encodeURIComponent(playButton.dataset.job)}/files/${encodeURIComponent(playButton.dataset.file)}`;
    const video = document.querySelector("#library-video"); const audio = document.querySelector("#library-audio");
    const isVideo = /\.(mp4|webm|mov|mkv|mpeg|mpg)$/i.test(playButton.dataset.file);
    video.pause(); audio.pause(); video.hidden = !isVideo; audio.hidden = isVideo;
    (isVideo ? video : audio).src = url;
    document.querySelector("#preview-title").textContent = playButton.dataset.file;
    document.querySelector("#library-preview").hidden = false;
    document.querySelector("#library-preview").scrollIntoView({ behavior: "smooth" });
    return;
  }
  const convertButton = event.target.closest(".convert-file");
  if (convertButton) {
    convertButton.disabled = true; convertButton.textContent = "กำลังเพิ่มเข้าคิว…";
    const response = await fetch(`${base}/api/jobs/${encodeURIComponent(convertButton.dataset.job)}/convert`, {
      method: "POST", headers: headers({ "content-type": "application/json" }),
      body: JSON.stringify({ filename: convertButton.dataset.file, output_format: document.querySelector("#convert-format").value, bitrate: document.querySelector("#convert-bitrate").value, resolution: document.querySelector("#convert-resolution").value }),
    });
    if (!response.ok) alert(await response.text());
    await load();
    return;
  }
  const transcribeButton = event.target.closest(".transcribe-file");
  if (transcribeButton) {
    transcribeButton.disabled = true;
    transcribeButton.textContent = "กำลังเพิ่มเข้าคิว…";
    const response = await fetch(`${base}/api/jobs/${encodeURIComponent(transcribeButton.dataset.job)}/transcribe`, {
      method: "POST", headers: headers({ "content-type": "application/json" }),
      body: JSON.stringify({ filename: transcribeButton.dataset.file, language: document.querySelector("#language").value, model_profile: document.querySelector("#model-profile").value }),
    });
    if (!response.ok) alert(await response.text());
    await load();
    return;
  }
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
  const archiveAction = event.target.closest(".archive-job,.restore-job");
  if (archiveAction) {
    const closing = archiveAction.classList.contains("archive-job");
    if (closing && !confirm("ปิดงานนี้จากคิว? ไฟล์และเอกสารจะยังถูกเก็บไว้")) return;
    archiveAction.disabled = true;
    const endpoint = closing ? "archive" : "restore";
    const response = await fetch(`${base}/api/jobs/${encodeURIComponent(archiveAction.dataset.job)}/${endpoint}`, { method: "POST", headers: headers() });
    if (!response.ok) alert(await response.text()); await load(); return;
  }
  const action = event.target.closest(".retry,.cancel-job"); if (!action) return;
  action.disabled = true;
  const endpoint = action.classList.contains("retry") ? "retry" : "cancel";
  const response = await fetch(`${base}/api/jobs/${encodeURIComponent(action.dataset.job)}/${endpoint}`, { method: "POST", headers: headers() });
  if (!response.ok) alert(await response.text()); await load();
};

document.querySelector("#refresh").onclick = load;
document.querySelector("#open-jobs-folder").onclick = async (event) => {
  const button = event.currentTarget;
  const message = document.querySelector("#folder-message");
  button.disabled = true; message.textContent = "กำลังเปิด File Explorer บน Dell…";
  try {
    const response = await fetch(`${base}/api/open-jobs-folder`, { method: "POST", headers: headers() });
    if (!response.ok) throw Error(await response.text());
    message.textContent = "เปิดโฟลเดอร์งานรวมบนหน้าจอ Dell แล้ว";
  } catch (error) {
    message.textContent = `เปิดโฟลเดอร์ไม่สำเร็จ: ${error.message}`;
  } finally {
    button.disabled = false;
  }
};
document.querySelector("#preview-close").onclick = () => { document.querySelector("#library-audio").pause(); document.querySelector("#library-video").pause(); document.querySelector("#library-preview").hidden = true; };
document.querySelectorAll("#filter-search,#filter-status,#filter-media,#filter-archived").forEach((control) => control.addEventListener("input", load));
load();
setInterval(load, 4000);
