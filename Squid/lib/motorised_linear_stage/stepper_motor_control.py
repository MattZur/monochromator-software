"""
stepper_motor_control.py
=========================

Python driver library for the Arduino linear-stage stepper controller
defined in ``stepper_motor_control.ino``.

This module implements a thin, synchronous serial client around the
firmware's line-based text protocol:

    PING                -> PONG
    STATUS              -> STATUS:POS=<int>,STATE=<IDLE|MOVING|REWINDING>,
                            TRACK=<0|1>,HIST=<count>/<max>,JOG=<0|1>
    <int mm> (>= 3)     -> OK:MOVING            (async; later "OK:MOVE_COMPLETE POS=<int>")
                        -> ERR:PAST_SAFETY_LIMIT
                        -> ERR:BUSY
                        -> OK:ALREADY_THERE
    STOP                -> OK:STOPPED
    T1                  -> OK:TRACK_ON  / ERR:BUSY
    T0                  -> OK:TRACK_OFF / ERR:BUSY
    ZERO                -> OK:ZEROED / ERR:BUSY
    JOG                 -> OK:JOG_ON  / ERR:BUSY
    EXIT                -> OK:JOG_OFF / ERR:BUSY
    F[n] / B[n]         -> OK:MOVING (jog mode only; later "OK:MOVE_COMPLETE POS=<int>")
                           ERR:BAD_STEPS / ERR:PAST_SAFETY_LIMIT / ERR:BUSY
    N<n>                -> OK:JOG_STEPS=<n> / ERR:BAD_STEPS
    R                   -> OK:RESETTING (async; later "OK:RESET_COMPLETE POS=<int>")
                        -> OK:RESET_NOOP
                        -> OK:RESET
                        -> ERR:BUSY

Design notes
------------
* Every command produces an *immediate* one-line acknowledgement. Motion
  commands (a numeric move, or ``R`` while a net rewind is required) are
  asynchronous: the immediate reply only confirms the move has *started*.
  A second, unsolicited line (``OK:MOVE_COMPLETE POS=...`` or
  ``OK:RESET_COMPLETE POS=...``) arrives later when motion finishes.
  This library exposes both "fire and forget" and "wait for completion"
  behaviour via a ``wait=`` keyword argument.
* The firmware is strictly single-threaded/single-move: any command sent
  while ``state != IDLE`` is rejected with ``ERR:BUSY``. Callers should
  generally wait for completion before issuing another motion command.

Requires: pyserial (``pip install pyserial``)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

try:
    import serial  # pyserial
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pyserial is required for stepper_motor_control. "
        "Install it with: pip install pyserial"
    ) from exc


# --------------------------------------------------------------------------
# Constants (mirrored from the firmware, for client-side sanity checks)
# --------------------------------------------------------------------------

SAFETY_OFFSET = 960
STEPS_PER_REV = 320
MIN_POSITION_MM = -10  # firmware rejects any target below this

DEFAULT_BAUDRATE = 9600
DEFAULT_TIMEOUT_S = 2.0          # per-line read timeout
DEFAULT_BOOT_DELAY_S = 2.0       # Arduino resets on serial open; give it time
DEFAULT_MOVE_TIMEOUT_S = 60.0    # max time to wait for a move to complete
DEFAULT_IDLE_GAP_S = 0.3         # silence that marks the end of a multi-line reply

REWIND_HINT = (
    "No PONG received from the device. Use rewind mode: send the reset "
    "command ('R', or `stepper_client.py --port <PORT> reset`) to rewind "
    "tracked moves and return the stage to its starting position. If the "
    "device still does not answer, check the cable/port and, if needed, "
    "reposition with manual_reset.py (position must be between 2 mm and 3 mm)."
)


# --------------------------------------------------------------------------
# Data types
# --------------------------------------------------------------------------

class MotionState(str, Enum):
    IDLE = "IDLE"
    MOVING = "MOVING"
    REWINDING = "REWINDING"


@dataclass
class Status:
    """Parsed response to the STATUS command."""
    position: int
    state: MotionState
    tracking_enabled: bool
    history_count: int
    history_max: int
    jog_mode: bool = False

    def __str__(self) -> str:
        return (
            f"POS={self.position} STATE={self.state.value} "
            f"TRACK={'ON' if self.tracking_enabled else 'OFF'} "
            f"HIST={self.history_count}/{self.history_max} "
            f"JOG={'ON' if self.jog_mode else 'OFF'}"
        )


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------

class StepperError(Exception):
    """Base class for all errors raised by this library."""


class ConnectionNotOpenError(StepperError):
    """Raised when a command is attempted on a closed connection."""


class DeviceTimeoutError(StepperError):
    """Raised when the device does not respond within the expected time."""


class DeviceBusyError(StepperError):
    """Raised on ERR:BUSY - a move/reset is already in progress."""


class SafetyLimitError(StepperError):
    """Raised on ERR:PAST_SAFETY_LIMIT - requested target below MIN_POSITION_MM."""


class LineTooLongError(StepperError):
    """Raised on ERR:LINE_TOO_LONG - the command exceeded the firmware buffer."""


class BadStepsError(StepperError):
    """Raised on ERR:BAD_STEPS - jog step count was missing, non-numeric or <= 0."""


class JogModeError(StepperError):
    """Raised on ERR:JOG_MODE - a position command was sent while jog mode is on."""


class UnknownCommandError(StepperError):
    """Raised on ERR:UNKNOWN - the firmware did not recognize the command."""


class UnexpectedResponseError(StepperError):
    """Raised when the device returns something the client can't parse."""


