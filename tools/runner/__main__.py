from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path

try:
    import serial
except ImportError:
    serial = None

START = 0xAA
MSG_HELLO = 0x01
MSG_TEST_META = 0x02
MSG_TEST_CHUNK = 0x03
MSG_INFER_RESULT = 0x04
MSG_ACK = 0x05
MSG_NACK = 0x06
MSG_FINISH = 0x07


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for x in data:
        crc ^= (x << 8)
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


def pack(msg_t: int, seq: int, payload: bytes = b"") -> bytes:
    hdr = bytes([msg_t]) + struct.pack("<HH", seq, len(payload))
    return bytes([START]) + hdr + payload + struct.pack("<H", crc16(hdr + payload))


def read_frame(s: serial.Serial, timeout_s: float = 2.0):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        b = s.read(1)
        if not b or b[0] != START:
            continue
        head = s.read(5)
        if len(head) != 5:
            continue
        msg_t = head[0]
        seq, ln = struct.unpack("<HH", head[1:])
        payload = s.read(ln)
        crc_b = s.read(2)
        if len(payload) != ln or len(crc_b) != 2:
            continue
        got = struct.unpack("<H", crc_b)[0]
        exp = crc16(bytes([msg_t]) + head[1:] + payload)
        if got != exp:
            continue
        return {"type": msg_t, "seq": seq, "payload": payload}
    return None


def decode_tensor(data: bytes, dtype: str):
    dtype = (dtype or "uint8").lower()
    if dtype in ("uint8", "uint8_t"):
        return list(data)
    if dtype in ("int8", "int8_t"):
        return list(struct.unpack(f"<{len(data)}b", data))
    if dtype in ("float32", "float", "f32"):
        n = len(data) // 4
        return list(struct.unpack(f"<{n}f", data[: n * 4]))
    if dtype in ("int32", "i32"):
        n = len(data) // 4
        return list(struct.unpack(f"<{n}i", data[: n * 4]))
    raise RuntimeError(f"Unsupported output dtype: {dtype}")


def build(fw_dir="mik32_tinyml_firmware"):
    subprocess.check_call([sys.executable, "-m", "platformio", "run"], cwd=fw_dir)


def flash(fw_dir="mik32_tinyml_firmware"):
    subprocess.check_call([sys.executable, "-m", "platformio", "run", "-t", "upload"], cwd=fw_dir)


def hello(s: serial.Serial, retries: int = 10, timeout_s: float = 0.5) -> bool:
    for attempt in range(retries):
        seq = attempt + 1
        s.write(pack(MSG_HELLO, seq, b""))
        s.flush()
        frame = read_frame(s, timeout_s=timeout_s)
        if frame and frame["type"] == MSG_ACK and frame["seq"] == seq:
            return True
        time.sleep(0.1)
    return False


def run_tests(port: str, test_file: str, out_json: str, baud=115200, output_dtype="uint8"):
    if serial is None:
        raise RuntimeError("pyserial is required: python -m pip install pyserial")
    b = Path(test_file).read_bytes()
    if b[:4] != b"MKT1":
        raise RuntimeError("Bad test format")
    count = int.from_bytes(b[6:10], "little")
    vec_len = int.from_bytes(b[10:12], "little")
    off = 12

    results = []
    with serial.Serial(port, baud, timeout=0.2, rtscts=False, dsrdtr=False) as s:
        s.setDTR(False)
        s.setRTS(False)
        time.sleep(0.3)
        s.reset_input_buffer()
        s.reset_output_buffer()

        if not hello(s):
            raise RuntimeError(
                "No HELLO ack; run probe, reflash firmware, and check --baud/serial port"
            )

        for i in range(count):
            seq = i + 2
            vec = b[off : off + vec_len]
            off += vec_len

            s.write(pack(MSG_TEST_META, seq, struct.pack("<H", len(vec))))
            meta_resp = read_frame(s)
            if not meta_resp or meta_resp["type"] != MSG_ACK:
                raise RuntimeError(f"No ACK for META seq={seq}")


            s.write(pack(MSG_TEST_CHUNK, seq, vec))
            infer = read_frame(s)
            finish = read_frame(s)
            if not infer or infer["type"] != MSG_INFER_RESULT:
                raise RuntimeError(f"No INFER_RESULT seq={seq}")
            if not finish or finish["type"] != MSG_FINISH:
                raise RuntimeError(f"No FINISH seq={seq}")

            duration_us = None
            payload = infer["payload"]
            if len(payload) >= 4:
                duration_us = struct.unpack("<I", payload[:4])[0]
                payload = payload[4:]
            logits = decode_tensor(payload, output_dtype)
            pred = max(range(len(logits)), key=lambda k: logits[k]) if logits else -1
            row = {"id": i, "prediction": pred, "logits": logits}
            if duration_us is not None:
                row["duration_us"] = duration_us
            results.append(row)

    Path(out_json).write_text(json.dumps({"count": count, "vec_len": vec_len, "output_dtype": output_dtype, "results": results}, indent=2))


