#!/usr/bin/env python3
# Copyright (C) 2017 Collabora
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
# Authors: Shane Fagan - shane.fagan@collabora.com

import os
import time
import unittest
from subprocess import Popen, PIPE
import vsmlib.utils


RULES_PATH = os.path.abspath(os.path.join('.', 'sample_rules'))
LOGS_PATH = os.path.abspath(os.path.join('.', 'sample_logs'))
SIGNAL_NUMBER_PATH = os.path.abspath(os.path.join('.', 'signal_number_maps'))
SIGNAL_FORMAT = '{},{},\'{}\'\n'
VSM_LOG_FILE = 'vsm-tests.log'
SIGNAL_NUM_FILE = 'samples.vsi'
SIGNUM_DEFAULT = "[SIGNUM]"

def format_ipc_input(data):
    if not data:
        return []

    return [ (x.strip(), y.strip()) for x, y in \
             [ elm.split('=') for elm in data.split('\n') ] ]

def _remove_timestamp(output_string):
    # strip any prepended timestamp, if it exists
    output = ''
    for line in output_string.splitlines():
        try:
            timestamp, remainder = line.split(',', 1)
            output += remainder
        except ValueError:
            output += line

        # this re-adds a trailing newline
        output += '\n'

    return output

def _signal_format_safe(signal_to_num, signal, value):
    string = ''
    signum = None
    if signal in signal_to_num:
        signum = signal_to_num[signal]
    elif signal != '':
        signum = SIGNUM_DEFAULT

    if signum:
        string = SIGNAL_FORMAT.format(signal, signum, value)

    return string

