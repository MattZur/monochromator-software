# Plotting sets of spectrum data
# Plots the individual spectrum but also averages them
# Converts the photocurrent-angle plots to a wavelength-angle plot
# Modified from code working on the same project available at 
# https://github.com/leagagneux11/Summer_2026_Internship/blob/main/2.%20Deuterium%20Lamp/Deuterium%20Lamp%20Analysis%20Code.ipynb


# Note: current reposoitory does not have data used on it
# Does not save the figure at the moment, unsure on the desired file 
# path location for saving the figure, so it is commented out for now

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path

def actuator_angle_to_wavelength(theta_deg):
    # Equation 20 of Max's report: m * lambda = 2 * d * cos(phi) * sin(gamma * (theta - theta0))

    d = 835.5           # nm (1 / 1200 lines/mm)
    phi = 35            # degrees (half deviation angle)
    gamma = 1.00694     # NEW actuator scaling factor, Max's : 1.0028
    theta0 = -1.02898   # NEW degrees (angular offset), max's : 1.502
    m = 1               # first diffraction order

    theta_rad = np.radians(theta_deg)
    theta0_rad = np.radians(theta0)
    phi_rad = np.radians(phi)

    C = 2 * d * np.cos(phi_rad)  # ≈ 1365 nm

    wavelength = (C * np.sin(gamma * (theta_rad - theta0_rad))) / m

    return wavelength

# Main

#save_fig = False
# Counter is used to determine if the total_sum_photocurrent variable has been added to yet
counter = 0
# total_sum_photocurrent is used to calculate the average of all the files processed
total_sum_photocurrent = []
# num_files is used to determine how many files were processed, so that the average can be calculated
num_files = 0

# Define the directory path where the spectrum data files are located. Use pathlib to handle file paths.

path = Path("enter file path to where spectrum data is stored")  # Replace with the actual path to your data files
path_prefix = path
path_suffix = ".txt"

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

try:
    # Iterates over all .txt files in the specified directory and processes them
    for target in path.glob("*.txt"):
        
        print(str(target))
        try:

            df = pd.read_csv(str(target))

        except:
            print(f"File {target} failed to load.")  


        try:
            #print(f"File {target} failed to load.")             
            trimmed_path_file = target.stem
            #print(f"Trimmed name: {trimmed_path_file}")

            # Assume file format as follows: angle_deg,epos,current_mean_A,current_std_A,n_samples
            angle = df["angle_deg"]
            photocurrent = df["current_mean_A"]
            photocurrent_std = df["current_std_A"] / np.sqrt(df["n_samples"]) # errors are negligible

            wavelength_calibrated = actuator_angle_to_wavelength(angle)

            # Plot 1 : Raw Data (angles)
            ax1.errorbar(angle, photocurrent, yerr=photocurrent_std, fmt='.',label=f"{trimmed_path_file}", zorder=1)

            # Plot 2 : Calibrated Spectrum
            ax2.errorbar(wavelength_calibrated, photocurrent, yerr=photocurrent_std, fmt='.',label=f"{trimmed_path_file}", zorder=1)

            if counter == 0:
                total_sum_photocurrent = photocurrent
                counter += 1
            else:
                total_sum_photocurrent += photocurrent

        except:
            print(f"File {target} failed to be processed.")        

        num_files += 1

except:
    print(f"Error occurred while trying to glob files.")

# Plot the average spectrum of all the files processed
photocurrent_avg = total_sum_photocurrent / num_files

ax1.plot(angle, photocurrent_avg, 'r-', linewidth=1, label="Average", zorder=2)
ax2.plot(wavelength_calibrated, photocurrent_avg, 'r-', linewidth=1, label="Average")

ax1.set_xlabel('Actuator Angle (degrees)', fontsize=12)
ax1.set_ylabel('Photocurrent (A)', fontsize=12)
ax1.set_title('Raw Data: Photocurrent vs Angle', fontsize=14)
ax1.set_yscale('log')
ax1.grid(True, alpha=0.3)

ax1.legend()

ax2.set_xlabel('Wavelength (nm)', fontsize=12)
ax2.set_ylabel('Photocurrent (A)', fontsize=12)
ax2.set_title('Spectrum: Eq 20 Calibration', fontsize=14)
ax2.set_yscale('log')
ax2.grid(True, alpha=0.3)

ax2.legend()

plt.tight_layout()

#if save_fig:
#    plt.savefig(f"{path_file1.rsplit('.', 1)[0]}_{path_file2.rsplit('.', 1)[0]}.png", dpi=600, bbox_inches='tight')
#plt.show()