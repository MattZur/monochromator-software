##Squid
This has the code controlling the Keithley picoammeter and the monochromator for automated data acquisition. 

First, in command prompt, go to this directory and run 'source setup.sh', this loads up the virtual environment with all the packages needed.

'squid.py' has both the keithley control code and the data acquisition from the monochromator. This is used for collecting spectra using the monochromator and a SiPM. In main(), you can specify which angle ranges to scan over, how fine a scan you want. In the CONFIG, you can set the number of data points taken at a given position at the top (num_samples).