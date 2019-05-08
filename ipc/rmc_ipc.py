#!/usr/bin/env python3
# dstc client side
# Copyright (C) 2018 Jaguar Land Rover
#
# All rights reserved.
#

import re
import struct
import sys
import dstc
import vsd
from . import IPC
import logging
import os
import string
from threading import Thread
import time
import struct

verbose = True
fifo_fd = None
signals = {}
sigName = None
command = None

# this callback is based on the vsd_swig/vsd_sub_example
def process_signal(signal, path, value):
    global fifo_fd
    global sigName
    # the VSM should be monitoring the fifo and trigger the receive()
    # after we write the value
    value = round(value, 1)
    sigName = path
    if verbose:
        logging.info("From IPC process_signal(), the signal is :" + str(signal) + ":")
        logging.info("From IPC process_signal(), the path is :" + str(path) + ":")
        logging.info("From IPC process_signal(), the value is :" + str(value) + ":")

    os.write(fifo_fd, bytearray(struct.pack("f", value)))
    # need to write both signal and value into the fifo
    # then, in receive(), in the case of multiple signal types,
    # we'll know which signal type we are dealing with
    # the signal value is in the csv file. The tuner will send the signal number
    # and, we can look that number up from the table

    if verbose:
        logging.info("From IPC process_signal(), finished writing to fifo")


def parse_csv(csv_file):
    global signals
    if verbose:
        logging.info("From rmc_ipc, parse_csv(), the csv_file is " + str(csv_file))

    try:
        with open(csv_file) as fp:
            line = fp.readline()
            signals = {'badSignal':'0000'}
            while line:
                line = line.strip()
                if verbose:
                    logging.info("From rmc_ipc, parse_csv(), The line to process is " + line)
                myBits = line.split(',')
                mySignal = myBits[0]
                mySignalID = myBits[1]
                signals[mySignal] = mySignalID
                if verbose:
                    logging.info("From rmc_ipc, parse_csv(), The signal is " + mySignal)
                    logging.info("From rmc_ipc, parse_csv(), The signalID is " + mySignalID)
                line = fp.readline()

    except Exception as e:
        logging.info("From rmc_ipc, parse_csv(), parse_csv exception is " + str(e))
        pass

    signals.pop('badSignal', None)

    if verbose:
        logging.info("From rmc_ipc, parse_csv(), we parsed {} signals".format(len(signals)))

    if not len(signals) > 0:
        signals = None

    return signals


class RMCIPC(IPC):
    """IPC module to communicate with the RMC system.
    """
    def __init__(self, myFifo, csv_file):
        global fifo_fd
        if verbose:
            logging.info("rmc_ipc __init__()...")
            logging.info("rmc_ipc __init__(), myFifo is " + str(myFifo))
            logging.info("rmc_ipc __init__(), csv_file is " + str(csv_file))
        self._re = re.compile('^Vehicle\.([a-zA-Z]+)')
        # open fifo for read/write non-blocking
        self._myFifo = myFifo
        self._signals = parse_csv(csv_file)
        if not self._signals:
            print("From rmc_ipc, ERROR: no signals could not be parsed from " + csv_file)
            sys.exit(1)
        fifo_fd = os.open(self._myFifo, os.O_RDWR | os.O_NONBLOCK)
        if verbose:
            logging.info("rmc_ipc init(), the fifo_fd is " + str(fifo_fd))

        self.client_func = dstc.register_client_function("set_fm_frequency", "d")

        self._ctx = vsd.create_context()
        vsd.set_callback(self._ctx, process_signal)
        if vsd.load_from_file(self._ctx, "./vss_rel_2.0.0-alpha+005.csv") != 0:
            print("Could not load vss_rel_2.0.0-alpha+005.csv")
            sys.exit(255)
        sig = vsd.signal(self._ctx, "Vehicle.setfrequency");
        vsd.subscribe(self._ctx, sig)

        if verbose:
            logging.info("rmc_ipc is waiting for remote dstc function")
        dstc.activate()

        # 100000 seems enough
        # increase this value if tests timeout
        # also see dstc.process_events() in send()
        while not dstc.remote_function_available(self.client_func):
            dstc.process_events(100000)

        if verbose:
            logging.info("From class RMCIPC, init complete")

    def close(self):
        pass

    def fileno(self):
        if verbose:
            logging.info("From rmc_ipc fileno(), the fifo file descriptor is " + str(fifo_fd))
        return fifo_fd

    def format_string_as_double(self, thing):
        double_val = float(thing)
        formatted_double_val = "{:3.1f}".format(double_val)
        return float(formatted_double_val)

    def split_signal(self, pre_signal):
        if verbose:
            logging.info("From rmc_ipc split_signal(), the pre-processed signal is " + str(pre_signal))
        myBits = pre_signal.split('.')
        processed_signal = myBits[1]
        if verbose:
            logging.info("From rmc_ipc split_signal(), the post-processed signal is " + str(processed_signal))
        return processed_signal

    def send(self, signal, value):
        global command
        command = self.split_signal(signal)
        if verbose:
            logging.info("From rmc_ipc.py, send(), the signal is " + str(signal))
            logging.info("From rmc_ipc.py, send(), the value is " + str(value))
            logging.info("From rmc_ipc.py, send(), the command is " + str(command))
            logging.info("From rmc_ipc.py, send(), the object type of value is " + str(type(value)))

        m = self._re.match(signal)
        if m is None:
            if verbose:
                logging.info("From rmc_ipc.py, send(), no match")
            return

        # for can signals, this was a tuple
        # sig_cat, sig_name = m.groups()
        # for the dstc tuner, this is the control signal
        # read from the rules file for this test
        # need to ensure this matches a signal from the csv file
        sig_cat = m.groups()
        if verbose:
            logging.info("sig_cat is " + str(sig_cat[0]))

        if sig_cat[0] == command:
            # 1000000 seems enough for the test system to receive the
            # callback from the tuner after setting the frequency
            # increase this value if tests frequently timeout
            self.client_func(self.format_string_as_double(value))
            if verbose:
                logging.info("From rmc_ipc just called self.client_func(value) " + str(value))
            dstc.process_events(100000)

    def receive(self):
        logging.info("From rmc_ipc.py, receive, the sigName is " + str(sigName))
        # this function reads the signal/value tuple from the fifo
        # we wrote these values in process_signal()
        # this function reads the signal name from the csv file
        # using the signal number as the key
        # it then appends the ".reply" to the signal name and
        # returns the re-formatted tuple back to the VSM

        # 255 bytes should be sufficient
        n = 255
        ret = os.read(fifo_fd, n) # read at most n bytes
        if verbose:
            logging.info("From rmc_ipc.py, receive, read from fifo: " + str(ret))
        myFloat = struct.unpack("<f", ret)
        myFloat = round(myFloat[0], 1)
        if verbose:
            logging.info("From rmc_ipc.py, receive, the formatted float value is: " + str(myFloat))

        # need to use the signal read from the fifo to do the lookup from the csv file
        signal = sigName + ".reply"
        value = str(myFloat)
        if verbose:
            logging.info("From rmc_ipc.py, receive, returning signal: " + str(signal))
            logging.info("From rmc_ipc.py, receive, returning value: " + str(value))
        myTuple = (signal, value)

        return myTuple
