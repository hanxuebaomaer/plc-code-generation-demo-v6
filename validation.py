"""Conservative structural checks. These checks are NOT a PLC/C++ compiler."""
import re

CHECKS = [
    ("syntax", "语法与成对结构"),
    ("structure", "程序与接口结构"),
    ("variables", "变量与类型声明"),
    ("naming", "命名与可读性"),
    ("requirements", "需求与逻辑对应"),
    ("boundaries", "边界与保护条件"),
]


def strip_comments(code, language):
    if language == "st":
        code = re.sub(r"\(\*.*?\*\)", "", code, flags=re.S)
    else:
        code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return re.sub(r"//[^\n]*", "", code)


def _cpp_balanced(code):
    code = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', code)
    stack = []
    for char in code:
        if char in "({[":
            stack.append(char)
        elif char in ")}]":
            if not stack or stack.pop() != dict(zip(")}]", "({["))[char]:
                return False
    return not stack


def structural_issues(code, language):
    clean = strip_comments(code, language)
    if language == "st":
        clean = re.sub(r"'(?:\$.|''|[^'])*'", "''", clean)
    issues = []
    if "```" in clean:
        issues.append("含 Markdown 围栏，请只保留代码")
    if language == "st":
        # A stack catches crossed/nested blocks, not just equal counts.
        words = re.findall(r"\b(?:FUNCTION_BLOCK|END_FUNCTION_BLOCK|PROGRAM|END_PROGRAM|FUNCTION|END_FUNCTION|VAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP|_EXTERNAL|_GLOBAL)?|END_VAR|IF|END_IF|CASE|END_CASE|FOR|END_FOR|WHILE|END_WHILE|REPEAT|END_REPEAT)\b", clean, re.I)
        stack = []
        for word in words:
            word = word.upper()
            if word.startswith("END_"):
                expected = word[4:]
                if not stack or stack.pop() != expected:
                    issues.append("块结束标记缺失、交叉或顺序错误")
                    break
            else:
                stack.append("VAR" if word.startswith("VAR") else word)
        if stack:
            issues.append("存在尚未闭合的声明或控制结构")
        if not re.search(r"\b(FUNCTION_BLOCK|PROGRAM|FUNCTION)\s+\w+", clean, re.I):
            issues.append("缺少完整 POU 定义")
        if not re.search(r"\bVAR(?:_INPUT|_OUTPUT|_IN_OUT)?\b", clean, re.I):
            issues.append("缺少变量声明区")
        if not re.search(r"\w+\s*:\s*\w+", clean):
            issues.append("缺少带类型的变量声明")
        if not re.search(r":=|\b(?:TON|TOF|R_TRIG|CTU)\s*\(", clean, re.I):
            issues.append("未发现主体赋值或功能块调用")
        if re.search(r"\b(?:def\s+\w+\(|class\s+\w+|#include)\b", clean):
            issues.append("输出包含非 ST 结构")
    else:
        if not _cpp_balanced(clean):
            issues.append("括号或代码块未配对")
        if not re.search(r"\b(?:class|struct)\s+\w+|\b(?:void|bool|double|int)\s+\w+\s*\(", clean):
            issues.append("缺少 C++ 类、结构体或函数接口")
        if re.search(r"\bFUNCTION_BLOCK\b|\bEND_VAR\b|\bdef\s+\w+\s*\(", clean, re.I):
            issues.append("输出包含非 C++ 结构")
        if "{" not in clean or ";" not in clean:
            issues.append("C++ 主体结构不完整")
    return list(dict.fromkeys(issues))


