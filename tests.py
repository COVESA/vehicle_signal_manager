#!/usr/bin/env python3
# Copyright (C) 2017 Collabora
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
# Authors: Shane Fagan - shane.fagan@collabora.com

import os
import unittest
from subprocess import Popen, PIPE


RULES_PATH = os.path.abspath(os.path.join('.', 'sample_rules'))
SIGNAL_FORMAT = '{},[SIGNUM],\'{}\'\n'
VSM_LOG_FILE = 'vsm-tests.log'

def format_ipc_input(data):
    return [ (x.strip(), y.strip()) for x, y in \
             [ elm.split('=') for elm in data.split('\n') ] ]


class TestVSM(unittest.TestCase):
    ipc_module = None

    def setUp(self):
        if TestVSM.ipc_module == 'zeromq':
            self._init_zeromq()

    def _init_zeromq(self):
        import zmq
        from ipc.zeromq import SOCKET_ADDR
        self._zmq_addr = SOCKET_ADDR
        context = zmq.Context()
        self._zmq_socket = context.socket(zmq.PAIR)
        self._zmq_socket.connect(self._zmq_addr)

    def _send(self, signal, value):
        if TestVSM.ipc_module == 'zeromq':
            self._zmq_socket.send_pyobj((signal, value))
            return

        raise NotImplemented

    def _receive(self):
        if TestVSM.ipc_module == 'zeromq':
            return self._zmq_socket.recv_pyobj()

        raise NotImplemented


    def run_vsm(self, name, input_data, expected_output,
                use_initial=True, send_quit=False):
        conf = os.path.join(RULES_PATH, name + '.yaml')
        initial_state = os.path.join(RULES_PATH, name + '.initial.yaml')

        cmd = ['./vsm' ]

        # Read from the log file for the zeromq tests, otherwise direct
        # verbose output (including state dumps) to stdout so the tests
        # can parse them.
        log_file = VSM_LOG_FILE if TestVSM.ipc_module == 'zeromq' else '-'
        cmd += [ '--log-file={}'.format(log_file) ]

        if use_initial and os.path.exists(initial_state):
            cmd += ['--initial-state={}'.format(initial_state)]

        cmd += [conf]

        if TestVSM.ipc_module:
            cmd += [ '--ipc-module={}'.format(TestVSM.ipc_module) ]

        if TestVSM.ipc_module == 'zeromq':
            process = Popen(cmd)

            for signal, value in format_ipc_input(input_data):
                self._send(signal, value)

            # Send 'quit' for those tests with no signal reply, otherwise
            # they will be stuck on 'receive'.
            if send_quit:
                self._send('quit', '')

            sig, val = self._receive()
            process.terminate()

            # Read state dump from log file.
            with open(VSM_LOG_FILE) as f:
                state_output = f.read()

            signal_output = '' if (sig == '') else SIGNAL_FORMAT.format(sig, val)
            output_final = state_output + signal_output
        else:
            process = Popen(cmd, stdin=PIPE, stdout=PIPE)

            output, _ = process.communicate(input=input_data.encode(), timeout=2)
            output_string = output.decode()

            # strip any prepended timestamp, if it exists
            output_final = ''
            # note: this strips any trailing whitespace
            for line in output_string.splitlines():
                try:
                    timestamp, remainder = line.split(',', 1)
                    output_final += remainder
                except ValueError:
                    output_final += line

                # this re-adds a trailing newline
                output_final += '\n'

        self.assertEqual(output_final , expected_output)

    def test_simple0(self):
        input_data = 'transmission_gear = "reverse"'
        expected_output = '''
State = {
transmission_gear = reverse
}
condition: (transmission_gear == 'reverse') => True
car.backup,[SIGNUM],'True'
        '''
        self.run_vsm('simple0', input_data, expected_output.strip() + '\n')

    def test_simple0_delayed(self):
        input_data = 'transmission_gear = "reverse"'
        expected_output = '''
State = {
transmission_gear = reverse
}
condition: (transmission_gear == 'reverse') => True
car.backup,[SIGNUM],'True'
        '''
        self.run_vsm('simple0_delay', input_data, expected_output.strip() + '\n')

    def test_simple0_uninteresting(self):
        input_data = 'phone_call = "inactive"'
        expected_output = '''
State = {
phone_call = inactive
}
condition: (phone_call == 'active') => False
        '''
        self.run_vsm('simple0', input_data, expected_output.strip() + '\n',
                send_quit=True)

    def test_simple2_initial(self):
        input_data = 'damage = true'
        expected_output = '''
State = {
damage = True
moving = false
}
condition: (moving != True and damage == True) => True
car.stop,[SIGNUM],'True'
        '''
        self.run_vsm('simple2', input_data, expected_output.strip() + '\n')

    def test_simple2_initial_uninteresting(self):
        input_data = 'moving = false'
        expected_output = '''
State = {
moving = False
}
        '''
        self.run_vsm('simple2', input_data, expected_output.strip() + '\n',
                send_quit=True)

    def test_simple2_modify_uninteresting(self):
        input_data = 'moving = true\ndamage = true'
        expected_output = '''
State = {
moving = True
}
condition: (moving != True and damage == True) => False
State = {
damage = True
moving = True
}
condition: (moving != True and damage == True) => False
        '''
        self.run_vsm('simple2', input_data, expected_output.strip() + '\n',
                send_quit=True)

    def test_simple2_multiple_signals(self):
        input_data = 'moving = false\ndamage = true'
        expected_output = '''
State = {
moving = False
}
State = {
damage = True
moving = False
}
condition: (moving != True and damage == True) => True
car.stop,[SIGNUM],'True'
        '''
        self.run_vsm('simple2', input_data, expected_output.strip() + '\n', False)

    def test_delay(self):
        input_data = ''
        
        expected_output = 'wipers.front.on,[SIGNUM],\'True\'\n'

        # NOTE: ideally, this would ensure the delay in output
        self.run_vsm('delay', input_data, expected_output.strip() + '\n', False)

    def test_exclusive_conditions(self):
        input_data = 'remote_key = "unlock"\nlock_state = true\nremote_key = "lock"'
        expected_output = 'State = {\nremote_key = unlock\n}\nState = {\nlock_state = True\nremote_key = unlock\n}\nState = {\nlock_state = True\nremote_key = lock\n}\nlock_state,[SIGNUM],\'True\'\nlock_state,[SIGNUM],\'False\'\nhorn,[SIGNUM],\'True\'\n'
        self.run_vsm('exclusive_conditions', input_data, expected_output, False)


    def test_subclauses_arithmetic_booleans(self):
        input_data = 'flux_capacitor.energy_generated = 1.1\nmovement.speed = 140'
        expected_output = 'movement.speed,[SIGNUM],\'100\'\n'

        self.run_vsm('subclauses_arithmetic_booleans', input_data,
                expected_output.strip() + '\n', False)

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVSM)
    unittest.TextTestRunner(verbosity=2).run(suite)

    TestVSM.ipc_module = 'zeromq'
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVSM)
    unittest.TextTestRunner(verbosity=2).run(suite)
