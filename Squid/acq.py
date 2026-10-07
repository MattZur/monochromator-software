import os
import sys
import traceback

from io                import read_config_file
from stability import stability
import squid

def acq(config_file):
    print("Starting the acquisition pack...")

    # take full path
    full_path = os.path.expandvars(config_file)

    conf_dict = read_config_file(full_path)
    # check the method implemented, currently just process
    try:
        match conf_dict.pop('acquisition'):
            case 'stabilty':
            # removing the first two components so that the other arguments are passed correctly
                match conf_dict.pop('keithley_model'):
                    case 6487:
                        stability(**conf_dict)
                    case other:
                        raise RuntimeError(f"keithley_model {other} acquisition isn't currently implemented.")
            case 'spectrum':
                match conf_dict.pop('keithley_model'):
                    case 6487:
                        squid.main(**conf_dict)
                    case other:
                        raise RuntimeError(f"keithley_model {other} acquisition isn't currently implemented.")
            case other:
                raise RuntimeError(f"acquisition of {other} not currently implemented.")
    except KeyError as e:
        print(f"\nError in the configuration file, incorrect or missing argument: {e} \n")
        traceback.print_exc()
        sys.exit(2)