class TestVSM(unittest.TestCase):
    ipc_module = None

    def setUp(self):
        if TestVSM.ipc_module == 'zeromq':
            self._init_zeromq()

    def tearDown(self):
        if TestVSM.ipc_module == 'zeromq':
            self._tear_down_zeromq()

    def _init_zeromq(self):
        import zmq
        from ipc.zeromq import SOCKET_ADDR
        self._zmq_addr = SOCKET_ADDR
        context = zmq.Context()
        self._zmq_socket = context.socket(zmq.PAIR)
        self._zmq_socket.connect(self._zmq_addr)

    def _tear_down_zeromq(self):
        self._zmq_socket.close()

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
                use_initial=True, send_quit=False, replay_case=None,
                wait_time_ms=0):
        conf = os.path.join(RULES_PATH, name + '.yaml')
        initial_state = os.path.join(RULES_PATH, name + '.initial.yaml')

        cmd = ['./vsm' ]

        sig_num_path = os.path.join(SIGNAL_NUMBER_PATH, SIGNAL_NUM_FILE)
        cmd += [ '--signal-number-file={}'.format(sig_num_path) ]

        # Direct verbose output (including state dumps) to log file so the tests
        # can parse them.
        cmd += [ '--log-file={}'.format(VSM_LOG_FILE) ]

        if use_initial and os.path.exists(initial_state):
            cmd += ['--initial-state={}'.format(initial_state)]

        cmd += [conf]

        if replay_case:
            replay_file = os.path.join(LOGS_PATH, replay_case + '.log')

            if os.path.exists(replay_file):
                cmd += ['--replay-log-file={}'.format(replay_file)]

        if TestVSM.ipc_module:
            cmd += [ '--ipc-module={}'.format(TestVSM.ipc_module) ]

        if TestVSM.ipc_module == 'zeromq':
            signal_to_num, _ = vsmlib.utils.parse_signal_num_file(sig_num_path)

            process = Popen(cmd)

            process_output = ''
            for signal, value in format_ipc_input(input_data):
                self._send(signal, value)
                # Record sent signal directly from the test.
                process_output += _signal_format_safe(signal_to_num, signal,
                                                      value)

            # Send 'quit' for those tests with no signal reply, otherwise
            # they will be stuck on 'receive'.
            if send_quit:
                self._send('quit', '')

            sig, val = self._receive()
            # Give some time for the logger to write all the output.
            time.sleep(0.01)
            process.terminate()

            process_output += _signal_format_safe(signal_to_num, sig, val)
        else:
            process = Popen(cmd, stdin=PIPE, stdout=PIPE)

            timeout_s = 2
            if wait_time_ms > 0:
                timeout_s = wait_time_ms / 1000

            output, _ = process.communicate(input=input_data.encode(),
                    timeout=timeout_s)
            cmd_output = output.decode()

            process_output = _remove_timestamp(cmd_output)

        # Read state dump from log file.
        with open(VSM_LOG_FILE) as f:
            state_output = f.read()

        log_output = _remove_timestamp(state_output)
        output_final = log_output + process_output

        self.assertEqual(output_final , expected_output)


    def test_simple0(self):
        input_data = 'transmission.gear = "reverse"'
        expected_output = '''
transmission.gear,9,'reverse'
State = {
transmission.gear = reverse
}
car.backup,3,'True'
State = {
car.backup = True
transmission.gear = reverse
}
condition: (transmission.gear == 'reverse') => True
transmission.gear,9,'"reverse"'
car.backup,3,'True'
        '''
        self.run_vsm('simple0', input_data, expected_output.strip() + '\n')

    def test_simple0_delayed(self):
        input_data = 'transmission.gear = "reverse"'
        expected_output = '''
transmission.gear,9,'reverse'
State = {
transmission.gear = reverse
}
condition: (transmission.gear == 'reverse') => True
car.backup,3,'True'
State = {
car.backup = True
transmission.gear = reverse
}
transmission.gear,9,'"reverse"'
car.backup,3,'True'
        '''
        self.run_vsm('simple0_delay', input_data, expected_output.strip() + '\n')

    def test_simple0_uninteresting(self):
        '''
        A test case where conditions to emit another signal are never triggered
        '''

        input_data = 'phone.call = "inactive"'
        expected_output = '''
phone.call,7,'inactive'
State = {
phone.call = inactive
}
condition: (phone.call == 'active') => False
phone.call,7,'"inactive"'
        '''
        self.run_vsm('simple0', input_data, expected_output.strip() + '\n',
                send_quit=True)

    def test_simple2_initial(self):
        input_data = 'damage = True'
        expected_output = '''
damage,5,True
State = {
damage = True
moving = False
}
car.stop,4,'True'
State = {
car.stop = True
damage = True
moving = False
}
condition: (moving != True and damage == True) => True
damage,5,'True'
car.stop,4,'True'
        '''
        self.run_vsm('simple2', input_data, expected_output.strip() + '\n')

    def test_simple2_initial_uninteresting(self):
        '''
        A test case where conditions to emit another signal are never triggered
        '''

        input_data = 'moving = False'
        expected_output = '''
moving,6,False
State = {
moving = False
}
moving,6,'False'
        '''
        self.run_vsm('simple2', input_data, expected_output.strip() + '\n',
                send_quit=True)

    def test_simple2_modify_uninteresting(self):
        '''
        A test case where conditions to emit another signal are never triggered
        '''

        input_data = 'moving = True\ndamage = True'
        expected_output = '''
moving,6,True
State = {
moving = True
}
condition: (moving != True and damage == True) => False
damage,5,True
State = {
damage = True
moving = True
}
condition: (moving != True and damage == True) => False
moving,6,'True'
damage,5,'True'
        '''
        self.run_vsm('simple2', input_data, expected_output.strip() + '\n',
                send_quit=True)

    def test_simple2_multiple_signals(self):
        input_data = 'moving = False\ndamage = True'
        expected_output = '''
moving,6,False
State = {
moving = False
}
damage,5,True
State = {
damage = True
moving = False
}
car.stop,4,'True'
State = {
car.stop = True
damage = True
moving = False
}
condition: (moving != True and damage == True) => True
moving,6,'False'
damage,5,'True'
car.stop,4,'True'
        '''
        self.run_vsm('simple2', input_data, expected_output.strip() + '\n', False)

    def test_simple0_log_replay(self):
        '''
        A test of the log replay functionality
        '''

        if self.ipc_module:
            self.skipTest("test not compatible with IPC module")

        input_data = ''
        expected_output = '''
phone.call,7,'active'
State = {
phone.call = active
}
car.stop,4,'True'
State = {
car.stop = True
phone.call = active
}
phone.call,7,'active'
car.stop,4,'True'
        '''
        self.run_vsm('simple0', input_data, expected_output.strip() + '\n',
                replay_case='simple0-replay', wait_time_ms=5000)

    def test_simple3_xor_condition(self):
        input_data = 'phone.call = "active"\nspeed.value = 5.0'
        expected_output = '''
phone.call,7,'active'
State = {
phone.call = active
}
speed.value,8,5.0
State = {
phone.call = active
speed.value = 5.0
}
car.stop,4,'True'
State = {
car.stop = True
phone.call = active
speed.value = 5.0
}
condition: (phone.call == 'active' ^^ speed.value > 50.90) => True
phone.call,7,'"active"'
speed.value,8,'5.0'
car.stop,4,'True'
        '''
        self.run_vsm('simple3', input_data, expected_output.strip() + '\n')

    def test_monitored_condition_satisfied(self):
        '''
        This test case sets up the monitor for the subcondition and
        satisfies the subcondition before the 'stop' timeout (and thus omits the
        error message in the expected output).
        '''

        # skip when running with IPC module because error messages are not
        # transmitted
        if self.ipc_module:
            self.skipTest("test not compatible with IPC module")

        input_data = 'transmission.gear = "forward"\n' \
                'transmission.gear = "reverse"\n' \
                'camera.backup.active = True'
        expected_output = '''
transmission.gear,9,'reverse'
State = {
transmission.gear = reverse
}
transmission.gear,9,'forward'
State = {
transmission.gear = forward
}
condition: (transmission.gear == 'reverse') => False
transmission.gear,9,'reverse'
State = {
transmission.gear = reverse
}
lights.external.backup,14,'True'
State = {
lights.external.backup = True
transmission.gear = reverse
}
condition: (transmission.gear == 'reverse') => True
camera.backup.active,15,True
State = {
camera.backup.active = True
lights.external.backup = True
transmission.gear = reverse
}
parent condition: transmission.gear == reverse
condition: (camera.backup.active == True) => True
transmission.gear,9,'reverse'
transmission.gear,9,'"forward"'
transmission.gear,9,'"reverse"'
lights.external.backup,14,'True'
camera.backup.active,15,'True'
        '''
        self.run_vsm('monitored_condition', input_data,
                expected_output.strip() + '\n', wait_time_ms=1500)

    def test_monitored_condition_child_failure(self):
        '''
        This test case sets up the monitor for the subcondition and
        intentionally allows it to fail by not satisfying the subcondition
        before the 'stop' timeout.
        '''

        # skip when running with IPC module because error messages are not
        # transmitted
        if self.ipc_module:
            self.skipTest("test not compatible with IPC module")

        input_data = 'transmission.gear = "forward"\n' \
            'transmission.gear = "reverse"'
        expected_output = '''
transmission.gear,9,'reverse'
State = {
transmission.gear = reverse
}
transmission.gear,9,'forward'
State = {
transmission.gear = forward
}
condition: (transmission.gear == 'reverse') => False
transmission.gear,9,'reverse'
State = {
transmission.gear = reverse
}
lights.external.backup,14,'True'
State = {
lights.external.backup = True
transmission.gear = reverse
}
condition: (transmission.gear == 'reverse') => True
condition not met by 'start' time of 200ms
transmission.gear,9,'reverse'
transmission.gear,9,'"forward"'
transmission.gear,9,'"reverse"'
lights.external.backup,14,'True'
        '''
        self.run_vsm('monitored_condition', input_data,
                expected_output.strip() + '\n', wait_time_ms=1500)

    def test_monitored_condition_parent_cancellation(self):
        '''
        This test case sets up the monitor for the subcondition and changes the
        evaluation of the parent condition to cancel the monitor before the
        'stop' timeout.
        '''

        # skip when running with IPC module because error messages are not
        # transmitted
        if self.ipc_module:
            self.skipTest("test not compatible with IPC module")

        input_data = 'transmission.gear = "forward"\n' \
            'transmission.gear = "reverse" \n' \
            'transmission.gear = "forward"'
        expected_output = '''
transmission.gear,9,'reverse'
State = {
transmission.gear = reverse
}
transmission.gear,9,'forward'
State = {
transmission.gear = forward
}
condition: (transmission.gear == 'reverse') => False
transmission.gear,9,'reverse'
State = {
transmission.gear = reverse
}
lights.external.backup,14,'True'
State = {
lights.external.backup = True
transmission.gear = reverse
}
condition: (transmission.gear == 'reverse') => True
transmission.gear,9,'forward'
State = {
lights.external.backup = True
transmission.gear = forward
}
condition: (transmission.gear == 'reverse') => False
transmission.gear,9,'reverse'
transmission.gear,9,'"forward"'
transmission.gear,9,'"reverse"'
lights.external.backup,14,'True'
transmission.gear,9,'"forward"'
        '''
        self.run_vsm('monitored_condition', input_data,
                expected_output.strip() + '\n', wait_time_ms=1500)

    def test_parallel(self):
        # skip when running with IPC module because output is slightly different
        if self.ipc_module:
            self.skipTest("test not compatible with IPC module")

        input_data = 'transmission.gear = "reverse"\n'\
                'wipers = True'
        expected_output = '''
transmission.gear,9,'reverse'
State = {
transmission.gear = reverse
}
reverse,16,'True'
State = {
reverse = True
transmission.gear = reverse
}
condition: (transmission.gear == 'reverse') => True
wipers,17,True
State = {
reverse = True
transmission.gear = reverse
wipers = True
}
lights,18,'on'
State = {
lights = on
reverse = True
transmission.gear = reverse
wipers = True
}
condition: (wipers == True) => True
transmission.gear,9,'"reverse"'
reverse,16,'True'
wipers,17,'True'
lights,18,'on'
        '''
        self.run_vsm('parallel', input_data, expected_output.strip() + '\n',
                False)

    def test_sequence_in_order(self):
        # skip when running with IPC module because output is slightly different
        if self.ipc_module:
            self.skipTest("test not compatible with IPC module")

        input_data = 'transmission.gear = "park"\n' \
                'ignition = True'
        expected_output = '''
transmission.gear,9,'park'
State = {
transmission.gear = park
}
parked,11,'True'
State = {
parked = True
transmission.gear = park
}
condition: (transmission.gear == 'park') => True
ignition,10,True
State = {
ignition = True
parked = True
transmission.gear = park
}
ignited,12,'True'
State = {
ignited = True
ignition = True
parked = True
transmission.gear = park
}
condition: (ignition == True) => True
transmission.gear,9,'"park"'
parked,11,'True'
ignition,10,'True'
ignited,12,'True'
        '''
        self.run_vsm('sequence', input_data, expected_output.strip() + '\n')

    def test_sequence_out_then_in_order(self):
        # skip when running with IPC module because output is slightly different
        if self.ipc_module:
            self.skipTest("test not compatible with IPC module")

        input_data = 'ignition = True\n' \
                'transmission.gear = "park"\n' \
                'ignition = True'
        expected_output = '''
ignition,10,True
State = {
ignition = True
}
changed value for signal 'ignition' ignored because prior conditions in its sequence block have not been met
transmission.gear,9,'park'
State = {
ignition = True
transmission.gear = park
}
parked,11,'True'
State = {
ignition = True
parked = True
transmission.gear = park
}
condition: (transmission.gear == 'park') => True
ignition,10,True
State = {
ignition = True
parked = True
transmission.gear = park
}
ignited,12,'True'
State = {
ignited = True
ignition = True
parked = True
transmission.gear = park
}
condition: (ignition == True) => True
ignition,10,'True'
transmission.gear,9,'"park"'
parked,11,'True'
ignition,10,'True'
ignited,12,'True'
        '''
        self.run_vsm('sequence', input_data, expected_output.strip() + '\n')

    def test_unconditional_emit(self):
        input_data = ''
        expected_output = '''
lock.state,13,'True'
State = {
lock.state = True
}
lock.state,13,'True'
        '''
        self.run_vsm('unconditional_emit', input_data,
                expected_output.strip() + '\n')

    def test_delay(self):
        input_data = 'wipers.front.on = True'
        expected_output = '''
wipers.front.on,5020,True
State = {
wipers.front.on = True
}
condition: (wipers.front.on == True) => True
lights.external.headlights,19,'True'
State = {
lights.external.headlights = True
wipers.front.on = True
}
wipers.front.on,5020,'True'
lights.external.headlights,19,'True'
        '''
        # NOTE: ideally, this would ensure the delay in output but, for
        # simplicity, that is handled in a manual test case. This simply ensures
        # the output is correct.
        self.run_vsm('delay', input_data, expected_output.strip() + '\n', False,
                wait_time_ms=2500)

    def test_subclauses_arithmetic_booleans(self):
        # skip when running with IPC module because output is slightly different
        if self.ipc_module:
            self.skipTest("test not compatible with IPC module")

        input_data = 'flux_capacitor.energy_generated = 1.1\nspeed.value = 140'
        expected_output = '''
flux_capacitor.energy_generated,5030,1.1
State = {
flux_capacitor.energy_generated = 1.1
}
lights.external.time_travel_imminent,5032,'True'
State = {
flux_capacitor.energy_generated = 1.1
lights.external.time_travel_imminent = True
}
condition: (flux_capacitor.energy_generated >= 1.21 * 0.9 and not (flux_capacitor.energy_generated >= 1.21)
) => True
lights.external.time_travel_imminent,5032,'True'
State = {
flux_capacitor.energy_generated = 1.1
lights.external.time_travel_imminent = True
}
condition: (flux_capacitor.energy_generated >= 1.21 * 0.9 and not (flux_capacitor.energy_generated >= 1.21)
) => True
speed.value,8,140
State = {
flux_capacitor.energy_generated = 1.1
lights.external.time_travel_imminent = True
speed.value = 140
}
lights.internal.time_travel_imminent,5031,'True'
State = {
flux_capacitor.energy_generated = 1.1
lights.external.time_travel_imminent = True
lights.internal.time_travel_imminent = True
speed.value = 140
}
condition: (( speed.value >= (88 - 10) * 1.6 and speed.value <  88 * 1.6 ) or ( flux_capacitor.energy_generated >= 1.21 * 0.9 and flux_capacitor.energy_generated < 1.21 )
) => True
lights.internal.time_travel_imminent,5031,'True'
State = {
flux_capacitor.energy_generated = 1.1
lights.external.time_travel_imminent = True
lights.internal.time_travel_imminent = True
speed.value = 140
}
condition: (( speed.value >= (88 - 10) * 1.6 and speed.value <  88 * 1.6 ) or ( flux_capacitor.energy_generated >= 1.21 * 0.9 and flux_capacitor.energy_generated < 1.21 )
) => True
flux_capacitor.energy_generated,5030,'1.1'
lights.external.time_travel_imminent,5032,'True'
lights.external.time_travel_imminent,5032,'True'
speed.value,8,'140'
lights.internal.time_travel_imminent,5031,'True'
lights.internal.time_travel_imminent,5031,'True'
        '''
        self.run_vsm('subclauses_arithmetic_booleans', input_data,
                expected_output.strip() + '\n', False)

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVSM)
    unittest.TextTestRunner(verbosity=2).run(suite)

    TestVSM.ipc_module = 'zeromq'
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVSM)
    unittest.TextTestRunner(verbosity=2).run(suite)
