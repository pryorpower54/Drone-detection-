#!/usr/bin/env python3
"""RF FPV drone detector: pans a directional antenna, sweeps drone bands with a
HackRF, and sends an alert with a bearing when drone-like RF shows up.

Passive receive-only. Nothing in this program transmits.

  python3 run.py                 # real hardware, settings from config.toml
  python3 run.py --sim           # simulated antenna + drone, no hardware needed
  python3 run.py --passes 10     # stop after 10 pan passes
"""

import argparse
import tomllib

from rfdetect.alerts import Alerter
from rfdetect.detector import Detector
from rfdetect.mount import ServoMount, SimulatedMount, pan_positions
from rfdetect.scanner import HackRFScanner, SimulatedScanner


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--sim", action="store_true", help="simulate the scanner and mount")
    ap.add_argument("--passes", type=int, default=0, help="stop after N pan passes (0 = run forever)")
    args = ap.parse_args()

    with open(args.config, "rb") as f:
        cfg = tomllib.load(f)
    if args.sim:
        cfg["scanner"]["type"] = cfg["mount"]["type"] = "sim"

    bands, mcfg = cfg["bands"], cfg["mount"]
    state = {"pass": 0}

    mount = ServoMount(mcfg) if mcfg["type"] == "servo" else SimulatedMount(mcfg)
    if cfg["scanner"]["type"] == "hackrf":
        scanner = HackRFScanner(cfg["scanner"], bands)
    else:
        scanner = SimulatedScanner(cfg["scanner"], bands, cfg.get("sim", {}), mount, lambda: state["pass"])
    detector = Detector(cfg["detector"], bands, cfg["scanner"]["bin_width_hz"])
    alerter = Alerter(cfg["alerts"])

    positions = pan_positions(mcfg["min_angle"], mcfg["max_angle"], mcfg["step_deg"])
    print(f"Watching {', '.join(b['name'] for b in bands)} across {positions[0]}-{positions[-1]} deg. "
          f"Learning background for {cfg['detector']['learn_cycles']} passes...", flush=True)

    try:
        while not args.passes or state["pass"] < args.passes:
            learning = detector.learning(state["pass"])
            per_angle = {}
            for angle in positions:
                mount.move(angle)
                merged = {}
                for _ in range(mcfg["sweeps_per_position"]):
                    for name, m in detector.analyze(angle, scanner.sweep(), learning).items():
                        merged[name] = Detector.merge(merged.get(name), m)
                per_angle[angle] = merged

            if not learning:
                for det in detector.end_pass(per_angle):
                    alerter.send(det)
            elif not detector.learning(state["pass"] + 1):
                print("Background learned. Now watching for drones.", flush=True)
            state["pass"] += 1
            positions.reverse()  # sweep back the other way next pass
    except KeyboardInterrupt:
        pass
    finally:
        mount.close()


if __name__ == "__main__":
    main()