_ERROR_MAP = {
    "ERR:BUSY": DeviceBusyError,
    "ERR:PAST_SAFETY_LIMIT": SafetyLimitError,
    "ERR:LINE_TOO_LONG": LineTooLongError,
    "ERR:UNKNOWN": UnknownCommandError,
    "ERR:BAD_STEPS": BadStepsError,
    "ERR:JOG_MODE": JogModeError,
}


# --------------------------------------------------------------------------
# Main client
# --------------------------------------------------------------------------

_STATUS_RE = re.compile(
    r"^STATUS:POS=(?P<pos>-?\d+),STATE=(?P<state>IDLE|MOVING|REWINDING),"
    r"TRACK=(?P<track>[01]),HIST=(?P<hist>\d+)/(?P<histmax>\d+)(?:,JOG=(?P<jog>[01]))?$"
)
_COMPLETE_RE = re.compile(r"^OK:(MOVE_COMPLETE|RESET_COMPLETE) POS=(-?\d+)$")


class StepperMotorController:
    """
    Serial client for the Arduino stepper stage controller.

    Example
    -------
    >>> with StepperMotorController("/dev/ttyACM0") as ctl:
    ...     ctl.ping()
    ...     ctl.move_to(10)          # blocks until move completes
    ...     print(ctl.get_status())
    """

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT_S,
        boot_delay: float = DEFAULT_BOOT_DELAY_S,
        auto_open: bool = True,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.boot_delay = boot_delay
        self._ser: Optional["serial.Serial"] = None
        # Position from a completion line that arrived while we were waiting
        # for something else (e.g. a move started with wait=False).
        self._stashed_complete: Optional[int] = None
        # Most recent immediate reply (lets callers see exactly which R outcome occurred).
        self.last_reply: str = ""
        if auto_open:
            self.open()

    # -- connection lifecycle ------------------------------------------------

    def open(self) -> None:
        """Open the serial port and wait for the Arduino boot banner."""
        if self._ser and self._ser.is_open:
            return
        self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        # Opening the port resets most Arduino boards; give the firmware
        # time to boot and flush the READY/WARNING/INFO banner it prints.
        time.sleep(self.boot_delay)
        self._ser.reset_input_buffer()
        self._stashed_complete = None

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()

    def __enter__(self) -> "StepperMotorController":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        return bool(self._ser and self._ser.is_open)

    # -- low-level I/O --------------------------------------------------------

    def _require_open(self) -> "serial.Serial":
        if not self._ser or not self._ser.is_open:
            raise ConnectionNotOpenError("Serial connection is not open. Call open() first.")
        return self._ser

    def _write_line(self, line: str) -> None:
        ser = self._require_open()
        ser.write((line.strip() + "\n").encode("ascii"))
        ser.flush()

    def _read_line(self, timeout: Optional[float] = None) -> str:
        """Read a single line, raising DeviceTimeoutError if none arrives."""
        ser = self._require_open()
        original_timeout = ser.timeout
        try:
            if timeout is not None:
                ser.timeout = timeout
            raw = ser.readline()
        finally:
            ser.timeout = original_timeout

        if raw == b"":
            raise DeviceTimeoutError(
                f"No response from device within {timeout or self.timeout}s"
            )
        return raw.decode("ascii", errors="replace").strip()

    def _raise_for_error(self, line: str) -> None:
        exc_cls = _ERROR_MAP.get(line)
        if exc_cls:
            raise exc_cls(line)

    def _send_and_read(self, command: str, timeout: Optional[float] = None) -> str:
        """
        Send a command and return its immediate one-line acknowledgement.

        Unsolicited lines that may be sitting in the buffer (INFO: notices,
        or an OK:*_COMPLETE from an earlier wait=False move) are skipped so
        they are never mistaken for this command's reply. Completion lines
        are remembered for wait_for_move_complete().
        """
        self._write_line(command)
        while True:
            line = self._read_line(timeout=timeout)
            match = _COMPLETE_RE.match(line)
            if match:
                self._stashed_complete = int(match.group(2))
                continue
            if line.startswith("INFO"):
                continue
            self._raise_for_error(line)
            self.last_reply = line
            return line

    # -- simple commands -------------------------------------------------------

    def ping(self, timeout: Optional[float] = None) -> bool:
        """Send PING and confirm the device answers PONG."""
        line = self._send_and_read("PING", timeout=timeout)
        if line != "PONG":
            raise UnexpectedResponseError(f"Expected PONG, got: {line!r}")
        return True

    def check_connection(self, timeout: Optional[float] = None) -> tuple[bool, str]:
        """
        Non-raising connectivity check. Sends PING and returns ``(ok, message)``.

        If the device does not answer PONG (wrong reply, timeout, or any
        error), ``ok`` is False and ``message`` tells the user to use rewind
        mode (the R / reset command).
        """
        try:
            line = self._send_and_read("PING", timeout=timeout)
        except StepperError:
            return False, REWIND_HINT
        if line != "PONG":
            return False, f"Unexpected reply {line!r}. " + REWIND_HINT
        return True, "PONG"

    def get_status(self, timeout: Optional[float] = None) -> Status:
        """Send STATUS and return the parsed device state."""
        line = self._send_and_read("STATUS", timeout=timeout)
        match = _STATUS_RE.match(line)
        if not match:
            raise UnexpectedResponseError(f"Could not parse STATUS response: {line!r}")
        return Status(
            position=int(match.group("pos")),
            state=MotionState(match.group("state")),
            tracking_enabled=match.group("track") == "1",
            history_count=int(match.group("hist")),
            history_max=int(match.group("histmax")),
            jog_mode=match.group("jog") == "1",
        )

    def stop(self, timeout: Optional[float] = None) -> None:
        """Immediately halt any move and hold the current position."""
        line = self._send_and_read("STOP", timeout=timeout)
        if line != "OK:STOPPED":
            raise UnexpectedResponseError(f"Unexpected STOP response: {line!r}")

    def zero(self, timeout: Optional[float] = None) -> None:
        """Declare the current physical position as home (3 mm) and clear history."""
        line = self._send_and_read("ZERO", timeout=timeout)
        if line != "OK:ZEROED":
            raise UnexpectedResponseError(f"Unexpected ZERO response: {line!r}")

    def track_on(self, timeout: Optional[float] = None) -> None:
        """Enable move-history tracking (clears any existing history)."""
        line = self._send_and_read("T1", timeout=timeout)
        if line != "OK:TRACK_ON":
            raise UnexpectedResponseError(f"Unexpected T1 response: {line!r}")

    def track_off(self, timeout: Optional[float] = None) -> None:
        """Disable move-history tracking (clears any existing history)."""
        line = self._send_and_read("T0", timeout=timeout)
        if line != "OK:TRACK_OFF":
            raise UnexpectedResponseError(f"Unexpected T0 response: {line!r}")

    # -- jog mode ----------------------------------------------------------

    def jog_on(self, timeout: Optional[float] = None) -> None:
        """Enter firmware jog mode (relative F/B stepping)."""
        line = self._send_and_read("JOG", timeout=timeout)
        if line != "OK:JOG_ON":
            raise UnexpectedResponseError(f"Unexpected JOG response: {line!r}")

    def jog_off(self, timeout: Optional[float] = None) -> None:
        """Leave firmware jog mode."""
        line = self._send_and_read("EXIT", timeout=timeout)
        if line != "OK:JOG_OFF":
            raise UnexpectedResponseError(f"Unexpected EXIT response: {line!r}")

    def set_jog_steps(self, steps: int, timeout: Optional[float] = None) -> None:
        """Set the default jog step size used by bare F / B (jog mode only)."""
        if steps <= 0:
            raise BadStepsError("Jog step size must be a positive integer")
        line = self._send_and_read(f"N{int(steps)}", timeout=timeout)
        if line != f"OK:JOG_STEPS={int(steps)}":
            raise UnexpectedResponseError(f"Unexpected N response: {line!r}")

    def jog(
        self,
        steps: Optional[int] = None,
        forward: bool = True,
        wait: bool = True,
        move_timeout: float = DEFAULT_MOVE_TIMEOUT_S,
    ) -> Optional[int]:
        """
        Jog forward/backward by ``steps`` (or the firmware's default jog
        size if None). Jog mode must already be on (see ``jog_on``).
        Returns the final position when ``wait`` is True.
        """
        if steps is not None and steps <= 0:
            raise BadStepsError("Jog steps must be a positive integer")
        cmd = ("F" if forward else "B") + ("" if steps is None else str(int(steps)))
        line = self._send_and_read(cmd)
        if line != "OK:MOVING":
            raise UnexpectedResponseError(f"Unexpected jog response: {line!r}")
        if not wait:
            return None
        return self.wait_for_move_complete(timeout=move_timeout)

    # -- motion commands ---------------------------------------------------

    def move_to(
        self,
        position_mm: int,
        wait: bool = True,
        move_timeout: float = DEFAULT_MOVE_TIMEOUT_S,
    ) -> Optional[int]:
        """
        Move the stage to an absolute position (in mm, matching the
        firmware's numeric command). Values below MIN_POSITION_MM are
        rejected by the firmware with SafetyLimitError.

        If ``wait`` is True (default), blocks until the device reports
        completion and returns the final position. If ``wait`` is False,
        returns None immediately after the move is accepted and started;
        call ``wait_for_move_complete()`` later to collect the result.
        """
        if position_mm < MIN_POSITION_MM:
            # Fail fast client-side; the firmware would reject this anyway.
            raise SafetyLimitError(
                f"Requested position {position_mm} is below the minimum "
                f"of {MIN_POSITION_MM}mm"
            )

        line = self._send_and_read(str(int(position_mm)))

        if line == "OK:ALREADY_THERE":
            return self.get_status().position if wait else None
        if line != "OK:MOVING":
            raise UnexpectedResponseError(f"Unexpected move response: {line!r}")

        if not wait:
            return None
        return self.wait_for_move_complete(timeout=move_timeout)

    def reset(
        self,
        wait: bool = True,
        move_timeout: float = DEFAULT_MOVE_TIMEOUT_S,
    ) -> Optional[int]:
        """
        Send the R (reset) command. Behaviour depends on tracking state:
          - tracking on, net movement pending: rewinds (async) -> OK:RESETTING
          - tracking on, no net movement: OK:RESET_NOOP
          - tracking off: disables the driver immediately -> OK:RESET

        Returns the final position if ``wait`` is True and a rewind
        occurred; otherwise returns None.
        """
        line = self._send_and_read("R")

        if line in ("OK:RESET_NOOP", "OK:RESET"):
            return None
        if line != "OK:RESETTING":
            raise UnexpectedResponseError(f"Unexpected R response: {line!r}")

        if not wait:
            return None
        return self.wait_for_move_complete(timeout=move_timeout)

    def wait_for_move_complete(self, timeout: float = DEFAULT_MOVE_TIMEOUT_S) -> int:
        """
        Block until an unsolicited OK:MOVE_COMPLETE / OK:RESET_COMPLETE
        line arrives, and return the reported position.
        """
        if self._stashed_complete is not None:
            pos, self._stashed_complete = self._stashed_complete, None
            return pos

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DeviceTimeoutError(
                    f"Move did not complete within {timeout}s"
                )
            try:
                line = self._read_line(timeout=min(remaining, 1.0))
            except DeviceTimeoutError:
                continue  # per-read timeout; the overall deadline decides
            if not line:
                continue
            match = _COMPLETE_RE.match(line)
            if match:
                return int(match.group(2))
            # Ignore/skip any other unsolicited lines (e.g. INFO: lines)
            # rather than treating them as fatal.

    def wait_until_idle(self, poll_interval: float = 0.25, timeout: float = DEFAULT_MOVE_TIMEOUT_S) -> Status:
        """
        Poll STATUS until the device reports IDLE. Useful as a fallback
        when the completion line may have been missed, or after issuing
        commands with wait=False.
        """
        deadline = time.monotonic() + timeout
        while True:
            status = self.get_status()
            if status.state == MotionState.IDLE:
                return status
            if time.monotonic() >= deadline:
                raise DeviceTimeoutError(f"Device did not become IDLE within {timeout}s")
            time.sleep(poll_interval)

    # -- passthrough ---------------------------------------------------------

    def send_raw(
        self,
        command: str,
        timeout: Optional[float] = None,
        idle_gap: float = DEFAULT_IDLE_GAP_S,
        move_timeout: float = DEFAULT_MOVE_TIMEOUT_S,
    ) -> List[str]:
        """
        Send an arbitrary command line and return ALL lines the device
        replies with, as a list (errors are not raised). Intended for
        interactive/CLI use.

        * The first line is the immediate acknowledgement (DeviceTimeoutError
          if nothing arrives within ``timeout``).
        * If that acknowledgement starts a motion (OK:MOVING / OK:RESETTING),
          reading continues until the OK:*_COMPLETE line arrives (or
          ``move_timeout`` passes), so both lines are returned.
        * Otherwise any further lines are collected until the device has been
          silent for ``idle_gap`` seconds (e.g. INFO: notices).
        """
        self._write_line(command)
        lines: List[str] = [self._read_line(timeout=timeout)]

        if lines[0] in ("OK:MOVING", "OK:RESETTING"):
            deadline = time.monotonic() + move_timeout
            while time.monotonic() < deadline:
                try:
                    line = self._read_line(timeout=min(1.0, deadline - time.monotonic()))
                except DeviceTimeoutError:
                    continue
                lines.append(line)
                if _COMPLETE_RE.match(line):
                    break
            return lines

        while True:
            try:
                lines.append(self._read_line(timeout=idle_gap))
            except DeviceTimeoutError:
                return lines
