# Copyright (C) 2018 Collabora Limited
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Authors:
#  * Guillaume Tucker <guillaume.tucker@collabora.com>

import importlib


def load(name, *args, **kwargs):
    """Load an IPC class and return an instance of it.

    The provided name needs to be a module and a class name in a dotted format.
    For example: ipc.something.MyIPC

    An instance of this class will be created using any arbitrary args and
    kwargs passed to it.  The resulting object will be returned.
    """
    module_name, _, cls_name = name.rpartition('.')
    module = importlib.import_module(module_name)
    return getattr(module, cls_name)(*args, **kwargs)


class IPC(object):
    """The IPC module interface

    All the VSM IPC modules should inherit from this class and implement the
    necessary methods to enable the VSM to use them.
    """

    def __init__(self):
        """Connect to the IPC system."""
        pass

    def close(self):
        """Close connection to the IPC system."""
        pass

    def send(self, signal, value):
        """Send signal to the IPC system.

        Both signal and value arguments are strings, with the signal name and
        which value to send.  The IPC module should take care of reformatting
        these arguments into a message to send via its IPC mechanism.  It
        should also filter out unknown signals.
        """
        raise NotImplementedError("IPC.send")

    def receive(self):
        """Receive signal from the IPC system.

        When called, this method should block while the IPC module is waiting
        for an incoming message to be read.  It should then handle the data and
        reformat it to return a (signal, value) 2-tuple with strings, in the
        same format as for the send(signal, value) method arguments.
        """
        raise NotImplementedError("IPC.receive")
