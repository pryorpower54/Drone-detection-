"""Turns raw spectrum sweeps into per-band detections.

The detector learns a background noise floor for every (antenna angle, frequency
bin) pair, so a Wi-Fi router that is always to the north doesn't trigger
alerts. A band "trips" at an angle when energy rises well above that learned
background in a way that looks like drone RF:

  wideband: a continuous block of bins at least min_width_mhz wide
            (analog video is ~6-8 MHz, digital HD video 10-40 MHz)
  hopping:  several short, narrow bursts scattered across the band
            (frequency-hopping control links such as ELRS and Crossfire)

A detection is only confirmed after the band trips in confirm_hits of the last
confirm_window pan passes, which filters out one-off spikes.
"""

from collections import deque


def _segments(flags):
    """Runs of consecutive True values, as (start_index, length)."""
    segs, start = [], None
    for i, f in enumerate(flags + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            segs.append((start, i - start))
            start = None
    return segs


class Detector:
    def __init__(self, cfg, bands, bin_width_hz):
        self.cfg = cfg
        self.bands = bands
        self.bin_mhz = bin_width_hz / 1e6
        self.baseline = {}  # (angle, freq_hz) -> dB
        self.history = {b["name"]: deque(maxlen=cfg["confirm_window"]) for b in bands}

    def learning(self, cycle):
        return cycle < self.cfg["learn_cycles"]

    def analyze(self, angle, spectrum, learning):
        """Process one sweep at one angle. Returns {band_name: measurement}."""
        alpha = self.cfg["baseline_alpha"]
        results = {}
        for band in self.bands:
            lo, hi = band["start_mhz"] * 1e6, band["stop_mhz"] * 1e6
            freqs = sorted(f for f in spectrum if lo <= f <= hi)
            excess, flags = [], []
            for f in freqs:
                key = (angle, f)
                base = self.baseline.get(key, spectrum[f])
                ex = spectrum[f] - base
                hot = ex >= band["threshold_db"] and not learning
                # Adapt the floor slowly; barely at all while a bin is lit up,
                # so a hovering drone doesn't get absorbed into the background.
                a = alpha / 20 if hot else alpha
                self.baseline[key] = base + a * (spectrum[f] - base) if key in self.baseline else spectrum[f]
                excess.append(ex)
                flags.append(hot)

            segs = _segments(flags)
            peak_i = max(range(len(excess)), key=excess.__getitem__) if excess else None
            m = {"peak_mhz": freqs[peak_i] / 1e6 if peak_i is not None else 0.0,
                 "excess_db": excess[peak_i] if peak_i is not None and flags[peak_i] else 0.0,
                 "wide_mhz": 0.0, "bursts": 0}
            for start, n in segs:
                width = n * self.bin_mhz
                m["wide_mhz"] = max(m["wide_mhz"], width)
                if width <= band.get("max_burst_width_mhz", 0):
                    m["bursts"] += 1
            results[band["name"]] = m
        return results

    @staticmethod
    def merge(a, b):
        """Combine measurements from several sweeps at the same angle."""
        if a is None:
            return dict(b)
        return {"peak_mhz": a["peak_mhz"] if a["excess_db"] >= b["excess_db"] else b["peak_mhz"],
                "excess_db": max(a["excess_db"], b["excess_db"]),
                "wide_mhz": max(a["wide_mhz"], b["wide_mhz"]),
                "bursts": a["bursts"] + b["bursts"]}

    def tripped(self, band, m):
        if band["kind"] == "wideband":
            return m["wide_mhz"] >= band["min_width_mhz"]
        return m["bursts"] >= band["min_bursts"]

    def end_pass(self, per_angle):
        """Call after each pan pass with {angle: {band_name: merged measurement}}.

        Returns a list of confirmed detections with an estimated bearing.
        """
        detections = []
        for band in self.bands:
            name = band["name"]
            hits = {a: m[name] for a, m in per_angle.items() if self.tripped(band, m[name])}
            self.history[name].append(bool(hits))
            if not hits or sum(self.history[name]) < self.cfg["confirm_hits"]:
                continue
            # Bearing: the angle where the signal stood furthest above background.
            bearing, best = max(hits.items(), key=lambda kv: (kv[1]["excess_db"], kv[1]["bursts"]))
            detail = (f"{best['wide_mhz']:.0f} MHz wide signal" if band["kind"] == "wideband"
                      else f"{best['bursts']} hop bursts")
            detections.append({"band": name, "bearing": bearing, "peak_mhz": best["peak_mhz"],
                               "excess_db": best["excess_db"], "detail": detail})
        return detections
