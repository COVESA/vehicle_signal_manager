# Copyright (C) 2017, 2018 Jaguar Land Rover
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Authors:
#  * Gustavo Noronha <gustavo.noronha@collabora.com>
#  * Shane Fagan <shane.fagan@collabora.com>
#  * Guillaume Tucker <guillaume.tucker@collabora.com>

import sys
import os
import argparse
import yaml
import ast
import threading
import time
import json
import ipc.stream
import os
import uuid
import vsmlib.utils
import re

LOGIC_REPLACE = {'\|\|': 'or',
                 '&&': 'and',
                 r'!([^=])': r'not \1',
                 'true': 'True',
                 'false': 'False'}

LOG_FILE_PATH_DEFAULT = 'vsm.log'

LOG_CAT_CONDITION_CHECKS = 'condition-checks'

SIGNAL_PREFIX_OUTGOING = '<'
SIGNAL_PREFIX_INCOMING = '>'
SIGNAL_PREFIX_DELIM = ' '

REPLAY_RATE_MIN = 1
REPLAY_RATE_MAX = 10000

NODE_CONDITION = 'condition'
# position of condition node within a list in the rule file
NODE_CONDITION_POS = 0
NODE_EMIT = 'emit'
NODE_START = 'start'
NODE_STOP = 'stop'
NODE_PARALLEL = 'parallel'
NODE_SEQUENCE = 'sequence'
# a special name for the rules document root node
NODE_ROOT = 'root'
# a special node to group YAML map elements together which otherwise would not
# maintain their grouping in a tree
NODE_BLOCK = 'block'

# these keywords wrap one or more conditions into a block where:
# * parallel:  all matching conditions will be executed
# * sequence:  any and all matching conditions will be executed but conditions
#              will only be monitored in their sequential order
WRAPPER_KEYWORDS = (NODE_PARALLEL, NODE_SEQUENCE)

program_start_time_ms = 0
logger = None
config_tree = None
# NOTE: these are global because variables can't be passed by reference in
# parsed code so we can't encapsulate it
node_refs = {}
state = None
ipc_obj = None
signal_to_num = {}
args = None

def _format_signal_msg(signal, value, indicator):
    signum = "[SIGNUM]"
    if signal in signal_to_num:
        signum = signal_to_num[signal]
    return '{} {},{},{},{}'.format(indicator, get_runtime(), signal, signum,
                                   repr(value))

def _handle_xor_condition(condition):
    '''
        Group within parentheses sub-clauses of XOR expressions and replace
        its operator (^^) by the not equality operator (!=)
    '''
    try:
        lhs, rhs = condition.split('^^')
    except ValueError:
        return condition

    return "({}) != ({})".format(lhs.strip(), rhs.strip())


class Logger(object):
    '''
        Utility class for logging messages
    '''

    def __init__(self, pipeout_fd):
        self.pipeout_fd = pipeout_fd

    def i(self, msg, timestamp=True):
        '''
            Log an informative (non-error) message
        '''
        os.write(self.pipeout_fd, (msg + '\n').encode('UTF-8'))

    def e(self, msg, timestamp=True):
        '''
            Log an error
        '''
        os.write(self.pipeout_fd, (msg + '\n').encode('UTF-8'))

    def signal(self, signal, value, indicator):
        '''
            Log signal emission/reception
        '''
        msg = _format_signal_msg(signal, value, indicator)
        os.write(self.pipeout_fd, (msg + '\n').encode('UTF-8'))