def probe(port: str, baud=115200, seconds=3.0):
    if serial is None:
        raise RuntimeError("pyserial is required: python -m pip install pyserial")
    with serial.Serial(port, baud, timeout=0.1, rtscts=False, dsrdtr=False) as s:
        s.setDTR(False)
        s.setRTS(False)
        time.sleep(0.3)
        s.reset_input_buffer()
        s.reset_output_buffer()

        print(f"listening on {port} at {baud} for {seconds:.1f}s")
        t0 = time.time()
        raw = bytearray()
        while time.time() - t0 < seconds:
            chunk = s.read(256)
            if chunk:
                raw.extend(chunk)

        if raw:
            printable = bytes(raw).decode("ascii", errors="replace")
            print(f"raw[{len(raw)}] hex={bytes(raw).hex(' ')}")
            print(f"raw text: {printable!r}")
        else:
            print("raw: no bytes received")

        ok = hello(s)
        print(f"hello: {'ok' if ok else 'no ack'}")


def write_model_data(model_path: Path, out_c: Path):
    data = model_path.read_bytes()
    lines = [
        '#include "model_data.h"',
        "",
        "const uint8_t model_data[] = {",
    ]
    for i in range(0, len(data), 12):
        chunk = ", ".join(f"0x{x:02x}" for x in data[i : i + 12])
        lines.append(f"    {chunk},")
    lines.extend([
        "};",
        "const uint32_t model_data_len = sizeof(model_data);",
        "",
    ])
    out_c.write_text("\n".join(lines))


def inspect_npz(dataset_path: Path, npz_key=None, npz_label_key=None):
    if dataset_path.suffix.lower() != ".npz":
        return {"kind": "file", "path": str(dataset_path)}
    try:
        import numpy as np
    except Exception as exc:
        return {"kind": "npz", "error": f"numpy is required to inspect npz: {exc}"}

    loaded = np.load(dataset_path, allow_pickle=True)
    keys = list(loaded.files)

    def pick(preferred, fallback):
        if preferred:
            return preferred if preferred in loaded else None
        for key in fallback:
            if key in loaded:
                return key
        return keys[0] if keys else None

    input_key = pick(npz_key, ("x", "X", "features", "vectors", "images", "data", "inputs", "texts", "text", "arr_0"))
    label_key = pick(npz_label_key, ("y", "Y", "labels", "label", "target", "targets", "arr_1"))


    info = {"kind": "npz", "keys": keys, "input_key": input_key, "label_key": label_key}
    if input_key:
        arr = loaded[input_key]
        info["input_shape"] = list(arr.shape)
        info["input_dtype"] = str(arr.dtype)
        info["input_is_string"] = arr.dtype.kind in ("U", "S", "O")
        if not info["input_is_string"] and arr.ndim >= 1:
            sample_elements = int(arr[0].size) if arr.shape[0] else 0
            info["sample_input_bytes"] = sample_elements * int(arr.dtype.itemsize)
        if "metadata_json" in loaded:
            try:
                raw = loaded["metadata_json"].item()
                info["metadata_json"] = json.loads(str(raw))
            except Exception:
                info["metadata_json"] = str(loaded["metadata_json"])
    if label_key:
        labels = loaded[label_key]
        info["label_shape"] = list(labels.shape)
        info["label_dtype"] = str(labels.dtype)
        info["label_is_string"] = labels.dtype.kind in ("U", "S", "O")
    if "logits" in loaded:
        logits = loaded["logits"]
        info["output_shape"] = list(logits.shape)
        info["output_dtype"] = str(logits.dtype)
    return info

