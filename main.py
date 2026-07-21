from __future__ import annotations

import logging
import os
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from llm_client import LLMClient, LLMServiceError
from validator_fallback import fallback_code, fallback_validation, looks_like_plc_request


load_dotenv()

INDEX_HTML = "<!doctype html>\n<html lang=\"zh-CN\">\n<head>\n  <meta charset=\"UTF-8\" />\n  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n  <title>工业PLC代码生成与验证平台 Demo</title>\n  <link rel=\"stylesheet\" href=\"/static/styles.css\" />\n</head>\n<body>\n  <div class=\"page\">\n    <header class=\"header\">\n      <div class=\"brand\">\n        <div class=\"logo\">PLC<span></span></div>\n        <div>\n          <h1>工业PLC代码生成与验证平台 Demo</h1>\n          <p>小样本微调模型 · IEC 61131-3 Structured Text (ST) · 代码生成与校验</p>\n        </div>\n      </div>\n      <div class=\"status-row\">\n        <div id=\"modelStatus\" class=\"badge badge-warn\">模型加载中...</div>\n        <div class=\"badge badge-red\">Demo展示模式</div>\n      </div>\n    </header>\n\n    <div id=\"notice\" class=\"notice\">系统初始化中...</div>\n\n    <main class=\"main-grid\">\n      <section class=\"card input-card red-left\">\n        <div class=\"card-title\"><span class=\"icon\">✎</span><h2>需求输入</h2></div>\n        <textarea id=\"requirement\" placeholder=\"请输入工业PLC/ST控制需求\"></textarea>\n        <div class=\"chips\">\n          <button data-template=\"motor\">⚙ 电机控制</button>\n          <button data-template=\"pump\">♨ 泵阀联锁</button>\n          <button data-template=\"conveyor\">♣ 传送带计数</button>\n          <button data-template=\"alarm\">♙ 报警保护</button>\n          <button data-template=\"timer\">⏱ 定时控制</button>\n        </div>\n        <div class=\"actions\">\n          <button id=\"generateBtn\" class=\"primary\">&lt;/&gt; 生成代码</button>\n          <button id=\"clearBtn\" class=\"secondary\">⌫ 清空输入</button>\n        </div>\n      </section>\n\n      <section class=\"card code-card\">\n        <div class=\"card-header\">\n          <div class=\"card-title\"><span class=\"icon code-icon\">&lt;/&gt;</span><h2>ST代码生成结果</h2></div>\n          <div class=\"small-actions\">\n            <button id=\"copyBtn\">▣ 复制代码</button>\n            <button id=\"exportBtn\">⇩ 导出.st</button>\n          </div>\n        </div>\n        <div id=\"chatBox\" class=\"chat-box hidden\"></div>\n        <pre id=\"codeBox\" class=\"code-box\"></pre>\n        <div class=\"code-actions\"><button id=\"validateBtn\" class=\"outline-red\">开始代码验证</button></div>\n      </section>\n    </main>\n\n    <section class=\"workflow\">\n      <div class=\"step\"><span>⇲</span>需求输入</div><i></i>\n      <div class=\"step\"><span>♧</span>模型生成</div><i></i>\n      <div class=\"step\"><span>&lt;/&gt;</span>代码返回</div><i></i>\n      <div class=\"step\"><span>♢</span>自动校验</div>\n    </section>\n\n    <section class=\"bottom-grid\">\n      <section class=\"card check-card\">\n        <div class=\"card-title\"><span class=\"icon\">▣</span><h2>检测项</h2></div>\n        <ul class=\"check-list\">\n          <li>✓ 语法检查 <b>›</b></li>\n          <li>✓ POU结构检查 <b>›</b></li>\n          <li>✓ 输入/输出变量完整性 <b>›</b></li>\n          <li>✓ 命名规范检查 <b>›</b></li>\n          <li>✓ 逻辑一致性检查 <b>›</b></li>\n          <li>✓ IEC 61131-3 规范符合性 <b>›</b></li>\n        </ul>\n      </section>\n\n      <section class=\"card summary-card\">\n        <div class=\"card-title\"><span class=\"icon\">◷</span><h2>验证结果总览</h2></div>\n        <div class=\"status-grid\">\n          <div class=\"status pass\"><span>✓</span><label>语法状态</label><b id=\"syntaxStatus\">待验证</b></div>\n          <div class=\"status pass\"><span>✓</span><label>POU结构</label><b id=\"pouStatus\">待验证</b></div>\n          <div class=\"status pass\"><span>✓</span><label>变量映射</label><b id=\"varStatus\">待验证</b></div>\n          <div class=\"status warn\"><span>!</span><label>逻辑规则</label><b id=\"logicStatus\">待验证</b></div>\n          <div class=\"status warn\"><span>!</span><label>风险提示</label><b id=\"riskStatus\">待验证</b></div>\n        </div>\n      </section>\n\n      <section class=\"card suggest-card red-left-small\">\n        <div class=\"card-title\"><span class=\"icon\">?</span><h2>问题定位与优化建议</h2></div>\n        <ol id=\"suggestions\"><li>等待代码验证结果。</li></ol>\n        <div class=\"conclusion\">\n          <h3>验证结论</h3>\n          <div id=\"conclusionText\" class=\"conclusion-bar\">待验证</div>\n        </div>\n      </section>\n    </section>\n\n    <footer>适用于工业PLC控制代码生成、Demo演示与模型验证</footer>\n  </div>\n  <script src=\"/static/app.js\"></script>\n</body>\n</html>\n"
STYLES_CSS = ":root{\n  --red:#d6001c;--dark:#152233;--muted:#66758a;--line:#dbe3ee;--bg:#f4f7fb;\n  --green:#11985a;--green-bg:#eafaf1;--yellow:#f59e0b;--yellow-bg:#fff7e6;\n}\n*{box-sizing:border-box} body{margin:0;font-family:\"Microsoft YaHei\",Arial,sans-serif;background:linear-gradient(180deg,#f7f9fc,#eef3f8);color:var(--dark)}\n.page{width:100%;max-width:1920px;margin:0 auto;padding:16px 26px 20px}.header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px}.brand{display:flex;gap:20px;align-items:center}.logo{width:74px;height:74px;border-radius:12px;background:linear-gradient(145deg,#e0001b,#c40019);color:white;font-size:28px;font-weight:900;display:flex;align-items:center;justify-content:center;flex-direction:column;box-shadow:0 10px 24px rgba(214,0,28,.22)}.logo span{display:block;width:24px;height:5px;border:2px solid white;border-top:0;margin-top:8px;border-radius:2px}.brand h1{font-size:36px;line-height:1.1;margin:0 0 8px;font-weight:900;letter-spacing:-1px}.brand p{font-size:16px;color:var(--muted);margin:0}.status-row{display:flex;gap:14px;margin-top:8px}.badge{padding:12px 18px;border-radius:9px;font-size:16px;font-weight:700;border:1px solid}.badge-ok{color:#0d7f4d;background:#ecfff5;border-color:#9ce4bd}.badge-warn{color:#965b00;background:#fff8e8;border-color:#f5d48d}.badge-red{color:var(--red);background:#fff4f5;border-color:#ffb7c0}.notice{background:white;border:1px solid var(--line);border-radius:10px;padding:11px 16px;color:#526176;margin-bottom:16px;box-shadow:0 4px 16px rgba(21,34,51,.04)}.main-grid{display:grid;grid-template-columns:42% 58%;gap:24px}.card{background:white;border:1px solid var(--line);border-radius:14px;box-shadow:0 10px 26px rgba(21,34,51,.07);padding:24px;position:relative;overflow:hidden}.red-left:before,.red-left-small:before{content:\"\";position:absolute;left:0;top:58px;bottom:26px;width:8px;background:var(--red);border-radius:0 8px 8px 0}.red-left-small:before{top:54px;bottom:18px}.card-title{display:flex;align-items:center;gap:10px}.card-title h2{font-size:25px;margin:0;font-weight:900}.icon{color:var(--red);font-weight:900;font-size:24px}.input-card textarea{width:100%;height:168px;resize:vertical;border:1px solid #cdd8e5;border-radius:10px;margin-top:18px;padding:22px;font-size:18px;line-height:1.75;outline:none}.input-card textarea:focus{border-color:#e25a6a;box-shadow:0 0 0 3px rgba(214,0,28,.08)}.chips{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}.chips button,.small-actions button,.secondary{border:1px solid #d6dfeb;background:#f8fafc;border-radius:8px;padding:10px 14px;font-size:15px;font-weight:700;color:#4a5b70;cursor:pointer}.chips button:hover{border-color:#e25a6a;color:var(--red)}.actions{display:flex;gap:14px}.primary{background:var(--red);border:0;border-radius:9px;color:#fff;font-size:17px;font-weight:900;padding:14px 26px;box-shadow:0 10px 18px rgba(214,0,28,.22);cursor:pointer}.primary:disabled,.outline-red:disabled{opacity:.6;cursor:not-allowed}.secondary{font-size:16px;padding:14px 24px}.code-card{padding:24px 24px 14px}.card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.small-actions{display:flex;gap:12px}.code-box{min-height:326px;max-height:458px;overflow:auto;background:#fbfdff;border:1px solid #d5dfeb;border-radius:11px;margin:0;padding:16px 18px 16px 0;font-family:Consolas,\"Cascadia Mono\",monospace;font-size:16px;line-height:1.5;white-space:pre;color:#172033}.code-line{display:flex}.ln{width:54px;text-align:right;padding-right:18px;color:#8796aa;user-select:none}.kw{color:#0b51ff;font-weight:800}.type{color:#6d28d9;font-weight:800}.op{color:#0b51ff;font-weight:800}.chat-box{min-height:326px;background:#fbfdff;border:1px solid #d5dfeb;border-radius:11px;padding:24px;font-size:18px;line-height:1.8;color:#263548}.hidden{display:none}.code-actions{display:flex;justify-content:flex-end;margin-top:12px}.outline-red{border:1px solid #ffabb5;color:var(--red);background:#fff7f8;border-radius:9px;padding:13px 22px;font-size:17px;font-weight:900;cursor:pointer}.workflow{display:flex;align-items:center;justify-content:center;gap:22px;margin:22px 0}.workflow i{width:130px;border-top:2px dashed #b8c5d5}.step{display:flex;align-items:center;gap:11px;font-size:19px;font-weight:900}.step span{display:inline-flex;width:42px;height:42px;border-radius:50%;background:var(--red);color:#fff;align-items:center;justify-content:center;box-shadow:0 8px 20px rgba(214,0,28,.25);font-size:18px}.bottom-grid{display:grid;grid-template-columns:25% 35% 40%;gap:24px}.check-list{list-style:none;margin:18px 0 0;padding:0}.check-list li{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #edf1f6;padding:12px 2px;color:#314156;font-size:17px}.check-list li::first-letter{color:var(--green)}.check-list b{color:#9aa8b8}.status-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}.status{display:grid;grid-template-columns:34px 1fr auto;align-items:center;gap:12px;border-radius:10px;padding:16px 18px;font-size:16px}.status span{width:25px;height:25px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:white;font-weight:900}.pass{background:var(--green-bg);border:1px solid #bcebd0}.pass span{background:var(--green)}.pass b{color:#067040}.warn{background:var(--yellow-bg);border:1px solid #ffd98c}.warn span{background:var(--yellow)}.warn b{color:#7d4b00}.suggest-card ol{margin:16px 0 20px;padding-left:28px;font-size:16px;line-height:1.9}.suggest-card li::marker{color:var(--red);font-weight:900}.conclusion{border-top:1px solid #e3e9f2;padding-top:14px}.conclusion h3{margin:0 0 10px}.conclusion-bar{background:var(--green-bg);border:1px solid #87dcae;color:#08733f;border-radius:9px;padding:14px;font-size:20px;font-weight:900;text-align:center}footer{text-align:center;color:#738096;padding:18px 0 4px;border-top:1px solid #dfe7f1;margin-top:20px}@media (max-width:1200px){.main-grid,.bottom-grid{grid-template-columns:1fr}.workflow{flex-wrap:wrap}.workflow i{width:70px}.brand h1{font-size:28px}}\n"
APP_JS = "const templates = {\n  motor: '请使用 IEC 61131-3 标准结构化文本（ST语言）编写“电动机的正反转控制”相关工业控制代码，包含正转启动、反转启动、停止、热继电器正常允许信号、正反转互锁和运行输出。',\n  pump: '请编写水泵启停控制ST代码，包含启动信号、停止信号、低液位保护、高液位允许、急停信号和水泵运行输出。',\n  conveyor: '请编写传送带工件计数ST代码，包含传感器输入、复位信号、计数阈值、当前计数和满料报警输出。',\n  alarm: '请编写设备报警保护ST代码，包含故障输入、复位按钮、报警锁存和报警输出。',\n  timer: '请编写延时启动控制ST代码，包含启动输入、停止输入、延时时间、定时器和运行输出。'\n};\n\nconst defaultCode = `FUNCTION_BLOCK SelfLock\nVAR_INPUT\n    xStart : BOOL;\n    xStop : BOOL;\n    xThermalOK : BOOL;\nEND_VAR\nVAR_OUTPUT\n    xRun : BOOL;\nEND_VAR\n\nxRun := (xStart OR xRun) AND NOT xStop AND xThermalOK;\n\nEND_FUNCTION_BLOCK`;\n\nlet currentCode = defaultCode;\nconst $ = (id) => document.getElementById(id);\n\nfunction escapeHtml(value) {\n  return String(value).replace(/[&<>\"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[ch]));\n}\n\nfunction highlight(line) {\n  let text = escapeHtml(line);\n  const keywords = ['FUNCTION_BLOCK','END_FUNCTION_BLOCK','PROGRAM','END_PROGRAM','FUNCTION','END_FUNCTION','VAR_INPUT','VAR_OUTPUT','VAR_IN_OUT','VAR','END_VAR','IF','THEN','ELSE','ELSIF','END_IF','CASE','OF','END_CASE'];\n  keywords.forEach(k => { text = text.replaceAll(k, `<span class=\"kw\">${k}</span>`); });\n  ['BOOL','BYTE','WORD','DWORD','USINT','SINT','UINT','INT','UDINT','DINT','REAL','LREAL','TIME','TON','TOF','TP','CTU','CTD','R_TRIG','F_TRIG','FALSE','TRUE'].forEach(k => { text = text.replaceAll(k, `<span class=\"type\">${k}</span>`); });\n  ['AND','OR','NOT','XOR'].forEach(k => { text = text.replaceAll(k, `<span class=\"op\">${k}</span>`); });\n  return text;\n}\n\nfunction renderCode(code) {\n  currentCode = code || '';\n  $('chatBox').classList.add('hidden');\n  $('codeBox').classList.remove('hidden');\n  $('validateBtn').disabled = !currentCode.trim();\n  $('codeBox').innerHTML = currentCode.split('\\n').map((line, i) => `<div class=\"code-line\"><span class=\"ln\">${i + 1}</span><span>${highlight(line)}</span></div>`).join('');\n}\n\nfunction renderChat(message) {\n  currentCode = '';\n  $('codeBox').classList.add('hidden');\n  $('chatBox').classList.remove('hidden');\n  $('validateBtn').disabled = true;\n  $('chatBox').innerHTML = `<b>智能助手：</b><br>${escapeHtml(message || '请输入具体PLC/ST代码生成需求。')}`;\n}\n\nfunction setNotice(text) {\n  $('notice').textContent = text;\n}\n\nfunction setLoading(button, loading, label) {\n  button.disabled = loading;\n  button.textContent = loading ? '处理中...' : label;\n}\n\nfunction responseMessage(response, data) {\n  if (response.ok) return '';\n  return data?.detail || '请求暂时未完成，请稍后重试。';\n}\n\nasync function loadHealth() {\n  try {\n    const response = await fetch('/api/health', {cache: 'no-store'});\n    const health = await response.json();\n    if (health.status === 'ok') {\n      $('modelStatus').className = health.llm_configured ? 'badge badge-ok' : 'badge badge-warn';\n      $('modelStatus').textContent = health.llm_configured ? '模型已加载' : '模型准备中';\n      setNotice('系统就绪。请输入控制需求并生成ST代码。');\n      return;\n    }\n    throw new Error('not ready');\n  } catch (_error) {\n    $('modelStatus').className = 'badge badge-warn';\n    $('modelStatus').textContent = '系统准备中';\n    setNotice('系统正在准备，请稍后刷新页面。');\n  }\n}\n\nasync function generate() {\n  const requirement = $('requirement').value.trim();\n  if (!requirement) {\n    setNotice('请先输入需求。');\n    return;\n  }\n\n  const button = $('generateBtn');\n  setLoading(button, true, '</> 生成代码');\n  try {\n    const response = await fetch('/api/generate-code', {\n      method: 'POST',\n      headers: {'Content-Type': 'application/json'},\n      body: JSON.stringify({requirement})\n    });\n    const data = await response.json();\n    const error = responseMessage(response, data);\n    if (error) throw new Error(error);\n\n    if (data.mode === 'code' && data.content) {\n      renderCode(data.content);\n      resetValidation();\n      setNotice('代码已生成，可复制、导出或开始代码验证。');\n    } else {\n      renderChat(data.content);\n      setNotice('已完成本次回复。需要生成代码时，请描述具体PLC控制工况。');\n    }\n  } catch (error) {\n    setNotice(error.message || '请求暂时未完成，请稍后重试。');\n  } finally {\n    setLoading(button, false, '</> 生成代码');\n  }\n}\n\nasync function validateCode() {\n  const requirement = $('requirement').value.trim();\n  const code = currentCode.trim();\n  if (!code) {\n    setNotice('当前没有ST代码可验证。');\n    return;\n  }\n\n  const button = $('validateBtn');\n  setLoading(button, true, '开始代码验证');\n  try {\n    const response = await fetch('/api/validate-code', {\n      method: 'POST',\n      headers: {'Content-Type': 'application/json'},\n      body: JSON.stringify({requirement, code})\n    });\n    const data = await response.json();\n    const error = responseMessage(response, data);\n    if (error) throw new Error(error);\n\n    $('syntaxStatus').textContent = data.syntax_status || '待复核';\n    $('pouStatus').textContent = data.pou_structure || '待复核';\n    $('varStatus').textContent = data.variable_mapping || '待复核';\n    $('logicStatus').textContent = data.logic_rule || '待复核';\n    $('riskStatus').textContent = `${data.risk_count ?? 0}项建议`;\n    $('conclusionText').textContent = data.conclusion || '建议复核';\n    const suggestions = Array.isArray(data.suggestions) && data.suggestions.length ? data.suggestions : ['建议结合目标PLC平台进行工程复核。'];\n    $('suggestions').innerHTML = suggestions.map(item => `<li>${escapeHtml(item)}</li>`).join('');\n    setNotice('验证结果已更新，请查看下方结果总览与优化建议。');\n  } catch (error) {\n    setNotice(error.message || '验证暂时未完成，请稍后重试。');\n  } finally {\n    setLoading(button, false, '开始代码验证');\n  }\n}\n\nfunction resetValidation() {\n  ['syntaxStatus','pouStatus','varStatus','logicStatus','riskStatus'].forEach(id => { $(id).textContent = '待验证'; });\n  $('suggestions').innerHTML = '<li>等待代码验证结果。</li>';\n  $('conclusionText').textContent = '待验证';\n}\n\nasync function copyCode() {\n  if (!currentCode.trim()) {\n    setNotice('当前没有代码可复制。');\n    return;\n  }\n  try {\n    await navigator.clipboard.writeText(currentCode);\n  } catch (_error) {\n    const area = document.createElement('textarea');\n    area.value = currentCode;\n    document.body.appendChild(area);\n    area.select();\n    document.execCommand('copy');\n    area.remove();\n  }\n  setNotice('代码已复制到剪贴板。');\n}\n\nfunction exportCode() {\n  if (!currentCode.trim()) {\n    setNotice('当前没有代码可导出。');\n    return;\n  }\n  const blob = new Blob([currentCode], {type: 'text/plain;charset=utf-8'});\n  const url = URL.createObjectURL(blob);\n  const anchor = document.createElement('a');\n  anchor.href = url;\n  anchor.download = 'generated_plc_code.st';\n  anchor.click();\n  URL.revokeObjectURL(url);\n  setNotice('已导出 .st 文件。');\n}\n\nfunction bind() {\n  $('generateBtn').addEventListener('click', generate);\n  $('validateBtn').addEventListener('click', validateCode);\n  $('copyBtn').addEventListener('click', copyCode);\n  $('exportBtn').addEventListener('click', exportCode);\n  $('clearBtn').addEventListener('click', () => {\n    $('requirement').value = '';\n    setNotice('输入已清空。');\n  });\n  document.querySelectorAll('[data-template]').forEach(button => {\n    button.addEventListener('click', () => {\n      $('requirement').value = templates[button.dataset.template] || templates.motor;\n      setNotice('已填入示例工况。点击“生成代码”查看结果。');\n    });\n  });\n}\n\n$('requirement').value = templates.motor;\nrenderCode(defaultCode);\nbind();\nloadHealth();\n"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("plc-demo")

