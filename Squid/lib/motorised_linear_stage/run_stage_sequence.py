"""Move the stage through a fixed sequence of positions, then reset.

Usage: python run_stage_sequence.py [PORT]
If PORT is omitted, the script looks for an Arduino Uno R4 automatically.
Requires stepper_motor_control.py (in the same folder) and pyserial.
"""

import sys
import time

from serial.tools import list_ports

from stepper_motor_control import StepperMotorController

# Arduino USB vendor ID and the product IDs of the Uno R4 Minima / Uno R4 WiFi.
ARDUINO_VID = 0x2341
UNO_R4_PIDS = {0x0069, 0x1002}
POSITIONS = [13, 48, 73, 48, 13]
PAUSE_S = 3


def main() -> None:
    if len(sys.argv) > 1:
        port = sys.argv[1]  # manual override
    else:
        matches = [
            p.device
            for p in list_ports.comports()
            if (p.vid == ARDUINO_VID and p.pid in UNO_R4_PIDS)
            or "uno r4" in (p.description or "").lower()
        ]
        if len(matches) != 1:
            sys.exit(
                f"Expected exactly one Arduino Uno R4, found {len(matches)}: {matches}. "
                "Pass the port explicitly, e.g. python run_stage_sequence.py /dev/tty.usbmodem1101"
            )
        port = matches[0]
        print(f"Found Arduino Uno R4 on {port}")

    with StepperMotorController(port) as ctl:
        # check_connection() returns (ok, message) and never raises, so a
        # missing PONG stops the run with the library's rewind-mode hint.
        ok, msg = ctl.check_connection()
        if not ok:
            sys.exit(msg)
        print("PONG received - connection OK")

        ctl.track_on()

        for pos in POSITIONS:
            final = ctl.move_to(pos)  # blocks until the move completes
            print(f"Moved to {pos} (device reports POS={final})")

            ok, msg = ctl.check_connection()
            if not ok:
                sys.exit(f"No PONG at position {pos}. {msg}")
            print(f"PONG received at {pos}; waiting {PAUSE_S}s")
            time.sleep(PAUSE_S)

        ctl.reset()
        print("Reset complete")


if __name__ == "__main__":
    main()