class Catapult(Logger):

    def __init__(self, pipeout_fd):
        super().__init__(pipeout_fd)
        self.pid = os.getpid()

        # Open the JSON Array file
        os.write(self.pipeout_fd, '[\n'.encode('UTF-8'))

    def i(self, msg, timestamp=True):
        pass

    def e(self, msg, timestamp=True):
        pass

    def signal(self, signal, value, indicator):
        '''
            Log signal emission/reception using the catapult format
        '''
        # A JSON object represents a catapult trace event
        sigtype = 'incoming' if indicator == SIGNAL_PREFIX_INCOMING else 'outgoing'
        event = {
            "name": signal,
            "pid": self.pid,
            "ts": (get_runtime() * 1000),
            "cat": "signal,{}".format(sigtype),
            "ph": "i",
            "args": { "value": value }
        }
        os.write(self.pipeout_fd, (json.dumps(event) + ',\n').encode('UTF-8'))

class State(object):
    '''
        Class to handle states
    '''
    def __init__(self, initial_state, rules, log_categories):
        class VariablesStorage(object):
            pass
        self.variables = VariablesStorage()
        self.log_categories = log_categories

        self.rules = {}
        self.exec_queue = []

        with open(rules) as rules_file:
            self.parse_rules(rules_file)

        if initial_state:
            with open(initial_state) as f:
                data = yaml.load(f.read())

                for item in data:
                    item = item.replace(" ", "").split("=")
                    vars(self.variables)[item[0]] = item[1]

        # inject this object into the globals dictionary so it will be available
        # to the function we're executing (since it won't really be filled in
        # until after this constructor completes)
        global_vars = globals()
        global_vars["state"] = self

        for rule in self.exec_queue:
            exec(rule, global_vars, self._undot_variables(vars(self.variables)))

    def handle_emit(self, data, parent):
        signal = data[NODE_EMIT]["signal"]
        value = data[NODE_EMIT]["value"]

        conditional_node = False
        for node in parent.children:
            if node.node_type == NODE_CONDITION:
                conditional_node = True
                break

        replaying = False
        if args.replay_log_file:
            replaying = True

        # avoid emitting duplicate emit if replaying
        if not conditional_node and replaying:
            return None

        if signal not in signal_to_num:
            self._exit_signal_num_missing(signal)

        if "delay" in data[NODE_EMIT].keys():
            action = "threading.Thread(target=delayed_emit, args=( \
                            \'{}\', \'{}\', {})).start()".format(signal,
                            value, data[NODE_EMIT]["delay"])
        else:
            action = "emit(\'{}\', \'{}\')".format(signal, value)

        ast_node = ast.parse(action)

        parent.add_child(TreeNode(NODE_EMIT, ast_node))

        return ast_node

    def _exit_signal_num_missing(self, signal):
        print("signal '{}' not in signal number mapping file".format(signal),
              file=sys.stderr)
        exit(1)

    def handle_condition(self, data, parent):
        orig_condition = data[NODE_CONDITION]
        # Handle XOR operator (if it is found)
        if orig_condition.find('^^') >= 0:
            condition = _handle_xor_condition(orig_condition)
        else:
            condition = orig_condition

        condition_expr = ast.parse(condition).body[0]

        # Parse identifiers (variables).
        parser = ParseIdentifiers()
        parser.visit(condition_expr)

        for ident in parser.identifiers:
            if ident not in signal_to_num:
                self._exit_signal_num_missing(ident)

        # Replace dot (.) by underscore (_) in the condition identifiers so they
        # can be correctly interpreted like Python variables.
        eval_condition = self._undot_identifiers(condition, parser.identifiers)
        eval_condition_expr = ast.parse(eval_condition).body[0]

        start_time_ms = -1
        stop_time_ms = -1
        if NODE_START in data or NODE_STOP in data:
            if NODE_START not in data:
                logger.e(
                        "'{}' keyword has no corresponding '{}' keyword".format(
                            NODE_STOP, NODE_START))
            elif NODE_STOP not in data:
                logger.e(
                        "'{}' keyword has no corresponding '{}' keyword".format(
                            NODE_START, NODE_STOP))
            else:
                start_time_ms = data[NODE_START]
                stop_time_ms = data[NODE_STOP]

        condition_node = TreeNode(NODE_CONDITION, condition_expr,
                start=start_time_ms, stop=stop_time_ms,
                signals=parser.identifiers)
        parent.add_child(condition_node)

        emit_signal = None
        emit_value = None
        actions_true = []
        actions_false = []
        if NODE_EMIT in data:
            emit_signal = data[NODE_EMIT]["signal"]
            emit_value = data[NODE_EMIT]["value"]

        if self.log_categories[LOG_CAT_CONDITION_CHECKS]:
            action_true_2_code = self.generate_condition_code(orig_condition,
                    True, condition_node, emit_signal, emit_value)
            action_true_2 = ast.parse(action_true_2_code)

            action_false_code = self.generate_condition_code(orig_condition,
                    False, condition_node, None, None)
            action_false = ast.parse(action_false_code)

            actions_true.append(action_true_2.body[0])
            actions_false.append(action_false.body[0])

        ifnode = ast.If(eval_condition_expr.value, actions_true, actions_false)
        ast_module = ast.Module([ifnode])

        ast.fix_missing_locations(ast_module)

        rule = compile(ast_module, '<string>', 'exec')
        condition_node.rule = rule

        return [condition_expr, rule, parser.identifiers]

    def handle_children(self, data, child_type, parent):
        # Build a dict, the key is the keyword used to decide how they are run
        # the items and sub items are the various rules and sub rules
        rules = {child_type:[]}
        conditions = []

        # wrapper keywords (which this method handles) can only have list items
        # as direct children
        if issubclass(type(data[child_type]), list):
            wrapper_node = TreeNode(child_type, None)
            parent.add_child(wrapper_node)

            for item in data[child_type]:
                block_node = TreeNode(NODE_BLOCK, None)
                wrapper_node.add_child(block_node)

                rule = self.__parse_items(item, block_node)
                if rule != "" and isinstance(rule, list):
                    # conditions to evaluate
                    conditions.append(rule[0])

                    # code to execute if conditions are met
                    rules[child_type].append(rule[1])
        else:
            logger.e(child_type + " block contains non-list item as direct "
                "child")

        return [conditions, rules]

    # NOTE: this is static as variables can't be passed by reference in parsed
    # code so we can't depend on the `self` variable
    @staticmethod
    def condition_changed(condition, result, node_ref, emit_signal=None,
            emit_value=None):
        node = node_refs[node_ref]
        node.notify_condition(result)

        all_ancestor_conditions_met = True
        for ancestor in node.get_ancestor_conditions():
            if not ancestor.condition_met:
                all_ancestor_conditions_met = False

            if ancestor.signals:
                for signal in ancestor.signals:
                    ancestor_value = "(unset)"
                    if signal in vars(state.variables):
                        ancestor_value = vars(state.variables)[signal]

                    logger.i("parent condition: {} == {}".format(signal,
                        ancestor_value))

        logger.i("condition: ({}) => {}".format(condition, str(result)))

        # emit the corresponding signal if all ancestor conditions have been met
        if all_ancestor_conditions_met and result and emit_signal:
            emit(emit_signal, emit_value)

    def generate_condition_code(self, condition, result, node, emit_signal,
            emit_value):
        node_ref = repr(node)
        node_refs[node_ref] = node

        if emit_signal:
            return "State.condition_changed({}, {}, \'{}\', \'{}\', " \
                    "\'{}\')".format(repr(condition), result, node_ref,
                            emit_signal, emit_value)
        else:
            return "State.condition_changed({}, {}, \'{}\')".format(
                    repr(condition), result, node_ref)

    def __parse_items(self, item, parent):
        conditions_rules = None

        if NODE_PARALLEL in item:
            conditions_rules = self.handle_children(item, NODE_PARALLEL, parent)
        if NODE_SEQUENCE in item:
            conditions_rules = self.handle_children(item, NODE_SEQUENCE, parent)
        if NODE_CONDITION in item:
            condition, rule, identifiers = self.handle_condition(item, parent)
            self.add_rule(identifiers, rule)
        elif NODE_EMIT in item:
            module = self.handle_emit(item, parent)
            rule = None
            if module != None:
                rule = compile(module, '<string>', 'exec')

            if rule != None:
                # queue up rules to execute until after this class has finished
                # initializing
                self.exec_queue.append(rule)

        if conditions_rules:
            return conditions_rules

    def parse_rules(self, rules_file):
        '''
            Parse YAML rules for policy manager and return ast code.
        '''
        data = rules_file.read()

        # Translate logical operations to Python, so that they
        # can be compiled.
        for key, value in LOGIC_REPLACE.items():
             data = re.sub(key, value, data).strip()

        data = yaml.safe_load(data)

        # Currently we support only lists in yaml at base level
        if issubclass(type(data), list):
            for item in data:
                # this empty node serves to group its child(ren) together just
                # as the list item in the YAML file groups its child(ren)
                # together
                block_node = TreeNode(NODE_BLOCK, None)
                config_tree.add_child(block_node)

                rules = self.__parse_items(item, block_node)

    def add_rule(self, identifiers, rule):
        for signal_name in identifiers:
            if not signal_name in self.rules:
                self.rules[signal_name] = []
            self.rules[signal_name].append(rule)

    def got_signal(self, signal, value):
        self.got_signal_record(signal, value)

        # No conditions based on the signal that was emitted,
        # nothing to be done.
        if not signal in self.rules:
            return

        elif signal in self.rules:
            for rule in self.rules[signal]:
                exec_rule = True

                condition_node_matches = config_tree.get_conditions_by_rule(
                        rule)
                for condition in condition_node_matches:
                    if condition.condition_is_sequence_blocked():
                        logger.e("changed value for signal '{}' ignored " \
                                "because prior conditions in its sequence " \
                                "block have not been met".format(signal))
                        exec_rule = False
                        break

                if exec_rule:
                    try:
                        exec(rule, globals(),
                                self._undot_variables(vars(self.variables)))
                    except NameError:
                        # Names used in rules are not always present
                        # in the state.
                        pass

    def got_signal_record(self, signal, value):
        # Record received signal in logs.
        logger.signal(signal, value, SIGNAL_PREFIX_INCOMING)
        self._update_report_state(signal, value)

    def _update_report_state(self, signal, value):
        vars(self.variables)[signal] = value

        logger.i("State = {")
        for k, v in sorted(vars(self.variables).items()):
            logger.i("{} = {}".format(k, v))
        logger.i("}")

    def _undot_identifiers(self, condition, identifiers):
        for ident in identifiers:
            # Replace '.' by '_' in identifiers.
            if ident.find('.') >= 0:
                condition = condition.replace(ident, ident.replace('.', '_'))
        return condition

    def _undot_variables(self, variables):
        # Replace '.' by '_' in variables names (identifiers)
        return { k.replace('.', '_'): v for k, v in variables.items() }

