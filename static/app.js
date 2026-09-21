"use strict";
const $ = id => document.getElementById(id);
const state = { language: "st", code: "", complete: false, revision: 0, busy: false, controller: null, scenarios: [], source: "", codeId: "", started: 0 };
const labels = { pass: "初步通过", warn: "待复核", fail: "需修改", pending: "待检查" };
const checkDefs = [["syntax", "语法与成对结构"], ["structure", "程序与接口结构"], ["variables", "变量与类型声明"], ["naming", "命名与可读性"], ["requirements", "需求与逻辑对应"], ["boundaries", "边界与保护条件"]];
const stageDefs = [["input", "需求接收", "确认需求和目标语言"], ["generation", "代码生成", "按当前需求组织接口和逻辑"], ["structure", "同步结构检查", "生成过程中持续更新"], ["review", "需求对应审查", "完整代码返回后逐项比对"]];
let stages = {}, renderTimer = null, elapsedTimer = null, toastTimer = null;
const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function toast(message) { $("toast").textContent = message; $("toast").hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $("toast").hidden = true, 3500); }
function notice(message) { $("notice").textContent = message; $("notice").hidden = !message; }
function resetStages() { stages = Object.fromEntries(stageDefs.map(([id, title, message]) => [id, { title, message, status: "pending" }])); renderStages(); }
function renderStages() {
  $("timeline").innerHTML = stageDefs.map(([id], i) => { const s = stages[id]; return `<li class="${s.status}" title="${esc(s.message)}"><span class="step-symbol">${s.status === "done" ? "✓" : s.status === "warn" ? "!" : String(i + 1).padStart(2, "0")}</span><div><strong>${esc(s.title)}</strong><small>${esc(s.message)}</small></div></li>`; }).join("");
}
function emptyReport() { renderReport({ checks: checkDefs.map(([id, label]) => ({ id, label, status: "pending", detail: "等待本次代码检查" })), conclusion: "等待生成或验证代码", coverage: [], suggestions: [] }); }
function renderReport(report) {
  const byId = Object.fromEntries((report.checks || []).map(c => [c.id, c]));
  const checks = checkDefs.map(([id, label]) => ({ id, label, status: "pending", detail: "等待检查", ...byId[id] }));
  $("checks").innerHTML = checks.map(c => `<div class="check-row ${Object.hasOwn(labels, c.status) ? c.status : "pending"}"><span class="check-icon">${({ pass: "✓", warn: "!", fail: "×", pending: "·" })[c.status] || "·"}</span><strong>${esc(c.label)}</strong><span class="detail" title="${esc(c.detail)} · ${esc(c.method || "辅助审查")}">${esc(c.detail)}</span><span class="result">${labels[c.status] || "待检查"}</span></div>`).join("");
  $("checkCount").textContent = `${checks.filter(c => c.status !== "pending").length} / 6`;
  const overall = checks.some(c => c.status === "fail") ? "fail" : checks.some(c => c.status === "pending") ? "pending" : checks.some(c => c.status === "warn") ? "warn" : "pass";
  $("conclusion").className = "conclusion " + overall;
  $("conclusion").textContent = report.conclusion || "等待审查";
  const priority = { fail: 0, warn: 1, pass: 2 };
  const coverage = [...(report.coverage || [])].sort((a,b) => (priority[a.status] ?? 1) - (priority[b.status] ?? 1));
  const suggestions = report.suggestions || [];
  const item = x => `<div class="coverage-item"><header><span>${esc(x.requirement)}</span><span class="badge ${Object.hasOwn(labels, x.status) ? x.status : "warn"}">${labels[x.status] || "待复核"}</span></header><p>${esc(x.evidence)}</p></div>`;
  // Keep every concern accessible; only passing evidence is folded by default.
  const primaryCount = Math.max(3, coverage.filter(x => x.status !== "pass").length);
  let html = coverage.length ? coverage.slice(0, primaryCount).map(item).join("") : '<p class="muted">等待完整代码审查。</p>';
  if (coverage.length > primaryCount) html += `<details class="more-details"><summary>其余 ${coverage.length - primaryCount} 项依据</summary>${coverage.slice(primaryCount).map(item).join("")}</details>`;
  if (suggestions.length) html += `<div class="suggestions"><h4>修改与复核建议</h4><ul>${suggestions.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
  else if (coverage.length) html += '<p class="muted">暂无需修改项。</p>';
  $("reviewSummary").textContent = coverage.length ? `${coverage.length} 项对应${suggestions.length ? " · " + suggestions.length + " 条建议" : ""}` : "待审查";
  if (overall === "fail" || overall === "warn" && report.source === "review") $("reviewDisclosure").open = true;
  if (overall === "pending" && !coverage.length) $("reviewDisclosure").open = false;
  $("reviewDetails").innerHTML = html;
}
function highlight(code) {
  // Tokenize once: never re-process generated HTML spans.
  const pattern = /\(\*[\s\S]*?(?:\*\)|$)|\/\*[\s\S]*?(?:\*\/|$)|\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:FUNCTION_BLOCK|END_FUNCTION_BLOCK|VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR|END_VAR|IF|THEN|ELSIF|ELSE|END_IF|CASE|OF|END_CASE|FOR|TO|BY|DO|END_FOR|WHILE|END_WHILE|REPEAT|UNTIL|END_REPEAT|PROGRAM|END_PROGRAM|FUNCTION|END_FUNCTION|AND|OR|XOR|NOT|TRUE|FALSE|RETURN|RETAIN|CONSTANT|class|struct|public|private|protected|enum|switch|case|break|return|if|else|for|while|const|constexpr|static|true|false|namespace|using|include|auto)\b|\b(?:BOOL|INT|UINT|UDINT|DINT|USINT|SINT|REAL|LREAL|TIME|STRING|TON|TOF|R_TRIG|CTU|bool|int|double|float|void|unsigned|char|size_t)\b|\b(?:T#\d+(?:\.\d+)?\w*|\d+(?:\.\d+)?)\b/g;
  let result = "", last = 0;
  for (const m of code.matchAll(pattern)) {
    result += esc(code.slice(last, m.index));
    const t = m[0];
    const kind = t.startsWith("(*") || t.startsWith("/*") || t.startsWith("//") ? "comment" : /^["']/.test(t) ? "string" : /^(?:T#|\d)/.test(t) ? "number" : /^(BOOL|INT|UINT|UDINT|DINT|USINT|SINT|REAL|LREAL|TIME|STRING|TON|TOF|R_TRIG|CTU|bool|int|double|float|void|unsigned|char|size_t)$/.test(t) ? "type" : "keyword";
    // Close the span at each newline to keep line-number markup valid.
    result += t.split("\n").map(s => `<span class="tok-${kind}">${esc(s)}</span>`).join("\n");
    last = m.index + t.length;
  }
  return result + esc(code.slice(last));
}
function renderCode() {
  clearTimeout(renderTimer); renderTimer = null;
  const view = $("codeView"), scroller = $("editorScroll");
  const nearBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
  view.hidden = !state.code; $("emptyState").hidden = !!state.code;
  if (state.code) view.innerHTML = highlight(state.code).split("\n").map((line, i) => `<span class="code-line"><span class="line-number">${i + 1}</span><span class="line-code">${line || " "}</span></span>`).join("");
  else view.textContent = "";
  $("codeStats").textContent = `${state.code ? state.code.split("\n").length : 0} 行 · UTF-8`;
  if (nearBottom && state.busy) scroller.scrollTop = scroller.scrollHeight;
}
function scheduleCode() { if (!renderTimer) renderTimer = setTimeout(renderCode, 100); }
function updateActions() {
  $("copy").disabled = $("export").disabled = !state.complete;
  $("validate").disabled = !state.complete || state.busy;
  $("generate").disabled = state.busy || !$("requirement").value.trim();
  $("cancel").hidden = !state.busy;
  $("generate").querySelector("span").textContent = state.busy ? "生成与审查中…" : "生成并验证";
  $("generate").classList.toggle("busy-mark", state.busy);
}
function setBusy(busy) {
  const wasBusy = state.busy;
  state.busy = busy;
  clearInterval(elapsedTimer);
  if (busy) {
    state.started = Date.now();
    elapsedTimer = setInterval(() => $("elapsed").textContent = `已用时 ${Math.floor((Date.now() - state.started) / 1000)} s`, 1000);
  } else if (wasBusy && state.started) $("elapsed").textContent = `本次用时 ${Math.floor((Date.now() - state.started) / 1000)} s`;
  updateActions();
}
function invalidate() {
  state.controller?.abort(); state.revision++; state.complete = false; state.codeId = "";
  setBusy(false); emptyReport(); resetStages();
  state.started = 0; $("elapsed").textContent = "尚未开始";
  $("charCount").textContent = `${$("requirement").value.length} / 20000`;
  $("outputHint").textContent = state.code ? "需求已变更：当前代码是上一版结果，请重新生成。" : "代码完整返回后，可以复制、导出或重新验证。";
  $("codeSource").textContent = state.code ? "旧结果 · 待重新生成" : "等待生成";
}
function language(value) {
  if (value === state.language) return;
  state.language = value; state.code = ""; invalidate(); renderCode();
  document.querySelectorAll("[data-language]").forEach(b => { b.classList.toggle("selected", b.dataset.language === value); b.setAttribute("aria-pressed", String(b.dataset.language === value)); });
  $("exportText").textContent = "导出 ." + value;
  $("codeFilename").textContent = "control_module." + value;
  $("editorLanguage").textContent = value === "st" ? "STRUCTURED TEXT" : "C++ 17";
}
async function jsonRequest(url, options = {}) {
  const response = await fetch(url, options);
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "请求未完成，请检查输入或稍后重试。");
  return result;
}
async function readEvents(url, body, onEvent, controller) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: controller.signal });
  if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(typeof data.detail === "string" ? data.detail : "服务暂忙，请稍后重试。"); }
  if (!response.body) throw new Error("浏览器未提供可读取的响应，请更换现代浏览器后重试。");
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = "", ended = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      let split;
      while ((split = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, split); buffer = buffer.slice(split + 2);
        const payload = frame.split("\n").filter(s => s.startsWith("data:")).map(s => s.slice(5).trim()).join("\n");
        if (payload) { const e = JSON.parse(payload); if (["done", "error", "chat"].includes(e.type)) ended = true; onEvent(e); }
      }
      if (done) break;
    }
    if (!ended) throw new Error("连接中断，本次审查尚未完成，请重新验证或生成。");
  } finally { reader.releaseLock(); }
}
async function run(validateOnly = false) {
  if (state.busy) return;
  const requirement = $("requirement").value.trim();
  if (!requirement || (validateOnly && !state.complete)) return;
  state.controller?.abort(); const controller = new AbortController(); state.controller = controller;
  const revision = ++state.revision;
  notice(""); emptyReport(); resetStages();
  if (!validateOnly) { state.code = ""; state.complete = false; state.codeId = ""; renderCode(); }
  else { stages.input.status = stages.generation.status = "done"; stages.generation.message = "使用当前完整代码"; renderStages(); }
  setBusy(true);
  const timeout = setTimeout(() => controller.abort(), 390000);
  const payload = { requirement, language: state.language, ...(validateOnly ? { code: state.code } : {}) };
  try {
    await readEvents(validateOnly ? "/api/validate-stream" : "/api/generate-stream", payload, e => {
      if (revision !== state.revision) return;
      if (e.type === "delta") { state.code += e.text; scheduleCode(); $("codeSource").textContent = "生成中 · 同步检查"; }
      if (e.type === "stage" && stages[e.stage]) { stages[e.stage] = { ...stages[e.stage], status: e.status, message: e.message }; renderStages(); }
      if (e.type === "checks") { if (!e.code_id || !state.codeId || e.code_id === state.codeId) renderReport(e.report); }
      if (e.type === "code") {
        state.code = e.code; state.complete = true; state.codeId = e.code_id; state.source = e.source; renderCode(); updateActions();
        $("codeSource").textContent = ({ model: "模型生成", cache: "相同需求 · 已复用代码", reference: "离线参考代码" })[e.source] || "完整代码";
        $("outputHint").textContent = "代码已完整返回，正在进行需求对应审查。";
      }
      if (e.type === "done") { renderReport(e.report); $("outputHint").textContent = e.report.conclusion + "。"; }
      if (e.type === "notice") notice(e.message);
      if (e.type === "chat") { notice(e.content); state.code = ""; renderCode(); }
      if (e.type === "error") {
        notice(e.message);
        if (e.clear_code) { state.code = ""; state.complete = false; renderCode(); }
        for (const s of Object.values(stages)) if (s.status === "active") { s.status = "warn"; s.message = "本步骤暂未完成，可重试"; }
        renderStages(); $("outputHint").textContent = "本次处理未全部完成，请重试。";
      }
    }, controller);
  } catch (err) {
    if (revision === state.revision) {
      notice(err.name === "AbortError" ? "已停止本次处理。完整代码可保留，未完成的检查需重新运行。" : err.message);
      for (const s of Object.values(stages)) if (s.status === "active") { s.status = "warn"; s.message = "本步骤已中断，请重试"; }
      renderStages();
    }
  } finally {
    clearTimeout(timeout);
    if (revision === state.revision) { setBusy(false); renderCode(); }
  }
}

async function importFile(file) {
  if (!file) return;
  if (file.size > 2 * 1024 * 1024) return toast("文件不能超过 2 MB。");
  const revision = state.revision;
  $("importButton").disabled = true; $("importButton").textContent = "读取中…";
  try {
    const data = new FormData(); data.append("file", file);
    const result = await jsonRequest("/api/import-file", { method: "POST", body: data, signal: AbortSignal.timeout(30000) });
    if (state.revision !== revision) return toast("读取期间需求已变更，未覆盖当前内容；请重新导入。");
    if ($("requirement").value.trim() && !window.confirm("导入内容将替换当前需求说明。是否继续？")) return;
    $("requirement").value = result.text; invalidate();
    document.querySelectorAll(".scenario").forEach(b => { b.classList.remove("selected"); b.setAttribute("aria-pressed", "false"); });
    $("fileInfo").hidden = false; $("fileInfo").textContent = `${result.filename} · ${result.characters} 字符`;
    notice(result.notice);
  } catch (e) { toast(e.message || "文件读取未完成，请重试。"); }
  finally { $("importButton").disabled = false; $("importButton").textContent = "选择文件"; $("fileInput").value = ""; }
}

$("generate").addEventListener("click", () => run());
$("validate").addEventListener("click", () => run(true));
$("cancel").addEventListener("click", () => state.controller?.abort());
$("requirement").addEventListener("input", () => { invalidate(); $("fileInfo").hidden = true; document.querySelectorAll(".scenario").forEach(b => { b.classList.remove("selected"); b.setAttribute("aria-pressed", "false"); }); });
$("clear").addEventListener("click", () => { $("requirement").value = ""; invalidate(); $("fileInfo").hidden = true; notice(""); $("requirement").focus(); });
document.querySelectorAll("[data-language]").forEach(b => b.addEventListener("click", () => language(b.dataset.language)));
$("copy").addEventListener("click", async () => { if (!state.complete) return; try { await navigator.clipboard.writeText(state.code); toast("代码已复制"); } catch { toast("当前浏览器未允许剪贴板访问，请手动选中代码复制。"); } });
$("export").addEventListener("click", () => {
  if (!state.complete) return;
  const blob = new Blob([state.code], { type: "text/plain;charset=utf-8" }), url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = url; a.download = "control_module." + state.language; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); toast("代码文件已导出");
});
$("importButton").addEventListener("click", () => $("fileInput").click());
$("fileInput").addEventListener("change", e => importFile(e.target.files[0]));
for (const name of ["dragenter", "dragover"]) $("dropZone").addEventListener(name, e => { e.preventDefault(); $("dropZone").classList.add("dragging"); });
for (const name of ["dragleave", "drop"]) $("dropZone").addEventListener(name, e => { e.preventDefault(); $("dropZone").classList.remove("dragging"); if (name === "drop") importFile(e.dataTransfer.files[0]); });

async function init() {
  resetStages(); emptyReport(); updateActions();
  try {
    const [health, data] = await Promise.all([jsonRequest("/health"), jsonRequest("/api/scenarios")]);
    $("serviceStatus").className = "status-pill " + (health.generation_ready ? "ready" : "offline");
    $("serviceStatus").innerHTML = `<i></i>${health.generation_ready ? "服务已就绪" : "离线演示模式"}`;
    state.scenarios = data.scenarios;
    $("scenarios").innerHTML = data.scenarios.map(s => `<button class="scenario" data-scenario="${esc(s.id)}" title="${esc(s.description)}" aria-pressed="false"><svg><use href="#i-${esc(s.icon)}"/></svg><span><strong>${esc(s.title)}</strong><small>${esc(s.tag)}</small></span></button>`).join("");
    $("scenarios").addEventListener("click", e => {
      const button = e.target.closest("[data-scenario]"); if (!button) return;
      const scenario = state.scenarios.find(s => s.id === button.dataset.scenario); if (!scenario) return;
      $("requirement").value = scenario.requirement; invalidate(); notice(""); $("fileInfo").hidden = true;
      document.querySelectorAll(".scenario").forEach(b => { b.classList.toggle("selected", b === button); b.setAttribute("aria-pressed", String(b === button)); });
    });
    $("scenarios").querySelector("button")?.click();
  } catch { $("serviceStatus").innerHTML = "<i></i>连接待恢复"; notice("页面已打开，但服务暂未就绪。请稍后刷新。"); }
}
init();
