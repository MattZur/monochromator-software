import numpy as np
import matplotlib.pyplot as plt


def plot_data(name):

    # Tell NumPy it's comma-separated
    data = np.loadtxt("/home/f71225bp/Documents/Monochromator/week_11-thurs-summary.txt", delimiter=',')

    x = data[:, 0]
    y = data[:, 1]
    yerr = data[:, 2]

    #plt.errorbar(x, np.log10(y), yerr=yerr, fmt='-', capsize=3, label = name)
    plt.scatter(x,np.log10(y))

#plot_data("/home/f71225bp/Documents/Monochromator/Monochromdata/week_10-tues-summary-1.txt")
plot_data("")
#plot_data("trial-0.01-0.01")
#plt.legend()
plt.xlabel('Angle')
plt.ylabel('log_10(Current)')
plt.legend()
plt.title('Angle vs Current Intensity Blue LED, slits at 0.5mm')
plt.grid(True)

plt.show()