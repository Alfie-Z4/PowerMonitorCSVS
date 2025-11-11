#!/usr/bin/env python3
"""Simplified Power Monitoring Script
=====================================

Purpose:
  Rebuilt minimal version removing university-specific multiprocessing, ZMQ, MQTT,
  and dashboard/database integrations. Keeps ONLY core mathematical logic
  (ADC averaged voltage -> RMS current -> power) and logs readings to a local CSV.

Hardware:
  Raspberry Pi + MCP3008 (BCRobotics library) + 50A current clamp (single phase measured,
  extrapolated to balanced 3-phase total using PHASES).

Output:
  /home/pi/power_monitoring/readings.csv with headers:
    timestamp,device_id,machine_id,current_rms,voltage,power_w,state

Extensible:
  Future additions (database, API, ML) can hook into Collector after each record.

"""

import csv
import math
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class Config:
    """Editable parameters for deployment.

    Adjust these per device before rollout.
    """

    # Identity metadata (optional, useful for later aggregation)
    DEVICE_ID = "pi-001"
    MACHINE_ID = "machine-A"

    # Electrical parameters (core math inputs)
    AMPLIFIER_GAIN = 100.0        # Gain in original formula
    CT_RANGE_AMPS = 50.0          # Clamp rating (A)
    LINE_VOLTAGE = 230.0          # Assumed line voltage (V); replace with measured if available
    PHASES = 3                    # 3 for balanced three-phase extrapolation; 1 if single-phase system

    # Sampling behaviour
    SAMPLE_RATE_HZ = 50           # Individual sample rate during one averaging window
    AVERAGING_WINDOW = 20         # Samples averaged to produce one record
    SLEEP_BETWEEN_WINDOWS_S = 0   # Optional pause after logging each window

    # Machine state classification thresholds (Amps RMS)
    IDLE_THRESHOLD = 0.5          # Below => idle
    FAULT_THRESHOLD = 100.0       # Above => fault

    # CSV output configuration
    CSV_PATH = Path("/home/pi/power_monitoring/readings.csv")
    CSV_FLUSH_INTERVAL = 10       # Flush buffered records every N writes

    # Run limits
    MAX_RECORDS = 0               # 0 => run indefinitely; else stop after N records


# ---------------------------------------------------------------------------
# ADC Driver (MCP3008 via BCRobotics library)
# ---------------------------------------------------------------------------

from bcr_mcp3008 import MCP3008  # requires package install; SPI must be enabled

class MCP3008ADC:
    """Simple wrapper around MCP3008 ADC.
    Converts raw 10-bit reading to voltage using 3.3V reference.
    """
    def __init__(self, channel: int = 0):
        self.adc = MCP3008(device=0)
        self.channel = channel
        self._adc_max = (2 ** 10) - 1  # 10-bit resolution
        self._vref = 3.3

    def sample_voltage(self) -> float:
        raw = self.adc.readData(self.channel)
        return (raw / self._adc_max) * self._vref


# ---------------------------------------------------------------------------
# Core Mathematical Logic (Preserved)
# ---------------------------------------------------------------------------

class PowerMath:
    """Implements original transformation:
    ADCAverageVoltage -> AmplifierVoltageIn -> ClampCurrent -> RMS -> Power.
    """
    ONE_OVER_SQRT2 = 1 / math.sqrt(2)

    def __init__(self, gain: float, ct_range: float, line_voltage: float, phases: int):
        self.gain = gain
        self.ct_range = ct_range
        self.line_voltage = line_voltage
        self.phases = phases

    def calculate(self, avg_adc_voltage: float) -> Tuple[float, float]:
        amplifier_voltage_in = avg_adc_voltage / self.gain
        clamp_current = amplifier_voltage_in * self.ct_range
        rms_current = clamp_current * self.ONE_OVER_SQRT2
        power_w = self.phases * rms_current * self.line_voltage
        return rms_current, power_w


# ---------------------------------------------------------------------------
# Machine State Classification
# ---------------------------------------------------------------------------

class StateClassifier:
    def __init__(self, idle_threshold: float, fault_threshold: float):
        self.idle_threshold = idle_threshold
        self.fault_threshold = fault_threshold

    def classify(self, current_rms: float) -> str:
        if current_rms < self.idle_threshold:
            return "idle"
        if current_rms > self.fault_threshold:
            return "fault"
        return "running"


# ---------------------------------------------------------------------------
# CSV Logger (Buffered)
# ---------------------------------------------------------------------------

class CSVLogger:
    HEADERS = ["timestamp", "device_id", "machine_id", "current_rms", "voltage", "power_w", "state"]

    def __init__(self, path: Path, flush_interval: int):
        self.path = path
        self.flush_interval = flush_interval
        self.buffer: List[Dict] = []
        self.total_written = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_headers()

    def _write_headers(self):
        with open(self.path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=self.HEADERS).writeheader()

    def log(self, record: Dict):
        self.buffer.append(record)
        if len(self.buffer) >= self.flush_interval:
            self.flush()

    def flush(self):
        if not self.buffer:
            return
        with open(self.path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.HEADERS)
            writer.writerows(self.buffer)
        self.total_written += len(self.buffer)
        self.buffer.clear()


# ---------------------------------------------------------------------------
# Collector Loop
# ---------------------------------------------------------------------------

class Collector:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.adc = MCP3008ADC(channel=0)
        self.math = PowerMath(cfg.AMPLIFIER_GAIN, cfg.CT_RANGE_AMPS, cfg.LINE_VOLTAGE, cfg.PHASES)
        self.classifier = StateClassifier(cfg.IDLE_THRESHOLD, cfg.FAULT_THRESHOLD)
        self.logger = CSVLogger(cfg.CSV_PATH, cfg.CSV_FLUSH_INTERVAL)
        self.record_count = 0

    def sample_window(self) -> float:
        samples = []
        interval = 1.0 / self.cfg.SAMPLE_RATE_HZ
        for _ in range(self.cfg.AVERAGING_WINDOW):
            v = self.adc.sample_voltage()
            samples.append(v)
            time.sleep(interval)
        return sum(samples) / len(samples)

    def run(self):
        print(f"[START] Device={self.cfg.DEVICE_ID} Machine={self.cfg.MACHINE_ID} CSV={self.cfg.CSV_PATH}")
        print(f"[INFO] Gain={self.cfg.AMPLIFIER_GAIN} CT={self.cfg.CT_RANGE_AMPS} Phases={self.cfg.PHASES} Vline={self.cfg.LINE_VOLTAGE}")
        while True:
            avg_v = self.sample_window()
            current_rms, power_w = self.math.calculate(avg_v)
            state = self.classifier.classify(current_rms)
            record = {
                "timestamp": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
                "device_id": self.cfg.DEVICE_ID,
                "machine_id": self.cfg.MACHINE_ID,
                "current_rms": round(current_rms, 4),
                "voltage": round(self.cfg.LINE_VOLTAGE, 1),
                "power_w": round(power_w, 2),
                "state": state,
            }
            self.logger.log(record)
            self.record_count += 1
            if self.cfg.MAX_RECORDS and self.record_count >= self.cfg.MAX_RECORDS:
                break
            if self.cfg.SLEEP_BETWEEN_WINDOWS_S > 0:
                time.sleep(self.cfg.SLEEP_BETWEEN_WINDOWS_S)
        self.logger.flush()
        print(f"[END] Wrote {self.logger.total_written} records -> {self.cfg.CSV_PATH}")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    cfg = Config()
    Collector(cfg).run()


if __name__ == "__main__":  # pragma: no cover
    main()
