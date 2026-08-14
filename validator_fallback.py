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
    "pid",
    "st代码",
    "结构化文本",
    "iec 61131",
    "function_block",
    "program",
    "功能块",
    "电机",
    "电动机",
    "三相",
    "顺序",
    "正反转",
    "星三角",
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
    "加热",
    "风机",
    "气缸",
    "启停",
    "控制逻辑",
)


def looks_like_plc_request(text: str) -> bool:
    normalized = text.lower().replace(" ", "")
    return any(term.replace(" ", "") in normalized for term in PLC_TERMS)


def fallback_code(requirement: str) -> str:
    """Return a requirement-specific demonstration fallback, never a universal self-lock."""
    text = requirement.lower()
    if any(term in text for term in ("pid", "温度控制", "温度传感器", "精确温度", "闭环")):
        return TEMPERATURE_PID
    if "顺序" in text or all(token in text for token in ("m1", "m2", "m3")) or "三台电机" in text:
        return THREE_MOTOR_SEQUENCE
    if any(term in text for term in ("星三角", "星-三角", "星型三角")):
        return STAR_DELTA_START
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
    if any(term in text for term in ("自锁", "单台电机", "电机启停")):
        return SELF_LOCK
    return _generic_control_frame(requirement)


def fallback_validation(requirement: str, code: str) -> dict[str, Any]:
    upper = code.upper()
    checks = {
        "pou_start": bool(re.search(r"\b(PROGRAM|FUNCTION_BLOCK|FUNCTION)\b", upper)),
        "pou_end": bool(re.search(r"\b(END_PROGRAM|END_FUNCTION_BLOCK|END_FUNCTION)\b", upper)),
        "end_var": "END_VAR" in upper,
        "assignment": ":=" in code,
        "semicolon": ";" in code,
        "if_balanced": len(re.findall(r"(?m)^\s*IF\b", upper))
        == len(re.findall(r"\bEND_IF\b", upper)),
        "case_balanced": len(re.findall(r"(?m)^\s*CASE\b", upper))
        == len(re.findall(r"\bEND_CASE\b", upper)),
        "not_other_language": not bool(
            re.search(r"\b(def |#include|console\.log|public static void)\b", code, re.I)
        ),
    }

    pou_ok = checks["pou_start"] and checks["pou_end"]
    syntax_ok = all(
        checks[key]
        for key in (
            "end_var",
            "assignment",
            "semicolon",
            "if_balanced",
            "case_balanced",
            "not_other_language",
        )
    )

    declarations = re.findall(
        r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*"
        r"(BOOL|BYTE|WORD|DWORD|SINT|USINT|INT|UINT|DINT|UDINT|REAL|LREAL|TIME|STRING|TON|TOF|TP|R_TRIG|F_TRIG|CTU|CTD)\b",
        code,
        flags=re.I,
    )
    variable_ok = bool(declarations)
    naming_score = _naming_score(declarations)
    naming_status = "通过" if naming_score >= 0.7 else "基本通过" if declarations else "未通过"

    logic_ok, relevance_notes = _requirement_relevance(requirement, code)

    suggestions: list[str] = []
    if not pou_ok:
        suggestions.append("请补全POU起止结构，并确认程序类型与结束关键字匹配。")
    if not syntax_ok:
        suggestions.append("请复核变量区、赋值分号以及IF或CASE等结构是否完整闭合。")
    if not variable_ok:
        suggestions.append("请补充并核对输入、输出及内部变量声明。")
    if naming_status != "通过":
        suggestions.append("建议统一布尔量、数值量、时间量和功能块实例的命名前缀。")
    suggestions.extend(relevance_notes)
    if "(*" not in code:
        suggestions.append("可补充关键逻辑注释，便于工程复核与后续维护。")

    if not suggestions:
        suggestions = ["建议在目标PLC编程环境中完成编译，并结合实际I/O与安全条件复核。"]

    standard_ok = syntax_ok and pou_ok
    if all((pou_ok, syntax_ok, variable_ok, logic_ok)):
        conclusion = "可用于演示"
    elif any((pou_ok, syntax_ok, variable_ok, logic_ok)):
        conclusion = "基本可用"
    else:
        conclusion = "建议复核"

    return {
        "syntax_status": "通过" if syntax_ok else "未通过",
        "pou_structure": "通过" if pou_ok else "未通过",
        "variable_mapping": "通过" if variable_ok else "未通过",
        "naming_convention": naming_status,
        "logic_rule": "通过" if logic_ok else "未通过",
        "standard_compliance": "通过" if standard_ok else "基本通过" if pou_ok else "未通过",
        "risk_count": len([item for item in suggestions if "目标PLC" not in item]),
        "suggestions": suggestions[:6],
        "conclusion": conclusion,
        "disclaimer": "当前结果为代码结构与逻辑辅助检查，工程应用前仍需结合目标PLC平台进行编译和测试。",
    }


