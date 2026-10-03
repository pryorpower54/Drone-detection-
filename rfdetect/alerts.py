"""Alert delivery: console, a CSV log, and phone push notifications via ntfy."""

import csv
import datetime
import os
import time
import urllib.request


class Alerter:
    def __init__(self, cfg):
        self.topic = cfg.get("ntfy_topic", "")
        self.server = cfg.get("ntfy_server", "https://ntfy.sh").rstrip("/")
        self.cooldown = cfg.get("cooldown_s", 120)
        self.log_file = cfg.get("log_file", "detections.csv")
        self.last_sent = {}

    def log(self, det):
        new = not os.path.exists(self.log_file)
        with open(self.log_file, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "band", "bearing_deg", "peak_mhz", "excess_db", "detail"])
            w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), det["band"],
                        det["bearing"], f"{det['peak_mhz']:.1f}", f"{det['excess_db']:.1f}", det["detail"]])

    def send(self, det):
        self.log(det)
        msg = (f"{det['band']} activity, bearing ~{det['bearing']} deg, "
               f"peak {det['peak_mhz']:.1f} MHz, +{det['excess_db']:.0f} dB over background. {det['detail']}")
        print(f"[ALERT] {msg}", flush=True)

        now = time.monotonic()
        if now - self.last_sent.get(det["band"], -1e9) < self.cooldown:
            return
        self.last_sent[det["band"]] = now
        if not self.topic:
            return
        req = urllib.request.Request(
            f"{self.server}/{self.topic}", data=msg.encode(),
            headers={"Title": "Possible drone detected", "Priority": "high", "Tags": "warning,satellite"})
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            print(f"[warn] ntfy push failed: {e}", flush=True)