class ParseIdentifiers(ast.NodeVisitor):
    '''
        Class to parse identifiers (signals and attributes names)
    '''

    def __init__(self):
        self.identifiers = []
        self._attributes = []

    def visit_Name(self, node):
        def make_identifier(node_id):
            return '.'.join(reversed(self._attributes + [node.id]))

        if self._attributes:
            # If a name is found with attributes available, build the identifier
            # and reset the attributes list.
            self.identifiers.append(make_identifier(node.id))
            self._attributes = []
        else:
            self.identifiers.append(node.id)

        super().generic_visit(node)

    def visit_Attribute(self, node):
        self._attributes.append(node.attr)
        super().generic_visit(node)

class LogReplayer(object):
    '''
        Class to enact log file replaying (signals only)
    '''

    signals = []

    def __init__(self, state, replay_log, replay_rate):
        with open(replay_log) as f:
            content = f.readlines()
            for line in content:
                self.__parse_replay_log_line(line)

        for signal in self.signals:
            # by default, don't adjust time scale (ie, 100%)
            scaled_delay_ms = signal.time_ms
            if replay_rate:
                scaled_delay_ms = signal.time_ms / (replay_rate / 100)

            remaining_delay_ms = max(scaled_delay_ms - get_runtime(), 0)

            if signal.direction == self.Signal.DIRECTION_IN:
                delayed_got_signal(signal.name, signal.value,
                        remaining_delay_ms, state)
            if signal.direction == self.Signal.DIRECTION_OUT:
                # don't need to check conditions of parents as that has already
                # happened in the log we're replaying
                delayed_emit(signal.name, signal.value, remaining_delay_ms,
                        state)

    def __parse_replay_log_line(self, line):
        if SIGNAL_PREFIX_DELIM not in line:
            return

        prefix, remainder = line.split(SIGNAL_PREFIX_DELIM, 1)
        direction = None
        if prefix == SIGNAL_PREFIX_INCOMING:
            direction = self.Signal.DIRECTION_IN

        if prefix == SIGNAL_PREFIX_OUTGOING:
            direction = self.Signal.DIRECTION_OUT

        if direction:
            try:
                time_ms, name, signum, value = remainder.split(',')
                time_ms = int(time_ms)
                # eval() the value to effectively reverse the excessive repr()
                # which will be applied before printing this value (which would
                # result in values like "'True'\n" instead of 'True'
                value = eval(value)
                self.signals.append(self.Signal(direction, time_ms, name,
                    value))
            except ValueError as err:
                logger.e('failed to parse line (invalid number of elements): ' +
                        '{}; line was:\n{}'.format(err, line))

                return

    class Signal:
        DIRECTION_OUT = 'out'
        DIRECTION_IN = 'in'

        def __init__(self, direction, time_ms, name, value):
            self.direction = direction
            self.time_ms = time_ms
            self.name = name
            self.value = value

