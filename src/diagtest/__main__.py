#!/usr/bin/env python3
''' Allow running diagtest as module: `python -m diagtest` '''

from diagtest import main

if __name__ == "__main__":
    # click edits the parameters for this call, however pylint cannot possibly know about this
    main() # pylint: disable=no-value-for-parameter
