const limits = {
  characters: Number(document.body.dataset.maxCharacters),
  bytes: Number(document.body.dataset.maxPayloadBytes),
};
const state = {
  embedFile: null,
  detectFile: null,
  embedUrl: null,
  detectUrl: null,
  capacityOk: false,
  capacityRequestId: 0,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function fileSize(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatName(file) {
  const ext = file.name.split(".").pop()?.toUpperCase() || "IMAGE";
  return ext === "JPG" ? "JPEG" : ext;
}

function setupTabs() {
  $$(".tab").forEach((tab) => tab.addEventListener("click", () => {
    $$(".tab").forEach((item) => {
      const active = item === tab;
      item.classList.toggle("active", active);
      item.setAttribute("aria-selected", String(active));
    });
    $$(".panel").forEach((panel) => {
      const active = panel.id === `${tab.dataset.tab}-panel`;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
    });
  }));
}

function setPreview(kind, file) {
  const preview = $(`#${kind}-preview`);
  const dropzone = $(`#${kind}-dropzone`);
  const previous = state[`${kind}Url`];
  if (previous) URL.revokeObjectURL(previous);
  const url = URL.createObjectURL(file);
  state[`${kind}Url`] = url;
  state[`${kind}File`] = file;
  const img = preview.querySelector("img");
  img.src = url;
  img.onload = () => {
    preview.querySelector(".file-meta").textContent = `${file.name} · ${formatName(file)} · ${img.naturalWidth} × ${img.naturalHeight} · ${fileSize(file.size)}`;
  };
  dropzone.hidden = true;
  preview.hidden = false;
  if (kind === "embed") checkCapacity();
}

function setupUploader(kind) {
  const input = $(`#${kind}-file`);
  const zone = $(`#${kind}-dropzone`);
  input.addEventListener("change", () => input.files[0] && setPreview(kind, input.files[0]));
  ["dragenter", "dragover"].forEach((event) => zone.addEventListener(event, (e) => {
    e.preventDefault(); zone.classList.add("dragover");
  }));
  ["dragleave", "drop"].forEach((event) => zone.addEventListener(event, (e) => {
    e.preventDefault(); zone.classList.remove("dragover");
  }));
  zone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) setPreview(kind, file);
  });
  $(`#${kind}-preview .replace-file`).addEventListener("click", () => input.click());
}

async function apiFetch(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "请求未能完成，请稍后重试。");
  return data;
}

async function checkCapacity() {
  const requestId = ++state.capacityRequestId;
  const file = state.embedFile;
  const strength = $('input[name="strength"]:checked').value;
  const note = $("#capacity-note");
  state.capacityOk = false;
  note.className = "capacity";
  note.textContent = "正在检查图片容量…";
  const form = new FormData();
  form.append("file", file);
  form.append("strength", strength);
  try {
    const data = await apiFetch("/api/watermark/capacity", { method: "POST", body: form });
    if (requestId !== state.capacityRequestId) return;
    state.capacityOk = data.sufficient;
    note.classList.add(data.sufficient ? "ok" : "bad");
    note.textContent = data.sufficient
      ? `容量可用 · 当前图片最大推荐水印长度：${data.recommended_max_characters} 字符 / ${data.max_payload_bytes} bytes`
      : "当前图片尺寸过小，不建议写入隐藏水印。";
  } catch (error) {
    if (requestId !== state.capacityRequestId) return;
    note.classList.add("bad");
    note.textContent = error.message;
  }
}

function validateMessage() {
  const input = $("#message");
  const counter = $("#message-counter");
  const error = $("#message-error");
  const characters = Array.from(input.value).length;
  const bytes = new TextEncoder().encode(input.value).length;
  const valid = characters > 0 && characters <= limits.characters && bytes <= limits.bytes;
  counter.textContent = `${characters} / ${limits.characters} · ${bytes} / ${limits.bytes} bytes`;
  counter.classList.toggle("invalid", !valid && input.value.length > 0);
  if (characters > limits.characters) error.textContent = `水印内容不能超过 ${limits.characters} 个字符。`;
  else if (bytes > limits.bytes) error.textContent = "文本字节长度超过当前协议容量。";
  else error.textContent = "";
  error.hidden = !error.textContent;
  return valid;
}