def inspect_tflite(model_path: Path):
    data = model_path.read_bytes()
    return {
        "path": str(model_path),
        "size_bytes": len(data),
        "is_tflite": data.find(b"TFL3", 0, 16) >= 0,
    }


def write_unsupported_report(run_dir: Path, model_info, dataset_info, reasons):
    fit = {
        "supported": False,
        "runtime": "tflite-micro",
        "model": model_info,
        "dataset": dataset_info,
        "reasons": reasons,
        "next_step": "Use a numeric dataset whose input tensor byte size matches the embedded TFLite model input.",
    }
    report = {
        "status": "unsupported",
        "accuracy": None,
        "latency_us": None,
        "fit": fit,
    }
    (run_dir / "fit.json").write_text(json.dumps(fit, indent=2))
    (run_dir / "report.json").write_text(json.dumps(report, indent=2))


def summarize(results_path: Path, manifest_path: Path | None, report_path: Path, csv_path: Path):
    data = json.loads(results_path.read_text())
    results = data["results"]
    labels = None
    if manifest_path and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        labels = manifest.get("labels")

    durations = [r["duration_us"] for r in results if "duration_us" in r]
    correct = None
    accuracy = None
    if labels:
        n = min(len(labels), len(results))
        correct = sum(1 for i in range(n) if int(labels[i]) == int(results[i]["prediction"]))
        accuracy = correct / n if n else None

    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "prediction", "label", "correct", "duration_us", "logits"])
        for r in results:
            label = labels[r["id"]] if labels and r["id"] < len(labels) else ""
            ok = int(label == r["prediction"]) if label != "" else ""
            writer.writerow([r["id"], r["prediction"], label, ok, r.get("duration_us", ""), r["logits"]])

    report = {
        "count": data["count"],
        "vec_len": data["vec_len"],
        "latency_us": {
            "min": min(durations) if durations else None,
            "max": max(durations) if durations else None,
            "avg": (sum(durations) / len(durations)) if durations else None,
            "median": sorted(durations)[len(durations) // 2] if durations else None,
        },
        "accuracy": accuracy,
        "correct": correct,
        "has_labels": labels is not None,
    }
    report_path.write_text(json.dumps(report, indent=2))
    return report


def run_pipeline(args):
    run_id = args.run_id or str(uuid.uuid4())
    run_dir = Path(args.runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    model_dst = run_dir / "model.tflite"
    dataset_dst = run_dir / Path(args.dataset).name
    shutil.copyfile(args.model, model_dst)
    shutil.copyfile(args.dataset, dataset_dst)


    model_info = inspect_tflite(model_dst)
    dataset_info = inspect_npz(dataset_dst, npz_key=args.npz_key, npz_label_key=args.npz_label_key)
    reasons = []
    if not model_info["is_tflite"]:
        reasons.append("model file does not look like a TFLite flatbuffer")
    if dataset_info.get("input_is_string"):
        reasons.append("dataset input is string; current board protocol/runtime expects fixed-size numeric byte vectors")
    if dataset_info.get("label_is_string"):
        reasons.append("dataset labels are strings; current metric code can only compare numeric class ids on board outputs")

    if reasons:
        write_unsupported_report(run_dir, model_info, dataset_info, reasons)
        print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "status": "unsupported", "reasons": reasons}, indent=2))
        raise SystemExit("Unsupported model/dataset for current firmware runtime")

    write_model_data(model_dst, Path(args.fw_dir) / "model" / "model_data.c")

    tests_path = run_dir / "tests.mktest"
    vec_len = args.vec_len
    if vec_len is None:
        vec_len = dataset_info.get("sample_input_bytes")
    if not vec_len:
        raise SystemExit("Cannot infer --vec-len from dataset; pass it explicitly")
    testgen_cmd = [
        sys.executable,
        "-m",
        "tools.testgen",
        "generate",
        "--input",
        str(dataset_dst),
        "--output",
        str(tests_path),
        "--vec-len",
        str(vec_len),
        "--count",
        str(args.count),
    ]
    if args.npz_key:
        testgen_cmd += ["--npz-key", args.npz_key]
    if args.npz_label_key:
        testgen_cmd += ["--npz-label-key", args.npz_label_key]
    subprocess.check_call(testgen_cmd)

    build(args.fw_dir)
    flash(args.fw_dir)

    results_path = run_dir / "results.json"
    output_dtype = args.output_dtype
    if output_dtype == "auto":
        output_dtype = dataset_info.get("output_dtype") or "uint8"
    run_tests(args.port, str(tests_path), str(results_path), baud=args.baud, output_dtype=output_dtype)

    report = summarize(
        results_path,
        tests_path.with_suffix(".manifest.json"),
        run_dir / "report.json",
        run_dir / "predictions.csv",
    )
    print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "report": report}, indent=2))


