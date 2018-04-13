# Copyright (C) 2018 Collabora Limited
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Authors:
#  * Guillaume Tucker <guillaume.tucker@collabora.com>

import ipc
import socket
import sys


class StreamIPC(ipc.FilenoIPC):
    """IPC module based on a generic communication stream.

    This class is to keep a pair of streams, for input and output, and
    implement a basic text-based API in the format `signal=value\n`.
    """

    def __init__(self, input_stream, output_stream):
        self._in = input_stream
        self._out = output_stream

    def close(self):
        close(self._in)
        close(self._out)

    def fileno(self):
        return self._in.fileno()

    def send(self, signal, value):
        self._write('{}={}\n'.format(signal, value))

    def receive(self):
        line = self._readline()
        if line is None:
            return None
        return tuple(s.strip() for s in line.split('='))

    def _write(self, data):
        """Write some text data to emit a signal."""
        self._out.write(data)
        self._out.flush()

    def _readline(self):
        """Return one line from the input stream or None if EOF."""
        line = ''
        while not line:
            line = self._in.readline() or None
            if line is None:
                break
            line = line.strip()
        return line


class StdioIPC(StreamIPC):
    """Stream IPC class based on stdin and stdout."""

    def __init__(self, *args, **kwargs):
        super(StdioIPC, self).__init__(sys.stdin, sys.stdout, *args, **kwargs)


class SocketIPC(StreamIPC):
    """Stream IPC class based on a TCP client connection to a server

    This class will first open a client connection to a server specified by the
    given host and port.  It will then use it for both input and output streams
    using regular file interface functions.
    """

    def __init__(self, host, port, *args, **kwargs):
        self._sock = socket.create_connection((host, port))
        self._file = self._sock.makefile('rw')
        super(SocketIPC, self).__init__(self._file, self._file, *args, **kwargs)

    def close(self):
        self._file.close()
        self._sock.close()

    def fileno(self):
        return self._sock.fileno()
