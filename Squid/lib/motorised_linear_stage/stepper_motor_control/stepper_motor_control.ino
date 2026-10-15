/*
 * Linear Stage Stepper Motor Controller
 * ======================================
 *
 * Drives a single stepper motor (via a STEP/DIR/ENABLE driver, e.g. DM542-style)
 * to position a linear stage, with serial-command control and optional move
 * history tracking for auto-rewind.
 *
 * HARDWARE
 *   pinPUL (D2) - Step/pulse output
 *   pinDIR (D4) - Direction output (HIGH = forward)
 *   pinENA (D6) - Driver enable (HIGH = enabled/holding, LOW = disabled/free)
 *
 * MOTION MODEL
 *   Position is tracked in full steps (STEPS_PER_REV = 320 steps/rev, 0.5 mm/step)
 *   as a signed step count (posicionActual), forward = positive.
 *   Step pulses are generated non-blocking in stepStateMachine(), toggling PUL
 *   every STEP_HALF_PERIOD_US (1500 us) and counting a step complete on the
 *   falling edge. A DIR_SETTLE_US (500 us) delay is enforced after any
 *   direction/enable change before stepping begins.
 *
 *   Numeric commands are interpreted as a target position in whole
 *   revolutions ("mm"), converted to steps and offset by SAFETY_OFFSET
 *   (960 steps) to keep the stage within a safe travel range. Requests below
 *   3 mm are rejected (ERR:PAST_SAFETY_LIMIT).
 *
 * SERIAL COMMANDS (9600 baud, newline-terminated, case-insensitive)
 *   <integer >= 3>  Move to absolute position (mm), e.g. "50", max 100mm
 *   R               Reset: if tracking is on, rewinds by the net of all
 *                   tracked moves since T1; otherwise just disables the driver
 *   T1 / T0         Enable / disable move history tracking (clears history)
 *   STOP            Immediately halt any move and hold position (driver enabled)
 *   STATUS          Report position, state, tracking flag, and history usage
 *   PING            Connectivity check -> "PONG"
 *   ZERO            Declare the current physical position as the 3 mm home
 *                   position (use after repositioning by hand / manual_reset.py)
 *   JOG             Enter jog mode (only when idle) -> "OK:JOG_ON"
 *   EXIT            Leave jog mode -> "OK:JOG_OFF"
 *
 * JOG MODE (relative stepping)
 *   While jog mode is on, numeric position commands are rejected
 *   (ERR:JOG_MODE) and these commands are available instead:
 *     F        Move forward by the current jog step size
 *     B        Move backward by the current jog step size
 *     F<n>     Move forward  exactly <n> steps, e.g. "F50"
 *     B<n>     Move backward exactly <n> steps, e.g. "B50"
 *     N<n>     Set the default jog step size to <n> steps -> "OK:JOG_STEPS=<n>"
 *   PING, STATUS, STOP, R, T1, T0 and EXIT keep working. Jog moves are
 *   tracked like normal moves when tracking is on (so R can rewind them) and
 *   are refused (ERR:PAST_SAFETY_LIMIT) if they would leave the allowed
 *   travel range (-10 mm .. 100 mm).
 *
 * PERSISTENT STATE (EEPROM)
 *   Opening the serial port resets most Arduino boards, which used to wipe the
 *   position, tracking flag and move history on every new connection (so a
 *   separate "R" run had nothing to rewind). These are now saved to EEPROM
 *   after every state change and restored at boot. If the board is reset or
 *   loses power mid-move the saved position is uncertain: a warning is printed
 *   at boot; reposition and send ZERO.
 *
 * MOVE HISTORY
 *   When tracking is enabled, each trackable move's signed step count is
 *   stored in history[] (capped at MAX_HISTORY = 20 entries). R sums these
 *   and drives a single rewind move back to the pre-tracking net position.
 *
 * SAFETY NOTES
 *   - Do not move the stage manually, even with power off.
 *   - On startup, verify the physical position is between 2 mm and 3 mm;
 *     if not, use manual_reset.py instead of powering through firmware moves.
 *   - The driver is disabled (LOW) at idle/reset-without-tracking to avoid
 *     holding torque when not needed, and re-enabled (HIGH) during moves
 *     and after STOP to hold the current position.
 */

#include <EEPROM.h>

const int pinPUL = 2;
const int pinDIR = 4;
const int pinENA = 6;

const long SAFETY_OFFSET = 960;
const long STEPS_PER_REV = 320;              // full step, 0.5mm
const unsigned int STEP_HALF_PERIOD_US = 1500; // time HIGH and time LOW per pulse edge
const unsigned long DIR_SETTLE_US = 500;       // settle time after changing direction