def model_info(args):
    info = {
        "model": inspect_tflite(Path(args.model)),
        "dataset": inspect_npz(Path(args.dataset), npz_key=args.npz_key, npz_label_key=args.npz_label_key) if args.dataset else None,
    }
    print(json.dumps(info, indent=2))


def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("build")
    sp.add_parser("flash")
    r = sp.add_parser("run-tests")
    r.add_argument("--port", required=True)
    r.add_argument("--tests", required=True)
    r.add_argument("--out", default="results.json")
    r.add_argument("--baud", type=int, default=int(os.getenv("MIK32_BAUD", "115200")))
    r.add_argument("--output-dtype", default="uint8", choices=("uint8", "int8", "float32", "int32"))
    pr = sp.add_parser("probe")
    pr.add_argument("--port", required=True)
    pr.add_argument("--baud", type=int, default=int(os.getenv("MIK32_BAUD", "115200")))
    pr.add_argument("--seconds", type=float, default=3.0)
    pipe = sp.add_parser("run-pipeline")
    pipe.add_argument("--model", required=True)
    pipe.add_argument("--dataset", required=True)
    pipe.add_argument("--port", required=True)
    pipe.add_argument("--baud", type=int, default=int(os.getenv("MIK32_BAUD", "115200")))
    pipe.add_argument("--count", type=int, default=32)
    pipe.add_argument("--vec-len", type=int)
    pipe.add_argument("--npz-key")
    pipe.add_argument("--npz-label-key")
    pipe.add_argument("--output-dtype", default="auto", choices=("auto", "uint8", "int8", "float32", "int32"))
    pipe.add_argument("--runs-dir", default="runs")
    pipe.add_argument("--run-id")
    pipe.add_argument("--fw-dir", default="mik32_tinyml_firmware")
    mi = sp.add_parser("model-info")
    mi.add_argument("--model", required=True)
    mi.add_argument("--dataset")
    mi.add_argument("--npz-key")
    mi.add_argument("--npz-label-key")
    a = p.parse_args()

    if a.cmd == "build":
        build()
    elif a.cmd == "flash":
        flash()
    elif a.cmd == "run-tests":
        run_tests(a.port, a.tests, a.out, baud=a.baud, output_dtype=a.output_dtype)
    elif a.cmd == "probe":
        probe(a.port, baud=a.baud, seconds=a.seconds)
    elif a.cmd == "run-pipeline":
        run_pipeline(a)
    else:
        model_info(a)


if __name__ == "__main__":
    main()