"""
Monochromator spectrum scan.

Steps the monochromator through a list of angles and, at each one, records
`num_samples` current readings, writing the mean and standard deviation to
`<save_name>_spectrum.txt`. Shares the `Keithley6487` driver with `stability`.

Called from `acq` with the arguments of the config file (see spectrum.conf).
"""

import time
from pathlib import Path

from acq_utils import create_angle_array

from keithley import Keithley6487
from src import monochromator_library as mchrom

def spectrum(
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
    timeout: float = 5.0,
    delay: float = 0.05,
    settle_secs: float = 0.3,
) -> Path:
    """Run the spectrum scan. Returns the path of the output file."""
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