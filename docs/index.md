# **Welcome to MOENCH ZMQ TangoDS documentation!**

This documentation describes the custom implementation of the ZMQ server for the [MOENCH detector](https://www.psi.ch/en/lxn/moench) made in Paul Scherrer Institut in Villigen, Switzerland.

The original version of the software for MOENCH detectors is published in the [SLS detector group repository](https://github.com/slsdetectorgroup/slsDetectorPackage) and described in the corresponding [documentation](https://slsdetectorgroup.github.io/devdoc/). 

This version is done especially for MOENCH03 prototype and can be possibly adapted for the next revisions of MOENCH family detectors (see [Detector reference](detector.md)).

The core features of this project are:

1. tight integration of the processing software with the tango-controls framework
2. pure python codebase
3. unified interface for any kind of processing algorithm
4. easier modification and adjustment of the software

The current project, written in Python, is maintained by Leonid Lunin at the Max-Born-Institute, Berlin, Germany.