"""
Calibration A - calibrate monochromator angle data to a reference spectrum.

What the program does, in order:
  1. Reads either a single spectrum file, or every .txt (CSV-formatted)
     spectrum file in a directory.
  2. If a directory was given, averages the photocurrent over all files and
     combines their errors.
  3. Fits the angle -> wavelength conversion (gamma, theta0) so that the
     PDE-corrected data matches the reference spectrum.
       - default mode : gamma and theta0 both free (L-BFGS-B fit)
  4. Applies the final wavelength conversion, PDE correction and normalisation.
  5. Plots the calibrated data against the reference (optionally saves it).

Expected input file columns:
    angle_deg, epos, current_mean_A, current_std_A, n_samples

Usage examples:
    python calibrate_A.py "path/to/spectrum_folder"
    python calibrate_A.py "path/to/single_spectrum.txt"
    python calibrate_A.py "path/to/spectrum_folder" --init_guess 1.00694 1.0
    python calibrate_A.py "path/to/spectrum_folder" --save "out.png" --no-show
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar

# ---------------------------------------------------------------------------
# CONSTANTS AND REFERENCE DATA
# ---------------------------------------------------------------------------

# Path used when none is given on the command line (a file or a folder). Edit this.
DEFAULT_DATA_DIR = r"C:\Users\laugh\lea-summer-2026-internship-forked\lea-summer_2026_Internship\2. Deuterium Lamp\Spectrum_calibration_data_(30-10-2026)_1"

# Default initial guesses for the fit parameters (gamma, theta0). These are used in the
DEFAULT_GUESS = [1.00694, 0.5] 

# Physical constants for the wavelength conversion (Eq. 20 of Max's report).
# These were globals set inside get_wavelength() in the original code.
D = 835.5   # d
PHI = 35    # phi (degrees)

# REFERENCE DATA (wavelength in nm, intensity)
X_REF = np.array([
    115.0, 115.5, 116.0, 116.5, 117.0, 117.5, 118.0, 118.5, 119.0, 119.5, 120.0, 120.5, 121.0, 121.5, 122.0,
    122.5, 123.0, 123.5, 124.0, 124.5, 125.0, 125.5, 126.0, 126.5, 127.0, 127.5, 128.0, 128.5, 129.0, 129.5,
    130.0, 130.5, 131.0, 131.5, 132.0, 132.5, 133.0, 133.5, 134.0, 134.5, 135.0, 135.5, 136.0, 136.5, 137.0,
    137.5, 138.0, 138.5, 139.0, 139.5, 140.0, 140.5, 141.0, 141.5, 142.0, 142.5, 143.0, 143.5, 144.0, 144.5,
    145.0, 145.5, 146.0, 146.5, 147.0, 147.5, 148.0, 148.5, 149.0, 149.5, 150.0, 150.5, 151.0, 151.5, 152.0,
    152.5, 153.0, 153.5, 154.0, 154.5, 155.0, 155.5, 156.0, 156.5, 157.0, 157.5, 158.0, 158.5, 159.0, 159.5,
    160.0, 160.5, 161.0, 161.5, 162.0, 162.5, 163.0, 163.5, 164.0, 164.5, 165.0, 165.5, 166.0, 166.5, 167.0,
    167.5, 168.0, 168.5, 169.0, 169.5, 170.0,
    172.0, 174.0, 176.0, 178.0, 180.0, 182.0, 184.0, 186.0, 188.0, 190.0, 192.0, 194.0, 196.0, 198.0, 200.0,
    202.0, 204.0, 206.0, 208.0, 210.0, 212.0, 214.0, 216.0, 218.0, 220.0, 222.0, 224.0, 226.0, 228.0, 230.0,
    232.0, 234.0, 236.0, 238.0, 240.0,
    250.0, 260.0, 270.0, 280.0, 290.0, 300.0, 310.0, 320.0, 330.0, 340.0, 350.0, 360.0, 370.0, 380.0, 390.0, 400.0
])
Y_REF = np.array([
    0.0, 0.89, 2.0, 3.33, 5.0, 7.24, 10.0, 13.43, 17.0, 20.0, 22.71, 26.0, 32.0, 42.76, 50.0,
    44.0, 36.0, 38.06, 42.0, 47.04, 52.0, 55.5, 50.84, 35.0, 26.0, 23.12, 22.0, 23.84, 27.45, 30.0,
    30.99, 31.72, 32.0, 30.62, 27.68, 25.0, 22.84, 20.86, 20.0, 20.84, 22.57, 24.0, 24.83, 25.51, 26.0,
    26.3, 26.51, 26.72, 27.0, 27.59, 28.0, 27.66, 26.87, 26.0, 24.87, 23.6, 23.0, 24.08, 26.28, 28.0,
    28.94, 29.69, 30.0, 29.22, 27.78, 27.0, 29.07, 32.93, 35.0, 33.96, 32.04, 31.0, 31.71, 33.3, 35.0,
    36.5, 38.12, 40.0, 42.14, 44.7, 48.0, 53.28, 60.0, 67.17, 75.0, 82.03, 92.0, 120.0, 155.0, 155.0,
    175.0, 200.0, 160.0, 135.0, 110.0, 88.22, 70.0, 55.65, 45.0, 37.97, 32.5, 28.0, 23.95, 20.47, 18.0,
    16.27, 14.76, 13.46, 12.39, 11.57, 11.0, 9.63, 8.8, 8.23, 7.79, 7.5, 7.31, 7.17, 7.05, 6.93,
    6.8, 6.65, 6.5, 6.34, 6.17, 6.0, 5.81, 5.61, 5.39, 5.19, 5.0, 4.83, 4.68, 4.52, 4.37,
    4.2, 4.01, 3.8, 3.59, 3.38, 3.2, 3.03, 2.87, 2.71, 2.59, 2.5, 2.2, 1.91, 1.65, 1.4,
    1.18, 0.97, 0.79, 0.62, 0.48, 0.35, 0.24, 0.16, 0.09, 0.04, 0.01, 0.0
])

# Normalise the reference so its maximum is 100
Y_REF_NORM = Y_REF * (100.0 / np.max(Y_REF))

# PDE DATA (Photon Detection Efficiency - from Max's report, Fig. 3.2)
WL_PDE = np.array([120, 125, 130, 135, 140, 145, 150, 155, 160, 165, 170, 175, 180, 185, 190, 195, 200])
VALS_PDE = np.array([11, 12.5, 15.0, 19.0, 22.0, 24, 23.5, 23, 17, 23.5, 23.5, 24.0, 24.0, 24.0, 24.0, 24.0, 24.0])


# ---------------------------------------------------------------------------
# STEP 1 & 2: LOAD (AND AVERAGE) THE DATA
# ---------------------------------------------------------------------------

def load_single_file(file_path: Path):
    """
    Load a single .txt file and return the angle, photocurrent, and std arrays.
    Raises an exception if the file cannot be read or lacks required columns.
    """
    df = pd.read_csv(file_path)
    # Assumed format: angle_deg, epos, current_mean_A, current_std_A, n_samples
    angle = df["angle_deg"].to_numpy()
    photocurrent = df["current_mean_A"].to_numpy()
    # Standard error of the mean for this file (errors are negligible)
    photocurrent_std = (df["current_std_A"] / np.sqrt(df["n_samples"])).to_numpy()
    return angle, photocurrent, photocurrent_std


def load_and_average(path: Path):
    """
    Load spectrum data from `path`, which can be either:
      - a single file: its data is returned as-is, or
      - a directory: every .txt file in it is read and averaged together.

    Returns (angle, photocurrent_avg, photocurrent_std) as numpy arrays.
    For a directory, the per-file errors (std / sqrt(n_samples)) are combined
    as variances and the std of the average is sqrt(total_variance / num_files).
    For a single file, the std returned is that file's standard error.
    """
    print(path)

    # --- Single file case: nothing to average ---
    if path.is_file():
        print(f"Processing single file: {path}")
        return load_single_file(path)

    # --- Directory case: average all .txt files ---
    elif path.is_dir():
        total_sum_photocurrent = None   # running sum of photocurrent over files
        total_sum_variance = None       # running sum of variances over files
        reference_angle = None          # angle array of the first good file
        num_files = 0                   # how many files were processed successfully

        for target in sorted(path.glob("*.txt")):
            print(target)

            # Try to read the file; skip it if it cannot be read or lacks columns
            try:
                angle, photocurrent, photocurrent_std = load_single_file(target)
            except Exception as e:
                print(f"File {target} failed to load/process: {e}")
                continue

            print("file read successfully")

            if total_sum_photocurrent is None:
                # First good file: start the running sums
                total_sum_photocurrent = photocurrent.copy()
                total_sum_variance = photocurrent_std ** 2
                reference_angle = angle
            else:
                # The files are assumed to share the same angle range. Warn if not,
                # since adding arrays of different angles would be wrong.
                if len(angle) != len(reference_angle) or not np.array_equal(reference_angle, angle):
                    print(f"Warning: Angle arrays do not match for file {target}.")
                    if len(angle) != len(reference_angle):
                        print(f"  Skipping {target} (different number of points).")
                        continue
                total_sum_photocurrent += photocurrent
                # Combine variances so the std of the average can be found later
                total_sum_variance += photocurrent_std ** 2

            num_files += 1

        if num_files == 0:
            raise ValueError(f"No usable .txt files found in directory: {path}")

        photocurrent_avg = total_sum_photocurrent / num_files
        photocurrent_std = np.sqrt(total_sum_variance / num_files)
        print(f"Averaged {num_files} file(s).")
        return reference_angle, photocurrent_avg, photocurrent_std

    else:
        raise ValueError(f"Path is neither a file nor a directory: {path}")


# ---------------------------------------------------------------------------
# PHYSICS HELPERS
# ---------------------------------------------------------------------------

def get_wavelength(theta_deg, gamma, theta0):
    """Convert actuator angle (deg) to wavelength (nm) - Eq. 20 of Max's report."""
    C = 2 * D * np.cos(np.radians(PHI))
    return C * np.sin(gamma * (np.radians(theta_deg) - np.radians(theta0)))


