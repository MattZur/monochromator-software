#!/usr/bin/env python3
"""
stepper_client.py
==================

Command-line client for the Arduino linear-stage stepper controller
(``stepper_motor_control.ino``), built on top of ``stepper_motor_control.py``.

Usage
-----
    # One-off commands
    python stepper_client.py --port /dev/ttyACM0 ping
    python stepper_client.py --port /dev/ttyACM0 status
    python stepper_client.py --port /dev/ttyACM0 move 10
    python stepper_client.py --port /dev/ttyACM0 move 10 --no-wait
    python stepper_client.py --port /dev/ttyACM0 stop
    python stepper_client.py --port /dev/ttyACM0 track-on
    python stepper_client.py --port /dev/ttyACM0 track-off
    python stepper_client.py --port /dev/ttyACM0 reset
    python stepper_client.py --port /dev/ttyACM0 jog forward 50   # +50 steps
    python stepper_client.py --port /dev/ttyACM0 jog back 50      # -50 steps
    python stepper_client.py --port /dev/ttyACM0 jog forward      # firmware default size

    # Interactive REPL (send raw firmware commands directly)
    python stepper_client.py --port /dev/ttyACM0 shell

On Windows, --port will typically look like "COM3"; on Linux/macOS it's
usually something like "/dev/ttyACM0" or "/dev/ttyUSB0".
"""

from __future__ import annotations

import argparse
import sys

from stepper_motor_control import (
    DEFAULT_BAUDRATE,
    DEFAULT_BOOT_DELAY_S,
    DEFAULT_MOVE_TIMEOUT_S,
    StepperError,
    StepperMotorController,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI client for the Arduino stepper stage controller."
    )
    parser.add_argument(
        "--port", required=True, help="Serial port, e.g. /dev/ttyACM0 or COM3"
    )
    parser.add_argument(
        "--baud", type=int, default=DEFAULT_BAUDRATE, help="Baud rate (default: 9600)"
    )
    parser.add_argument(
        "--boot-delay",
        type=float,
        default=DEFAULT_BOOT_DELAY_S,
        help="Seconds to wait after opening the port for the Arduino to boot",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ping", help="Check connectivity (expects PONG; otherwise suggests rewind mode)")
    sub.add_parser("status", help="Print current position/state/tracking info")
    sub.add_parser("stop", help="Immediately halt any move and hold position")
    sub.add_parser("zero", help="Declare the current physical position as home (3 mm)")
    sub.add_parser("track-on", help="Enable move-history tracking")
    sub.add_parser("track-off", help="Disable move-history tracking")

    move_p = sub.add_parser("move", help="Move to an absolute position (mm)")
    move_p.add_argument("position_mm", type=int, help="Target position in mm (>= 3)")
    move_p.add_argument(
        "--no-wait",
        action="store_true",
        help="Return immediately instead of blocking until the move completes",
    )
    move_p.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_MOVE_TIMEOUT_S,
        help="Max seconds to wait for move completion",
    )

    reset_p = sub.add_parser("reset", help="Rewind tracked moves (or disable driver if untracked)")
    reset_p.add_argument(
        "--no-wait",
        action="store_true",
        help="Return immediately instead of blocking until the rewind completes",
    )
    reset_p.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_MOVE_TIMEOUT_S,
        help="Max seconds to wait for rewind completion",
    )

    jog_p = sub.add_parser(
        "jog", help="Jog forward/back a set number of steps (enters and leaves jog mode)"
    )
    jog_p.add_argument("direction", choices=["forward", "back"])
    jog_p.add_argument(
        "steps", type=int, nargs="?", default=None,
        help="Number of steps (default: firmware jog size)",
    )
    jog_p.add_argument("--timeout", type=float, default=DEFAULT_MOVE_TIMEOUT_S,
                       help="Max seconds to wait for the jog to complete")

    sub.add_parser("shell", help="Interactive REPL: type raw firmware commands directly")

    return parser


def run_command(ctl: StepperMotorController, args: argparse.Namespace) -> int:
    if args.command == "ping":
        ok, message = ctl.check_connection()
        print(message)
        if not ok:
            return 1

    elif args.command == "jog":
        ctl.jog_on()
        try:
            pos = ctl.jog(
                args.steps,
                forward=(args.direction == "forward"),
                move_timeout=args.timeout,
            )
        finally:
            try:
                ctl.jog_off()
            except StepperError:
                pass
        print(f"Jog complete. Position = {pos}")

    elif args.command == "status":
        print(ctl.get_status())

    elif args.command == "zero":
        ctl.zero()
        print("Current position set as home (3 mm).")

    elif args.command == "stop":
        ctl.stop()
        print("Stopped.")

    elif args.command == "track-on":
        ctl.track_on()
        print("Tracking enabled.")

    elif args.command == "track-off":
        ctl.track_off()
        print("Tracking disabled.")

    elif args.command == "move":
        wait = not args.no_wait
        result = ctl.move_to(args.position_mm, wait=wait, move_timeout=args.timeout)
        if wait:
            print(f"Move complete. Position = {result}")
        else:
            print("Move started (not waiting for completion).")

    elif args.command == "reset":
        wait = not args.no_wait
        result = ctl.reset(wait=wait, move_timeout=args.timeout)
        reply = ctl.last_reply
        if reply == "OK:RESET":
            print("Nothing was rewound: tracking is off or no moves were recorded. "
                  "The driver was just disabled. Send 'track-on' BEFORE moving to enable rewind.")
        elif reply == "OK:RESET_NOOP":
            print("Tracked moves cancel out; the stage is already at its starting position.")
        elif wait and result is not None:
            print(f"Reset/rewind complete. Position = {result}")
        else:
            print("Rewind started (not waiting for completion).")

    elif args.command == "shell":
        run_shell(ctl)

    return 0


def run_shell(ctl: StepperMotorController) -> None:
    """Simple interactive REPL: forwards raw lines to the firmware."""
    print("Interactive shell. Type firmware commands directly (e.g. STATUS, PING, 10, R, JOG, F50, B50, EXIT).")
    print("Type 'exit' or 'quit' to leave.")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            break
        try:
            for response in ctl.send_raw(line):
                print(response)
        except StepperError as exc:
            print(f"Error: {exc}")


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with StepperMotorController(
            args.port, baudrate=args.baud, boot_delay=args.boot_delay
        ) as ctl:
            return run_command(ctl, args)
    except StepperError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
