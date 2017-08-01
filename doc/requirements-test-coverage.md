Introduction
============
Requirements in the ESOW (in this directory) are satisfied by the following test cases. A test passing signifies that the corresponding requirements are fulfilled.

Many of the tests cover multiple requirements. For brevity, each requirement will only be listed once below. Additionally, some tests exist to cover edge cases or previously-discovered defects.

Unless otherwise specified, the test name refers to an automated test in `tests.py`. Manual tests are documented in `tests-manual.md`.

Tests and Requirements Fulfilled
================================
`test_simple0`:
* written in Python (req. G1)
* is able to track state when processing signals (req. PM1)
* Conditions that evaluate to true shall be able to emit zero or more
signals (req. PM22)
* Each emitted signal shall have a signal name (req. PM23)
* Each emitted signal shall have a signal value (req. PM24)
* The signal value shall be an arithmetic expression (req. PM25)
* The arithmetic expression shall have constants as operands (PM26)
* The arithmetic expression shall have signal values as operands
(req. PM27)
* The Policy Manager shall load its rules with monitors and
conditions from a configuration file (req. PM31)
* The configuration file shall be written in YAML (req. PM32)
* The Policy Manager shall be able to translate numerical signal IDs
to signal names used by the rule configuration files. (req. ID2)
* The signal name-ID mapping shall be read by the Policy Manager as an
external mapping file (req. ID5)
* The external mapping file shall have the same format as the ID file
in the Vehicle Signal Specification project (req. ID6)
* The Policy Manager shall emit an error if a rule contains a signal
name not present in the mapping file (req. ID7)
* The Policy Manager shall receive signals with numerical IDs (req.
ID1)

`test_subclauses_arithmetic_booleans`:
`test_simple3_xor_condition`:
* Conditions shall be specified as Boolean expressions (req. PM2)
* Boolean expressions shall be able to use signal values as operands
(req. PM3)
* Boolean expressions shall be able to use constant values as
operands (req. PM4)
* Boolean expressions shall be able to support arithmetic expressions
as operands (req. PM5)
* Boolean expressions shall be able to support sub-clauses within
parenthesis (req. PM6)
* Boolean expressions shall support GTE, GT, LTE, LT, EQ, NEQ, AND,
OR, XOR, and NOT as operators  (req. PM7)

`test_monitored_condition_satisfied`:
`test_monitored_condition_parent_cancellation`:
* Conditions shall be able to specify a start-stop time interval
within which its expression must evaluate to true (req. PM8)
* The interval start shall be specified as milliseconds after the
monitor becomes active (req. PM9)
* The interval stop shall be specified as milliseconds after the
interval starts (req. PM10)
* A monitored condition shall be able to contain child conditions
(req. PM13)
* Child conditions can be defined to an arbitrary depth, forming a
condition tree (req. PM14)
* Child conditions shall fulfil the same requirements as the main
conditions (req. PM15)
* Child conditions shall only be monitored when their hosting parent
condition are evaluating to true (PM16)

`test_monitored_condition_child_failure`:
* A monitored condition that is violated shall be logged (req. PM17)
* The log shall contain a reference to the violated condition (req.
PM18)
* The log shall contain the values of all signal operands in the
violated condition (req. PM19)
* The log shall contain a reference to all parent conditions (req.
PM20)
* The log shall contain the values of all signal operands of all
parent conditions (req. PM21)

`test_simple0_delayed`:
Manual test: Test Delay:
* The emitted signal shall be able to have a delay specified before
it is sent out (req. PM28)
* The delay shall be specified in milliseconds (req. PM29)

`test_simple0` (when run through ZeroMQ IPC module):
* The Development Policy Manager shall be able to load signal receive
and transmit code through Python extension modules (req. PP1)
* The Python extension module shall have a send command to transmit
signals (req. PP2)
* The send command shall accept a signal ID and a signal value as its
arguments (req. PP3)
* The Python extension module shall invoke a Python call when a
signal is received (req. PP4)
* The Python call shall be provided with a signal ID and a signal
value as its arguments (req. PP5)
* The signal value shall of one of the types supported by the GENIVI
Vehicle Signal Specification (req. PP6)
* The Policy Manager shall be able to record all signals received
from the network (req. SR1)
* The received signals shall be timestamped (at the time they're
received, for accuracy) (req. SR2)
* The signals shall be stored, together with its timestamp, in a
file. (req. SR3)
* The file shall be line-oriented and human readable. (req. SR4)
* Each line shall contain comma-separated values, which are escaped.
(req. SR7)
* The first field shall contain a msec timestamp relative to capture
start. (req. SR8)
* The second field shall contain the full signal name (req. SR9)
* modify logging output (as created for T5817) so the third field
shall contain the numerical signal ID as read from the Vehicle Signal
Specification (req. SR10)
* The fourth field shall contain the value of the signal (req. SR11)
* The value of the signal shall be formatted as python short string
literal. (req. SR12)
* The short string literal shall handle quotes and escapes as
specified by Python 3 Language Reference, Lexical analysis, chapter
2.4.1 (req. SR13)

`test_simple0_log_replay`:
* The Policy Manager shall be able to replay signals captured during
an earlier session. (req. SR14)

Manual test: Test Replay Rates (Slow):
Manual test: Test Replay Rates (Fast):
* The signal replay shall happen with the same timing as the signals
were captured with. (req. SR15)
* The signals will be replayed at the specified percentage of the
speed they were originally received at, with 100.0% being the same
speed. (req. SR18)

Manual test: Test Replay Rates (Normal):
* The signal replay shall be able to adjust the speed of the replay,
compared to the timing the signals were captured with. (req. SR16)
* The speed shall be provided as a decimal value between 0.0% and
10000.0% (req. SR17)

Requirements not fulfilled in time for Sprint 6
===============================================
[] VSI IPC module
