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
import pandas as pd
import numpy as np

import serial
from os import path
from io import StringIO

from PyQt5.Qt import *
from pyqtgraph import PlotWidget
from PyQt5 import QtCore
import pyqtgraph as pg
from pyqtgraph import ScatterPlotItem
from PyQt5.QtCore import pyqtSignal, QThread
import threading
import time
from scipy.optimize import minimize
import matplotlib.pyplot as plt
from scipy.stats import linregress
import statsmodels.api as sm

# Reduce displayed waveforms to avoid display freezes
CSI_VAID_SUBCARRIER_INTERVAL = 4
csi_vaid_subcarrier_len =0
DEFAULT_SERIAL_BAUDRATE = 1500000
DEFAULT_PLOT_INTERVAL_MS = 250
DEFAULT_FPS_REPORT_INTERVAL = 100

CSI_DATA_INDEX = 200  # buffer size
CSI_DATA_COLUMNS = 490
DATA_COLUMNS_NAMES_C5C6 = ['type', 'id', 'mac', 'rssi', 'rate','noise_floor','fft_gain','agc_gain', 'channel', 'local_timestamp',  'sig_len', 'rx_state', 'len', 'first_word', 'data']
DATA_COLUMNS_NAMES = ['type', 'id', 'mac', 'rssi', 'rate', 'sig_mode', 'mcs', 'bandwidth', 'smoothing', 'not_sounding', 'aggregation', 'stbc', 'fec_coding',
                      'sgi', 'noise_floor', 'ampdu_cnt', 'channel', 'secondary_channel', 'local_timestamp', 'ant', 'sig_len', 'rx_state', 'len', 'first_word', 'data']

csi_data_array = np.zeros(
    [CSI_DATA_INDEX, CSI_DATA_COLUMNS], dtype=np.float64)
csi_data_phase = np.zeros([CSI_DATA_INDEX, CSI_DATA_COLUMNS], dtype=np.float64)
csi_data_complex = np.zeros([CSI_DATA_INDEX, CSI_DATA_COLUMNS], dtype=np.complex64)
agc_gain_data = np.zeros([CSI_DATA_INDEX], dtype=np.float64)
fft_gain_data = np.zeros([CSI_DATA_INDEX], dtype=np.float64)
fft_gains = []
agc_gains = []