const uint8_t MAX_HISTORY = 20; // hard cap on tracked moves, bounds RAM use
long history[MAX_HISTORY];      // signed steps per tracked move (+forward/-backward)
uint8_t historyCount = 0;
bool historyFull = false;
bool trackingEnabled = false;

long posicionActual = 0; // net position in steps, forward = positive

// Travel limits in steps (same reference frame as posicionActual)
const long MIN_POS_STEPS = (-10L * STEPS_PER_REV) - SAFETY_OFFSET;
const long MAX_POS_STEPS = (100L * STEPS_PER_REV) - SAFETY_OFFSET;

// Jog mode
const long DEFAULT_JOG_STEPS = 16;
const long MAX_JOG_STEPS = 100000;
bool jogMode = false;
long jogSteps = DEFAULT_JOG_STEPS;

bool lastMoveTracked = false; // true if the move in progress added a history entry

// ---------- Persistent state (EEPROM) ----------
struct SavedState {
  uint16_t magic;
  long pos;
  uint8_t tracking;
  uint8_t count;
  uint8_t moving;      // 1 while a move is in progress (position then uncertain)
  long hist[MAX_HISTORY];
};
const uint16_t STATE_MAGIC = 0x5354;

void saveState(bool moving) {
  SavedState s;
  s.magic = STATE_MAGIC;
  s.pos = posicionActual;
  s.tracking = trackingEnabled ? 1 : 0;
  s.count = historyCount;
  s.moving = moving ? 1 : 0;
  for (uint8_t i = 0; i < MAX_HISTORY; i++) s.hist[i] = (i < historyCount) ? history[i] : 0;
  EEPROM.put(0, s); // put() only rewrites bytes that changed
}

// Returns 0 = nothing saved, 1 = restored, 2 = restored but position uncertain
uint8_t loadState() {
  SavedState s;
  EEPROM.get(0, s);
  if (s.magic != STATE_MAGIC || s.count > MAX_HISTORY ||
      s.pos < MIN_POS_STEPS || s.pos > MAX_POS_STEPS) return 0;
  posicionActual = s.pos;
  trackingEnabled = (s.tracking == 1);
  historyCount = s.count;
  for (uint8_t i = 0; i < historyCount; i++) history[i] = s.hist[i];
  return s.moving ? 2 : 1;
}

enum MotionState { IDLE, MOVING, REWINDING };
MotionState state = IDLE;

long stepsRemaining = 0;
bool moveDirForward = true;
bool pulseHigh = false;
bool waitingForSettle = false;
unsigned long dirChangedAtUs = 0;
unsigned long lastEdgeUs = 0;

const uint8_t CMD_BUF_LEN = 16;
char cmdBuf[CMD_BUF_LEN];
uint8_t cmdLen = 0;

void setup() {
  pinMode(pinPUL, OUTPUT);
  pinMode(pinDIR, OUTPUT);
  pinMode(pinENA, OUTPUT);
  digitalWrite(pinPUL, LOW);
  digitalWrite(pinENA, LOW); // disabled until a move is requested

  Serial.begin(9600);
  uint8_t restored = loadState();
  Serial.println(F("READY"));
  Serial.println(F("WARNING: Do not attempt to move the stage manually even with the power off"));
  if (restored == 0) {
    Serial.println(F("WARNING: Check that the position when connecting is between 2mm and 3mm"));
    Serial.println(F("INFO: If it's not, then quit and use the manual_reset.py program"));
  } else {
    Serial.print(F("INFO:STATE_RESTORED POS="));
    Serial.print(posicionActual);
    Serial.print(F(" TRACK="));
    Serial.print(trackingEnabled ? 1 : 0);
    Serial.print(F(" HIST="));
    Serial.println(historyCount);
    if (restored == 2) {
      Serial.println(F("WARNING: Board was reset during a move - position uncertain. Reposition and send ZERO"));
    }
  }
  Serial.println(F("INFO: Commands: Position(integer in mm), R, T1, T0, STOP, STATUS, PING, ZERO, JOG"));
  Serial.println(F("INFO: Jog mode: F[n], B[n], N<n>, EXIT"));
}

void loop() {
  readSerial();
  stepStateMachine();
}

// ---------- Serial input ----------

void readSerial() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdLen > 0) {
        cmdBuf[cmdLen] = '\0';
        processCommand(cmdBuf);
        cmdLen = 0;
      }
    } else if (cmdLen < CMD_BUF_LEN - 1) {
      cmdBuf[cmdLen++] = c;
    } else {
      // Line too long for our buffer - drop it rather than overflow.
      cmdLen = 0;
      Serial.println(F("ERR:LINE_TOO_LONG"));
    }
  }
}

