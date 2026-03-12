from battery import BatteryMonitor
import time
import random
import argparse


def _simulate_once_with_seed(monitor: BatteryMonitor, seed: int):
    random.seed(seed)
    return monitor._simulate_data()


def test_temperature_default_in_status():
    m = BatteryMonitor(source="simulator")
    status = m.get_status()
    assert "temperature" in status, "temperature missing from get_status()"
    assert isinstance(status["temperature"], (int, float)), f"temperature should be numeric: {status['temperature']}"
    assert -50.0 <= float(status["temperature"]) <= 100.0, f"temperature out of plausible range: {status['temperature']}"


def test_temperature_changes_over_time():
    # With update_interval > 0, temperature should drift due to ambient model / self-heating.
    random.seed(2026)
    m = BatteryMonitor(source="simulator", update_interval=1.0)
    t0 = m.get_status()["temperature"]
    for _ in range(30):
        m._simulate_data()
    t1 = m.get_status()["temperature"]
    assert abs(t1 - t0) > 0.05, f"temperature should change over time: t0={t0}, t1={t1}"


def test_low_temperature_soc_drops_faster():
    # Same seed => same base soc_drop; low temp should scale it up
    warm = BatteryMonitor(source="simulator", update_interval=0)
    cold = BatteryMonitor(source="simulator", update_interval=0)
    warm._soc = 50.0
    cold._soc = 50.0
    warm._temperature = 25.0
    cold._temperature = 5.0

    _simulate_once_with_seed(warm, seed=1234)
    _simulate_once_with_seed(cold, seed=1234)

    assert cold._soc < warm._soc, f"cold SOC should drop faster: cold={cold._soc}, warm={warm._soc}"
    # Expect noticeable difference from 1.25x scaling
    assert (warm._soc - cold._soc) > 0.05, f"SOC difference too small: warm={warm._soc}, cold={cold._soc}"


def test_high_temperature_voltage_is_lower():
    # High temp does not change soc_drop, only voltage offset, so SOC should match for same seed
    warm = BatteryMonitor(source="simulator", update_interval=0)
    hot = BatteryMonitor(source="simulator", update_interval=0)
    warm._soc = 50.0
    hot._soc = 50.0
    warm._temperature = 25.0
    hot._temperature = 40.0

    soc_w, v_w, _ = _simulate_once_with_seed(warm, seed=5678)
    soc_h, v_h, _ = _simulate_once_with_seed(hot, seed=5678)

    assert abs(soc_w - soc_h) < 1e-9, f"SOC should match at high temp (no scaling): warm={soc_w}, hot={soc_h}"
    assert v_h < v_w, f"hot voltage should be lower: hot={v_h}, warm={v_w}"

def main():
    # Quick correctness checks (no external test framework required)
    test_temperature_default_in_status()
    test_temperature_changes_over_time()
    test_low_temperature_soc_drops_faster()
    test_high_temperature_voltage_is_lower()
    print("Temperature tests passed.")

    # Re-randomize for the live demo loop so each run differs
    random.seed()

    monitor = BatteryMonitor(source="simulator", update_interval=1)
    monitor.start_monitoring()
    try:
        for i in range(10):
            status = monitor.get_status()
            print(
                f"Iteration {i+1}: SOC={status['soc']:.2f}%, Voltage={status['voltage']:.2f}V, "
                f"SOH={status['soh']:.2f}%, Temp={status['temperature']:.1f}C"
            )
            #验证数据范围
            assert  status['soc'] >= 0, f"soc too low: {status['soc']}"
            assert  status['voltage'] >= 20,  f"voltage too low: {status['voltage']}"
            assert 0 <= status['soh'] <= 100, f"soh out of range: {status['soh']}"
            print("data is valid")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Test stopped.")
if __name__ == "__main__":
    main()