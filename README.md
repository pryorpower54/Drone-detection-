# RF FPV Drone Detector

A passive, receive-only station that pans a directional antenna back and forth, sweeps the radio bands FPV drones use, and pushes an alert to your phone with a rough bearing when it hears drone-like signals.

It never transmits. It only listens, which is legal for hobbyists in most places (jamming or transmitting on these bands is not).

## Defaults I picked

You didn't specify these, so here is what the plan assumes. Any of them can change.

| Choice | Default | Why |
|---|---|---|
| Radio | HackRF One SDR | One cheap-ish receiver that covers 1 MHz to 6 GHz, so it hears 900 MHz, 2.4 GHz and 5.8 GHz. An RTL-SDR tops out around 1.7 GHz and would miss video. |
| Computer | Raspberry Pi 5 (Pi 4 also works) | Runs `hackrf_sweep` and the Python code, drives the servo from GPIO. |
| Antenna | One wideband log-periodic (LPDA) directional antenna | Covers all three bands with one antenna, and its narrow beam is what gives you a bearing. |
| Mount | 180° hobby servo, sweeping back and forth | Simplest. Back-and-forth avoids twisting the coax. See "360° option" below. |
| Bands | 5.8 GHz video, 2.4 GHz control, 900 MHz control | Covers analog/digital FPV video and ELRS, Crossfire, FrSky and similar control links. |
| Alerts | ntfy push notifications | Free, no account, works on iPhone and Android. Also logs every detection to `detections.csv`. |

## How it works

1. The servo steps the antenna across its range (every 15° by default).
2. At each angle the HackRF sweeps all three bands a few times and records signal power in 500 kHz slices.
3. For the first two passes it just learns what "normal" looks like at each angle and frequency, so your neighbour's Wi-Fi router to the east is ignored.
4. After that, it looks for energy well above that background that has a drone shape:
   - **Video (5.8 GHz)**: a solid block of signal at least 5 MHz wide. Analog video is about 6 to 8 MHz wide; DJI/Walksnail/HDZero digital video is 10 to 40 MHz.
   - **Control link (2.4 GHz and 900 MHz)**: several short, narrow bursts hopping around the band, which is what ELRS and Crossfire look like.
5. A band has to trip on 2 of the last 3 passes before you get alerted, to cut down on one-off spikes.
6. The alert includes the band, the bearing where the signal was strongest, the peak frequency and how far above background it was. Repeat alerts for the same band are held back for 2 minutes.

## Parts list

Prices are rough USD estimates and vary by seller.

