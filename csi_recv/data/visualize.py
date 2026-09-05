import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import ast

# Load CSV
file_path = "data/raw/1_empty_room.csv"
df = pd.read_csv(file_path)
print("Number of packets:", len(df))
print("Columns:")
print(df.columns.tolist())

# Use runtime_s column if available
if 'runtime_s' in df.columns:
    timestamps = pd.to_numeric(df['runtime_s'], errors='coerce')
    is_runtime_seconds = True
else:
    last_col = df.columns[-1]
    try:
        timestamps = pd.to_datetime(df[last_col])
    except Exception:
        timestamps = df[last_col].astype(str)
    is_runtime_seconds = False

def _format_timestamp_value(tv, is_runtime_seconds=False):
    try:
        if tv is None or (isinstance(tv, float) and np.isnan(tv)):
            return 'NaN'
        if isinstance(tv, (int, float, np.integer, np.floating)):
            s = f"{tv:.3f}"
            return f"{s} s" if is_runtime_seconds else s
        if hasattr(tv, 'strftime'):
            return tv.strftime("%Y-%m-%d %H:%M:%S")
        f = float(tv)
        s = f"{f:.3f}"
        return f"{s} s" if is_runtime_seconds else s
    except Exception:
        return str(tv)

def set_pkt_ts_xticks(ax, timestamps, max_ticks=10, is_runtime_seconds=False):
    n = len(timestamps)
    if n == 0:
        return
    tick_idxs = np.linspace(0, n - 1, min(max_ticks, n), dtype=int)
    tick_labels = []
    for i in tick_idxs:
        t = timestamps.iloc[i] if hasattr(timestamps, 'iloc') else timestamps[i]
        t_str = _format_timestamp_value(t, is_runtime_seconds=is_runtime_seconds)
        tick_labels.append(f"packet number: {i}\n time: {t_str}")
    ax.set_xticks(tick_idxs)
    ax.set_xticklabels(tick_labels, rotation=45, ha='right')

# Convert CSI string to array
csi_data = []
for value in df['data']:
    csi = ast.literal_eval(value)
    csi_data.append(csi)
csi_data = np.array(csi_data)
print("CSI raw shape:", csi_data.shape)

# Remove first 12 values
csi_payload = csi_data[:, 12:]
print("CSI payload shape:", csi_payload.shape)

# I/Q to amplitude
I = csi_payload[:, 0::2]
Q = csi_payload[:, 1::2]
amplitude = np.sqrt(I**2 + Q**2)
print("Amplitude shape:", amplitude.shape)

# GRAPH 1: mean amplitude
mean_amplitude = np.mean(amplitude, axis=1)
plt.figure(figsize=(12,5))
plt.plot(np.arange(len(mean_amplitude)), mean_amplitude)
plt.title(f"{file_path} - Average CSI Amplitude")
plt.xlabel("Packet Number / Timestamp")
plt.ylabel("Average Amplitude")
plt.grid()
set_pkt_ts_xticks(plt.gca(), timestamps, is_runtime_seconds=is_runtime_seconds)
plt.show()

# GRAPH 2: selected subcarriers
plt.figure(figsize=(12,6))
selected_subcarriers = [10,30,60,100,150]
x = np.arange(amplitude.shape[0])
for sc in selected_subcarriers:
    if sc < amplitude.shape[1]:
        plt.plot(x, amplitude[:, sc], label=f"Subcarrier {sc}")
plt.title(f"{file_path} - CSI Amplitude of Selected Subcarriers")
plt.xlabel("Packet Number / Timestamp")
plt.ylabel("Amplitude")
plt.legend()
plt.grid()
set_pkt_ts_xticks(plt.gca(), timestamps, is_runtime_seconds=is_runtime_seconds)
plt.show()

# GRAPH 3: heatmap
plt.figure(figsize=(14,6))
plt.imshow(amplitude.T, aspect="auto", interpolation="nearest")
plt.colorbar(label="Amplitude")
plt.title(f"{file_path} - CSI Amplitude Heatmap")
plt.xlabel("Packet Number / Timestamp")
plt.ylabel("Subcarrier Index")
set_pkt_ts_xticks(plt.gca(), timestamps, is_runtime_seconds=is_runtime_seconds)
plt.show()

# GRAPH 4: RSSI
plt.figure(figsize=(12,5))
plt.plot(np.arange(len(df)), df['rssi'])
plt.title(f"{file_path} - RSSI")
plt.xlabel("Packet Number / Timestamp")
plt.ylabel("RSSI (dBm)")
plt.grid()
set_pkt_ts_xticks(plt.gca(), timestamps, is_runtime_seconds=is_runtime_seconds)
plt.show()

# GRAPH 5: spectrogram
from scipy.signal import spectrogram
frequencies, times, Sxx = spectrogram(mean_amplitude, fs=1, nperseg=64, noverlap=32)
plt.figure(figsize=(14,6))
plt.pcolormesh(times, frequencies, 10 * np.log10(Sxx + 1e-10), shading="gouraud")
plt.colorbar(label="Power (dB)")
plt.title(f"{file_path} - CSI Spectrogram")
plt.xlabel("Time")
plt.ylabel("Frequency")
plt.show()