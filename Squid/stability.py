"""
Keithley 6487 Picoammeter — RS-232 Current Logger
====================================================
Records 1000 current readings via RS-232 and saves them
as either a CSV or HDF5 (.h5) file.

Dependencies:
    pip install pyserial h5py pandas

Usage:
    python keithley6487_logger.py

Configuration:
    Edit the CONFIG dict below, or pass CLI arguments:
        python keithley6487_logger.py --port COM3 --baud 9600 --output mydata --format csv
"""

import argparse
import sys
import os
import time
import datetime
import serial
import csv
import h5py
import pandas as pd
import numpy as np
sys.path.append("Home/Documents/Monochromator/Monochromator_control_code/src")
import src.mchrom_control_code_draft as mchrom


# ── Default configuration ────────────────────────────────────────────────────     bnbnnbbnnb
CONFIG = {
    "port":       "/dev/ttyUSB0",#"/dev/tty.usbserial-110",     # Serial port: "COM3" on Windows, "/dev/ttyUSB0" on Linux
    "baud":       19200,       # Baud rate  (6487 default: 9600)
    "bytesize":   serial.EIGHTBITS,
    "parity":     serial.PARITY_NONE,
    "stopbits":   serial.STOPBITS_ONE,
    "timeout":    5,          # Read timeout in seconds
    "num_samples": 1,      # Number of readings to collect
    "delay":      0.05,       # Delay between readings (seconds)
}


# ── Instrument commands (SCPI) ────────────────────────────────────────────────
INIT_COMMANDS = [
    "*RST",                   # Reset instrument to defaults
    "*CLS",
    ":SOUR:FUNC VOLT",

    #":SYST:ZCH OFF",          # Disable zero check
    #":CURR:RANG:AUTO ON",     # Auto-range current
    #":FORM:ELEM READ",
    #":SOUR:VOLT:RANG 500",
    ":SOUR:VOLT:LEV 53",
    #",
    #":OUTP ON",# Output reading only (no timestamp, status)
    #":MEAS:CURR?"
    ":SENS:CURR:PROT 1",
    ":SENS:FUNC 'CURR'",
    ":OUTP ON"

    #":SENS:CURR:RANG 0.02",

]

TRIGGER_CMD  = ":READ?"       # Trigger a single reading and return it
IDN_CMD      = "*IDN?"        # Identification query


# ── Helper functions ──────────────────────────────────────────────────────────

def open_instrument(cfg: dict) -> serial.Serial:
    """Open the RS-232 connection to the Keithley 6487."""
    try:
        inst = serial.Serial(
            port     = cfg["port"],
            baudrate = cfg["baud"],
            bytesize = cfg["bytesize"],
            parity   = cfg["parity"],
            stopbits = cfg["stopbits"],
            timeout  = cfg["timeout"],
            xonxoff  = False,
            rtscts   = False,
            dsrdtr   = False,
        )
        print(f"[INFO] Opened serial port: {cfg['port']} @ {cfg['baud']} baud")
        return inst
    except serial.SerialException as exc:
        print(f"[ERROR] Cannot open port '{cfg['port']}': {exc}")
        sys.exit(1)


def send_cmd(inst: serial.Serial, cmd: str, delay: float = 0.05) -> None:
    """Send a SCPI command (appends CR+LF terminator)."""
    inst.write((cmd + "\r\n").encode("ascii"))
    time.sleep(delay)


def query(inst: serial.Serial, cmd: str, delay: float = 0.1) -> str:
    """Send a command and return the stripped response."""
    inst.reset_input_buffer()
    send_cmd(inst, cmd, delay)
    response = inst.readline().decode("ascii", errors="replace").strip()
    return response


def initialise_instrument(inst: serial.Serial) -> None:
    """Send initialisation commands and verify communication."""
    idn = query(inst, IDN_CMD)
    if not idn:
        print("[WARNING] No IDN response — check cable and instrument settings.")
    else:
        print(f"[INFO] Instrument ID: {idn}")

    print("[INFO] Initialising instrument …")
    for cmd in INIT_COMMANDS:
        send_cmd(inst, cmd)
    time.sleep(0.5)
    print("[INFO] Initialisation complete.")

