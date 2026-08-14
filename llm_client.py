from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx


class LLMServiceError(RuntimeError):
    """Raised when the configured model service cannot produce a usable result."""


CODE_SYSTEM_PROMPT = """你是一名资深工业自动化PLC工程师，熟悉IEC 61131-3与结构化文本（ST）。
你的任务是把用户给出的具体工况转换为可读、完整、与需求逐项对应的ST代码，而不是套用固定示例。

必须遵守：
1. 只输出ST源代码，不输出Markdown围栏、前言、解释或结语；
2. 根据需求选择PROGRAM、FUNCTION_BLOCK或FUNCTION，并保证起止关键字完整；
3. 用户提到的每个设备、输入、输出、时间参数、顺序、互锁、故障及复位条件都必须在变量和逻辑中体现；
4. 不得把无关的“电动机自锁、热继电器、报警锁存”等固定模板强行套入其他工况；只有用户明确提出时才加入对应信号；
5. 多设备顺序控制应使用状态/步序或定时器清晰表达，并包含统一停止与故障处理；
6. PID/闭环控制应体现设定值、过程反馈、Kp/Ki/Kd、采样周期、积分限幅、输出限幅及复位；
7. 变量必须全部声明，命名清晰，关键逻辑带简短中文注释，语句以分号结束；
8. 复杂工况应给出足够完整的实现，不得只输出十余行的占位代码；
9. 不臆造现场I/O地址、厂商专用型号或用户未提供的安全认证结论；
10. 输出前自行核对：需求覆盖、POU完整、变量已声明、结构闭合、停止/故障条件有效。"""

CHAT_SYSTEM_PROMPT = """你是工业PLC代码生成与验证平台的智能助手。
对于问候或普通交流，使用简洁自然的中文正常回答，不要强行输出代码。
如果用户询问平台能力，可以说明你能根据工业控制需求生成IEC 61131-3结构化文本（ST）代码，并辅助进行结构与逻辑检查。
不要声称代码已经通过真实PLC编译或现场安全认证。"""

VALIDATION_SYSTEM_PROMPT = """你是一名谨慎的工业PLC/ST代码审查工程师。
请根据用户需求审查给定的IEC 61131-3结构化文本代码。逐项检查语法、POU结构、变量声明、命名规范、需求逻辑一致性及IEC 61131-3规范符合性。
不得声称已在真实PLC编译器或现场设备上验证。只返回一个JSON对象，不要输出Markdown或其他文字。"""


