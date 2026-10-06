import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks

def angle_to_wavelength_linear(theta_deg):
    return 24 * theta_deg + 25

data = np.loadtxt(r"./resolution_3.75_4.75_0.01_0.01_0.1.txt",
                  delimiter=',',
                  usecols=(0, 1))

angle = data[:, 0]
photocurrent = data[:, 1]

wavelength_linear = angle_to_wavelength_linear(angle)

peaks, _ = find_peaks(photocurrent, distance=20, prominence=1e-10)

if len(peaks) == 0:
    print("Aucun pic détecté. Essaie de réduire 'prominence'.")
else:
    peak_heights = photocurrent[peaks]

    top3_indices = peaks[np.argsort(peak_heights)[-3:]]

    top3_angles = angle[top3_indices]
    top3_wavelengths = angle_to_wavelength_linear(top3_angles)
    top3_heights = photocurrent[top3_indices]

    for i, (lam, intens) in enumerate(zip(top3_wavelengths, top3_heights), 1):
        print(f"   Pic {i} : λ = {lam:.1f} nm, Intensité = {intens:.2e} A")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

# Graphique 1 : Données brutes (angle)
ax1.plot(angle, photocurrent, 'b-', linewidth=1)
ax1.set_xlabel('Actuator Angle (degrees)', fontsize=12)
ax1.set_ylabel('Photocurrent (A)', fontsize=12)
ax1.set_title('Raw Data: Photocurrent vs Angle', fontsize=14)
ax1.set_yscale('log')
ax1.grid(True, alpha=0.3)

# Graphique 2 : Spectre avec approximation linéaire
ax2.plot(wavelength_linear, photocurrent, 'r-', linewidth=1)
ax2.set_xlabel('Wavelength (nm)', fontsize=12)
ax2.set_ylabel('Photocurrent (A)', fontsize=12)
ax2.set_title('Spectrum (Linear Approximation \nλ = 24θ + 25'')', fontsize=14)
ax2.set_yscale('log')
ax2.grid(True, alpha=0.3)

plt.tight_layout()

calibrated_spectrum_data = np.column_stack((wavelength_linear, photocurrent))

plt.show()