'''
def read_current(inst: serial.Serial) -> float | None:
    """
    Request a single current reading.
    Returns the value in Amperes, or None on parse error.
    """
    raw = query(inst, TRIGGER_CMD, delay=0.0)
    try:
        # The 6487 may return something like "+1.23456E-09A" or just "1.23456E-09"
        value = float(raw.replace("A", "").replace("NADC", "").strip())
        print(value)
        return value
    except ValueError:
        print(f"[WARNING] Could not parse reading: '{raw}'")
        return None
'''

def read_current(inst: serial.Serial) -> (float | None):
    """
    Request a single current reading.
    Returns the value in Amperes (2nd field), or None on parse error.
    """
    raw = query(inst, TRIGGER_CMD, delay=0.0)

    try:
        parts = raw.split(",")

        # Take the second value (index 1)
        current_str = parts[1].strip()

        # Clean and convert
        value = float(current_str.replace("A", "").replace("NADC", ""))

        print(value)
        return value

    except (ValueError, IndexError) as e:
        print(f"[WARNING] Could not parse reading: '{raw}' ({e})")
        return None

# ── Acquisition loop ──────────────────────────────────────────────────────────

def acquire(inst: serial.Serial, num_samples: int, delay: float) -> tuple[list, list]:
    """Collect `num_samples` current readings. Returns (timestamps, values)."""
    timestamps = []
    values     = []

    print(f"\n[INFO] Collecting {num_samples} readings …")
    print("       Press Ctrl+C to abort early.\n")

    try:
        while len(values) < num_samples:
            ts    = datetime.datetime.now().isoformat(timespec="milliseconds")
            value = read_current(inst)

            if value is not None:
                timestamps.append(ts)
                values.append(value)
                count = len(values)

                # Progress indicator every 50 samples
                if count % 50 == 0 or count == 1:
                    print(f"  [{count:>4}/{num_samples}]  {value:.6E} A   ({ts})")

            time.sleep(delay)

    except KeyboardInterrupt:
        print("\n[INFO] Acquisition interrupted by user.")

    print(f"\n[INFO] Collected {len(values)} readings.")
    return timestamps, values


# ── Save functions ────────────────────────────────────────────────────────────

def save_csv(filename: str, timestamps: list, values: list) -> None:
    """Save readings to a CSV file."""
    path = filename if filename.endswith(".csv") else filename + ".csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["index", "timestamp", "current_A"])
        for i, (ts, val) in enumerate(zip(timestamps, values), start=1):
            writer.writerow([i, ts, val])
    print(f"[INFO] Data saved → {path}")


def save_h5(filename: str, timestamps: list, values: list) -> None:
    """Save readings to an HDF5 file."""
    path = filename if filename.endswith(".h5") else filename + ".h5"
    with h5py.File(path, "w") as f:
        f.attrs["instrument"]   = "Keithley 6487"
        f.attrs["created"]      = datetime.datetime.now().isoformat()
        f.attrs["num_samples"]  = len(values)

        grp = f.create_group("measurements")
        grp.create_dataset("current_A",  data=np.array(values, dtype=np.float64))
        grp.create_dataset("timestamp",  data=np.array(timestamps, dtype=h5py.string_dtype()))
        grp.create_dataset("index",      data=np.arange(1, len(values) + 1, dtype=np.int32))

        # Attach units attribute
        grp["current_A"].attrs["units"] = "A"
    print(f"[INFO] Data saved → {path}")


