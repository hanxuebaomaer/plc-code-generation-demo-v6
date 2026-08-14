const templates = {
  motor: '请使用 IEC 61131-3 标准结构化文本（ST语言）编写“电动机正反转控制”功能块，包含正转启动、反转启动、停止、热继电器正常允许信号、正反转互锁和运行状态输出。',
  pump: '请编写水泵启停控制ST代码，包含启动信号、停止信号、低液位保护、高液位允许、急停信号和水泵运行输出。',
  conveyor: '请编写传送带工件计数ST代码，包含传感器输入、复位信号、计数阈值、当前计数和满料报警输出。',
  alarm: '请编写设备报警保护ST代码，包含故障输入、复位按钮、报警锁存和报警输出。',
  timer: '请编写延时启动控制ST代码，包含启动输入、停止输入、延时时间、定时器和运行输出。'
};

const defaultCode = `FUNCTION_BLOCK SelfLock
VAR_INPUT
    xStart : BOOL;
    xStop : BOOL;
    xThermalOK : BOOL;
END_VAR
VAR_OUTPUT
    xRun : BOOL;
END_VAR

xRun := (xStart OR xRun) AND NOT xStop AND xThermalOK;

END_FUNCTION_BLOCK`;

const validationItems = [
  ['syntax_status', 'syntaxStatus', 'checkSyntaxStatus'],
  ['pou_structure', 'pouStatus', 'checkPouStatus'],
  ['variable_mapping', 'varStatus', 'checkVariableStatus'],
  ['naming_convention', 'namingStatus', 'checkNamingStatus'],
  ['logic_rule', 'logicStatus', 'checkLogicStatus'],
  ['standard_compliance', 'standardStatus', 'checkStandardStatus']
];

let currentCode = defaultCode;
const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value).replace(/[&<>"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
}

function highlight(line) {
  let text = escapeHtml(line);
  const keywords = ['FUNCTION_BLOCK','END_FUNCTION_BLOCK','PROGRAM','END_PROGRAM','FUNCTION','END_FUNCTION','VAR_INPUT','VAR_OUTPUT','VAR_IN_OUT','VAR','END_VAR','IF','THEN','ELSE','ELSIF','END_IF','CASE','OF','END_CASE'];
  keywords.forEach(k => { text = text.replaceAll(k, `<span class="kw">${k}</span>`); });
  ['BOOL','BYTE','WORD','DWORD','USINT','SINT','UINT','INT','UDINT','DINT','REAL','LREAL','TIME','TON','TOF','TP','CTU','CTD','R_TRIG','F_TRIG','FALSE','TRUE'].forEach(k => { text = text.replaceAll(k, `<span class="type">${k}</span>`); });
  ['AND','OR','NOT','XOR'].forEach(k => { text = text.replaceAll(k, `<span class="op">${k}</span>`); });
  return text;
}

function renderCode(code) {
  currentCode = code || '';
  $('chatBox').classList.add('hidden');
  $('codeBox').classList.remove('hidden');
  $('validateBtn').disabled = !currentCode.trim();
  $('codeBox').innerHTML = currentCode
    .split('\n')
    .map((line, i) => `<div class="code-line"><span class="ln">${i + 1}</span><span>${highlight(line)}</span></div>`)
    .join('');
}

function renderChat(message) {
  currentCode = '';
  $('codeBox').classList.add('hidden');
  $('chatBox').classList.remove('hidden');
  $('validateBtn').disabled = true;
  $('chatBox').innerHTML = `<b>智能助手：</b><br>${escapeHtml(message || '请输入具体PLC/ST代码生成需求。')}`;
}

function setNotice(text) {
  $('notice').textContent = text;
}

function setLoading(button, loading, label) {
  button.disabled = loading;
  button.textContent = loading ? '处理中...' : label;
}

function responseMessage(response, data) {
  if (response.ok) return '';
  return data?.detail || '请求暂时未完成，请稍后重试。';
}

async function fetchJson(url, options, timeoutMs = 100000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {...options, signal: controller.signal});
    const data = await response.json();
    const error = responseMessage(response, data);
    if (error) throw new Error(error);
    return data;
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('本次处理时间较长，请稍后重试。');
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

async function loadHealth() {
  try {
    const response = await fetch('/api/health', {cache: 'no-store'});
    const health = await response.json();
    if (health.status !== 'ok') throw new Error('not ready');
    $('modelStatus').className = health.llm_configured ? 'badge badge-ok' : 'badge badge-warn';
    $('modelStatus').textContent = health.llm_configured ? '模型已加载' : '模型准备中';
    setNotice('系统就绪。请输入控制需求并生成ST代码。');
  } catch (_error) {
    $('modelStatus').className = 'badge badge-warn';
    $('modelStatus').textContent = '系统准备中';
    setNotice('系统正在准备，请稍后刷新页面。');
  }
}

async function generate() {
  const requirement = $('requirement').value.trim();
  if (!requirement) {
    setNotice('请先输入需求。');
    return;
  }

  const button = $('generateBtn');
  setLoading(button, true, '</> 生成代码');
  setNotice('正在根据当前需求生成结果，请稍候。');
  try {
    const data = await fetchJson('/api/generate-code', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({requirement})
    });

    if (data.mode === 'code' && data.content) {
      renderCode(data.content);
      resetValidation();
      setNotice('代码已生成，可复制、导出或开始代码验证。');
    } else {
      renderChat(data.content);
      resetValidation();
      setNotice('已完成本次回复。需要生成代码时，请描述具体PLC控制工况。');
    }
  } catch (error) {
    setNotice(error.message || '请求暂时未完成，请稍后重试。');
  } finally {
    setLoading(button, false, '</> 生成代码');
  }
}

