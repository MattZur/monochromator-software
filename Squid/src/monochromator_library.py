"""
Monochromator control (Xeryon XRTU_30_49 rotary stage, library v1.88).

The stage is connected the first time
it is needed (or explicitly with `init()` / `reset()`), 
and disconnected automatically at exit.

Typical use at the start of a measurement:

    mchrom.reset()        # connect if needed, otherwise recover and re-index
    mchrom.goTo(4.3)      # blocks until the stage is there, or raises
"""

import atexit
import sys
import threading
import time
import traceback
from pathlib import Path

# The Xeryon library lives in <project root>/lib; this file is in <project root>/src
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import lib.Xeryon.Xeryon as Xeryon  # noqa: E402

# ── Settings ──────────────────────────────────────────────────────────────────
PORT = "/dev/ttyACM0"
BAUD = 115200
AXIS = "X"

# Path to the Xeryon settings file. None = the library's default, which is
# "settings_default.txt" in the *current working directory* (if absent, nothing is sent).
SETTINGS_FILE = None

MIN_ANGLE, MAX_ANGLE = -15.0, 15.0   # travel limits, degrees
MAX_RETRIES = 2                      # reset-and-retry attempts if a move fails

# ── State (names kept from the original script) ───────────────────────────────
userInputZeroVal  = 0      # user-set zero position, subtracted by userdefined_current_position()
atPhysicalLimit   = False
displayedPosition = None
controller        = None
Mot               = None


class MonochromatorError(RuntimeError):
    """The stage could not be brought to the requested position."""


# ── Connection ────────────────────────────────────────────────────────────────

def init() -> None:
    """Connect to the stage and find its index. Does nothing if already connected."""
    global controller, Mot
    if controller is not None:
        return

    controller = Xeryon.Xeryon(PORT, BAUD)
    try:
        # keep as XRTU_30_49: this is the specific stage in the mchrom
        # (rotary stages already default to degrees, so no setUnits needed)
        Mot = controller.addAxis(Xeryon.Stage.XRTU_30_49, AXIS)
        controller.start(external_settings_default=SETTINGS_FILE)
        if not Mot.findIndex(forceWaiting=True):
            raise MonochromatorError("Could not find the stage index.")
    except Exception:
        cleanup()
        raise


def cleanup() -> None:
    """Stop the controller and release the serial port. Safe to call repeatedly."""
    global controller, Mot
    if controller is None:
        return
    print("cleaning up")
    try:
        controller.stop()
    except Exception:
        traceback.print_exc()
    finally:
        controller = Mot = None


atexit.register(cleanup)


def _ensure_connected() -> None:
    if controller is None:
        init()


def reset(hard: bool = False) -> None:
    """
    Put the stage in a known state. Call at the start of a run, or after a failed move.

    Not connected -> connect (which also finds the index).
    Connected     -> stop any scan, send ENBL=1 (clears the thermal / error-limit /
                     safety-timeout lockouts the Xeryon library asks for), re-find the index.
    If the index can't be found, or `hard=True`, drop the connection and reconnect
    from scratch (which also sends RSET and reloads the settings).
    The user zero (`userInputZeroVal`) is left untouched.
    """
    if controller is None:
        init()
        return

    if not hard:
        Mot.stopScan()
        Mot.sendCommand("ENBL=1")
        if Mot.findIndex(forceWaiting=True):
            return
        print("[WARNING] Soft reset could not find the index, reconnecting.")

    cleanup()
    time.sleep(1.0)                       # let the serial thread release the port
    init()


# ── Position ──────────────────────────────────────────────────────────────────

def get_position() -> float:
    """Encoder position in degrees (absolute, ignores the user zero)."""
    _ensure_connected()
    return Mot.getEPOS()


def userdefined_current_position() -> float:
    """Encoder position relative to the user-set zero."""
    return get_position() - userInputZeroVal


def goTo(value: float, retries: int = MAX_RETRIES) -> None:
    """
    Move to `value` degrees. Blocks until the controller reports the position reached
    (EPOS within its PTO2 tolerance and the position-reached flag set).

    setDPOS returns False when the move fails (end stop hit, error limit, safety
    timeouts, amplifier error). On failure the stage is reset (soft first, then a
    full reconnect) and the move retried, up to `retries` times.
    Raises ValueError for out-of-range targets and MonochromatorError if the
    position still can't be reached.
    """
    if not MIN_ANGLE <= value <= MAX_ANGLE:
        raise ValueError(f"{value} deg is outside the travel range [{MIN_ANGLE}, {MAX_ANGLE}]")

    _ensure_connected()
    for attempt in range(retries + 1):
        if Mot.setDPOS(value):
            return

        print(f"[WARNING] Did not reach {value} deg (at {Mot.getEPOS():.4f}), "
              f"attempt {attempt + 1}/{retries + 1}")
        if attempt < retries:
            reset(hard=attempt > 0)

    raise MonochromatorError(
        f"Could not reach {value} deg after {retries + 1} attempts (at {Mot.getEPOS():.4f}).")


def goToLimit(direction: float) -> None:
    """Scan until a physical limit: negative -> left, positive -> right."""
    _ensure_connected()
    if direction < 0:
        Mot.startScan(-1, untilLimit=True)
    elif direction > 0:
        Mot.startScan(1, untilLimit=True)


def step(size: float) -> None:
    """Step by `size` degrees; if that would pass a travel limit, scan to the limit instead."""
    if size == 0:
        return
    _ensure_connected()

    target = Mot.getEPOS() + size
    if target < MIN_ANGLE or target > MAX_ANGLE:
        print("Would exceed limit → scanning safely")
        goToLimit(-1 if target < MIN_ANGLE else 1)
    elif size < 0 and Mot.isAtLeftEnd():
        print("AT LEFT LIMIT")
    elif size > 0 and Mot.isAtRightEnd():
        print("AT RIGHT LIMIT")
    else:
        Mot.step(size)


# ── Monitoring ────────────────────────────────────────────────────────────────

def monitor_position(stop_event: threading.Event | None = None, interval: float = 0.1) -> None:
    """
    Keep `displayedPosition` / `atPhysicalLimit` up to date and print them.
    Blocks until `stop_event` is set, so normally run in a thread:

        stop = threading.Event()
        threading.Thread(target=mchrom.monitor_position, args=(stop,), daemon=True).start()
    """
    global displayedPosition, atPhysicalLimit
    _ensure_connected()
    stop_event = stop_event or threading.Event()

    while not stop_event.is_set():
        displayedPosition = userdefined_current_position()
        atPhysicalLimit = Mot.isAtLeftEnd() or Mot.isAtRightEnd()
        print(f"Position: {displayedPosition:.2f}  At Limit: {atPhysicalLimit}")
        stop_event.wait(interval)