# ── CLI / main ────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keithley 6487 RS-232 current logger"
    )
    parser.add_argument("--port",    default=CONFIG["port"],
                        help=f"Serial port (default: {CONFIG['port']})")
    parser.add_argument("--baud",    default=CONFIG["baud"], type=int,
                        help=f"Baud rate (default: {CONFIG['baud']})")
    parser.add_argument("--samples", default=CONFIG["num_samples"], type=int,
                        help=f"Number of readings (default: {CONFIG['num_samples']})")
    parser.add_argument("--delay",   default=CONFIG["delay"], type=float,
                        help=f"Delay between readings in seconds (default: {CONFIG['delay']})")
    parser.add_argument("--output",  default=None,
                        help="Output filename (without extension). Prompted if omitted.")
    parser.add_argument("--format",  choices=["csv", "h5"], default=None,
                        help="Output format: csv or h5. Prompted if omitted.")

    # ── Time-stability measurement parameters ─────────────────────────
    parser.add_argument("--angle", type=float, default=4.25,
                        help="Fixed monochromator angle/position (default: 4.25)")
    parser.add_argument("--num-points", type=int, default=100,
                        help="Number of time points N (default: 100)")
    parser.add_argument("--interval-min", type=float, default=5.0,
                        help="Interval between points M, in minutes (default: 5)")
    return parser.parse_args()


def prompt_output(args: argparse.Namespace) -> tuple[str, str]:
    """Prompt for filename and format if not provided on command line."""
    if args.output:
        filename = args.output
    else:
        filename = input("Enter output filename (without extension): ").strip()
        if not filename:
            filename = f"keithley6487_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if args.format:
        fmt = args.format
    else:
        while True:
            fmt = input("Save as [csv] or [h5]? ").strip().lower()
            if fmt in ("csv", "h5"):
                break
            print("  Please enter 'csv' or 'h5'.")

    return filename, fmt


def main() -> None:
    args = parse_args()

    # Update config from CLI
    CONFIG["port"]        = args.port
    CONFIG["baud"]        = args.baud
    CONFIG["num_samples"] = args.samples
    CONFIG["delay"]       = args.delay

    print("=" * 60)
    print("  Keithley 6487 RS-232 Current Logger")
    print("=" * 60)

    # ── Time-stability measurement setup ───────────────────────────────
    angle          = args.angle
    N_points       = args.num_points
    M_minutes      = args.interval_min
    interval_sec   = M_minutes * 60.0

    filename, fmt = "test", "csv"

    # Output file with the raw per-point statistics (t, mean, std)
    output_txt = (filename if filename.endswith(".txt") else filename + "_stability.txt")

    # Open port and instrument
    inst = open_instrument(CONFIG)
    initialise_instrument(inst)

    # Move to the fixed angle once, before starting the time series
    mchrom.goTo(angle)
    time.sleep(0.3)

    print(f"[INFO] Fixed angle/position: {angle}")
    print(f"[INFO] Time-stability run: {N_points} points every {M_minutes} min "
          f"({(N_points - 1) * M_minutes:.1f} min total)")

    t_start = time.time()

    with open(output_txt, "a") as file:
        file.write("t_min,timestamp,current_mean_A,current_std_A,n_samples\n")

        for point in range(N_points):
            # Absolute schedule (relative to t_start) avoids accumulated drift
            # from the time spent acquiring/writing at each point.
            target_t = point * interval_sec
            wait_time = target_t - (time.time() - t_start)
            if wait_time > 0:
                time.sleep(wait_time)

            t_min = point * M_minutes
            ts_now = datetime.datetime.now().isoformat(timespec="seconds")

            timestamps, values = acquire(inst, CONFIG["num_samples"], CONFIG["delay"])

            if not values:
                print(f"[WARNING] No data collected at t={t_min} min. Skipping point.")
                continue

            arr = np.array(values)
            mean_val = np.mean(arr)
            std_val  = np.std(arr)

            print(f"[INFO] t={t_min:>4} min  mean={mean_val:.6E} A  "
                  f"std={std_val:.6E} A  ({ts_now})")

            file.write(f"{t_min},{ts_now},{mean_val},{std_val},{len(values)}\n")
            file.flush()

    inst.close()
    print("[INFO] Serial port closed.")
    print(f"[INFO] Stability data saved -> {output_txt}")


if __name__ == "__main__":
    main()
