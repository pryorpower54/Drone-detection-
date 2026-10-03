"""Spectrum scanners. Each returns a dict {bin_center_hz: power_db} for one sweep."""

import math
import random
import shutil
import subprocess


def parse_hackrf_sweep(lines):
    """Parse hackrf_sweep CSV lines into {bin_center_hz: power_db}.

    Each line looks like:
      date, time, hz_low, hz_high, hz_bin_width, num_samples, dB, dB, ...
    """
    spectrum = {}
    for line in lines:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 7:
            continue
        try:
            hz_low = float(parts[2])
            bin_width = float(parts[4])
            powers = [float(p) for p in parts[6:]]
        except ValueError:
            continue
        for i, db in enumerate(powers):
            spectrum[hz_low + (i + 0.5) * bin_width] = db
    return spectrum


class HackRFScanner:
    """Runs one hackrf_sweep pass over every configured band."""

    def __init__(self, cfg, bands):
        if not shutil.which("hackrf_sweep"):
            raise RuntimeError("hackrf_sweep not found. Install with: sudo apt install hackrf")
        self.cmd = ["hackrf_sweep", "-1",
                    "-w", str(cfg["bin_width_hz"]),
                    "-l", str(cfg["lna_gain"]),
                    "-g", str(cfg["vga_gain"]),
                    "-a", "1" if cfg.get("amp") else "0"]
        for b in bands:
            self.cmd += ["-f", f"{int(b['start_mhz'])}:{int(math.ceil(b['stop_mhz']))}"]

    def sweep(self):
        out = subprocess.run(self.cmd, capture_output=True, text=True, timeout=30)
        if out.returncode != 0 and not out.stdout:
            raise RuntimeError(f"hackrf_sweep failed: {out.stderr.strip()[-300:]}")
        return parse_hackrf_sweep(out.stdout.splitlines())


class SimulatedScanner:
    """Fake spectrum for testing without hardware.

    Background: noise plus a Wi-Fi access point (same in every direction, so
    the detector should learn it away). After a few pan cycles a drone shows
    up at a fixed bearing with 5.8 GHz analog video and a 900 MHz hopping
    control link. Signal strength follows a simple antenna beam pattern.
    """

    BEAMWIDTH_DEG = 40

    def __init__(self, cfg, bands, sim_cfg, mount, cycle_counter):
        self.bin_hz = cfg["bin_width_hz"]
        self.bands = bands
        self.bearing = sim_cfg.get("drone_bearing_deg", 120)
        self.appear_after = sim_cfg.get("drone_appears_after_cycles", 3)
        self.mount = mount
        self.cycle = cycle_counter  # callable returning the current pan cycle
        self.rng = random.Random(1)

    def _gain(self):
        off = abs(self.mount.angle - self.bearing)
        return -12.0 * (off / (self.BEAMWIDTH_DEG / 2)) ** 2  # dB, ~-3 dB at edge of main lobe

    def sweep(self):
        drone = self.cycle() >= self.appear_after
        gain = self._gain()
        hops = {self.rng.uniform(862, 928) for _ in range(6)} if drone else set()
        spectrum = {}
        for b in self.bands:
            f = b["start_mhz"] * 1e6 + self.bin_hz / 2
            while f < b["stop_mhz"] * 1e6:
                mhz = f / 1e6
                db = -90 + self.rng.gauss(0, 1.5)
                if 2427 <= mhz <= 2447:  # Wi-Fi channel 6
                    db = max(db, -70 + self.rng.gauss(0, 2))
                if drone and abs(mhz - 5800) <= 4:  # analog video, Raceband R7
                    db = max(db, -55 + gain + self.rng.gauss(0, 1))
                if drone and any(abs(mhz - h) <= 0.25 for h in hops):
                    db = max(db, -60 + gain + self.rng.gauss(0, 1))
                spectrum[f] = db
                f += self.bin_hz
        return spectrum
