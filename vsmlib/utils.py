def parse_signal_num_file(filename):
    signal_to_num = {}
    vsi_version = -1
    try:
        with open(filename) as signal_to_num_file:
            lines = signal_to_num_file.readlines()
            for line in lines:
                line_stripped = line.strip()
                if vsi_version < 0:
                    try:
                        vsi_version = float(line_stripped)
                    except ValueError as err:
                        print("failed to parse VSI file version number from " \
                                "line: {}: {}".format(line, err),
                                file=sys.stderr)
                        exit(1)
                else:
                    try:
                        signal, signum_str = line_stripped.split(" ")
                        signal = signal.strip()
                        signum = int(signum_str.strip())
                        signal_to_num[signal] = signum
                    except ValueError as err:
                        print("malformed signal number file line: line: {}: " \
                                "{}".format(line, err), file=sys.stderr)
                        exit(1)
    except Exception as file_err:
        print("failed to open signal number file: {}".format(file_err),
                file=sys.stderr)
        exit(1)

    return signal_to_num, vsi_version
