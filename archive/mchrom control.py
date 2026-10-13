from Xeryon import *
import threading

controller  = Xeryon("COM5", 115200)          
Mot       = controller.addAxis(Stage.XRTU_30_49, "X") #keep this as XRTU_30_49 since this is the specific stage in the mchrom
controller.start()
Mot.findIndex()
Mot.setUnits(Units.deg)

userInputZeroVal = -15 #this is the set zero position that the user can set in the program
atPhysicalLimit  = False

def userdefined_current_position():
    return Mot.getEPOS()-userInputZeroVal

displayedPosition = userdefined_current_position()

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

thread = threading.Thread(target=monitor_position, daemon=True)
thread.start()


########### MAIN CODE HERE
goToLimit(-1)
for i in range(0,10):
    step(1)
    Mot.setDPOS(Mot.getEPOS())
    time.sleep(0.1)

goTo(3)


###########

controller.stop()
