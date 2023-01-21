# pytango-moenchZmqServer

## Description

This device connects to MOENCH detector and allows to control the state of the detector.

## Getting Started

### Dependencies
* `python >=3.8`
* `pytango >=9`
* `pyzmq`

## Start
Please note:
* a server starts with a virtual detector, when the `IS_VIRTUAL_DETECTOR` boolean property of `MoenchDetectorControl` tango device has been assigned to `True`. Otherwise a real detector must be turned on.
* As the `slsReceiver` executable must be run with sudo rights, the active user must have sudo rights. It is also necessary to provide the password for this user in the device tango property `ROOT_PASSWORD`. 

### using tango-starter (the most preferable way)
1. Choose a `moench` starter from `astor` dropdown menu.
2. Start the `MoenchDetectorControl` server in a common way.

### manually
Start servers via commands' sequence:
* `cd pytango-moenchdetector`
* `./MoenchDetectorControl moench [-v4]`
  
Please note that `MoenchDetectorControl` is nothing but a simlink to main .py file. 

## Help

Any additional information according to slsDetector, its python API or pytango references can be found under the links:

* [slsDetectorGroup wiki](https://slsdetectorgroup.github.io/devdoc/pydetector.html)
* [pytango reference](https://pytango.readthedocs.io/en/stable/)

## Authors

Contributors names and contact info

[@lrlunin](https://github.com/lrlunin)

[@dschick](https://github.com/dschick)
## Version History


## License

This project is licensed under the MIT License - see the LICENSE.md file for details

## Acknowledgments

Inspiration, code snippets, etc.
* Daniel Schick
