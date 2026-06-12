#!/usr/bin/env python3
"""Log SmokeLens JSON readings from a POSIX serial port into segmented CSV."""

import argparse
import csv
import glob
import json
import os
from pathlib import Path
import select
import termios
from datetime import datetime, timezone


COLUMNS = [
    "received_at_iso",
    "segment_id",
    "node_id",
    "timestamp",
    "mode",
    "collection_label",
    "inference_class",
    "cigarette_detected",
    "inference_score",
    "model_version",
    "voc_raw",
    "co_raw",
    "voc_mv",
    "co_mv",
    "pm1_0",
    "pm2_5",
    "pm10",
    "temperature",
    "humidity",
    "pms_valid",
    "button_mode_data_collection",
    "button_cooking_fume",
    "button_vehicle_exhaust",
    "button_cigarette_smoke",
    "button_led_cigarette",
    "raw_json",
]

BAUD_RATES = {
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
}


def safe_name(value):
    text = str(value or "unknown")
    return "".join(character if character.isalnum() or character in "_.-" else "_" for character in text)


def segment_info(reading):
    node_id = str(reading.get("node_id") or "unknown_node")
    mode = str(reading.get("mode") or "unknown_mode")
    label = reading.get("collection_label") if mode == "data_collection" else "inference"
    label = str(label or "unlabeled")
    return (node_id, mode, label)


def open_segment(output_dir, info):
    now = datetime.now()
    segment_id = now.strftime("%Y%m%d_%H%M%S")
    node_id, mode, label = info
    filename = f"{segment_id}_{safe_name(node_id)}_{safe_name(mode)}_{safe_name(label)}.csv"
    path = output_dir / filename
    output_dir.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=COLUMNS)
    writer.writeheader()
    handle.flush()
    print(f"# opened segment: {path}")
    return {"id": segment_id, "path": path, "handle": handle, "writer": writer, "rows": 0}


def close_segment(segment):
    if not segment:
        return
    segment["handle"].close()
    print(f"# closed segment: {segment['path']} rows={segment['rows']}")


def configure_serial(file_descriptor, baud_rate):
    if baud_rate not in BAUD_RATES:
        raise ValueError(f"unsupported baud rate: {baud_rate}")

    attributes = termios.tcgetattr(file_descriptor)
    attributes[0] = termios.IGNPAR
    attributes[1] = 0
    attributes[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attributes[3] = 0
    attributes[4] = BAUD_RATES[baud_rate]
    attributes[5] = BAUD_RATES[baud_rate]
    attributes[6][termios.VMIN] = 0
    attributes[6][termios.VTIME] = 10
    termios.tcsetattr(file_descriptor, termios.TCSANOW, attributes)
    termios.tcflush(file_descriptor, termios.TCIFLUSH)


def reading_row(reading, segment, raw_json):
    buttons = reading.get("buttons") or {}
    return {
        "received_at_iso": datetime.now(timezone.utc).astimezone().isoformat(),
        "segment_id": segment["id"],
        "node_id": reading.get("node_id"),
        "timestamp": reading.get("timestamp"),
        "mode": reading.get("mode"),
        "collection_label": reading.get("collection_label"),
        "inference_class": reading.get("inference_class"),
        "cigarette_detected": reading.get("cigarette_detected"),
        "inference_score": reading.get("inference_score"),
        "model_version": reading.get("model_version"),
        "voc_raw": reading.get("voc_raw"),
        "co_raw": reading.get("co_raw"),
        "voc_mv": reading.get("voc_mv"),
        "co_mv": reading.get("co_mv"),
        "pm1_0": reading.get("pm1_0"),
        "pm2_5": reading.get("pm2_5"),
        "pm10": reading.get("pm10"),
        "temperature": reading.get("temperature"),
        "humidity": reading.get("humidity"),
        "pms_valid": reading.get("pms_valid"),
        "button_mode_data_collection": buttons.get("mode_data_collection"),
        "button_cooking_fume": buttons.get("cooking_fume"),
        "button_vehicle_exhaust": buttons.get("vehicle_exhaust"),
        "button_cigarette_smoke": buttons.get("cigarette_smoke"),
        "button_led_cigarette": buttons.get("led_cigarette"),
        "raw_json": raw_json,
    }


def log_serial(port, baud_rate, output_dir):
    file_descriptor = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    configure_serial(file_descriptor, baud_rate)
    segment = None
    current_info = None
    buffer = b""

    print(f"# listening on {port} at {baud_rate} baud")
    print(f"# output dir: {output_dir}")
    print("# close Arduino Serial Monitor before running this logger")
    print("# press Ctrl+C to stop")

    try:
        while True:
            readable, _, _ = select.select([file_descriptor], [], [], 1.0)
            if not readable:
                continue
            chunk = os.read(file_descriptor, 4096)
            if not chunk:
                continue
            buffer += chunk

            while b"\n" in buffer:
                raw_line, buffer = buffer.split(b"\n", 1)
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if not line.startswith("{"):
                    print(line)
                    continue
                try:
                    reading = json.loads(line)
                except json.JSONDecodeError:
                    print(f"# skipped invalid JSON: {line}")
                    continue

                info = segment_info(reading)
                if info != current_info:
                    close_segment(segment)
                    segment = open_segment(output_dir, info)
                    current_info = info

                segment["writer"].writerow(reading_row(reading, segment, line))
                segment["handle"].flush()
                segment["rows"] += 1
                print(f"# logged {info[0]} {info[1]}/{info[2]} rows={segment['rows']}")
    except KeyboardInterrupt:
        print("\n# logger stopped")
    finally:
        close_segment(segment)
        os.close(file_descriptor)


def main():
    default_output = Path(__file__).resolve().parent.parent / "data" / "serial"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Serial device, for example /dev/cu.usbserial-130")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--output-dir", type=Path, default=default_output)
    parser.add_argument("--list-ports", action="store_true")
    args = parser.parse_args()

    if args.list_ports:
        ports = sorted(glob.glob("/dev/cu.*"))
        print("# serial ports:" if ports else "# no serial ports found")
        for port in ports:
            print(f"#   {port}")
        if not args.port:
            return

    if not args.port:
        parser.error("pass --port, for example --port /dev/cu.usbserial-130")

    log_serial(args.port, args.baud, args.output_dir)


if __name__ == "__main__":
    main()