class TreeNode:
    '''
    A representation of a node in the tree of the rules file.

    This is used to maintain the hierarchy of the various rules elements so they
    may be reflected for behavior such as subconditions' dependence on changes
    to their parent conditions.
    '''

    def __init__(self, node_type, value, start=-1, stop=-1, signals=None):
        self.parent = None
        self.node_type = node_type
        self.value = value
        self.children = []
        self.rule = None

        if node_type == NODE_CONDITION:
            self.monitor_init_time_ms = -1
            self.start_timer = None
            self.stop_timer = None
            self.condition_met = False
            self.start_time_ms = start
            self.stop_time_ms = stop
            self.signals = signals

        elif node_type == NODE_SEQUENCE:
            self.next_grandchild_index = 0

    def __str__(self):
        return self.__str_indent("")

    def __str_indent(self, indent):
        string = "{}type: {}, value: {}".format(indent, self.node_type,
                str(self.value))
        for child in self.children:
            string += "\n" + child.__str_indent(indent + "  ")
        return string

    def add_child(self, child):
        self.children.append(child)
        child.parent = self

    def find(self, value):
        '''
        Find the given value in the tree, starting at this node and searching
        below (but never up).
        '''
        found_node = None

        if self.value == value:
            return self

        for child in self.children:
            found_node = child.find(value)
            if found_node != None:
                break

        return found_node

    def find_subconditions(self):
        '''
        If this node is a condition node, find all subconditions.

        Subconditions are not direct descendents of a condition node but a child
        of the condition node's sibling "wrapper block" (eg, is wrapped by a
        "parallel" or "sequence" keyword). This pattern may continue to an
        arbitrary depth like:

                                ⋮         ⋮
                          condition A  ____parallel_____
                                      /        |        \\
                              condition B  condition C  sequence
                                  ⋮            ⋮          |
                                                    condition D
                                                        ⋮

        In this example, conditions B-D are subconditions of condition A.
        '''
        subconditions = []

        if self.node_type == NODE_CONDITION:
            for sibling in self.get_siblings():
                if sibling.node_type in WRAPPER_KEYWORDS:
                    # all wrapper blocks contain exactly one "block" node which
                    # contains the real content nodes
                    sibling_grandchildren = sibling.children[0].children

                    for child in sibling_grandchildren:
                        if child.node_type == NODE_CONDITION:
                            subconditions.append(child)
                            subconditions.extend(child.find_subconditions())

        return subconditions

    def get_ancestor_conditions(self):
        if self.node_type == NODE_CONDITION and self.parent:
            conditions = self._get_ancestor_conditions()
            # exclude self because it is not an ancestor of itself
            conditions.remove(self)
            return conditions

        return []

    def _get_ancestor_conditions(self):
        ancestor_conditions = []

        if self.node_type == NODE_CONDITION:
            ancestor_conditions.append(self)

        if self.node_type != NODE_ROOT and self.parent:
            # for wrapper nodes, we need to follow a path through their sibling
            # condition nodes since the ancestry isn't direct
            if self.parent.node_type in WRAPPER_KEYWORDS:
                parent_siblings = self.parent.get_siblings()
                for parent_sibling in parent_siblings:
                    if parent_sibling.node_type == NODE_CONDITION:
                        ancestor_conditions.extend(
                                parent_sibling._get_ancestor_conditions())
            else:
                ancestor_conditions.extend(
                        self.parent._get_ancestor_conditions())

        return ancestor_conditions

    def get_siblings(self):
        if self.parent == None:
            return []

        return [x for x in self.parent.children if x is not self]

    def notify_ancestor_condition(self, state):
        if state:
            if not self.start_timer and not self.stop_timer:
                # set up monitor
                self.monitor_init_time_ms = get_runtime()
                self.start_timer = threading.Timer(self.start_time_ms/1000,
                        self.start_timeout_func)
                self.stop_timer = threading.Timer(self.stop_time_ms/1000,
                        self.stop_timeout_func)
                self.start_timer.start()
                # check the timer still exists because it may be cleared out
                # with a start time of zero if the inner condition is not
                # already met
                if self.stop_timer:
                    self.stop_timer.start()
        else:
            # parent condition is no longer true so cancel monitor
            self._monitor_completed(True, "")

    def notify_condition(self, state):
        start_max_ms = self.monitor_init_time_ms + self.start_time_ms
        stop_min_ms = self.monitor_init_time_ms + self.stop_time_ms
        runtime = get_runtime()

        if state:
            # only allow the node's condition_met change from False to True if
            # we're before the 'start' time and a monitor is not active so our
            # thread can catch the failure without a race condition
            if runtime < start_max_ms or \
                    (not self.start_timer and not self.stop_timer):
                self.condition_met = True
        else:
            self.condition_met = False

            if (runtime >= start_max_ms and runtime < stop_min_ms) and \
                    (self.start_timer or self.stop_timer):
                self._monitor_completed(self.condition_met,
                        "subcondition not maintained between 'start' time of " \
                                "{}ms and 'stop' time of {}ms".format(
                            self.start_time_ms, self.stop_time_ms))


        for subcondition in self.find_subconditions():
            subcondition.notify_ancestor_condition(self.condition_met)

        if self.parent and self.parent.parent:
            self.parent.parent._sequence_iterate_safe(self)

    def _monitor_completed(self, succeeded, failure_message):
        if self.start_timer:
            self.start_timer.cancel()
            self.start_timer = None

        if self.stop_timer:
            self.stop_timer.cancel()
            self.stop_timer = None

        if not succeeded:
            self.condition_met = False
            logger.e(failure_message)

    def start_timeout_func(self):
        if not self.condition_met:
            self._monitor_completed(self.condition_met,
                    "condition not met by 'start' time of {}ms".format(
                        self.start_time_ms))

    def stop_timeout_func(self):
        self._monitor_completed(True, "")

    def _sequence_iterate_safe(self, condition_grandchild):
        if self.node_type != NODE_SEQUENCE:
            return

        if condition_grandchild.condition_is_sequence_next():
            self.next_grandchild_index += 1
            # there will be exactly one condition per child node
            if self.next_grandchild_index >= len(self.children):
                self.next_grandchild_index = 0
        else:
            pass

    def condition_is_sequence_next(self):
        grandparent = self.condition_get_sequence_grandparent()
        if not grandparent:
            return False

        next_seq_condition = grandparent.children[
                grandparent.next_grandchild_index].children[NODE_CONDITION_POS]

        if next_seq_condition is self:
            return True

        return False

    def condition_get_sequence_grandparent(self):
        if self.node_type == NODE_CONDITION:
            grandparent = None
            if self.parent:
                grandparent = self.parent.parent
                if grandparent and grandparent.node_type == NODE_SEQUENCE:
                    return grandparent

        return None

    def condition_is_sequence_blocked(self):
        seq_grandparent = self.condition_get_sequence_grandparent()
        if seq_grandparent and not self.condition_is_sequence_next():
            return True

        return False

    def get_conditions_by_rule(self, rule):
        conditions_matched = []
        for child in self.children:
            conditions_matched.extend(child.get_conditions_by_rule(rule))

        if self.node_type == NODE_CONDITION and self.rule is rule:
            conditions_matched.append(self)

        return conditions_matched

