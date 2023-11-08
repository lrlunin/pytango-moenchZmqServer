from .testserver_moench import MoenchZmqTestServer

# unfortunately we are not able to call the run_server of the MoenchZmqServer class directly
# because even in case of static functions we are not able to call them if they belong to the class
# https://stackoverflow.com/questions/60420533/how-to-add-console-script-entry-point-to-setup-py-that-call-a-class-function-pyt
# https://setuptools.readthedocs.io/en/stable/setuptools.html#automatic-script-creation

# therefore a __main__.py file is required
# this is considered as a normal practice because even an official pytango device of tango developer used this method


def main():
    import sys
    import tango.server

    args = ["MoenchZmqTestServer"] + sys.argv[1:]
    tango.server.run((MoenchZmqTestServer,), args=args)
