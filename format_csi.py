#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import savemat


def parse_csi(raw_values, representation):
    values = np.asarray(raw_values, dtype=np.float64)
    if values.size % 2 != 0:
        raise ValueError(f"CSI payload has an odd number of values: {values.size}")

    iq = values.reshape(-1, 2)
    complex_csi = iq[:, 0] + 1j * iq[:, 1]
    if representation == "magnitude":
        return np.abs(complex_csi)
    return complex_csi


def resample_subcarriers(csi, target_subcarriers):
    source_positions = np.arange(csi.size, dtype=np.float64)
    target_positions = np.linspace(0.0, csi.size - 1, target_subcarriers)
    if np.iscomplexobj(csi):
        real = np.interp(
            target_positions, source_positions, csi.real
        )
        imag = np.interp(
            target_positions, source_positions, csi.imag
        )
        return real + 1j * imag
    return np.interp(target_positions, source_positions, csi)


def estimate_source_hz(frame_table):
    if "runtime_s" not in frame_table.columns:
        return None

    runtime = pd.to_numeric(frame_table["runtime_s"], errors="coerce").dropna()
    if len(runtime) < 2:
        return None

    duration = runtime.iloc[-1] - runtime.iloc[0]
    if duration <= 0:
        return None
    return (len(runtime) - 1) / duration


def format_csv(input_file, output_file, frames_per_sample=5,
               subcarriers=30, representation="magnitude"):
    frame_table = pd.read_csv(input_file)
    if "data" not in frame_table.columns:
        raise ValueError("Input CSV must contain a 'data' column")

    subcarrier_frames = []
    for row_number, raw_json in enumerate(frame_table["data"], start=2):
        try:
            raw_values = json.loads(raw_json)
            subcarrier_frames.append(parse_csi(raw_values, representation))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid CSI data at CSV row {row_number}: {exc}"
            ) from exc

    if not subcarrier_frames:
        raise ValueError("Input CSV contains no CSI frames")

    subcarrier_counts = {frame.size for frame in subcarrier_frames}
    if len(subcarrier_counts) != 1:
        counts = ", ".join(str(count) for count in sorted(subcarrier_counts))
        raise ValueError(f"CSI frames have inconsistent subcarrier counts: {counts}")

    source_subcarriers = subcarrier_frames[0].size
    if subcarriers > source_subcarriers:
        raise ValueError(
            f"Cannot increase {source_subcarriers} subcarriers to {subcarriers}"
        )

    usable_frame_count = (
        len(subcarrier_frames) - len(subcarrier_frames) % frames_per_sample
    )
    if usable_frame_count == 0:
        raise ValueError(
            f"Need at least {frames_per_sample} CSI frames to create one sample"
        )

    samples = []
    for start in range(0, usable_frame_count, frames_per_sample):
        group = subcarrier_frames[start:start + frames_per_sample]
        resampled = np.stack([
            resample_subcarriers(frame, subcarriers)
            for frame in group
        ])

        # Wi-Pose shape: frame x subcarrier x TX antenna x RX antenna.
        mimo = np.repeat(resampled[:, :, None, None], 3, axis=2)
        mimo = np.repeat(mimo, 3, axis=3)
        samples.append(mimo)

    csi = np.stack(samples)
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() == ".npy":
        np.save(output_path, csi)
    elif output_path.suffix.lower() == ".npz":
        np.savez(output_path, CSI=csi)
    elif output_path.suffix.lower() == ".mat":
        savemat(output_path, {"CSI": csi}, long_field_names=True)
    else:
        raise ValueError("Output format must be .mat, .npz, or .npy")

    source_hz = estimate_source_hz(frame_table)
    output_hz = (
        source_hz / frames_per_sample if source_hz is not None else None
    )
    return csi, source_subcarriers, source_hz, output_hz


def main():
    parser = argparse.ArgumentParser(
        description="Convert ESP32 CSI CSV into Wi-Pose 5x30x3x3 samples"
    )
    parser.add_argument("input", nargs="?", default="csi.csv")
    parser.add_argument("-o", "--output", default="csi_wipose.mat")
    parser.add_argument("--frames", type=int, default=5)
    parser.add_argument("--subcarriers", type=int, default=30)
    parser.add_argument(
        "--representation",
        choices=("magnitude", "complex"),
        default="magnitude",
        help="Magnitude matches the real-valued example Wi-Pose MAT file",
    )
    args = parser.parse_args()

    if args.frames < 1:
        parser.error("--frames must be at least 1")
    if args.subcarriers < 1:
        parser.error("--subcarriers must be at least 1")

    csi, source_subcarriers, source_hz, output_hz = format_csv(
        args.input,
        args.output,
        frames_per_sample=args.frames,
        subcarriers=args.subcarriers,
        representation=args.representation,
    )

    print(f"Saved {csi.shape[0]} samples to {args.output}")
    print(f"CSI shape: {csi.shape}")
    print(
        f"Converted {source_subcarriers} subcarriers to "
        f"{args.subcarriers}; 1x1 replicated to 3x3"
    )
    if source_hz is not None:
        print(
            f"Measured input rate: {source_hz:.1f} Hz; "
            f"output sample rate: {output_hz:.1f} Hz"
        )


if __name__ == "__main__":
    main()
