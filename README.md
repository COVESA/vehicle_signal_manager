vehicle_signal_manager
----------------------
Vehicle Signal Manager to read, transform, and emit VSS signals based on
configurable rules.

Where to get
------------
Development is all happening upstream at:

https://github.com/GENIVI/vehicle_signal_manager

Installation and Dependencies
-----------------------------
The project can be run in-place and doesn't need to be installed. The
requirements are:

* Python 3
* PyYAML
* pyzmq (for the ZeroMQ IPC module)

Running
-------
Run the VSM prototype with a given rule file like:

`./vsm sample_rules/simple0.yaml`

State changes can be entered at `stdin` like:

`phone.call = 'active'`

By default, `vsm` will print any resulting signals to `stdout` and log
additional details to the log file (default: `vsm.log`).

Testing
-------
Run the test suite with:

`./tests.py`