def _naming_score(declarations: list[tuple[str, str]]) -> float:
    if not declarations:
        return 0.0
    matches = 0
    for name, data_type in declarations:
        lower = name.lower()
        dtype = data_type.upper()
        if dtype == "BOOL" and lower.startswith(("x", "b", "q")):
            matches += 1
        elif dtype in {"REAL", "LREAL"} and lower.startswith(("r", "lr")):
            matches += 1
        elif dtype in {"TIME", "TON", "TOF", "TP"} and lower.startswith(("t", "ton", "tof", "tp")):
            matches += 1
        elif dtype in {"UINT", "USINT", "UDINT"} and lower.startswith(("ui", "usi", "udi", "u")):
            matches += 1
        elif dtype in {"INT", "SINT", "DINT"} and lower.startswith(("i", "si", "di")):
            matches += 1
        elif dtype in {"R_TRIG", "F_TRIG", "CTU", "CTD"} and lower.startswith(("rt", "ft", "ct")):
            matches += 1
    return matches / len(declarations)


def _requirement_relevance(requirement: str, code: str) -> tuple[bool, list[str]]:
    if not requirement.strip():
        return False, ["未提供需求描述，无法完成需求一致性检查。"]
    req = requirement.lower()
    low = code.lower()
    notes: list[str] = []

    if any(term in req for term in ("pid", "温度", "闭环")):
        needed = {
            "设定值": ("setpoint", "设定"),
            "过程反馈": ("process", "feedback", "测量", "温度反馈"),
            "PID参数": ("kp", "ki", "kd"),
            "控制输出": ("output", "heater", "加热"),
        }
        for label, terms in needed.items():
            if not any(term in low for term in terms):
                notes.append(f"代码未充分体现PID温控的{label}。")

    sequential = "顺序" in req or all(token in req for token in ("m1", "m2", "m3"))
    if sequential:
        for name in ("m1", "m2", "m3"):
            if name not in low:
                notes.append(f"顺序启动需求中的{name.upper()}未在代码中体现。")
        if not any(term in low for term in ("ton", "timer", "step", "state")):
            notes.append("顺序启动逻辑缺少定时器或步序状态。")

    checks = [
        (("水泵", "泵阀"), ("pump", "泵"), "水泵/泵阀控制"),
        (("传送带", "输送带", "计数"), ("counter", "count", "conveyor"), "传送带计数"),
        (("正反转",), ("forward", "reverse"), "正反转互锁"),
        (("报警",), ("alarm",), "报警输出"),
    ]
    for req_terms, code_terms, label in checks:
        if any(term in req for term in req_terms) and not any(term in low for term in code_terms):
            notes.append(f"代码未体现需求中的{label}。")

    if not notes and not any(
        term in low
        for term in ("start", "stop", "run", "alarm", "pump", "motor", "timer", "counter", "pid", "state")
    ):
        notes.append("建议复核需求中的关键输入、输出与代码变量是否逐项对应。")
    return not notes, notes


def _generic_control_frame(requirement: str) -> str:
    note = re.sub(r"[()*]", "", requirement).replace("\n", " ").strip()[:160]
    return f"""FUNCTION_BLOCK RequirementControl
VAR_INPUT
    xEnable : BOOL;  (* 控制允许 *)
    xStop   : BOOL;  (* 停止命令 *)
    xFault  : BOOL;  (* 综合故障 *)
    xReset  : BOOL;  (* 复位命令 *)
END_VAR
VAR_OUTPUT
    xRun    : BOOL;  (* 运行输出 *)
    xReady  : BOOL;  (* 就绪状态 *)
END_VAR
VAR
    xCommandLatched : BOOL;
END_VAR

(* 原始需求摘要：{note} *)
IF xReset THEN
    xCommandLatched := FALSE;
ELSIF xEnable AND NOT xStop AND NOT xFault THEN
    xCommandLatched := TRUE;
ELSIF xStop OR xFault THEN
    xCommandLatched := FALSE;
END_IF;

xReady := xEnable AND NOT xFault;
xRun := xCommandLatched AND xReady AND NOT xStop;

END_FUNCTION_BLOCK"""


