"""
Keithley 6487 picoammeter and voltage source
"""

import time

import numpy as np
import serial

# ── Instrument constants ──────────────────────────────────────────────────────
COLUMN_TO_READ = 1          # index of the current in the :READ? reply (as in the original script)
CURRENT_PROTECTION = 1     # A, :SENS:CURR:PROT
MAX_PARSE_FAILURES = 20    # consecutive bad replies before giving up


class Keithley6487:
    """Minimal RS-232 driver for the Keithley 6487. Use as a context manager."""

    def __init__(self, port: str, baud: int = 19200, timeout: float = 0.2):
        # 8N1 and no flow control are pyserial's defaults
        self.ser = serial.Serial(port=port, baudrate=baud, timeout=timeout)
        print(f"[INFO] Opened {port} @ {baud} baud")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def write(self, cmd: str, delay: float = 0.05) -> None:
        self.ser.write((cmd + "\r\n").encode("ascii"))
        time.sleep(delay)

    def query(self, cmd: str, delay: float = 0.1) -> str:
        self.ser.reset_input_buffer()
        self.write(cmd, delay)
        return self.ser.readline().decode("ascii", errors="replace").strip()

    def initialise(self, bias: float) -> None:
        """Reset, apply `bias` volts from the internal source and enable output."""
        idn = self.query("*IDN?")
        print(f"[INFO] Instrument ID: {idn}" if idn else
              "[WARNING] No IDN response; check cable and instrument settings.")

        for cmd in (
            "*RST",
            "*CLS",
            ":SOUR:FUNC VOLT",
            f":SOUR:VOLT:LEV {bias}",
            f":SENS:CURR:PROT {CURRENT_PROTECTION}",
            ":SENS:FUNC 'CURR'",
            ":OUTP ON",
        ):
            self.write(cmd)
        time.sleep(0.5)

    def read_current(self) -> float | None:
        """One reading in amps, or None if the reply can't be parsed."""
        raw = self.query(":READ?", delay=0.0)
        try:
            values = raw.split(",")[COLUMN_TO_READ].strip()
            return float(values.replace("NADC", "").replace("A", ""))
        except (ValueError, IndexError) as exc:
            print(f"[WARNING] Could not parse reading '{raw}' ({exc})")
            return None

    def acquire(self, num_samples: int, delay: float = 0.0) -> np.ndarray:
        """Collect `num_samples` valid readings."""
        values, failures = [], 0
        while len(values) < num_samples:
            value = self.read_current()
            if value is None:
                failures += 1
                if failures >= MAX_PARSE_FAILURES:
                    raise RuntimeError(
                        f"{MAX_PARSE_FAILURES} consecutive unreadable replies from the picoammeter.")
                continue
            failures = 0
            values.append(value)
            if delay:
                time.sleep(delay)
        return np.array(values)

    def close(self) -> None:
        if self.ser.is_open:
            try:
                self.write(":OUTP OFF")   # never leave the bias on
            finally:
                self.ser.close()
                print("[INFO] Output off, serial port closed.")

