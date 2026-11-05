import os
import sys
import traceback

from packs.core.io import read_config_file
from packs.ana.ana_utils import stability_analysis
from packs.ana.ana_utils import stability_analysis_volatility


def acq(config_file):
    print("Starting the analysis pack...")

    # Take the full path
    full_path = os.path.expandvars(config_file)

    conf_dict = read_config_file(full_path)
    # Check the analysis method implemented, currently just process
    try:
        match conf_dict.pop('analysis'):
            case 'stabilty_analysis':
                print('Running Stability Report')
                stability_analysis(**conf_dict)
            case 'stability_analysis_volatility':
                print('Running Volatility Report...')
                stability_analysis_volatility(**conf_dict)
            case other:
                raise RuntimeError(f"analysis of {other} is not currently implemented.")
    except KeyError as e:
        print(f"\nError in the configuration file, incorrect or missing argument: {e} \n")
        traceback.print_exc()
        sys.exit(2)