def pde_at(wavelength):
    """Interpolate the PDE at the given wavelengths (flat beyond the table ends)."""
    return np.interp(wavelength, WL_PDE, VALS_PDE, left=VALS_PDE[0], right=VALS_PDE[-1])


# ---------------------------------------------------------------------------
# STEP 3: FREE FIT OF gamma AND theta0
# ---------------------------------------------------------------------------

def fit_gamma_and_theta0(angle, photocurrent_avg, init_guess=None):
    """Fit gamma and theta0 together by minimising the residual sum of squares."""

    def objective_function(params):
        gamma, theta0 = params
        w_calib = get_wavelength(angle, gamma, theta0)

        # Apply dynamic PDE correction
        y_corrected = photocurrent_avg / pde_at(w_calib)

        # Focus optimisation strictly on the primary peak features region
        mask_fit = (w_calib >= 115) & (w_calib <= 200)
        if np.sum(mask_fit) < 10:
            return 1e10  # too few points in range: penalise heavily

        w_fit = w_calib[mask_fit]
        y_fit = y_corrected[mask_fit]

        # Map reference onto current data wavelength array
        y_ref_lookup = np.interp(w_fit, X_REF, Y_REF_NORM)
        y_fit_scaled = y_fit * (100.0 / np.max(y_fit))

        # Minimise residual sum of squares
        return np.sum((y_fit_scaled - y_ref_lookup) ** 2)

    #init_guess = [1.00694, 1.0]          # gamma and theta0
    bounds = [(0.9, 1.1), (-2.0, 2.0)]   # allowed ranges (theta0 in degrees)
    result = minimize(objective_function, init_guess, bounds=bounds, method='L-BFGS-B')
    gamma_opt, theta0_opt = result.x
    return gamma_opt, theta0_opt, (115, 200)  # also return the normalisation window