def show(signal, value, indicator):
    '''
        Show signal emission/reception
    '''
    print(_format_signal_msg(signal, value, indicator))


class DebugIPC(ipc.stream.StdioIPC):

    def send(self, signal, value):
        show(signal, value, SIGNAL_PREFIX_OUTGOING)

    def receive(self):
        message = super(DebugIPC, self).receive()
        if message is not None:
            signal, value = message
            show(signal, value, SIGNAL_PREFIX_INCOMING)
        return message

    def _readline(self):
        line = super(DebugIPC, self)._readline()
        if line == "quit":
            exit(0)
        return line


# this includes an unused state parameter so it matches the signature of
# delayed_got_signal() for log replay purposes
def delayed_emit(signal, value, delay, state=None):
    time.sleep(delay/1000)
    emit(signal, value)

def emit(signal, value):
    # Record sent signal in logs.
    logger.signal(signal, value, SIGNAL_PREFIX_OUTGOING)
    ipc_obj.send(signal, value)
    state._update_report_state(signal, value)

def delayed_got_signal(signal, value, delay, state):
    time.sleep(delay/1000)
    show(signal, value, SIGNAL_PREFIX_INCOMING)
    state.got_signal_record(signal, value)

def process(state, signal, value):
    '''
        Handle the emitting of signals and adding values to state
    '''
    def is_string(value):
        if not isinstance(value, str) or len(value) <= 2:
            return False
        return (value[0] == '"' and value[-1] == '"') or \
            (value[0] == "'" and value[-1] == "'")

    def is_bool(value):
        # specifically only allow the first letter to be capital to disallow,
        # eg, "trUe"
        return value in ('true', 'True') or value in ('false', 'False')

    # Check and convert value to the types: string, bool, float or int
    try:
        if value == None:
            raise ValueError
        if is_string(value):
            value = value[1:-1]
        elif is_bool(value):
            value = value in ('true', 'True') or False
        elif value.find('.') >= 0:
            value = float(value)
        elif value.isnumeric():
            value = int(value)
        else:
            raise ValueError
    except ValueError:
        logger.e('incorrect value: {}'.format(value))
        return

    state.got_signal(signal, value)