function statusStyle(status) {
  if (status === '通过') return {className: 'pass', icon: '✓'};
  if (status === '基本通过') return {className: 'warn', icon: '!'};
  if (status === '未通过') return {className: 'fail', icon: '×'};
  return {className: 'pending', icon: '·'};
}

function applyValidationStatus(summaryId, checkId, status) {
  const value = status || '待验证';
  const style = statusStyle(value);
  const summaryText = $(summaryId);
  const summaryCard = summaryText.closest('.status');
  const icon = summaryCard.querySelector('.status-icon');
  summaryText.textContent = value;
  summaryCard.className = `status ${style.className}`;
  icon.textContent = style.icon;

  const checkText = $(checkId);
  checkText.textContent = value;
  checkText.className = `check-result ${style.className}`;
}

async function validateCode() {
  const requirement = $('requirement').value.trim();
  const code = currentCode.trim();
  if (!code) {
    setNotice('当前没有ST代码可验证。');
    return;
  }

  const button = $('validateBtn');
  setLoading(button, true, '开始代码验证');
  setNotice('正在检查当前代码，请稍候。');
  try {
    const data = await fetchJson('/api/validate-code', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({requirement, code})
    });

    validationItems.forEach(([key, summaryId, checkId]) => {
      applyValidationStatus(summaryId, checkId, data[key]);
    });

    const riskCount = Number.isFinite(Number(data.risk_count)) ? Number(data.risk_count) : 0;
    $('riskBadge').textContent = `${riskCount}项建议`;
    $('riskBadge').className = riskCount > 0 ? 'risk-badge warn' : 'risk-badge pass';
    $('conclusionText').textContent = data.conclusion || '建议复核';
    $('conclusionText').className = data.conclusion === '建议复核' ? 'conclusion-bar conclusion-warn' : 'conclusion-bar';

    const suggestions = Array.isArray(data.suggestions) && data.suggestions.length
      ? data.suggestions
      : ['建议结合目标PLC平台进行工程复核。'];
    $('suggestions').innerHTML = suggestions.map(item => `<li>${escapeHtml(item)}</li>`).join('');
    setNotice('验证结果已更新，左侧检测项与结果总览已逐项对应。');
  } catch (error) {
    setNotice(error.message || '验证暂时未完成，请稍后重试。');
  } finally {
    setLoading(button, false, '开始代码验证');
  }
}

function resetValidation() {
  validationItems.forEach(([_key, summaryId, checkId]) => {
    applyValidationStatus(summaryId, checkId, '待验证');
  });
  $('riskBadge').textContent = '待验证';
  $('riskBadge').className = 'risk-badge pending';
  $('suggestions').innerHTML = '<li>等待代码验证结果。</li>';
  $('conclusionText').textContent = '待验证';
  $('conclusionText').className = 'conclusion-bar';
}

async function copyCode() {
  if (!currentCode.trim()) {
    setNotice('当前没有代码可复制。');
    return;
  }
  try {
    await navigator.clipboard.writeText(currentCode);
  } catch (_error) {
    const area = document.createElement('textarea');
    area.value = currentCode;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  setNotice('代码已复制到剪贴板。');
}

function exportCode() {
  if (!currentCode.trim()) {
    setNotice('当前没有代码可导出。');
    return;
  }
  const blob = new Blob([currentCode], {type: 'text/plain;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'generated_plc_code.st';
  anchor.click();
  URL.revokeObjectURL(url);
  setNotice('已导出 .st 文件。');
}

function bind() {
  $('generateBtn').addEventListener('click', generate);
  $('validateBtn').addEventListener('click', validateCode);
  $('copyBtn').addEventListener('click', copyCode);
  $('exportBtn').addEventListener('click', exportCode);
  $('clearBtn').addEventListener('click', () => {
    $('requirement').value = '';
    setNotice('输入已清空。');
  });
  document.querySelectorAll('[data-template]').forEach(button => {
    button.addEventListener('click', () => {
      $('requirement').value = templates[button.dataset.template] || templates.motor;
      setNotice('已填入示例工况。点击“生成代码”查看结果。');
    });
  });
}

$('requirement').value = templates.motor;
renderCode(defaultCode);
resetValidation();
bind();
loadHealth();