@dataclass(slots=True)
class LLMClient:
    api_base: str
    api_key: str
    model: str
    timeout_seconds: float = 60.0
    code_max_tokens: int = 3800
    disable_thinking: bool = True
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_environment(cls) -> "LLMClient":
        return cls(
            api_base=os.getenv("LLM_API_BASE", "").strip(),
            api_key=os.getenv("LLM_API_KEY", "").strip(),
            model=os.getenv("LLM_MODEL", "").strip(),
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
            code_max_tokens=max(1200, int(os.getenv("LLM_CODE_MAX_TOKENS", "3800"))),
            disable_thinking=os.getenv("LLM_DISABLE_THINKING", "true").lower()
            not in {"0", "false", "no"},
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_base and self.api_key and self.model)

    def _endpoint(self) -> str:
        base = self.api_base.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _http_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                connect=min(8.0, self.timeout_seconds),
                read=self.timeout_seconds,
                write=15.0,
                pool=10.0,
            )
            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
        fast_mode: bool = False,
    ) -> str:
        if not self.is_configured:
            raise LLMServiceError("Model service is not configured")

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if fast_mode and self.disable_thinking:
            body["thinking"] = {"type": "disabled"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            client = self._http_client()
            response = await client.post(self._endpoint(), headers=headers, json=body)
            if response.status_code in {400, 422} and (
                "response_format" in body or "thinking" in body
            ):
                # Keep compatibility with providers that do not support these options.
                body.pop("response_format", None)
                body.pop("thinking", None)
                response = await client.post(self._endpoint(), headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise LLMServiceError(str(exc)) from exc

        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMServiceError("Unexpected model response") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMServiceError("Empty model response")
        if finish_reason == "length":
            raise LLMServiceError("Model response was truncated")
        return content.strip()

    async def chat(self, text: str) -> str:
        return await self._complete(
            [
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
            max_tokens=500,
            fast_mode=True,
        )

    async def generate_st_code(self, requirement: str) -> str:
        checklist = _requirement_checklist(requirement)
        prompt = f"""请严格按照下面的原始需求生成完整ST代码。

【原始需求】
{requirement}

【必须覆盖的需求清单】
{chr(10).join(f'- {item}' for item in checklist)}

【生成要求】
- 先在内部识别控制对象、输入、输出、时间参数、步骤、保护和复位条件，再生成代码；
- 变量声明与主体逻辑必须逐项覆盖原始需求；
- 对多设备、顺序、PID、状态机等复杂工况，输出应包含必要的内部变量、定时器或状态变量，不得简化为通用自锁逻辑；
- 在代码首部用一行ST注释简要说明当前控制对象，便于人工确认输出与输入对应；
- 只输出最终ST源代码。"""
        content = await self._complete(
            [
                {"role": "system", "content": CODE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.05,
            max_tokens=self.code_max_tokens,
            fast_mode=True,
        )
        code = _extract_st_code(content)
        issues = code_quality_issues(requirement, code)
        if not issues:
            return code

        repair_prompt = f"""原始需求：
{requirement}

下面代码未通过需求一致性检查：
{code}

需要修正的问题：
{chr(10).join(f'- {item}' for item in issues)}

请重新生成完整ST代码，逐项覆盖原始需求。只输出ST源代码，不要解释。"""
        repaired = await self._complete(
            [
                {"role": "system", "content": CODE_SYSTEM_PROMPT},
                {"role": "user", "content": repair_prompt},
            ],
            temperature=0.03,
            max_tokens=min(self.code_max_tokens + 600, 5000),
            fast_mode=True,
        )
        repaired_code = _extract_st_code(repaired)
        remaining = code_quality_issues(requirement, repaired_code)
        if remaining:
            raise LLMServiceError("Generated code is not aligned with the requirement")
        return repaired_code

    async def validate_st_code(
        self,
        requirement: str,
        code: str,
        local_result: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = f"""用户需求：
{requirement or '未提供额外需求描述'}

待审查ST代码：
{code}

本地结构检查结果（仅供参考，请结合需求复核）：
{json.dumps(local_result, ensure_ascii=False)}

严格返回以下字段：
{{
  "syntax_status": "通过/基本通过/未通过",
  "pou_structure": "通过/基本通过/未通过",
  "variable_mapping": "通过/基本通过/未通过",
  "naming_convention": "通过/基本通过/未通过",
  "logic_rule": "通过/基本通过/未通过",
  "standard_compliance": "通过/基本通过/未通过",
  "risk_count": 0,
  "suggestions": ["具体且简短的建议"],
  "conclusion": "可用于演示/基本可用/建议复核"
}}"""
        raw = await self._complete(
            [
                {"role": "system", "content": VALIDATION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.03,
            max_tokens=1100,
            json_mode=True,
            fast_mode=True,
        )
        result = _parse_json_object(raw)
        return _normalize_validation(result, local_result)


def _extract_st_code(text: str) -> str:
    fenced = re.search(r"```(?:st|pascal|iecst)?\s*(.*?)```", text, flags=re.I | re.S)
    if fenced:
        text = fenced.group(1)

    starts = [
        position
        for token in ("FUNCTION_BLOCK", "PROGRAM", "FUNCTION")
        if (position := text.upper().find(token)) >= 0
    ]
    if starts:
        text = text[min(starts) :]

    text = text.strip().replace("\r\n", "\n")
    if not re.search(r"\b(FUNCTION_BLOCK|PROGRAM|FUNCTION)\b", text, flags=re.I):
        raise LLMServiceError("Model response does not contain an ST POU")

    upper = text.upper()
    start_match = re.match(r"\s*(FUNCTION_BLOCK|PROGRAM|FUNCTION)\b", upper)
    if start_match:
        end_token = {
            "FUNCTION_BLOCK": "END_FUNCTION_BLOCK",
            "PROGRAM": "END_PROGRAM",
            "FUNCTION": "END_FUNCTION",
        }[start_match.group(1)]
        end_pos = upper.rfind(end_token)
        if end_pos >= 0:
            text = text[: end_pos + len(end_token)].strip()
    return text


def code_quality_issues(requirement: str, code: str) -> list[str]:
    """Return requirement-alignment issues that warrant one corrective retry."""
    req = requirement.lower()
    low = code.lower()
    issues: list[str] = []
    nonblank_lines = [line for line in code.splitlines() if line.strip()]

    complex_terms = ("pid", "顺序", "三台", "多台", "状态机", "配方", "级联", "闭环")
    minimum_lines = 24 if any(term in req for term in complex_terms) else 12
    if len(nonblank_lines) < minimum_lines:
        issues.append(f"代码过短，复杂度不足（至少应有约{minimum_lines}行有效结构和逻辑）")

    if "var_input" not in low or "var_output" not in low or "end_var" not in low:
        issues.append("输入、输出或变量区不完整")

    if any(term in req for term in ("pid", "温度", "闭环")):
        required_groups = (
            ("setpoint", "设定"),
            ("process", "feedback", "温度反馈", "测量"),
            ("kp",),
            ("ki",),
            ("kd",),
            ("output", "heater", "加热"),
        )
        missing = [group[0] for group in required_groups if not any(t in low for t in group)]
        if missing:
            issues.append("PID需求未体现：" + "、".join(missing))
        if "selflock" in low or "thermalok" in low:
            issues.append("PID温控代码误用了电机自锁或热继电器模板")

    sequential = "顺序" in req or all(token in req for token in ("m1", "m2", "m3"))
    if sequential:
        missing_motors = [name for name in ("m1", "m2", "m3") if name not in low]
        if missing_motors:
            issues.append("顺序启动需求缺少设备：" + "、".join(missing_motors))
        if not any(token in low for token in ("ton", "timer", "step", "state")):
            issues.append("顺序启动需求缺少步序或定时器")
        if "alarmlatch" in low or "selflock" in low:
            issues.append("顺序启动代码误用了无关的通用模板")
        if "停止" in req and "stop" not in low:
            issues.append("顺序启动需求中的统一停止条件未体现")
        if "故障" in req and "fault" not in low:
            issues.append("顺序启动需求中的无故障允许条件未体现")

    scenario_groups = [
        (("水泵", "泵阀", "pump"), ("pump", "泵"), "水泵/泵阀"),
        (("传送带", "输送带", "计数"), ("counter", "count", "conveyor"), "传送带计数"),
        (("报警", "故障锁存"), ("alarm", "fault"), "报警保护"),
        (("正反转",), ("forward", "reverse"), "正反转"),
    ]
    for req_terms, code_terms, label in scenario_groups:
        if any(term in req for term in req_terms) and not any(term in low for term in code_terms):
            issues.append(f"代码未体现{label}需求")

    if "自锁" not in req and any(term in req for term in complex_terms) and "selflock" in low:
        issues.append("复杂工况不应退化为电机自锁模板")

    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(秒|s|分钟|min)", req, flags=re.I):
        normalized_unit = "s" if unit.lower() in {"秒", "s"} else "m"
        time_literal = f"t#{value}{normalized_unit}".lower()
        if time_literal not in low and not re.search(
            rf"\b(?:time|interval|delay|period)\w*\b", low, flags=re.I
        ):
            issues.append(f"需求中的时间参数{value}{unit}未在代码中体现")
    return issues[:8]


def _requirement_checklist(requirement: str) -> list[str]:
    """Build a deterministic coverage contract without adding another model call."""
    req = requirement.lower()
    items = [
        "POU起止结构、VAR_INPUT、VAR_OUTPUT及必要的内部变量完整",
        "仅实现当前原始需求，不复用与当前工况无关的示例模板",
    ]

    if any(term in req for term in ("pid", "闭环", "精确温度")):
        items.extend(
            [
                "温度设定值与传感器过程反馈",
                "Kp、Ki、Kd和采样周期",
                "比例、积分、微分计算，积分/输出限幅及复位",
                "0%至100%加热输出与必要状态输出",
            ]
        )

    if "顺序" in req or all(token in req for token in ("m1", "m2", "m3")):
        items.extend(
            [
                "M1、M2、M3三台电机分别声明并按M1→M2→M3启动",
                "相邻启动间隔由TON定时器或明确步序实现",
                "停止时三台电机同时撤销输出",
            ]
        )

    mappings = [
        (("故障", "fault"), "故障输入必须参与启动许可和停机逻辑"),
        (("复位", "reset"), "复位输入及其对锁存/状态的清除逻辑"),
        (("正反转",), "正转与反转输出及双向互锁"),
        (("水泵", "泵阀"), "水泵/阀门输入输出、液位或联锁条件"),
        (("传送带", "输送带", "计数"), "传感器沿检测、计数、复位和阈值输出"),
        (("报警",), "报警触发、锁存或复位条件"),
    ]
    for terms, item in mappings:
        if any(term in req for term in terms):
            items.append(item)

    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(秒|s|分钟|min)", req, flags=re.I):
        items.append(f"明确体现原始时间参数：{value}{unit}")

    return list(dict.fromkeys(items))


def _parse_json_object(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.I | re.S)
    candidate = fenced.group(1).strip() if fenced else text.strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", candidate, flags=re.S)
        if not match:
            raise LLMServiceError("Validation response is not JSON")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMServiceError("Validation response is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise LLMServiceError("Validation response is not an object")
    return parsed


def _normalize_validation(
    result: dict[str, Any], fallback: dict[str, Any]
) -> dict[str, Any]:
    statuses = {"通过", "基本通过", "未通过"}
    normalized: dict[str, Any] = {}
    for key in (
        "syntax_status",
        "pou_structure",
        "variable_mapping",
        "naming_convention",
        "logic_rule",
        "standard_compliance",
    ):
        value = str(result.get(key, fallback[key]))
        normalized[key] = value if value in statuses else fallback[key]

    suggestions = result.get("suggestions", fallback["suggestions"])
    if not isinstance(suggestions, list):
        suggestions = fallback["suggestions"]
    normalized["suggestions"] = [
        str(item)[:180] for item in suggestions[:6] if str(item).strip()
    ]
    if not normalized["suggestions"]:
        normalized["suggestions"] = fallback["suggestions"]

    try:
        risk_count = int(result.get("risk_count", len(normalized["suggestions"])))
    except (TypeError, ValueError):
        risk_count = len(normalized["suggestions"])
    normalized["risk_count"] = max(0, min(risk_count, 99))

    conclusion = str(result.get("conclusion", fallback["conclusion"]))
    if conclusion not in {"可用于演示", "基本可用", "建议复核"}:
        conclusion = fallback["conclusion"]
    normalized["conclusion"] = conclusion
    normalized["disclaimer"] = "当前结果为代码结构与逻辑辅助检查，工程应用前仍需结合目标PLC平台进行编译和测试。"
    return normalized