def local_report(code, language, partial=False):
    issues = structural_issues(code, language)
    clean = strip_comments(code, language)
    if language == "st":
        containers = re.findall(r"\b(?:FUNCTION_BLOCK|PROGRAM|FUNCTION)\s+(\w+)", clean, re.I)
        declarations = len(re.findall(r"\b\w+\s*:\s*\w+", clean))
    else:
        containers = re.findall(r"\b(?:class|struct)\s+(\w+)", clean)
        declarations = len(re.findall(r"\b(?:bool|int|double|float|unsigned|auto)\s+\w+", clean))
    state = "pending" if partial else ("fail" if issues else "pass")
    checks = []
    for key, label in CHECKS:
        status, detail = "pending", "等待完整代码与需求审查"
        if key == "syntax":
            status = state
            detail = f"已接收 {len(code.splitlines())} 行，正在核对成对结构；未闭合片段暂不判错" if partial else (
                "；".join(issues) if issues else "基础结构与成对标记检查完成；不代表编译通过")
        elif key == "structure":
            status = "pending" if partial else ("fail" if any("定义" in i or "接口" in i or "完整" in i for i in issues) else "pass")
            detail = ("已识别：" + "、".join(containers[:4]) + "；等待完整程序" if containers else "正在等待程序或接口定义") if partial else "检查程序容器、接口和主体的存在性；接口含义待审查"
        elif key == "variables":
            status = "pending" if partial else "warn"
            detail = f"已识别约 {declarations} 处带类型声明，正在收集使用关系" if partial else "基础声明已检查；类型兼容性和使用关系待进一步审查"
        elif not partial:
            status = "warn"
            detail = "需要结合完整需求进一步审查，规则检查不作肯定结论"
        checks.append({"id": key, "label": label, "status": status, "detail": detail, "method": "增量检查" if partial else "规则检查"})
    return summarize(checks, "partial" if partial else "rules", issues)


def summarize(checks, source, suggestions=None, coverage=None):
    failures = sum(c["status"] == "fail" for c in checks)
    warnings = sum(c["status"] == "warn" for c in checks)
    pending = any(c["status"] == "pending" for c in checks)
    return {
        "checks": checks, "source": source,
        "risk_count": failures + warnings,
        "conclusion": "检查进行中" if pending else ("存在需修改项" if failures else "存在待复核项" if warnings else "6 项初步通过 · 辅助审查完成"),
        "suggestions": list(dict.fromkeys(suggestions or [])), "coverage": coverage or [],
        "scope_note": "本结果为结构规则与模型辅助审查，不是编译、仿真、实车测试或安全认证。",
    }


def merge_review(local, remote):
    """Model output cannot turn a detected structural failure into a pass."""
    entries = remote.get("checks", []) if isinstance(remote, dict) else []
    entries = {str(x.get("id")): x for x in entries if isinstance(x, dict)} if isinstance(entries, list) else {}
    checks = []
    for item in local["checks"]:
        check = dict(item)
        model = entries.get(item["id"], {})
        if model.get("status") in {"pass", "warn", "fail"} and isinstance(model.get("detail"), str):
            if item["status"] != "fail":
                check.update(status=model["status"], detail=model["detail"][:1000], method="规则 + 模型审查")
        check["repairable"] = check["status"] in {"warn", "fail"} and (item["status"] == "fail" or model.get("repairable") is True)
        checks.append(check)
    suggestions = remote.get("suggestions", [])
    suggestions = [s[:1000] for s in suggestions if isinstance(s, str)] if isinstance(suggestions, list) else []
    coverage = remote.get("coverage", [])
    coverage = [{"requirement": str(x.get("requirement", ""))[:500], "evidence": str(x.get("evidence", ""))[:700], "status": x.get("status") if x.get("status") in {"pass", "warn", "fail"} else "warn"} for x in coverage if isinstance(x, dict)] if isinstance(coverage, list) else []
    requirement_check = next(c for c in checks if c["id"] == "requirements")
    if any(x["status"] == "fail" for x in coverage):
        requirement_check.update(status="fail", detail="需求逐项比对中存在未满足项，请查看下方对应依据。")
    elif any(x["status"] == "warn" for x in coverage) and requirement_check["status"] == "pass":
        requirement_check.update(status="warn", detail="需求逐项比对中存在待确认项，请查看下方对应依据。")
    elif not coverage and requirement_check["status"] == "pass":
        requirement_check.update(status="warn", detail="本次审查未返回需求对应证据，需要重新验证。")
    if not entries:
        suggestions.insert(0, "详细审查暂未完成，请稍后重新验证。")
    return summarize(checks, "review" if entries else "rules", suggestions, coverage)


def repair_needed(report):
    return report.get("source") == "review" and any(c["status"] == "fail" or c.get("repairable") and c["status"] == "warn" for c in report["checks"])


def improved_report(before, after):
    """A repair is accepted only after review, with fewer issues and no new check regression."""
    if after.get("source") != "review":
        return False
    rank = {"pass": 0, "warn": 1, "fail": 2, "pending": 3}
    previous = {c["id"]: c["status"] for c in before["checks"]}
    if any(rank[c["status"]] > rank[previous.get(c["id"], "pending")] for c in after["checks"]):
        return False
    def score(report):
        return (sum(c["status"] == "fail" for c in report["checks"]), sum(c["status"] == "warn" for c in report["checks"]))
    return score(after) < score(before)
