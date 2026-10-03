"""Pan mounts. A mount moves the antenna and reports its current angle."""

import time


def pan_positions(min_angle, max_angle, step):
    """Angles for one pan pass. The caller reverses the list each pass so the
    antenna sweeps back and forth and the coax never winds up."""
    out = list(range(int(min_angle), int(max_angle) + 1, int(step)))
    if out[-1] != max_angle:
        out.append(int(max_angle))
    return out


class ServoMount:
    """Hobby servo driven from a Raspberry Pi GPIO pin via gpiozero.

    Uses the pigpio pin factory when available, which gives jitter-free PWM.
    Run `sudo pigpiod` first for that.
    """

    def __init__(self, cfg):
        from gpiozero import AngularServo
        try:
            from gpiozero.pins.pigpio import PiGPIOFactory
            factory = PiGPIOFactory()
        except Exception:
            factory = None
        self.cfg = cfg
        self.servo = AngularServo(
            cfg["gpio_pin"],
            min_angle=cfg["min_angle"], max_angle=cfg["max_angle"],
            min_pulse_width=cfg["min_pulse_ms"] / 1000,
            max_pulse_width=cfg["max_pulse_ms"] / 1000,
            pin_factory=factory)
        self.angle = cfg["min_angle"]

    def move(self, angle):
        self.servo.angle = angle
        self.angle = angle
        time.sleep(self.cfg["settle_s"])

    def close(self):
        self.servo.detach()


class SimulatedMount:
    def __init__(self, cfg):
        self.angle = cfg["min_angle"]

    def move(self, angle):
        self.angle = angle

    def close(self):
        pass