class csi_data_graphical_window(QWidget):
    def __init__(self, plot_interval_ms: int = DEFAULT_PLOT_INTERVAL_MS):
        super().__init__()

        self.resize(1280, 900)

        self.plotWidget_ted = PlotWidget(self)
        self.plotWidget_ted.setGeometry(QtCore.QRect(0, 0, 640, 300))
        self.plotWidget_ted.setYRange(-2*np.pi, 2*np.pi)
        self.plotWidget_ted.addLegend()
        self.plotWidget_ted.setTitle('Phase Data - Last Frame')  # 添加标题
        self.plotWidget_ted.setLabel('left', 'Phase (rad)')  # Y轴标签
        self.plotWidget_ted.setLabel('bottom', 'Subcarrier Index')  # X轴标签

        self.csi_amplitude_array = np.abs(csi_data_complex)
        self.csi_phase_array = np.angle(csi_data_complex)
        self.curve = self.plotWidget_ted.plot([], name='CSI Row Data', pen='r')

        self.plotWidget_multi_data = PlotWidget(self)
        self.plotWidget_multi_data.setGeometry(QtCore.QRect(0, 300, 1280, 300))
        self.plotWidget_multi_data.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis)
        self.plotWidget_multi_data.addLegend()
        self.plotWidget_multi_data.setTitle('Subcarrier Amplitude Data')  # 添加标题
        self.plotWidget_multi_data.setLabel('left', 'Amplitude')  # Y轴标签
        self.plotWidget_multi_data.setLabel('bottom', 'Time (Cumulative Packet Count)')  # X轴标签

        self.curve_list = []
        agc_curve = self.plotWidget_multi_data.plot(
            agc_gain_data, name='AGC Gain', pen=[255,255,0])
        fft_curve = self.plotWidget_multi_data.plot(
            fft_gain_data, name='FFT Gain', pen=[255,255,0])
        self.curve_list.append(agc_curve)
        self.curve_list.append(fft_curve)

        for i in range(CSI_DATA_COLUMNS):
            curve = self.plotWidget_multi_data.plot(
                self.csi_amplitude_array[:, i], name=str(i), pen=(255, 255, 255))
            self.curve_list.append(curve)



        self.plotWidget_phase_data = PlotWidget(self)
        self.plotWidget_phase_data.setGeometry(QtCore.QRect(0, 600, 1280, 300))
        self.plotWidget_phase_data.getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis)
        self.plotWidget_phase_data.addLegend()
        self.plotWidget_multi_data.setTitle('Subcarrier Phase Data')  # 添加标题
        self.plotWidget_multi_data.setLabel('left', 'Phase (rad)')  # Y轴标签
        self.plotWidget_multi_data.setLabel('bottom', 'Time (Cumulative Packet Count)')  # X轴标签


        self.curve_phase_list = []
        for i in range(CSI_DATA_COLUMNS):
            phase_curve = self.plotWidget_phase_data.plot(
                np.angle(self.csi_amplitude_array[:, i]), name=str(i), pen=(255, 255, 255))
            self.curve_phase_list.append(phase_curve)


        # IQ 图窗口
        self.plotWidget_iq = PlotWidget(self)
        self.plotWidget_iq.setGeometry(QtCore.QRect(640, 0, 640, 300))
        self.plotWidget_iq.setLabel('left', 'Q (Imag)')
        self.plotWidget_iq.setLabel('bottom', 'I (Real)')
        self.plotWidget_iq.setTitle('IQ Plot - Last Frame')
        view_box = self.plotWidget_iq.getViewBox()
        view_box.setRange(QtCore.QRectF(-30, -30, 60, 60))  # 可以调整范围的大小，保证原点在中间

        self.plotWidget_iq.getViewBox().setAspectLocked(True)
        self.iq_scatter = ScatterPlotItem(size=6)
        self.plotWidget_iq.addItem(self.iq_scatter)

        self.iq_colors = []



        self.timer = pg.QtCore.QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(plot_interval_ms)
        self.deta_len = 0

    def update_curve_colors(self, color_list):
        self.deta_len = len(color_list)
        self.iq_colors = color_list
        self.plotWidget_ted.setXRange(0, self.deta_len//2)
        for i in range(0, self.deta_len, CSI_VAID_SUBCARRIER_INTERVAL):
            self.curve_list[i + 2].setPen(color_list[i])
            self.curve_phase_list[i].setPen(color_list[i])

    def update_data(self):

        i = np.real(csi_data_complex[-1, :])
        q = np.imag(csi_data_complex[-1, :])

        points = []
        for idx in range(self.deta_len):
            if idx < len(self.iq_colors):
                color = self.iq_colors[idx]
            else:
                color = (200, 200, 200)
            points.append({'pos': (i[idx], q[idx]), 'brush': pg.mkBrush(color)})

        self.iq_scatter.setData(points)


        self.csi_amplitude_array = np.abs(csi_data_complex)
        self.csi_phase_array = np.angle(csi_data_complex)
        self.csi_row_data = self.csi_phase_array[-1, :]

        self.curve.setData(self.csi_row_data)

        self.curve_list[0].setData(agc_gain_data)
        self.curve_list[1].setData(fft_gain_data)

        for i in range(0, CSI_DATA_COLUMNS, CSI_VAID_SUBCARRIER_INTERVAL):
            self.curve_list[i + 2].setData(self.csi_amplitude_array[:, i])
            self.curve_phase_list[i].setData(self.csi_phase_array[:, i])

def generate_subcarrier_colors(red_range, green_range, yellow_range, total_num,interval=1):
    colors = []
    for i in range(total_num):
        if red_range and red_range[0] <= i <= red_range[1]:
            intensity = int(255 * (i - red_range[0]) / (red_range[1] - red_range[0]))
            colors.append((intensity, 0, 0))
        elif green_range and green_range[0] <= i <= green_range[1]:
            intensity = int(255 * (i - green_range[0]) / (green_range[1] - green_range[0]))
            colors.append((0, intensity, 0))
        elif yellow_range and yellow_range[0] <= i <= yellow_range[1]:
            intensity = int(255 * (i - yellow_range[0]) / (yellow_range[1] - yellow_range[0]))
            colors.append((0, intensity, intensity))
        else:
            colors.append((200, 200, 200))

    return colors


def csi_data_read_parse(port: str, baudrate: int, csv_writer, log_file_fd, callback=None,
                        enable_plot_processing: bool = True, fps_report_interval: int = DEFAULT_FPS_REPORT_INTERVAL):
    global fft_gains, agc_gains
    serial_dev = serial.Serial(port=port, baudrate=baudrate, bytesize=8, parity='N', stopbits=1, timeout=1)
    count =0
    capture_start_time = None
    frame_count = 0
    perf_window_start = None
    first_device_timestamp = None
    last_device_timestamp = None
    if serial_dev.isOpen():
        print('open success')
    else:
        print('open failed')
        return
    while True:
        line = serial_dev.readline()
        if not line:
            break
        strings = line.decode('utf-8', errors='ignore').strip()
        index = strings.find('CSI_DATA')

        if index == -1:
            log_file_fd.write(strings + '\n')
            log_file_fd.flush()
            continue

        csv_reader = csv.reader(StringIO(strings))
        csi_data = next(csv_reader)
        csi_data_len = int (csi_data[-3])
        if len(csi_data) != len(DATA_COLUMNS_NAMES) and len(csi_data) != len(DATA_COLUMNS_NAMES_C5C6):
            print('element number is not equal',len(csi_data),len(DATA_COLUMNS_NAMES) )
            # print(csi_data)
            log_file_fd.write('element number is not equal\n')
            log_file_fd.write(strings + '\n')
            log_file_fd.flush()
            continue

        try:
            csi_raw_data = json.loads(csi_data[-1])
        except json.JSONDecodeError:
            print('data is incomplete')
            log_file_fd.write('data is incomplete\n')
            log_file_fd.write(strings + '\n')
            log_file_fd.flush()
            continue
        if csi_data_len != len(csi_raw_data):
            print('csi_data_len is not equal',csi_data_len,len(csi_raw_data))
            log_file_fd.write('csi_data_len is not equal\n')
            log_file_fd.write(strings + '\n')
            log_file_fd.flush()
            continue

        fft_gain = int(csi_data[6])
        agc_gain = int(csi_data[7])
        ts_index = 9 if len(csi_data) == len(DATA_COLUMNS_NAMES_C5C6) else 18
        device_timestamp = int(csi_data[ts_index])
        if first_device_timestamp is None:
            first_device_timestamp = device_timestamp
        last_device_timestamp = device_timestamp

        fft_gains.append(fft_gain)
        agc_gains.append(agc_gain)

        if capture_start_time is None:
            capture_start_time = time.perf_counter()
        runtime_s = time.perf_counter() - capture_start_time

        csi_data.append(f'{runtime_s:.6f}')

        csv_writer.writerow(csi_data)

        frame_count += 1
        if perf_window_start is None:
            perf_window_start = time.perf_counter()
        elif frame_count % fps_report_interval == 0:
            now = time.perf_counter()
            host_window_s = now - perf_window_start
            host_fps = fps_report_interval / host_window_s if host_window_s > 0 else 0.0
            device_elapsed_ms = (last_device_timestamp - first_device_timestamp) if first_device_timestamp is not None else 0
            device_fps = (frame_count / (device_elapsed_ms / 1000.0)) if device_elapsed_ms > 0 else 0.0
            print(f'[stats] frames={frame_count} host_fps={host_fps:.2f} device_fps={device_fps:.2f}')
            perf_window_start = now

        if enable_plot_processing:
            # Rotate data to the left
            csi_data_complex[:-1] = csi_data_complex[1:]
            agc_gain_data[:-1] = agc_gain_data[1:]
            fft_gain_data[:-1] = fft_gain_data[1:]
            agc_gain_data[-1] = agc_gain
            fft_gain_data[-1] = fft_gain

        if count ==0 and callback is not None:
            count = 1
            print('none',csi_data_len)
            if csi_data_len == 106:
                colors = generate_subcarrier_colors((0,25), (27,53), None, len(csi_raw_data))
            elif  csi_data_len == 114:
                colors = generate_subcarrier_colors((0,27), (29,56), None, len(csi_raw_data))
            elif  csi_data_len == 52:
                colors = generate_subcarrier_colors((0,12), (13,26), None, len(csi_raw_data))
            elif  csi_data_len == 234 :
                colors = generate_subcarrier_colors((0,28), (29,56), (60,116), len(csi_raw_data))
            elif  csi_data_len == 228 :
                colors = generate_subcarrier_colors((0,28), (29,57), (57,113), len(csi_raw_data))
            elif  csi_data_len == 490 :
                colors = generate_subcarrier_colors((0,61), (62,122), (123,245), len(csi_raw_data))
            elif  csi_data_len == 128 :
                colors = generate_subcarrier_colors((0,31), (32,63), None, len(csi_raw_data))
            elif  csi_data_len == 256 :
                colors = generate_subcarrier_colors((0,32), (32,63), (64,128), len(csi_raw_data))
            elif  csi_data_len == 512 :
                colors = generate_subcarrier_colors((0,63), (64,127), (128,256), len(csi_raw_data))
            elif  csi_data_len == 384 :
                colors = generate_subcarrier_colors((0,63), (64,127), (128,192), len(csi_raw_data))
            elif csi_data_len > 0 and csi_data_len <= 612:
                raw_len = len(csi_raw_data)
                colors = generate_subcarrier_colors((0,raw_len//2), (raw_len//2+1,raw_len-1), None, raw_len)
            callback(colors)

        if enable_plot_processing:
            for i in range(csi_data_len // 2):
                csi_data_complex[-1][i] = complex(csi_raw_data[i * 2 + 1],
                                                csi_raw_data[i * 2])
    serial_dev.close()
    return


class SubThread (QThread):
    data_ready = pyqtSignal(object)
    def __init__(self, serial_port, baudrate, save_file_name, log_file_name, fps_report_interval):
        super().__init__()
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.fps_report_interval = fps_report_interval

        save_file_fd = open(save_file_name, 'w', newline='', buffering=1024 * 1024)
        self.log_file_fd = open(log_file_name, 'w')
        self.csv_writer = csv.writer(save_file_fd)
        self.csv_writer.writerow(DATA_COLUMNS_NAMES + ['runtime_s'])

    def run(self):
        csi_data_read_parse(self.serial_port, self.baudrate, self.csv_writer, self.log_file_fd,
                            callback=self.data_ready.emit, enable_plot_processing=True,
                            fps_report_interval=self.fps_report_interval)

    def __del__(self):
        self.wait()
        self.log_file_fd.close()


if __name__ == '__main__':
    if sys.version_info < (3, 6):
        print(' Python version should >= 3.6')
        exit()

    parser = argparse.ArgumentParser(
        description='Read CSI data from serial port and display it graphically')
    parser.add_argument('-p', '--port', dest='port', action='store', required=True,
                        help='Serial port number of csv_recv device')
    parser.add_argument('-s', '--store', dest='store_file', action='store', default='./csi_data.csv',
                        help='Save the data printed by the serial port to a file') 
    parser.add_argument('-l', '--log', dest='log_file', action='store', default='./csi_data_log.txt',
                        help='Save other serial data the bad CSI data to a log file')
    parser.add_argument('-b', '--baudrate', dest='baudrate', action='store', type=int,
                        default=DEFAULT_SERIAL_BAUDRATE,
                        help='Serial baudrate (must match ESP-IDF monitor UART baudrate)')
    parser.add_argument('--headless', action='store_true',
                        help='Run capture without Qt visualization for higher throughput')
    parser.add_argument('--fps-report-interval', dest='fps_report_interval', action='store', type=int,
                        default=DEFAULT_FPS_REPORT_INTERVAL,
                        help='Frames between host/device FPS diagnostic prints')
    parser.add_argument('--plot-interval-ms', dest='plot_interval_ms', action='store', type=int,
                        default=DEFAULT_PLOT_INTERVAL_MS,
                        help='Qt plot refresh period in milliseconds')
    parser.add_argument('--plot-stride', dest='plot_stride', action='store', type=int, default=CSI_VAID_SUBCARRIER_INTERVAL,
                        help='Only refresh every Nth subcarrier in GUI mode')

    args = parser.parse_args()
    serial_port = args.port
    file_name = args.store_file
    log_file_name = args.log_file
    baudrate = args.baudrate
    fps_report_interval = max(1, args.fps_report_interval)
    CSI_VAID_SUBCARRIER_INTERVAL = max(1, args.plot_stride)

    if args.headless:
        with open(file_name, 'w', newline='', buffering=1024 * 1024) as save_file_fd, open(log_file_name, 'w') as log_file_fd:
            csv_writer = csv.writer(save_file_fd)
            csv_writer.writerow(DATA_COLUMNS_NAMES + ['runtime_s'])
            csi_data_read_parse(serial_port, baudrate, csv_writer, log_file_fd,
                                callback=None, enable_plot_processing=False,
                                fps_report_interval=fps_report_interval)
    else:
        app = QApplication(sys.argv)

        subthread = SubThread(serial_port, baudrate, file_name, log_file_name, fps_report_interval)

        window = csi_data_graphical_window(plot_interval_ms=max(50, args.plot_interval_ms))
        subthread.data_ready.connect(window.update_curve_colors)
        subthread.start()
        window.show()

        sys.exit(app.exec())