void processCommand(char *raw) {
  for (uint8_t i = 0; raw[i] != '\0'; i++) raw[i] = toupper(raw[i]);

  if (strcmp(raw, "PING") == 0) {
    Serial.println(F("PONG"));
    return;
  }

  if (strcmp(raw, "STATUS") == 0) {
    printStatus();
    return;
  }

  if (strcmp(raw, "STOP") == 0) {
    // If a tracked move is cut short, record only the steps actually taken so
    // a later rewind doesn't overshoot.
    if (state == MOVING && lastMoveTracked && historyCount > 0 && stepsRemaining > 0) {
      long &h = history[historyCount - 1];
      h = (h > 0) ? (h - stepsRemaining) : (h + stepsRemaining);
    }
    stepsRemaining = 0;
    waitingForSettle = false;
    if (state != IDLE) {
      state = IDLE;
      digitalWrite(pinENA, HIGH); // hold current position rather than free-spin
    }
    saveState(false);
    Serial.println(F("OK:STOPPED"));
    return;
  }

  if (strcmp(raw, "ZERO") == 0) {
    if (state != IDLE) { Serial.println(F("ERR:BUSY")); return; }
    posicionActual = 0;
    historyCount = 0;
    historyFull = false;
    saveState(false);
    Serial.println(F("OK:ZEROED"));
    return;
  }

  if (strcmp(raw, "JOG") == 0) {
    if (state != IDLE) { Serial.println(F("ERR:BUSY")); return; }
    jogMode = true;
    Serial.println(F("OK:JOG_ON"));
    return;
  }

  if (strcmp(raw, "EXIT") == 0) {
    if (state != IDLE) { Serial.println(F("ERR:BUSY")); return; }
    jogMode = false;
    Serial.println(F("OK:JOG_OFF"));
    return;
  }

  if (strcmp(raw, "T1") == 0) {
    if (state != IDLE) { Serial.println(F("ERR:BUSY")); return; }
    trackingEnabled = true;
    historyCount = 0;
    historyFull = false;
    saveState(false);
    Serial.println(F("OK:TRACK_ON"));
    return;
  }

  if (strcmp(raw, "T0") == 0) {
    if (state != IDLE) { Serial.println(F("ERR:BUSY")); return; }
    trackingEnabled = false;
    historyCount = 0;
    historyFull = false;
    saveState(false);
    Serial.println(F("OK:TRACK_OFF"));
    return;
  }

  if (strcmp(raw, "R") == 0) {
    handleReset();
    return;
  }

if (jogMode) {
    handleJogCommand(raw);
    return;
  }

char *endPtr;
  long revs = strtol(raw, &endPtr, 10);

if (endPtr != raw && *endPtr == '\0') {  // valid full numeric string
    if (revs < -10) {
      Serial.println(F("ERR:PAST_SAFETY_LIMIT"));
      return;
    }

    long targetPos = (revs * STEPS_PER_REV) - SAFETY_OFFSET;
    long delta = targetPos - posicionActual;

    if (delta == 0) {
      Serial.println(F("OK:ALREADY_THERE"));
      return;
    }

    bool dirForward = (delta > 0);
    long steps = labs(delta);

    startMove(steps, dirForward, true);
    return;
  }

Serial.println(F("ERR:UNKNOWN"));
}

// ---------- Jog mode ----------

// Parses "<digits>" into *out. Returns false if empty, non-numeric or <= 0.
bool parsePositiveLong(const char *s, long *out) {
  char *endPtr;
  long v = strtol(s, &endPtr, 10);
  if (endPtr == s || *endPtr != '\0' || v <= 0 || v > MAX_JOG_STEPS) return false;
  *out = v;
  return true;
}

void handleJogCommand(char *raw) {
  char cmd = raw[0];
  const char *arg = raw + 1;

  if (cmd == 'N') {
    long n;
    if (!parsePositiveLong(arg, &n)) { Serial.println(F("ERR:BAD_STEPS")); return; }
    jogSteps = n;
    Serial.print(F("OK:JOG_STEPS="));
    Serial.println(jogSteps);
    return;
  }

  if (cmd == 'F' || cmd == 'B') {
    long steps = jogSteps;
    if (*arg != '\0' && !parsePositiveLong(arg, &steps)) {
      Serial.println(F("ERR:BAD_STEPS"));
      return;
    }
    if (state != IDLE) { Serial.println(F("ERR:BUSY")); return; }

    bool dirForward = (cmd == 'F');
    long target = posicionActual + (dirForward ? steps : -steps);
    if (target < MIN_POS_STEPS || target > MAX_POS_STEPS) {
      Serial.println(F("ERR:PAST_SAFETY_LIMIT"));
      return;
    }
    startMove(steps, dirForward, true);
    return;
  }

  // A plain number while jogging is almost certainly a mistake.
  char *endPtr;
  strtol(raw, &endPtr, 10);
  if (endPtr != raw && *endPtr == '\0') {
    Serial.println(F("ERR:JOG_MODE"));
  } else {
    Serial.println(F("ERR:UNKNOWN"));
  }
}

