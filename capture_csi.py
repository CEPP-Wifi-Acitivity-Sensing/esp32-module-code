#!/usr/bin/env python3
# -*-coding:utf-8-*-

# SPDX-FileCopyrightText: 2021-2025 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
#

# WARNING: we don't check for Python build-time dependencies until
# check_environment() function below. If possible, avoid importing
# any external libraries here - put in external script, or import in
# their specific function instead.

import sys
import csv
import json
import argparse
import serial
import time
from io import StringIO

DATA_COLUMNS_NAMES_C5C6 = ['type', 'id', 'mac', 'rssi', 'rate','noise_floor','fft_gain','agc_gain', 'channel', 'local_timestamp',  'sig_len', 'rx_state', 'len', 'first_word', 'data', 'runtime_s']
DATA_COLUMNS_NAMES = ['type', 'id', 'mac', 'rssi', 'rate', 'sig_mode', 'mcs', 'bandwidth', 'smoothing', 'not_sounding', 'aggregation', 'stbc', 'fec_coding',
                      'sgi', 'noise_floor', 'ampdu_cnt', 'channel', 'secondary_channel', 'local_timestamp', 'ant', 'sig_len', 'rx_state', 'len', 'first_word', 'data', 'runtime_s']

def csi_data_read_parse(port: str, csv_writer, log_file_fd):
    start_time = time.monotonic()
    serial_port = serial.Serial(port=port, baudrate=921600, bytesize=8, parity='N', stopbits=1)
    count = 0

    if not serial_port.is_open:
        print('open failed')
        return

    print('open success')
    while True:
        line = serial_port.readline()
        if not line:
            break

        strings = line.decode('utf-8', errors='replace').strip()
        if 'CSI_DATA' not in strings:
            log_file_fd.write(strings + '\n')
            log_file_fd.flush()
            continue

        csi_data = next(csv.reader(StringIO(strings)))
        expected_len = len(DATA_COLUMNS_NAMES) - 1
        c5c6_len = len(DATA_COLUMNS_NAMES_C5C6) - 1
        if len(csi_data) != expected_len and len(csi_data) != c5c6_len:
            print('element number is not equal', len(csi_data), expected_len)
            log_file_fd.write('element number is not equal\n')
            log_file_fd.write(strings + '\n')
            log_file_fd.flush()
            continue

        csi_data_len = int(csi_data[-3])
        try:
            csi_raw_data = json.loads(csi_data[-1])
        except json.JSONDecodeError:
            print('data is incomplete')
            log_file_fd.write('data is incomplete\n')
            log_file_fd.write(strings + '\n')
            log_file_fd.flush()
            continue

        if csi_data_len != len(csi_raw_data):
            print('csi_data_len is not equal', csi_data_len, len(csi_raw_data))
            log_file_fd.write('csi_data_len is not equal\n')
            log_file_fd.write(strings + '\n')
            log_file_fd.flush()
            continue

        runtime_s = time.monotonic() - start_time
        csi_data.append(runtime_s)
        csv_writer.writerow(csi_data)
        count += 1

        subcarrier_count = csi_data_len // 2
        if subcarrier_count < 30:
            print(f'warning: only {subcarrier_count} complex subcarriers captured')

        if count == 1:
            print(f'capturing CSI: {csi_data_len} bytes, {subcarrier_count} complex subcarriers')

        if count % 100 == 0:
            measured_hz = count / runtime_s if runtime_s > 0 else 0.0
            print(f'packet={csi_data[1]} runtime_s={runtime_s:.3f} rssi={csi_data[3]} '
                  f'subcarriers={subcarrier_count} rate={measured_hz:.1f} Hz count={count}')

    serial_port.close()


if __name__ == '__main__':
    if sys.version_info < (3, 6):
        print('Python version should be >= 3.6')
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description='Read CSI data from the serial receiver and save it as CSV')
    parser.add_argument('-p', '--port', dest='port', action='store', required=True,
                        help='Serial port of the CSI receiver device')
    parser.add_argument('-s', '--store', dest='store_file', action='store', default='./csi_data.csv',
                        help='CSV output file')
    parser.add_argument('-l', '--log', dest='log_file', action='store', default='./csi_data_log.txt',
                        help='Log file for non-CSI and malformed serial data')

    args = parser.parse_args()

    with open(args.store_file, 'w', newline='', encoding='utf-8') as csv_file, \
            open(args.log_file, 'w', encoding='utf-8') as log_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(DATA_COLUMNS_NAMES)
        try:
            csi_data_read_parse(args.port, csv_writer, log_file)
        except KeyboardInterrupt:
            print('\nCapture stopped')
        except serial.SerialException as exc:
            print(f'Serial error: {exc}')
