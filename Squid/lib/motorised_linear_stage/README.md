# Python-Library
Python Library used to control the motorised linear stage.

## Assembly
The stage assembly consists of: 
- Arduino UNO R4
- Stepping motor driver (attached to the Arduino and a cooling fan)
- Stepping motor 
- UHV linear travel feedthrough HTL-133-4

## Files
* the library (used elsewhere in this repo)
* the CLI (to be used for setting the zero position)
* the Arduino sketch (to be used for uploading to a new Arduino)
    - this should remain within ./stepper_motor_control/ for upload