"""Remove isolated spikes from CSI CSV data.

The cleaner keeps every packet and all metadata unchanged. Only I/Q pairs
that are isolated outliers compared with nearby packets are replaced.
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np


def _local_median(values, radius):
	"""Return a centered rolling median using edge values at the boundaries."""
	padded = np.pad(values, ((radius, radius), (0, 0)), mode="edge")
	result = np.empty_like(values, dtype=float)
	for row in range(values.shape[0]):
		result[row] = np.median(padded[row : row + 2 * radius + 1], axis=0)
	return result


def _spike_mask(csi, radius, threshold):
	"""Find isolated I/Q spikes using a rolling median and MAD."""
	local_median = _local_median(csi, radius)
	residual = np.abs(csi - local_median)

	padded_residual = np.pad(
		residual, ((radius, radius), (0, 0)), mode="edge"
	)
	local_mad = np.empty_like(residual, dtype=float)
	for row in range(residual.shape[0]):
		window = padded_residual[row : row + 2 * radius + 1]
		local_mad[row] = np.median(window, axis=0)

	# CSI values are integer samples, so a one-count tolerance avoids
	# changing normal quantization noise when MAD is zero.
	scale = np.maximum(local_mad, 1.0)
	return residual > threshold * scale


def cleanse_csv(input_path, output_path, radius=3, threshold=6.0):
	"""Clean ``input_path`` and write a CSV with the same columns."""
	with input_path.open("r", newline="", encoding="utf-8") as source:
		reader = csv.DictReader(source)
		if not reader.fieldnames or "data" not in reader.fieldnames:
			raise ValueError("CSV must contain a data column")
		rows = list(reader)

	if not rows:
		output_path.parent.mkdir(parents=True, exist_ok=True)
		with output_path.open("w", newline="", encoding="utf-8") as target:
			csv.DictWriter(target, fieldnames=reader.fieldnames).writeheader()
		return 0

	parsed = [json.loads(row["data"]) for row in rows]
	lengths = {len(packet) for packet in parsed}
	if len(lengths) != 1 or next(iter(lengths)) % 2:
		raise ValueError("All data values must have the same even length")

	raw = np.asarray(parsed, dtype=float)
	mask = _spike_mask(raw, radius, threshold)
	pair_mask = mask[:, 0::2] | mask[:, 1::2]
	local_median = _local_median(raw, radius)
	cleaned = raw.copy()
	cleaned[:, 0::2][pair_mask] = local_median[:, 0::2][pair_mask]
	cleaned[:, 1::2][pair_mask] = local_median[:, 1::2][pair_mask]
	cleaned = np.rint(cleaned).astype(int)

	for row, packet in zip(rows, cleaned):
		row["data"] = json.dumps(packet.tolist(), separators=(",", ":"))

	output_path.parent.mkdir(parents=True, exist_ok=True)
	with output_path.open("w", newline="", encoding="utf-8") as target:
		writer = csv.DictWriter(target, fieldnames=reader.fieldnames)
		writer.writeheader()
		writer.writerows(rows)

	return int(pair_mask.sum())


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--input", required=True, type=Path, help="Raw CSI CSV")
	parser.add_argument("--output", type=Path, help="Cleaned CSV destination")
	parser.add_argument(
		"--radius",
		type=int,
		default=3,
		help="Packets on each side of the rolling window (default: 3)",
	)
	parser.add_argument(
		"--threshold",
		type=float,
		default=6.0,
		help="MAD multiplier; larger values remove fewer spikes (default: 6)",
	)
	args = parser.parse_args()

	if args.radius < 1 or args.threshold <= 0:
		parser.error("radius must be >= 1 and threshold must be > 0")

	output = args.output or args.input.with_name(f"{args.input.stem}_cleaned.csv")
	replaced = cleanse_csv(args.input, output, args.radius, args.threshold)
	print(f"Wrote {output} ({replaced} CSI I/Q pairs replaced)")


if __name__ == "__main__":
	main()
