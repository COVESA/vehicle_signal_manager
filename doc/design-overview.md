Introduction
============
This document describes, at a high level, the main design aspects of the Vehicle
Signal Manager (VSM). For additional details, please see the ESOW in this
directory.

Motivation
----------
The Vehicle Signal Manager project is a prototype signal management system which
abstracts events (such as the transmission changing to "reverse") and possible
system reactions (such as the "reverse camera" feed appearing on the display).

VSM allows the rules for these relationships to be specified in a configuration
file which may be easily maintained by the manufacturer rather than hard-coding
them in code which must be re-compiled and tested as has traditionally been the
case.

Parser
======
The parser (currently in the `vsm` script) reads a VSM rule file and populates
an abstract syntax tree with the rule elements to be applied by the Policy
Manager. The VSM rule file format is described in the `rules.md` document in
this directory.

Policy Manager
==============
The majority of the `vsm` script functions as the Policy Manager. Core
responsibilities include:

* creating rules based on the abstract syntax tree
* building a tree of conditions and wrapper blocks (needed for monitored
  conditions)
* maintaining the a map of signals and their values which is factored into
  condition evaluations as certain conditions (eg, nested conditions, sequential
  conditions) depend upon parent or sibling conditions
* creating and managing timers triggered by monitored conditions
* reading and writing signal emissions from/to the transport method (either the
  terminal, which is the default, or an IPC module)

VSM abstracts a vehicle's reaction to input signals to the rules file. This
makes adjustments to this behavior as simple as editing the file and confirming
expected behavior with the `vsm` script by inputting expected signal emissions
and checking output.

Pluggable IPC framework
=======================
Signal I/O may be redirected through an optional IPC module. These modules
override the default, terminal-based `send()` and `receive()` methods which
allows signals to be directed to/from other processes or even network
destinations for the purposes of reaction or logging.

This prototype version of VSM includes IPC modules for the ZeroMQ messaging
protocol and the Vehicle Signal Interface (VSI) messaging system.

Run `vsm --help` for details on specifying an IPC module at run-time.