# ---------------------------------------------------------------------------
# STEP 4: FINAL CORRECTION AND NORMALISATION
# ---------------------------------------------------------------------------

def apply_calibration(angle, photocurrent_avg, gamma_opt, theta0_opt, norm_window):
    """Convert to wavelength, correct for PDE and normalise the peak region to 100."""
    wavelength_final = get_wavelength(angle, gamma_opt, theta0_opt)
    photocurrent_corrected = photocurrent_avg / pde_at(wavelength_final)

    # Normalise using the maximum (the doublet) inside the chosen window
    lo, hi = norm_window
    mask_peaks = (wavelength_final >= lo) & (wavelength_final <= hi)
    val_doublet_max = np.max(photocurrent_corrected[mask_peaks])
    photocurrent_normalise = photocurrent_corrected * (100.0 / val_doublet_max)
    return wavelength_final, photocurrent_normalise


# ---------------------------------------------------------------------------
# STEP 5: PLOTTING
# ---------------------------------------------------------------------------

def plot_result(wavelength_final, photocurrent_normalise, gamma_opt, theta0_opt,
                save_path=None, show=True):
    """Plot calibrated data vs reference using a broken x-axis (100-240 | 240-400 nm)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, sharey=True, figsize=(11, 6),
                                   gridspec_kw={'width_ratios': [5, 1]})
    fig.subplots_adjust(wspace=0.04)

    # Same curves on both panels; each panel just shows a different x range
    ax1.plot(X_REF, Y_REF_NORM, color='#e32219', linewidth=1.5, label='Reference (normalized)')
    ax1.plot(wavelength_final, photocurrent_normalise, color='blue', linestyle='-',
             linewidth=1.5, label='Data + PDE (calibrated)')
    ax2.plot(X_REF, Y_REF_NORM, color='#e32219', linewidth=2.5)
    ax2.plot(wavelength_final, photocurrent_normalise, color='blue', linestyle='-', linewidth=1.5)

    ax1.set_xlim(100, 240)
    ax2.set_xlim(240, 400)
    ax1.set_ylim(0.1, 120)

    ax1.set_xticks([100, 120, 140, 160, 180, 200, 220, 240])
    ax2.set_xticks([300, 400])
    ax1.set_yticks([0, 25, 50, 75, 100])

    ax1.grid(True, color='#b0b0b0', linestyle='-', linewidth=0.5)
    ax2.grid(True, color='#b0b0b0', linestyle='-', linewidth=0.5)

    # Hide the inner spines to make the "axis break" look
    ax1.spines['right'].set_visible(False)
    ax2.spines['left'].set_visible(False)
    ax2.tick_params(left=False, labelleft=False)

    fig.suptitle(
        f"Deuterium Lamp - Calibration A (d = {D:.2f}, $\\phi$ = {PHI:.2f}, "
        f"$\\gamma$ = {gamma_opt:.5f}, $\\theta_0$ = {theta0_opt:.5f}°)",
        fontsize=14, y=0.95)

    # Little diagonal "break" marks between the two panels
    d_tick = .012
    kwargs = dict(transform=ax1.transAxes, color='black', clip_on=False, linewidth=1.2)
    ax1.plot((1 - d_tick, 1 + d_tick), (-d_tick, +d_tick), **kwargs)
    ax1.plot((1 - d_tick, 1 + d_tick), (1 - d_tick, 1 + d_tick), **kwargs)
    kwargs.update(transform=ax2.transAxes)
    ax2.plot((-d_tick * 5, +d_tick * 5), (-d_tick, +d_tick), **kwargs)
    ax2.plot((-d_tick * 5, +d_tick * 5), (1 - d_tick, 1 + d_tick), **kwargs)

    # Box with the fitted parameters
    info_text = f"$\\gamma$ = {gamma_opt:.5f}\n$\\theta_0$ = {theta0_opt:.5f}°"
    ax1.text(0.97, 0.965, info_text, transform=ax1.transAxes, fontsize=10,
             verticalalignment='top', horizontalalignment='right',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='white', edgecolor='#b0b0b0', alpha=0.9))

    ax1.legend(loc='upper left')
    fig.text(0.5, 0.02, 'WAVELENGTH (nm)', ha='center', fontsize=12)
    fig.text(0.06, 0.5, 'RELATIVE INTENSITY (%)', va='center', rotation='vertical', fontsize=12)

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Figure saved to {save_path}")
    if show:
        plt.show()


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Calibrate spectrum data (angle -> wavelength, PDE-corrected) to a reference spectrum.")
    parser.add_argument("data_path", nargs="*", default=None,
                        help="A single spectrum .txt file, or a directory of .txt files "
                             "to average (optional: falls back to DEFAULT_DATA_DIR)")
    parser.add_argument("--init_guess", nargs=2, type=float, default=DEFAULT_GUESS,
                        help="Initial guesses for gamma and theta0")
    parser.add_argument("--save", type=Path, default=None,
                        help="Save the final figure to this path (e.g. result.png)")
    parser.add_argument("--no-show", action="store_true",
                        help="Do not open plot windows (useful when saving only)")
    args = parser.parse_args()

    # Build the path. Joining the pieces handles unquoted paths with spaces,
    # and stripping quotes handles the Windows trailing-backslash issue
    # ("C:\\folder\\" arrives with a stray quote on the end).
    if args.data_path:
        raw = " ".join(args.data_path).strip().strip('"').strip("'")
        print(raw)
        data_path = Path(raw)
    else:
        data_path = Path(DEFAULT_DATA_DIR)

    # Accept either a file or a folder (load_and_average handles both cases)
    if not data_path.exists():
        parser.error(f"Path not found: {data_path!r}  (check the path and quotes)")

    # 1-2. Load the data (and average if a directory was given)
    angle, photocurrent_avg, photocurrent_std = load_and_average(data_path)

    # 3. Fit the calibration parameters

    gamma_opt, theta0_opt, norm_window = fit_gamma_and_theta0(angle, photocurrent_avg, init_guess=args.init_guess)
    print(f"gamma = {gamma_opt:.5f}, theta0 = {theta0_opt:.5f} deg")

    # 4. Apply the calibration and normalise
    wavelength_final, photocurrent_normalise = apply_calibration(
        angle, photocurrent_avg, gamma_opt, theta0_opt, norm_window)

    # 5. Plot / save
    plot_result(wavelength_final, photocurrent_normalise, gamma_opt, theta0_opt,
                save_path=args.save, show=not args.no_show)


if __name__ == "__main__":
    main()