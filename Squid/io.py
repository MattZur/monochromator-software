import os
import ast
import configparser


def read_config_file(file_path  :  str) -> dict:
    '''
    This function collects the relevant information from `config.conf` and passes it to the pack in which it is used.
    Example:
    >> squid acq config.conf

    Parameters
    ----------

    file_path (str)  :  Path to config file

    Returns
    -------

    arg_dict (dict)  :  Dictionary of relevant arguments for the pack
    '''
    # setup config parser
    config = configparser.ConfigParser()

    if not os.path.exists(file_path):
        raise FileNotFoundError(2, 'No such config file', file_path)


    # read in arguments, require the required ones
    config.read(file_path)
    arg_dict = {}
    for section in config.sections():
        for key in config[section]:
            # the config should be written in such a way that the python evaluator
            # can determine its type
            #
            # we can setup stricter rules at some other time
            arg_dict[key] = ast.literal_eval(config[section][key])

    return arg_dict