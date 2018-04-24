# Copyright (C) 2018 Jaguar Land Rover
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Authors:
#  * Guillaume Tucker <guillaume.tucker@collabora.com>

import importlib
import select


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


class FilenoIPC(IPC):
    """Interface for IPC modules that read from a file descriptor.

    In order to be able to wait for an input from multiple modules, each IPC
    module needs to provide a file descriptor via the fileno() method.  This
    will then be used directly with the select() standard library function.
    """
    def fileno(self):
        """Return the file descriptor to use to read incoming data."""
        raise NotImplementedError("IPC.fileno")


class IPCList(IPC):
    """List of multiple IPC modules to use in parallel.

    This will instanciate a list of class names and use them as a list of IPC
    modules.  Each signal that the VSM needs to send will be sent through all
    the modules.  Likewise, a signal received from any module will be used by
    the VSM.  Each module that needs to be able to receive signals must
    implement the FilenoIPC interface (essentially the fileno() method) for
    this purpose.  Modules without this method will only be able to send
    signals, not receive any.
    """

    def __init__(self, names):
        self._list = list(load(name) for name in names)
        self._inputs = list(i for i in self._list if hasattr(i, 'fileno'))
        self._read = list()

    def close(self):
        for i in self._list:
            i.close()

    def send(self, *args, **kw):
        for i in self._list:
            i.send(*args, **kw)

    def receive(self, *args, **kw):
        if not self._read:
            self._read, _, _ = select.select(self._inputs, [], [])
        return self._read.pop().receive(*args, **kw)
