"""Small, exact-match offline references. Never route arbitrary input by one keyword."""
from scenarios import SCENARIOS

CAB_ST = """(* 离线参考：操作端判断；不连接真实车辆。 *)
FUNCTION_BLOCK CabSelection
VAR_INPUT
    xKeyA : BOOL;
    xKeyB : BOOL;
    xReset : BOOL;
END_VAR
VAR_OUTPUT
    xActiveA : BOOL := FALSE;
    xActiveB : BOOL := FALSE;
    xConflict : BOOL := FALSE;
    xTractionBlocked : BOOL := TRUE;
END_VAR
VAR
    (* 0=待选端，1=A占用，2=B占用，3=等待两端退出 *)
    iState : INT := 0;
END_VAR

IF xReset AND NOT xKeyA AND NOT xKeyB THEN
    iState := 0;
END_IF;
CASE iState OF
    0:
        IF xKeyA AND xKeyB THEN
            iState := 3;
        ELSIF xKeyA THEN
            iState := 1;
        ELSIF xKeyB THEN
            iState := 2;
        END_IF;
    1:
        IF NOT xKeyA THEN
            iState := 3;
        END_IF;
    2:
        IF NOT xKeyB THEN
            iState := 3;
        END_IF;
    3:
        IF NOT xKeyA AND NOT xKeyB THEN
            iState := 0;
        END_IF;
ELSE
    iState := 3;
END_CASE;
xActiveA := (iState = 1) AND xKeyA;
xActiveB := (iState = 2) AND xKeyB;
xConflict := xKeyA AND xKeyB;
xTractionBlocked := xConflict OR NOT (xActiveA OR xActiveB);
END_FUNCTION_BLOCK
"""

CAB_CPP = """// 离线参考：操作端判断；每周期调用 update，不连接真实车辆。
class CabSelection {
public:
    struct Inputs {
        bool keyA{false};
        bool keyB{false};
        bool reset{false};
    };
    struct Outputs {
        bool activeA{false};
        bool activeB{false};
        bool conflict{false};
        bool tractionBlocked{true};
    };

    Outputs update(const Inputs& in) {
        if (in.reset && !in.keyA && !in.keyB) state_ = State::Idle;
        switch (state_) {
        case State::Idle:
            if (in.keyA && in.keyB) state_ = State::WaitRelease;
            else if (in.keyA) state_ = State::A;
            else if (in.keyB) state_ = State::B;
            break;
        case State::A:
            if (!in.keyA) state_ = State::WaitRelease;
            break;
        case State::B:
            if (!in.keyB) state_ = State::WaitRelease;
            break;
        case State::WaitRelease:
            if (!in.keyA && !in.keyB) state_ = State::Idle;
            break;
        }
        Outputs out;
        out.activeA = state_ == State::A && in.keyA;
        out.activeB = state_ == State::B && in.keyB;
        out.conflict = in.keyA && in.keyB;
        out.tractionBlocked = out.conflict || !(out.activeA || out.activeB);
        return out;
    }
private:
    enum class State { Idle, A, B, WaitRelease };
    State state_{State::Idle};
};
"""

MILEAGE_ST = """(* 离线参考：外部持久化层负责掉电保持。每周期调用一次。 *)
FUNCTION_BLOCK MileageAccumulator
VAR_INPUT
    xEnabled : BOOL;
    rSpeedKmh : LREAL;
    rDeltaSeconds : LREAL;
    xResetTrip : BOOL;
END_VAR
VAR_OUTPUT
    rTotalKm : LREAL := 0.0;
    rTripKm : LREAL := 0.0;
    xInputInvalid : BOOL := FALSE;
END_VAR
VAR
    rIncrementKm : LREAL := 0.0;
END_VAR
(* 正向有效范围检查也拒绝 NaN 和无穷值。 *)
xInputInvalid := NOT ((rDeltaSeconds > 0.0) AND (rDeltaSeconds <= 1.0)
    AND (rSpeedKmh >= -200.0) AND (rSpeedKmh <= 200.0));
rIncrementKm := 0.0;
IF xEnabled AND NOT xInputInvalid THEN
    rIncrementKm := ABS(rSpeedKmh) * rDeltaSeconds / 3600.0;
    rTotalKm := rTotalKm + rIncrementKm;
END_IF;
IF xResetTrip THEN
    rTripKm := 0.0;
ELSE
    rTripKm := rTripKm + rIncrementKm;
END_IF;
END_FUNCTION_BLOCK
"""

MILEAGE_CPP = """#include <cmath>

// 离线参考：外部持久化层负责掉电保持；周期单位为秒。
class MileageAccumulator {
public:
    struct Inputs {
        bool enabled{false};
        double speedKmh{0.0};
        double deltaSeconds{0.0};
        bool resetTrip{false};
    };
    struct Outputs {
        double totalKm{0.0};
        double tripKm{0.0};
        bool inputInvalid{false};
    };
    Outputs update(const Inputs& in) {
        const bool valid = std::isfinite(in.speedKmh)
            && std::isfinite(in.deltaSeconds)
            && in.deltaSeconds > 0.0 && in.deltaSeconds <= 1.0
            && std::abs(in.speedKmh) <= 200.0;
        out_.inputInvalid = !valid;
        const double increment = (in.enabled && valid)
            ? std::abs(in.speedKmh) * in.deltaSeconds / 3600.0 : 0.0;
        out_.totalKm += increment;
        if (in.resetTrip) out_.tripKm = 0.0;
        else out_.tripKm += increment;
        return out_;
    }
private:
    Outputs out_{};
};
"""


def fallback_code(requirement, language):
    for scenario in SCENARIOS:
        if requirement.strip() == scenario["requirement"].strip():
            return {
                ("cab", "st"): CAB_ST, ("cab", "cpp"): CAB_CPP,
                ("mileage", "st"): MILEAGE_ST, ("mileage", "cpp"): MILEAGE_CPP,
            }.get((scenario["id"], language))
    return None