| Part | Example | Approx. cost |
|---|---|---|
| SDR receiver | HackRF One (genuine Great Scott Gadgets, or a reputable clone) | $120 to $350 |
| Computer | Raspberry Pi 5, 4 GB, plus official 27 W USB-C power supply | $75 |
| microSD card | 32 GB, A1/A2 rated | $10 |
| Directional antenna | Log-periodic PCB antenna, about 700 MHz to 6 GHz, SMA connector | $25 to $50 |
| Coax | Short (under 30 cm) low-loss SMA male to SMA male pigtail | $10 |
| Pan servo | High-torque metal-gear 180° servo, e.g. DS3218 or MG996R | $15 to $20 |
| Servo power | 5 to 6 V, 3 A UBEC or buck converter (don't power the servo from the Pi) | $10 |
| Pan bracket | Servo pan bracket or a lazy-susan bearing plus servo horn | $10 to $15 |
| Mounting | Tripod or pole mount, zip ties, jumper wires | $15 to $25 |
| Enclosure (outdoor use) | Weatherproof ABS box for the Pi and HackRF | $20 to $30 |
| **Total** | | **about $310 to $590** |

Optional upgrades:

- **Filtered LNA** for 2.4/5.8 GHz to improve range (keep it right at the antenna).
- **360° option**: NEMA 17 stepper with a TMC2209 driver and an RF slip ring, or a continuous-rotation mount that reverses every turn.
- **Budget video-only alternative**: an RX5808 5.8 GHz video receiver module reads signal strength on all 40 FPV channels for under $10. It only detects analog 5.8 GHz video, but it's very cheap.

## Wiring

```
 Antenna ──SMA coax── HackRF One ──USB── Raspberry Pi 5
                                            │ GPIO18 (pin 12) ──── servo signal (orange/yellow)
                                            │ GND    (pin 6)  ──┬─ servo ground (brown/black)
 UBEC 5-6 V out (+) ─────────────────────── servo power (red)   │
 UBEC ground ───────────────────────────────────────────────────┘
```

The servo ground, UBEC ground and Pi ground must be tied together. Keep the HackRF close to the antenna so the coax stays short; at 5.8 GHz every extra 30 cm of thin coax costs noticeable range.

## Software setup (on the Pi)

```bash
sudo apt update
sudo apt install -y hackrf pigpio python3-gpiozero python3-pigpio
sudo systemctl enable --now pigpiod      # smooth servo PWM

hackrf_info                              # should list your HackRF
hackrf_sweep -1 -f 5640:5960 | head      # should print rows of numbers

# copy the rf-detector folder to the Pi, then:
cd rf-detector
python3 run.py --sim --passes 6          # quick test with a fake drone, no hardware
python3 run.py                           # the real thing
```

Python 3.11 or newer is required (Raspberry Pi OS Bookworm ships 3.11). There are no pip dependencies.

### Phone alerts

1. Install the **ntfy** app (iOS or Android) and subscribe to a hard-to-guess topic name, e.g. `aaron-drone-7f3k9`.
2. Put the same name in `config.toml` under `[alerts] ntfy_topic`.
3. Test it: `curl -d "test alert" https://ntfy.sh/aaron-drone-7f3k9`

Anyone who knows the topic name can read it, so don't use something guessable.

### Run on boot

```bash
sudo tee /etc/systemd/system/rf-detector.service >/dev/null <<'EOF'
[Unit]
Description=RF drone detector
After=network-online.target pigpiod.service

[Service]
WorkingDirectory=/home/pi/rf-detector
ExecStart=/usr/bin/python3 run.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now rf-detector
journalctl -u rf-detector -f             # watch the output
```

## Files

| File | What it does |
|---|---|
| `run.py` | Main loop: pan, sweep, detect, alert. `--sim` runs with no hardware. |
| `config.toml` | All the settings: bands, thresholds, servo, alerts. |
| `rfdetect/scanner.py` | Runs `hackrf_sweep` and parses its output; also a simulated scanner. |
| `rfdetect/detector.py` | Learns the background and decides what counts as drone RF. |
| `rfdetect/mount.py` | Servo pan mount (gpiozero) and a simulated mount. |
| `rfdetect/alerts.py` | Console, CSV log and ntfy push alerts. |

## Tuning it in the field

- **Too many false alarms**: raise `threshold_db` for that band, raise `min_bursts`, or set `confirm_hits = 3`.
- **Missing a drone you know is flying**: set `amp = true`, lower `threshold_db`, or slow the pan (`sweeps_per_position = 5`).
- **Slow to react**: one pass takes roughly (number of angles) × (`settle_s` + `sweeps_per_position` × about 1 s). Use a bigger `step_deg` or fewer sweeps per position.
- **Something moved in the background** (new router): restart the program so it relearns, or raise `baseline_alpha` so it adapts faster.
- The best first test is a friend flying an FPV quad at known distances and directions while you watch `detections.csv`.

## Honest limitations

- **It detects radio, not drones.** Anything else on these bands that looks similar (a new Wi-Fi hotspot, a wireless camera, a 900 MHz LoRa device) can trigger it. The background learning and the shape checks reduce this but don't eliminate it.
- **2.4 GHz is crowded.** ELRS shares the band with Wi-Fi and Bluetooth, so expect that band to be the noisiest. 900 MHz control and 5.8 GHz video are more reliable signals.
- **A drone that isn't transmitting is invisible.** Autonomous drones flying pre-programmed routes with no video or control link won't show up.
- **Range** depends heavily on antenna, terrain and the drone's transmit power. Expect a few hundred metres for typical FPV gear with this setup, more with an LNA and clear line of sight. That is an estimate, not a measured figure.
- **Bearing is coarse**, roughly ±15 to 30° with one LPDA and 15° steps.
- `hackrf_sweep` is restarted for every sweep, which adds about half a second of overhead each time. Fine for a first build; streaming it continuously is the obvious speed-up.

## Next steps once the basics work

1. Field-test with a real FPV quad and tune thresholds.
2. Stream `hackrf_sweep` continuously instead of one-shot for faster scans.
3. Add a 5.8 GHz analog video decoder so the alert can include a screenshot of what the drone sees.
4. Record labelled spectrum snapshots and train a small classifier to tell drone links from Wi-Fi better.
5. Two stations a known distance apart can cross their bearings to estimate the drone's position on a map.