function showError(target, message, title = "处理未完成") {
  target.hidden = false;
  target.innerHTML = `<div class="result-head"><span class="status-icon error">!</span><div><h2>${escapeHtml(title)}</h2><p>${escapeHtml(message)}</p></div></div>`;
  target.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function setBusy(button, busy, text) {
  if (!button.dataset.label) button.dataset.label = button.querySelector("span").textContent;
  button.disabled = busy;
  button.querySelector("span").textContent = busy ? text : button.dataset.label;
}

async function submitEmbed(event) {
  event.preventDefault();
  const button = $("#embed-submit");
  const result = $("#embed-result");
  if (!state.embedFile) return showError(result, "请先选择一张 PNG、JPG 或 JPEG 图片。");
  if (!validateMessage()) return showError(result, "请输入有效的水印内容，并检查字符与字节长度。");
  if (!state.capacityOk) return showError(result, "当前图片容量不足，或容量检查尚未通过。");
  const format = $('input[name="output-format"]:checked').value;
  const form = new FormData();
  form.append("file", state.embedFile);
  form.append("message", $("#message").value);
  form.append("strength", $('input[name="strength"]:checked').value);
  form.append("output_format", format);
  form.append("jpeg_quality", $("#jpeg-quality").value);
  setBusy(button, true, "正在处理图片…");
  result.hidden = true;
  try {
    const data = await apiFetch("/api/watermark/embed", { method: "POST", body: form });
    result.hidden = false;
    result.innerHTML = `
      <div class="result-head"><span class="status-icon">✓</span><div><h2>水印添加成功</h2><p>服务器重新读取输出文件并完成完整性验证</p></div></div>
      <div class="result-grid">
        <div class="result-item"><small>水印内容</small><strong>${escapeHtml(data.message)}</strong></div>
        <div class="result-item"><small>输出格式</small><strong>${data.output_format.toUpperCase()}</strong></div>
        <div class="result-item"><small>图片尺寸</small><strong>${data.width} × ${data.height}</strong></div>
        <div class="result-item"><small>PSNR</small><strong>${data.psnr} dB</strong></div>
        <div class="result-item"><small>SSIM</small><strong>${data.ssim}</strong></div>
        <div class="result-item"><small>协议 / 完整性</small><strong>v${data.protocol_version} · 通过</strong></div>
      </div>
      <a class="download-button" href="${data.download_url}">下载处理后的图片</a>`;
    result.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    showError(result, error.message);
  } finally {
    setBusy(button, false, "");
  }
}

async function submitDetect() {
  const button = $("#detect-submit");
  const result = $("#detect-result");
  if (!state.detectFile) return showError(result, "请先选择需要检测的图片。", "尚未选择图片");
  const form = new FormData();
  form.append("file", state.detectFile);
  setBusy(button, true, "正在检测水印…");
  result.hidden = true;
  try {
    const data = await apiFetch("/api/watermark/detect", { method: "POST", body: form });
    if (data.valid) {
      result.hidden = false;
      result.innerHTML = `
        <div class="result-head"><span class="status-icon">✓</span><div><h2>检测到有效隐藏水印</h2><p>纠错与完整性校验均已通过</p></div></div>
        <div class="result-grid">
          <div class="result-item"><small>内容</small><strong>${escapeHtml(data.message)}</strong></div>
          <div class="result-item"><small>协议版本</small><strong>v${data.protocol_version}</strong></div>
          <div class="result-item"><small>数据完整性</small><strong>ECC / CRC 通过</strong></div>
        </div>`;
    } else if (data.damaged) {
      showError(result, "检测到疑似隐藏水印，但数据已经损坏，无法可靠恢复。", "水印数据已损坏");
    } else {
      showError(result, "未检测到有效隐藏水印。", "未检测到水印");
    }
    result.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    showError(result, error.message, "检测未完成");
  } finally {
    setBusy(button, false, "");
  }
}

function setupFormatControls() {
  $$('input[name="output-format"]').forEach((input) => input.addEventListener("change", () => {
    const jpeg = input.value === "jpeg" && input.checked;
    $("#quality-field").hidden = !jpeg;
    $("#jpeg-note").hidden = !jpeg;
  }));
  $$('input[name="strength"]').forEach((input) => input.addEventListener("change", () => {
    if (state.embedFile) checkCapacity();
  }));
}

setupTabs();
setupUploader("embed");
setupUploader("detect");
setupFormatControls();
$("#message").addEventListener("input", validateMessage);
$("#embed-form").addEventListener("submit", submitEmbed);
$("#detect-submit").addEventListener("click", submitDetect);
