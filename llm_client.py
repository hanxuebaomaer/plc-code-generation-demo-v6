from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx


class LLMServiceError(RuntimeError):
    """Raised when the configured model service cannot produce a usable result."""


CODE_SYSTEM_PROMPT = """你是一名经验丰富的工业自动化PLC工程师，熟悉IEC 61131-3标准与结构化文本（ST）语言。
根据用户需求生成完整、规范、可读的PLC/ST代码。

必须遵守：
1. 只输出ST源代码，不输出Markdown代码围栏、解释、前言或结语；
2. 选择合适的PROGRAM、FUNCTION_BLOCK或FUNCTION，并保持起止结构完整；
3. 声明所使用的输入、输出及内部变量，变量名称清晰；
4. 控制逻辑与需求一致，互锁、保护、定时和复位条件表达明确；
5. 使用IEC 61131-3常见语法，语句以分号结束；
6. 不臆造现场I/O地址、设备型号或未提供的安全条件；
7. 代码用于方案演示，复杂安全逻辑应通过注释提醒工程复核。"""

CHAT_SYSTEM_PROMPT = """你是工业PLC代码生成与验证平台的智能助手。
对于问候或普通交流，使用简洁自然的中文正常回答，不要强行输出代码。
如果用户询问平台能力，可以说明你能根据工业控制需求生成IEC 61131-3结构化文本（ST）代码，并辅助进行结构与逻辑检查。
不要声称代码已经通过真实PLC编译或现场安全认证。"""

VALIDATION_SYSTEM_PROMPT = """你是一名谨慎的工业PLC/ST代码审查工程师。
请根据用户需求审查给定的IEC 61131-3结构化文本代码。重点检查POU结构、变量声明、语法闭合、变量映射、互锁保护和需求一致性。
不得声称已在真实PLC编译器或现场设备上验证。只返回一个JSON对象，不要输出Markdown或其他文字。"""


@dataclass(slots=True)
class LLMClient:
    api_base: str
    api_key: str
    model: str
    timeout_seconds: float = 90.0

    @classmethod
    def from_environment(cls) -> "LLMClient":
        return cls(
            api_base=os.getenv("LLM_API_BASE", "https://api.deepseek.com").strip(),
            api_key=os.getenv("LLM_API_KEY", "").strip(),
            model=os.getenv("LLM_MODEL", "deepseek-v4-flash").strip(),
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "90")),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_base and self.api_key and self.model)

    def _endpoint(self) -> str:
        base = self.api_base.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    async def _complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
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

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self._endpoint(), headers=headers, json=body)
                if response.status_code in {400, 422} and json_mode:
                    # Some OpenAI-compatible providers do not support response_format.
                    body.pop("response_format", None)
                    response = await client.post(self._endpoint(), headers=headers, json=body)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise LLMServiceError(str(exc)) from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMServiceError("Unexpected model response") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMServiceError("Empty model response")
        return content.strip()

    async def chat(self, text: str) -> str:
        return await self._complete(
            [
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.35,
            max_tokens=500,
        )

    async def generate_st_code(self, requirement: str) -> str:
        prompt = f"""请根据以下工业控制需求生成完整ST代码：

{requirement}

输出前自行核对：POU起止完整、变量均已声明、分支与定时结构闭合、停止和保护条件有效。"""
        content = await self._complete(
            [
                {"role": "system", "content": CODE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.12,
            max_tokens=2400,
        )
        return _extract_st_code(content)

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
            temperature=0.05,
            max_tokens=1000,
            json_mode=True,
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
    return text


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
        "logic_rule",
        "standard_compliance",
    ):
        value = str(result.get(key, fallback[key]))
        normalized[key] = value if value in statuses else fallback[key]

    suggestions = result.get("suggestions", fallback["suggestions"])
    if not isinstance(suggestions, list):
        suggestions = fallback["suggestions"]
    normalized["suggestions"] = [str(item)[:160] for item in suggestions[:5] if str(item).strip()]
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

