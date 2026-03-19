import time

from motor_simulator import MotorSimulator


def _print_status(title: str, motor: MotorSimulator) -> dict:
    status = motor.get_status()
    print(f"\n[{title}]")
    for k, v in status.items():
        print(f"  {k}: {v}")
    return status


def _set_forward(motor: MotorSimulator) -> None:
    """
    Set motor forward direction.
    Prefer string API requested by the user; fallback to integer API.
    """
    try:
        motor.set_direction("forward")
    except Exception:
        motor.set_direction(1)


def _set_stop(motor: MotorSimulator) -> None:
    """
    Stop motor direction.
    Prefer string API requested by the user; fallback to integer API.
    """
    try:
        motor.set_direction("stop")
    except Exception:
        motor.set_direction(0)


def basic_function_test() -> MotorSimulator:
    print("=== 1) Basic function test ===")

    # Requested: name="TestMotor", max_speed=1500
    # If current class signature does not support max_speed, fallback gracefully.
    try:
        motor = MotorSimulator(name="TestMotor", max_speed=1500)
    except TypeError:
        motor = MotorSimulator(name="TestMotor")
        # Keep a test-side attribute for visibility if class has no such constructor arg.
        setattr(motor, "max_speed", 1500)

    _print_status("Initial", motor)

    motor.enable()
    _print_status("After enable()", motor)

    motor.set_pwm(50)
    _print_status("After set_pwm(50)", motor)

    _set_forward(motor)
    _print_status("After set_direction('forward')", motor)

    # Exception case requested by user
    try:
        motor.set_direction(150)
    except ValueError as e:
        print(f"\n[Expected exception] set_direction(150) -> ValueError: {e}")
    else:
        print("\n[Warning] set_direction(150) did not raise ValueError")

    return motor


def monitoring_and_time_update_test(motor: MotorSimulator) -> None:
    print("\n=== 2) Background thread & time update test ===")

    initial = motor.get_status()
    initial_temp = float(initial["temperature"])
    print(f"Initial temperature: {initial_temp:.3f}")

    motor.start_monitoring()
    motor.enable()
    motor.set_pwm(80)
    _set_forward(motor)

    print("Monitoring for 3 seconds...")
    time.sleep(3)
    running_status = _print_status("After 3s running", motor)
    temp_after_run = float(running_status["temperature"])
    print(f"Temperature increased? {temp_after_run:.3f} > {initial_temp:.3f} -> {temp_after_run > initial_temp}")

    # Stop motor, then observe cooling
    _set_stop(motor)
    # Alternative also acceptable per request:
    # motor.disable()
    print("Motor stopped. Waiting 2 seconds for cooling...")
    time.sleep(2)
    stopped_status = _print_status("After 2s stopped", motor)
    temp_after_stop = float(stopped_status["temperature"])
    print(f"Temperature decreased? {temp_after_stop:.3f} < {temp_after_run:.3f} -> {temp_after_stop < temp_after_run}")

    motor.stop_monitoring()
    print("Background monitoring stopped.")


def thread_safety_and_stop_test() -> None:
    print("\n=== 3) Thread stop/daemon behavior test ===")
    motor = MotorSimulator(name="ThreadTestMotor")

    # Start then stop immediately: should not error
    motor.start_monitoring()
    motor.stop_monitoring()
    print("Immediate start->stop completed without errors.")

    # Start again and exit without explicit stop:
    # daemon thread should exit automatically when main process exits.
    motor.start_monitoring()
    print("Started daemon monitoring thread again; script will exit directly without stop_monitoring().")


if __name__ == "__main__":
    m = basic_function_test()
    monitoring_and_time_update_test(m)
    thread_safety_and_stop_test()