// ---------- Move handling ----------

void startMove(long steps, bool dirForward, bool trackable) {
  if (state != IDLE) {
    Serial.println(F("ERR:BUSY"));
    return;
  }

  digitalWrite(pinENA, HIGH);
  digitalWrite(pinDIR, dirForward ? HIGH : LOW);

  stepsRemaining = steps;
  moveDirForward = dirForward;
  pulseHigh = false;
  waitingForSettle = true;
  dirChangedAtUs = micros();
  state = MOVING;
  lastMoveTracked = false;

  if (trackable && trackingEnabled) {
    if (historyCount < MAX_HISTORY) {
      history[historyCount++] = dirForward ? steps : -steps;
      lastMoveTracked = true;
    } else if (!historyFull) {
      historyFull = true;
      Serial.println(F("INFO:HISTORY_FULL_NOT_TRACKED"));
    }
  }

  saveState(true);
  Serial.println(F("OK:MOVING"));
}

void handleReset() {
  if (state != IDLE) {
    Serial.println(F("ERR:BUSY"));
    return;
  }

  if (trackingEnabled && historyCount > 0) {
    long net = 0;
    for (uint8_t i = 0; i < historyCount; i++) net += history[i];

    historyCount = 0;
    historyFull = false;

    if (net == 0) {
      saveState(false);
      Serial.println(F("OK:RESET_NOOP"));
      return;
    }

    digitalWrite(pinENA, HIGH);
    digitalWrite(pinDIR, (net < 0) ? HIGH : LOW); // rewind = opposite of net direction
    stepsRemaining = abs(net);
    moveDirForward = (net < 0); // true means we'll be stepping "forward" internally
    pulseHigh = false;
    waitingForSettle = true;
    dirChangedAtUs = micros();
    state = REWINDING;
    lastMoveTracked = false;
    saveState(true);
    Serial.println(F("OK:RESETTING"));
  } else {
    historyCount = 0;
    historyFull = false;
    digitalWrite(pinENA, LOW);
    saveState(false);
    Serial.println(F("OK:RESET"));
  }
}

void stepStateMachine() {
  if (state == IDLE) return;

  if (waitingForSettle) {
    if (micros() - dirChangedAtUs < DIR_SETTLE_US) return;
    waitingForSettle = false;
    lastEdgeUs = micros();
  }

  if (stepsRemaining <= 0) {
    bool wasReset = (state == REWINDING);
    state = IDLE;
    digitalWrite(pinENA, LOW); // release driver after any move, reset or not
    saveState(false);
    if (wasReset) {
      Serial.print(F("OK:RESET_COMPLETE POS="));
    } else {
      Serial.print(F("OK:MOVE_COMPLETE POS="));
    }
    Serial.println(posicionActual);
    return;
  }

  unsigned long now = micros();
  if (now - lastEdgeUs >= STEP_HALF_PERIOD_US) {
    lastEdgeUs = now;
    pulseHigh = !pulseHigh;
    digitalWrite(pinPUL, pulseHigh ? HIGH : LOW);
    if (!pulseHigh) { // completed one full pulse on the falling edge
      stepsRemaining--;
      posicionActual += moveDirForward ? 1 : -1;
    }
  }
}

// ---------- Status ----------

void printStatus() {
  Serial.print(F("STATUS:POS="));
  Serial.print(posicionActual);
  Serial.print(F(",STATE="));
  switch (state) {
    case IDLE: Serial.print(F("IDLE")); break;
    case MOVING: Serial.print(F("MOVING")); break;
    case REWINDING: Serial.print(F("REWINDING")); break;
  }
  Serial.print(F(",TRACK="));
  Serial.print(trackingEnabled ? 1 : 0);
  Serial.print(F(",HIST="));
  Serial.print(historyCount);
  Serial.print(F("/"));
  Serial.print(MAX_HISTORY);
  Serial.print(F(",JOG="));
  Serial.println(jogMode ? 1 : 0);
}
