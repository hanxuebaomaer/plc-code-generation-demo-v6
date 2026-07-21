from __future__ import annotations

import re
from typing import Any


PLC_TERMS = (
    "plc",
    "structured text",
    "motor",
    "pump",
    "conveyor",
    "alarm",
    "timer",
    "st代码",
    "结构化文本",
    "iec 61131",
    "function_block",
    "program",
    "功能块",
    "电机",
    "电动机",
    "正反转",
    "自锁",
    "互锁",
    "水泵",
    "泵阀",
    "阀门",
    "传送带",
    "输送带",
    "计数",
    "报警",
    "故障",
    "延时",
    "定时",
    "液位",
    "温度",
    "压力",
    "启停",
    "控制逻辑",
)


def looks_like_plc_request(text: str) -> bool:
    normalized = text.lower().replace(" ", "")
    return any(term.replace(" ", "") in normalized for term in PLC_TERMS)


def fallback_code(requirement: str) -> str:
    text = requirement.lower()
    if any(term in text for term in ("正反转", "正转", "反转")):
        return FORWARD_REVERSE
    if any(term in text for term in ("水泵", "泵阀", "液位", "泵站")):
        return PUMP_CONTROL
    if any(term in text for term in ("传送带", "输送带", "计数", "工件")):
        return CONVEYOR_COUNTER
    if any(term in text for term in ("报警", "故障", "锁存", "复位")):
        return ALARM_LATCH
    if any(term in text for term in ("延时", "定时", "延迟")):
        return DELAY_START
    return SELF_LOCK


def fallback_validation(requirement: str, code: str) -> dict[str, Any]:
    upper = code.upper()
    checks = {
        "pou_start": bool(re.search(r"\b(PROGRAM|FUNCTION_BLOCK|FUNCTION)\b", upper)),
        "pou_end": bool(re.search(r"\b(END_PROGRAM|END_FUNCTION_BLOCK|END_FUNCTION)\b", upper)),
        "end_var": "END_VAR" in upper,
        "assignment": ":=" in code,
        "semicolon": ";" in code,
        "if_balanced": upper.count("IF ") <= upper.count("END_IF"),
        "case_balanced": upper.count("CASE ") <= upper.count("END_CASE"),
        "not_other_language": not bool(re.search(r"\b(def |#include|console\.log|public static void)\b", code, re.I)),
    }

    pou_ok = checks["pou_start"] and checks["pou_end"]
    syntax_ok = all(
        checks[key]
        for key in ("end_var", "assignment", "semicolon", "if_balanced", "case_balanced", "not_other_language")
    )

    declared = set(
        name.lower()
        for name in re.findall(
            r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?:BOOL|BYTE|WORD|DWORD|SINT|USINT|INT|UINT|DINT|UDINT|REAL|LREAL|TIME|STRING|TON|TOF|TP|R_TRIG|F_TRIG|CTU|CTD)\b",
            code,
            flags=re.I,
        )
    )
    variable_ok = bool(declared)

    suggestions: list[str] = []
    if not pou_ok:
        suggestions.append("请补全POU起止结构，并确认程序类型与结束关键字匹配。")
    if not syntax_ok:
        suggestions.append("请复核变量区、赋值分号以及IF或CASE等结构是否完整闭合。")
    if not variable_ok:
        suggestions.append("请补充并核对输入、输出及内部变量声明。")
    if requirement and not any(term in code.lower() for term in ("start", "stop", "run", "alarm", "pump", "motor", "timer", "counter")):
        suggestions.append("建议结合输入需求再次核对关键控制信号与输出变量的对应关系。")
    if "(*" not in code:
        suggestions.append("可补充关键逻辑注释，便于工程复核与后续维护。")

    if not suggestions:
        suggestions = ["建议在目标PLC编程环境中完成编译，并结合实际I/O与安全条件复核。"]

    statuses = [pou_ok, syntax_ok, variable_ok]
    if all(statuses):
        conclusion = "可用于演示"
    elif any(statuses):
        conclusion = "基本可用"
    else:
        conclusion = "建议复核"

    return {
        "syntax_status": "通过" if syntax_ok else "基本通过",
        "pou_structure": "通过" if pou_ok else "未通过",
        "variable_mapping": "通过" if variable_ok else "基本通过",
        "logic_rule": "基本通过" if requirement else "未通过",
        "standard_compliance": "基本通过" if syntax_ok and pou_ok else "未通过",
        "risk_count": len([item for item in suggestions if "目标PLC" not in item]),
        "suggestions": suggestions[:5],
        "conclusion": conclusion,
        "disclaimer": "当前结果为代码结构与逻辑辅助检查，工程应用前仍需结合目标PLC平台进行编译和测试。",
    }