TEMPERATURE_PID = """FUNCTION_BLOCK TemperaturePIDControl
VAR_INPUT
    xEnable       : BOOL;  (* PID控制允许 *)
    xReset        : BOOL;  (* 积分与历史误差复位 *)
    rSetpoint     : REAL;  (* 温度设定值 *)
    rProcessValue : REAL;  (* 温度传感器反馈值 *)
    rKp           : REAL;  (* 比例系数 *)
    rKi           : REAL;  (* 积分系数 *)
    rKd           : REAL;  (* 微分系数 *)
    rCycleSec     : REAL;  (* 调用周期，单位s *)
    rOutputMin    : REAL;  (* 输出下限，通常为0.0 *)
    rOutputMax    : REAL;  (* 输出上限，通常为100.0 *)
END_VAR
VAR_OUTPUT
    rHeaterOutput : REAL;  (* 加热输出百分比 *)
    rError        : REAL;  (* 当前温差 *)
    xAtSetpoint   : BOOL;  (* 温度到达设定范围 *)
    xSaturated    : BOOL;  (* 输出达到限幅 *)
END_VAR
VAR
    rIntegral     : REAL;
    rDerivative   : REAL;
    rPreviousErr  : REAL;
    rRawOutput    : REAL;
END_VAR

IF xReset OR NOT xEnable THEN
    rIntegral := 0.0;
    rDerivative := 0.0;
    rPreviousErr := 0.0;
    rHeaterOutput := 0.0;
    xSaturated := FALSE;
ELSE
    rError := rSetpoint - rProcessValue;

    IF rCycleSec > 0.0 THEN
        rIntegral := rIntegral + (rError * rCycleSec);
        rDerivative := (rError - rPreviousErr) / rCycleSec;
    ELSE
        rDerivative := 0.0;
    END_IF;

    rRawOutput := (rKp * rError) + (rKi * rIntegral) + (rKd * rDerivative);

    IF rRawOutput > rOutputMax THEN
        rHeaterOutput := rOutputMax;
        xSaturated := TRUE;
        IF rKi <> 0.0 THEN
            rIntegral := (rOutputMax - (rKp * rError) - (rKd * rDerivative)) / rKi;
        END_IF;
    ELSIF rRawOutput < rOutputMin THEN
        rHeaterOutput := rOutputMin;
        xSaturated := TRUE;
        IF rKi <> 0.0 THEN
            rIntegral := (rOutputMin - (rKp * rError) - (rKd * rDerivative)) / rKi;
        END_IF;
    ELSE
        rHeaterOutput := rRawOutput;
        xSaturated := FALSE;
    END_IF;

    rPreviousErr := rError;
END_IF;

xAtSetpoint := xEnable AND (ABS(rSetpoint - rProcessValue) <= 0.5);

END_FUNCTION_BLOCK"""


THREE_MOTOR_SEQUENCE = """FUNCTION_BLOCK ThreeMotorSequence
VAR_INPUT
    xStart    : BOOL;  (* 顺序启动命令 *)
    xStop     : BOOL;  (* 三台电机统一停止 *)
    xFault    : BOOL;  (* 任一设备故障，TRUE时禁止启动并停机 *)
    xReset    : BOOL;  (* 顺序状态复位 *)
    tInterval : TIME;  (* 相邻电机启动间隔，例如T#5s *)
END_VAR
VAR_OUTPUT
    xM1Run       : BOOL;  (* 电机M1运行命令 *)
    xM2Run       : BOOL;  (* 电机M2运行命令 *)
    xM3Run       : BOOL;  (* 电机M3运行命令 *)
    xSequenceRun : BOOL;  (* 顺序启动过程有效 *)
    xSequenceDone: BOOL;  (* 三台电机均已投入 *)
END_VAR
VAR
    xStartLatched : BOOL;
    tonM2Delay    : TON;
    tonM3Delay    : TON;
END_VAR

(* 仅在无故障、未停止时接受启动命令 *)
IF xReset OR xStop OR xFault THEN
    xStartLatched := FALSE;
ELSIF xStart THEN
    xStartLatched := TRUE;
END_IF;

(* M1立即启动，M2和M3各延时一个设定间隔 *)
tonM2Delay(IN := xStartLatched, PT := tInterval);
tonM3Delay(IN := xStartLatched AND tonM2Delay.Q, PT := tInterval);

xM1Run := xStartLatched AND NOT xStop AND NOT xFault;
xM2Run := xM1Run AND tonM2Delay.Q;
xM3Run := xM2Run AND tonM3Delay.Q;

xSequenceRun := xStartLatched;
xSequenceDone := xM1Run AND xM2Run AND xM3Run;

END_FUNCTION_BLOCK"""


STAR_DELTA_START = """FUNCTION_BLOCK StarDeltaStarter
VAR_INPUT
    xStart      : BOOL;  (* 启动按钮 *)
    xStop       : BOOL;  (* 停止按钮 *)
    xOverloadOK : BOOL;  (* 过载保护正常 *)
    tStarTime   : TIME;  (* 星形运行时间 *)
    tTransfer   : TIME;  (* 星三角切换死区 *)
END_VAR
VAR_OUTPUT
    xMainContactor  : BOOL;
    xStarContactor  : BOOL;
    xDeltaContactor : BOOL;
END_VAR
VAR
    xRunLatched : BOOL;
    tonStar     : TON;
    tonTransfer : TON;
END_VAR

IF xStop OR NOT xOverloadOK THEN
    xRunLatched := FALSE;
ELSIF xStart THEN
    xRunLatched := TRUE;
END_IF;

tonStar(IN := xRunLatched, PT := tStarTime);
tonTransfer(IN := xRunLatched AND tonStar.Q, PT := tTransfer);

xMainContactor := xRunLatched;
xStarContactor := xRunLatched AND NOT tonStar.Q AND NOT xDeltaContactor;
xDeltaContactor := xRunLatched AND tonTransfer.Q AND NOT xStarContactor;

END_FUNCTION_BLOCK"""


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
