"""
Time-stability measurement

Biases the SiPM, parks the monochromator at a fixed angle and, every
`interval_mins` minutes, records `num_samples` current readings, writing the
mean and standard deviation to `<save_name>_stability.txt`.

Called from `acq` with the arguments of the config file:

    [required]
    acquisition      = 'stabilty'
    keithley_model   = 6487
    save_name        = 'test'

    [optional]
    overwrite        = False
    num_samples      = 100
    sipm_bias        = 53
    monochrom_angle  = 4.3
    interval_mins    = 5.0
    # also accepted: num_points, port, baud, delay
"""

import datetime
import time
from pathlib import Path

from keithley import Keithley6487
from src import monochromator_library as mchrom


def stability(
    save_name: str,
    overwrite: bool = False,
    num_samples: int = 100,
    sipm_bias: float = 53,
    monochrom_angle: float = 4.3,
    interval_mins: float = 5.0,
    num_points: int = 100,
    port: str = "/dev/ttyUSB0",
    baud: int = 19200,
    delay: float = 0.0,
) -> Path:
    """Run the time-stability measurement. Returns the path of the output file."""
    out_path = Path(f"{save_name}_stability.txt")
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"{out_path} exists; set overwrite = True to replace it.")

    interval_sec = interval_mins * 60.0
    print(f"[INFO] {num_points} points every {interval_mins} min at angle {monochrom_angle} "
          f"({(num_points - 1) * interval_mins:.1f} min total)")

    with Keithley6487(port, baud) as keithley, open(out_path, "w") as f:
        keithley.initialise(sipm_bias)
        mchrom.goTo(monochrom_angle)
        time.sleep(0.3)

        f.write("t_min,timestamp,current_mean_A,current_std_A,n_samples\n")
        t_start = time.time()

        try:
            for point in range(num_points):
                # Schedule against t_start so acquisition time doesn't accumulate as drift
                wait = point * interval_sec - (time.time() - t_start)
                if wait > 0:
                    time.sleep(wait)

                t_min = point * interval_mins
                stamp = datetime.datetime.now().isoformat(timespec="seconds")
                values = keithley.acquire(num_samples, delay)
                mean, std = values.mean(), values.std()

                print(f"[INFO] t={t_min:>6.1f} min  mean={mean:.6E} A  std={std:.6E} A  ({stamp})")
                f.write(f"{t_min},{stamp},{mean},{std},{len(values)}\n")
                f.flush()
        except KeyboardInterrupt:
            print("\n[INFO] Interrupted by user; data collected so far has been kept.")

    print(f"[INFO] Stability data saved -> {out_path}")
    return out_path