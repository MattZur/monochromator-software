import sys
sys.path.append("/home/f71225bp/Documents/Monochromator/Monochromator_control_code")
import lib.Xeryon.Xeryon as Xeryon
from lib.Xeryon.Xeryon import Stage, Units
import threading
import atexit
import traceback
userInputZeroVal = 0 #this is the set zero position that the user can set in the program
atPhysicalLimit  = False
controller = None
Mot = None
displayedPosition = None


def init():

    global controller
    global Mot
    controller  = Xeryon.Xeryon("/dev/ttyACM0", 115200)          
    Mot       = controller.addAxis(Stage.XRTU_30_49, "X") #keep this as XRTU_30_49 since this is the specific stage in the mchrom
    controller.start()
    Mot.findIndex()
    Mot.setUnits(Units.deg)

def userdefined_current_position():
    return Mot.getEPOS()-userInputZeroVal


def step(size):
    current = Mot.getEPOS()
    target = current + size

    # Check limits (-15 to 15)
    if target < -15:
        print("Would exceed left limit → scanning safely")
        Mot.startScan(-1, untilLimit=True)
        return

    elif target > 15:
        print("Would exceed right limit → scanning safely")
        Mot.startScan(1, untilLimit=True)
        return

    # Safe to step
    if size < 0:
        if not Mot.isAtLeftEnd():
            Mot.step(size)
        else:
            print("AT LEFT LIMIT")

    elif size > 0:
        if not Mot.isAtRightEnd():
            Mot.step(size)
        else:
            print("AT RIGHT LIMIT")

def goTo(value):
    if value <-15 or value > 15:
        print("Invalid position to move to")
        return
    else:
        Mot.setDPOS(value)

def goToLimit(value):
    if value<0:
        Mot.startScan(-1, untilLimit=True)
    elif value >0:
        Mot.startScan(1, untilLimit=True)


def monitor_position():
    global displayedPosition
    global atPhysicalLimit

    while True:
        displayedPosition = userdefined_current_position()

        if Mot.isAtLeftEnd() or Mot.isAtRightEnd():
            atPhysicalLimit = True
        else:
            atPhysicalLimit = False


        print(f"Position:  {displayedPosition:.2f} At Limit:  {atPhysicalLimit}")
        time.sleep(0.1)


def cleanup():
    print("cleaning up")
    if controller:
        controller.stop()

try:
    init()
    # code to do stuff
except Exception as e:
    print("it broke")
    print(e)
    traceback.format_exc()
finally:
    atexit.register(cleanup)
