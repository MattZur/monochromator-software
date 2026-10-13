The Xeryon Python Library:
Contains the Protocols the encoder controlling the grating uses to communicate with the computer. The Xeryon.py file contains all the protocols for all such devices so check this if there's any fundamental issues with connections. All the control code for our monochromator is implemented in 'monochrom_control_code_draft.py' in 'ourGUI'.

If you've got any issues with your control code trying to find the Xeryon.py file, we managed to fix it by putting it directly in our python site packages (probably not best practice, but it works). 
follow these steps:
1. in Command Prompt type,  python -m site
2. Find and go to directory ending in .../Lib/site-packages
3. Copy the Xeryon.py file into this directory

Better practice would be to set up a virtual environment containing all these packages for all software to do with the monochromator. Ask John Waiton how to do this lol.

ourGUI:
The "monochrom_control_code_draft.py" has all the functions that you'd need for any program controlling the monochromator. It calls the protocols from the Xeryon library and implements them into functions that make them more readable. E.g. step() moves in a specific direction by a given step size, goTo() moves the grating to a specified angle between -15 and 15. It also handles safety checks when the grating is moving, and handles safe bootup and disconection. If there's an issue with connecting to the correct COM port, check the port the monochromator is connected to and update that line at the top of this file.

The program "monochrom interface draft.py" that connects to the monochromator and loads a user interface to control the grating position manually. We've found this to be a lot more reliable than the company's UI. It loads the control code above and uses the defined functions. This can be improved significantly: add a display that shows the wavelength that should be on the output slit for a given angle. Make it so the presaved angle positions don't reset when closing the program (they're currently just saved in a python list)

Squid:
This has the code controlling the Keithley picoammeter and the monochromator for automated data acquisition. First, in command prompt, go to this directory and run 'source setup.sh', this loads up the virtual environment with all the packages we need. John Waiton set this up for us, so ask him if you want specifics of how all this works. 

'squid.py' has both the keithley control code and the data acquisition from the monochromator. The Keithley control code is copied from a version by Mattias Zurbriggen that takes similar data, so refer to him for anything that needs changing here. At the bottom, you can specify which angle ranges to scan over, how fine a scan you want, and you can set the number of data points taken at a given position at the top (num_samples). Ideally the keithley control code and the data taking would be separated, similar to 'monochrom_control_code_draft.py' but I couldn't get this to work. This has a lot of redundancy, with lots of code that can be removed entirely. 

THE MONOCHROMATOR:

The screeching on startup is apparently normal, and nothing to worry about. If the software can't find the axis for the encoder, this usually means the grating controller is getting stuck or caught on something. You can open the central chamber to check, but this shouldn't be an issue after the wiring is moved and secured for the final setup. The smallest increment the grating moves at is 0.01 degrees.

Make sure to connect all wires before switching on the power. The VGA cable is important, make sure it's not screwed on loose because if it is, the angle output to the encoder will be wrong. Both slits go down to a resolution of 0.01mm and can open up to >7mm. Have them as narrow as possible for data taking (especially the exit slit, having it at 0.01mm gave the best peaks with minimal optical artefacts). Bright and diffuse sources work best for consistent output. 

For any source, you should see a central peak, and a symmetrical intensity profile either side, e.g for a 265nm LED, this means peaks at -11.2, 0, +11.2 corresponding to the m=0 central peak, and m=1 peaks either side. Alignment of the optics affects intensity of the peaks a LOT. Make sure to do a rough scan across your data taking region to see if the intensity suits your purposes. There is an offset to this distribution based on variations in the angle the grating was installed at, so you'll see a horizontal shift in the distribution (when calibrating, this was +1.5, so the 265nm LED peaks were at -9.7, +1.5, +12.7). this offset can be changed with a knob at the top of the grating controller in the central chamber, so you can recalibrate it to 0 offset.

Having tried irises and wratten filter 18B (filters out visible light, lets through 250-300nm), neither reduced artefacts significantly. Filters reduced total intensity, but artefacts remained. This suggests they're caused by reflections in the chamber or internal effects. Taking readings with a blue LED showed the same artefacts, so we know they're not caused by diffraction (diffraction orders for blue wouldn't be visible). 


if you run into any other issues with any of this, you can email me mehansadias9@gmail.com