app = FastAPI(
    title="工业PLC代码生成与验证平台",
    version="6.0.0",
    docs_url=None,
    redoc_url=None,
)

configured_origins = [
    item.strip()
    for item in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if item.strip()
]
if configured_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

llm = LLMClient.from_environment()


class GenerateRequest(BaseModel):
    requirement: str = Field(min_length=1, max_length=8000)


class GenerateResponse(BaseModel):
    mode: Literal["code", "chat"]
    content: str
    can_validate: bool


class ValidateRequest(BaseModel):
    requirement: str = Field(default="", max_length=8000)
    code: str = Field(min_length=1, max_length=30000)


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


@app.get("/static/styles.css")
async def styles() -> Response:
    return Response(STYLES_CSS, media_type="text/css")


@app.get("/static/app.js")
async def script() -> Response:
    return Response(APP_JS, media_type="application/javascript")


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "plc-demo-platform",
        "version": "6.0.0",
        "llm_configured": llm.is_configured,
    }


@app.get("/api/health", include_in_schema=False)
async def api_health() -> dict[str, object]:
    return await health()


@app.post("/api/generate-code", response_model=GenerateResponse)
async def generate_code(payload: GenerateRequest) -> GenerateResponse:
    requirement = payload.requirement.strip()
    if not requirement:
        raise HTTPException(status_code=400, detail="请输入需求内容。")

    if not looks_like_plc_request(requirement):
        try:
            message = await llm.chat(requirement)
        except LLMServiceError as exc:
            logger.warning("Chat completion unavailable: %s", exc)
            message = (
                "您好！我是工业PLC代码生成与验证助手。您可以描述电动机、"
                "泵阀、传送带、报警保护或定时控制等需求，我会协助生成ST代码。"
            )
        return GenerateResponse(mode="chat", content=message, can_validate=False)

    try:
        code = await llm.generate_st_code(requirement)
        if not code.strip():
            raise LLMServiceError("Empty model response")
    except LLMServiceError as exc:
        logger.warning("Code generation unavailable; using safe fallback: %s", exc)
        code = fallback_code(requirement)
    return GenerateResponse(mode="code", content=code, can_validate=True)


@app.post("/api/validate-code")
async def validate_code(payload: ValidateRequest) -> dict[str, object]:
    requirement = payload.requirement.strip()
    code = payload.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="当前没有ST代码可验证。")

    local_result = fallback_validation(requirement, code)
    try:
        return await llm.validate_st_code(requirement, code, local_result)
    except LLMServiceError as exc:
        logger.warning("Model validation unavailable; using local review: %s", exc)
        return local_result


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "请求暂时未完成，请稍后重试。"},
    )