def log_processor(pipein_fd, log_file_path):
    pipein = os.fdopen(pipein_fd)
    log_file = sys.stdout

    if log_file_path == None or log_file_path == '':
        log_file_path = LOG_FILE_PATH_DEFAULT

    if log_file_path != '-':
        try:
            log_file = open(log_file_path, 'w')
        except Exception as e:
            log_file.write("failed to open log file '{}': {}\n".format(
                log_file_path, e))

    for line in pipein:
        log_file.write(line)
        log_file.flush()

    if log_file_path:
        log_file.close()

    pipein.close()

def run(state):
    try:
        while True:
            message = ipc_obj.receive()
            if message is None:
                logger.i("skipping invalid message")
                continue

            signal, value = message
            # 'quit' signal to close VSM endpoint.
            if signal == 'quit':
                ipc_obj.close()
                break

            process(state, signal, value)
    except KeyboardInterrupt:
        exit(0)

def get_runtime():
    return round(time.perf_counter() * 1000 - program_start_time_ms)

if __name__ == "__main__":
    program_start_time_ms = round(time.perf_counter() * 1000)

    parser = argparse.ArgumentParser()
    parser.add_argument('--initial-state', type=str,
                        help='Initial state, yaml file', required=False)
    parser.add_argument('rules', type=str,
                        help='yaml rules configuration')
    parser.add_argument('--ipc-modules', type=str, nargs='+',
                        help="List of IPC modules to load")
    parser.add_argument('--log-file', type=str,
            help='Write extra (non-signal emission) output to this file')
    parser.add_argument('--no-log-condition-checks',
            dest='log_condition_checks', action='store_false',
            help='Do not log condition checks (default: log them)')
    parser.add_argument('--replay-log-file', type=str,
            help='Use a log file to replay signal emission in real or scaled ' +
            'time')
    parser.add_argument('--replay-rate', type=float,
            help='The rate at which to play back the replay log. This value ' +
            'is a percentage of originally-recorded timing, specified as a ' +
            'decimal between ' + str(REPLAY_RATE_MIN) + ' and ' +
            str(REPLAY_RATE_MAX) + '. A value of 20 signifies playback at ' +
            '20%% of the original rate (ie, it will take 5 times as long to ' +
            'complete playback vs 100%%)')
    parser.set_defaults(log_condition_checks=True)
    parser.add_argument('--log-format', choices=['catapult'],
                        help='Write log file in specified format')
    parser.add_argument('--signal-number-file', type=str,
                        help='.vsi file which maps all signal names to numbers',
                        required=True)
    args = parser.parse_args()

    signal_to_num, vsi_version = vsmlib.utils.parse_signal_num_file(
        args.signal_number_file)

    log_categories = {LOG_CAT_CONDITION_CHECKS: args.log_condition_checks}

    if args.replay_rate and \
            (args.replay_rate < REPLAY_RATE_MIN or \
                    args.replay_rate > REPLAY_RATE_MAX):
        print('Replay rate must be between {} and {}, inclusive'.format(
            REPLAY_RATE_MIN, REPLAY_RATE_MAX), file=sys.stderr)
        exit(1)

    # fork separate process to handle logging so we don't block main process
    pipein_fd, pipeout_fd = os.pipe()
    if os.fork() == 0:
        os.close(pipeout_fd)
        log_processor(pipein_fd, args.log_file)
    else:
        os.close(pipein_fd)

        if args.log_format == 'catapult':
            logger = Catapult(pipeout_fd)
        else:
            logger = Logger(pipeout_fd)

        if not args.ipc_modules:
            ipc_obj = DebugIPC()
        elif len(args.ipc_modules) == 1:
            ipc_obj = ipc.load(args.ipc_modules[0])
        else:
            ipc_obj = ipc.IPCList(args.ipc_modules)

        config_tree = TreeNode(NODE_ROOT, None)

        state = State(args.initial_state, args.rules, log_categories)

        if args.replay_log_file:
            LogReplayer(state, args.replay_log_file, args.replay_rate)

        run(state)