SELF_LOCK = """FUNCTION_BLOCK SelfLock
VAR_INPUT
    xStart     : BOOL;  (* 启动按钮 *)
    xStop      : BOOL;  (* 停止按钮，按下为TRUE *)
    xThermalOK : BOOL;  (* 热继电器正常允许信号 *)
END_VAR
VAR_OUTPUT
    xRun       : BOOL;  (* 电机运行输出 *)
END_VAR

xRun := (xStart OR xRun) AND NOT xStop AND xThermalOK;

END_FUNCTION_BLOCK"""


FORWARD_REVERSE = """FUNCTION_BLOCK MotorForwardReverse
VAR_INPUT
    xForwardStart : BOOL;  (* 正转启动 *)
    xReverseStart : BOOL;  (* 反转启动 *)
    xStop         : BOOL;  (* 停止按钮，按下为TRUE *)
    xThermalOK    : BOOL;  (* 热继电器正常允许信号 *)
END_VAR
VAR_OUTPUT
    xForwardRun   : BOOL;  (* 正转输出 *)
    xReverseRun   : BOOL;  (* 反转输出 *)
END_VAR

IF xStop OR NOT xThermalOK THEN
    xForwardRun := FALSE;
    xReverseRun := FALSE;
ELSIF xForwardStart AND NOT xReverseStart AND NOT xReverseRun THEN
    xForwardRun := TRUE;
    xReverseRun := FALSE;
ELSIF xReverseStart AND NOT xForwardStart AND NOT xForwardRun THEN
    xForwardRun := FALSE;
    xReverseRun := TRUE;
END_IF;

END_FUNCTION_BLOCK"""


PUMP_CONTROL = """FUNCTION_BLOCK PumpLevelControl
VAR_INPUT
    xStart         : BOOL;  (* 启动命令 *)
    xStop          : BOOL;  (* 停止命令 *)
    xHighLevel     : BOOL;  (* 高液位启动条件 *)
    xLowLevel      : BOOL;  (* 低液位停泵保护 *)
    xEmergencyStop : BOOL;  (* 急停信号 *)
END_VAR
VAR_OUTPUT
    xPumpRun       : BOOL;  (* 水泵运行输出 *)
    xLowLevelAlarm : BOOL;  (* 低液位报警 *)
END_VAR

xLowLevelAlarm := xLowLevel;

IF xStop OR xEmergencyStop OR xLowLevel THEN
    xPumpRun := FALSE;
ELSIF xStart AND xHighLevel THEN
    xPumpRun := TRUE;
END_IF;

END_FUNCTION_BLOCK"""


CONVEYOR_COUNTER = """FUNCTION_BLOCK ConveyorCounter
VAR_INPUT
    xEnable    : BOOL;  (* 传送带允许运行 *)
    xSensor    : BOOL;  (* 工件检测信号 *)
    xReset     : BOOL;  (* 计数复位 *)
    uiTarget   : UINT;  (* 目标数量 *)
END_VAR
VAR_OUTPUT
    xConveyorRun : BOOL;  (* 传送带运行输出 *)
    xTargetReady : BOOL;  (* 达到目标数量 *)
    uiCount      : UINT;  (* 当前计数 *)
END_VAR
VAR
    rtSensor : R_TRIG;
    ctParts  : CTU;
END_VAR

rtSensor(CLK := xSensor);
ctParts(CU := rtSensor.Q, R := xReset, PV := uiTarget);

uiCount := ctParts.CV;
xTargetReady := ctParts.Q;
xConveyorRun := xEnable AND NOT xTargetReady;

END_FUNCTION_BLOCK"""


ALARM_LATCH = """FUNCTION_BLOCK AlarmLatch
VAR_INPUT
    xFault : BOOL;  (* 故障输入 *)
    xReset : BOOL;  (* 报警复位 *)
END_VAR
VAR_OUTPUT
    xAlarm : BOOL;  (* 锁存报警输出 *)
END_VAR

xAlarm := (xAlarm OR xFault) AND NOT xReset;

END_FUNCTION_BLOCK"""


DELAY_START = """FUNCTION_BLOCK DelayStart
VAR_INPUT
    xEnable : BOOL;  (* 启动允许 *)
    xStop   : BOOL;  (* 停止命令 *)
    tDelay  : TIME;  (* 启动延时 *)
END_VAR
VAR_OUTPUT
    xRun    : BOOL;  (* 延时完成后的运行输出 *)
END_VAR
VAR
    tonStart : TON;
END_VAR

tonStart(IN := xEnable AND NOT xStop, PT := tDelay);
xRun := tonStart.Q AND NOT xStop;

END_FUNCTION_BLOCK"""
