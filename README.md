# Simplified Power Monitoring (CSV Version)

This repository is now a **minimal edge data logger**: sample current via MCP3008 (BCRobotics library), compute RMS current & power, write rows to a local CSV file. All previous stack components (MQTT, Telegraf, InfluxDB, Grafana, ZMQ) have been removed.

## Features
* MCP3008 ADC sampling with averaging window.
* Original math preserved (average ADC voltage → amplifier input → clamp current → RMS → power).
* Three‑phase extrapolation via `PHASES` (set 3 for balanced system; 1 for single phase).
* CSV output at `/home/pi/power_monitoring/readings.csv`.
* Basic state classification (idle / running / fault).

## Main Script
`current_dc/code/power_monitor.py`

## Configuration (edit inside `Config` class)
| Name | Purpose | Example |
|------|---------|---------|
| DEVICE_ID | Unique device identifier | pi-001 |
| MACHINE_ID | Machine label | machine-A |
| AMPLIFIER_GAIN | Gain used in conversion | 100.0 |
| CT_RANGE_AMPS | Clamp rating (A) | 50.0 |
| LINE_VOLTAGE | Assumed voltage (V) | 230.0 |
| PHASES | Phases to scale power | 3 |
| SAMPLE_RATE_HZ | Per-sample rate | 50 |
| AVERAGING_WINDOW | Samples per record | 20 |
| IDLE_THRESHOLD | A < idle threshold => idle | 0.5 |
| FAULT_THRESHOLD | A > fault threshold => fault | 100.0 |
| CSV_FLUSH_INTERVAL | Buffer size before flush | 10 |
| MAX_RECORDS | 0 = infinite loop | 0 |

## Raspberry Pi Setup
```bash
sudo raspi-config nonint do_spi 0   # Enable SPI
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git

cd /home/pi
git clone https://github.com/<your-org>/<your-repo>.git
cd <your-repo>/current_dc
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python3 code/power_monitor.py
tail -f /home/pi/power_monitoring/readings.csv
```

## Optional systemd Service
```bash
sudo tee /etc/systemd/system/power_monitor.service >/dev/null <<'UNIT'
[Unit]
Description=Simplified Power Monitor
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/<your-repo>/current_dc/code
ExecStart=/usr/bin/python3 power_monitor.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now power_monitor.service
```

## CSV Row Example
```
2025-11-11T12:00:00.123Z,pi-001,machine-A,1.2345,230.0,852.82,running
```

## Extend Later
* Energy accumulation (Wh total)
* Measured voltage channel
* Calibration offsets
* REST/GraphQL API layer
* ML-based state classification

## Legacy Stack
Removed: docker-compose services (MQTT, Telegraf, InfluxDB, Grafana). Retrieve via Git history if needed.

## License
GPLv3 inherited from original project. Review before redistribution.