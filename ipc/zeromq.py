# Copyright (C) 2017, Jaguar Land Rover
# Copyright (C) 2018 Collabora Limited
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Authors:
#  * Guillaume Tucker <guillaume.tucker@collabora.com>

import ipc
import zmq

SOCKET_ADDR="tcp://127.0.0.1:9090"

class ZeromqIPC(ipc.IPC):

    def __init__(self):
        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.PAIR)
        self._socket.bind(SOCKET_ADDR)

    def close(self):
        self._socket.close()

    def send(self, signal, value):
        self._socket.send_pyobj((signal, value))

    def receive(self):
        return self._socket.recv_pyobj()
