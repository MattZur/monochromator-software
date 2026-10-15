import numpy as np
import time
from pathlib import Path
import datetime

from Squid.lib.readout_instruments.keithley import Keithley6487
from src import monochromator_library as mchrom


def create_angle_array(
    angle_start: float | None = None,
    angle_stop: float | None = None,
    angle_step: float | None = None,
    fine_ranges: list[tuple[float, float, float]] | None = None,
    include_coarse: bool = True,
) -> np.ndarray:
    """
    Sorted array of scan angles wihtout duplication.

    A coarse sweep (angle_start -> angle_stop inclusive, spacing angle_step) is
    combined with any number of fine ranges given as (start, stop, step).
    Set include_coarse = False to scan only the fine ranges.
    """
    segments = list(fine_ranges or [])
    if include_coarse:
        if None in (angle_start, angle_stop, angle_step):
            raise ValueError(
                "angle_start, angle_stop and angle_step are required when include_coarse = True")
        segments.insert(0, (angle_start, angle_stop, angle_step))
    if not segments:
        raise ValueError("No angles to scan: enable include_coarse or give fine_ranges.")

    angles = np.concatenate([np.arange(a, b + s / 2, s) for a, b, s in segments])
    return np.unique(np.round(angles, 10))


def single_pos_spectrum(
    save_name: str,
    overwrite: bool = False,
    num_samples: int = 1,
    sipm_bias: float = 53,
    angle_start: float | None = None,
    angle_stop: float | None = None,
    angle_step: float | None = None,
    fine_ranges: list[tuple[float, float, float]] | None = None,
    include_coarse: bool = True,
    port: str = "/dev/ttyUSB0",
    baud: int = 19200,
    timeout: float = 0.2, # not actually a timeout just the delay to each measurement 
    delay: float = 0.05, # made redundant by timeout
    settle_secs: float = 0.3,
) -> Path:
    """
    Monochromator spectrum scan.

    Steps the monochromator through a list of angles and, at each one, records
    `num_samples` current readings, writing the mean and standard deviation to
    `<save_name>_spectrum.txt`. Shares the `Keithley6487` driver with `stability`.

    Called from `acq` with the arguments of the config file (see spectrum.conf).
    """
    out_path = Path(f"{save_name}_spectrum.txt")
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"{out_path} exists; set overwrite = True to replace it.")

    angles = create_angle_array(angle_start, angle_stop, angle_step, fine_ranges, include_coarse)
    print(f"[INFO] Scanning {len(angles)} angles from {angles[0]} to {angles[-1]}")

    with Keithley6487(port, baud, timeout) as keithley, open(out_path, "w") as f:
        keithley.initialise(sipm_bias)
        f.write("angle_deg,epos,current_mean_A,current_std_A,n_samples\n")

        try:
            for i, angle in enumerate(angles, start=1):
                mchrom.goTo(angle)
                time.sleep(settle_secs)

                values = keithley.acquire(num_samples, delay)
                mean, std = values.mean(), values.std()
                epos = mchrom.Mot.getEPOS()

                print(f"[INFO] [{i}/{len(angles)}] angle={angle:.4f}  "
                      f"mean={mean:.6E} A  std={std:.6E} A")
                f.write(f"{angle},{epos},{mean},{std},{len(values)}\n")
                f.flush()
        except KeyboardInterrupt:
            print("\n[INFO] Interrupted by user; data collected so far has been kept.")

    print(f"[INFO] Spectrum data saved -> {out_path}")
    return out_path


def single_pos_stability(
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

