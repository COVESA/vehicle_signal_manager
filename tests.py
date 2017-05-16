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


class TestVSM(unittest.TestCase):
    def run_vsm(self, name, input_data, expected_output, use_initial=True):
        conf = os.path.join(RULES_PATH, name + '.yaml')
        initial_state = os.path.join(RULES_PATH, name + '.initial.yaml')

        cmd = ['./vsm' ]

        if use_initial and os.path.exists(initial_state):
            cmd += ['--initial-state={}'.format(initial_state)]

        cmd += [conf]

        process = Popen(cmd, stdin=PIPE, stdout=PIPE)

        output, _ = process.communicate(input=input_data.encode(), timeout=2)

        self.assertEqual(output.decode() , expected_output)

    def test_simple0(self):
        input_data = 'transmission_gear = "reverse"'
        expected_output = 'car.backup = True\n'
        self.run_vsm('simple0', input_data, expected_output)

    def test_simple0_uninteresting(self):
        input_data = 'phone_call = "inactive"'
        expected_output = ''
        self.run_vsm('simple0', input_data, expected_output)

    def test_simple2_initial(self):
        input_data = 'damage = true'
        expected_output = 'car.stop = True\n'
        self.run_vsm('simple2', input_data, expected_output)

    def test_simple2_initial_uninteresting(self):
        input_data = 'moving = false'
        expected_output = ''
        self.run_vsm('simple2', input_data, expected_output)

    def test_simple2_modify_uninteresting(self):
        input_data = 'moving = true\ndamage = true'
        expected_output = ''
        self.run_vsm('simple2', input_data, expected_output)

    def test_simple2_multiple_signals(self):
        input_data = 'moving = false\ndamage = true'
        expected_output = 'car.stop = True\n'
        self.run_vsm('simple2', input_data, expected_output, False)

if __name__ == '__main__':
    unittest.main()
