import argparse
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

import serial

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


def build(fw_dir="mik32_tinyml_firmware"):
    subprocess.check_call([sys.executable, "-m", "platformio", "run"], cwd=fw_dir)


def flash(fw_dir="mik32_tinyml_firmware"):
    subprocess.check_call([sys.executable, "-m", "platformio", "run", "-t", "upload"], cwd=fw_dir)


def hello(s: serial.Serial, retries: int = 10, timeout_s: float = 0.5) -> bool:
    for attempt in range(retries):
        seq = attempt + 1
        s.reset_input_buffer()
        s.write(pack(MSG_HELLO, seq, b""))
        s.flush()
        frame = read_frame(s, timeout_s=timeout_s)
        if frame and frame["type"] == MSG_ACK and frame["seq"] == seq:
            return True
        time.sleep(0.1)
    return False


def run_tests(port: str, test_file: str, out_json: str, baud=115200):
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

            logits = list(infer["payload"])
            pred = max(range(len(logits)), key=lambda k: logits[k]) if logits else -1
            results.append({"id": i, "prediction": pred, "logits": logits})

    Path(out_json).write_text(json.dumps({"count": count, "vec_len": vec_len, "results": results}, indent=2))


def probe(port: str, baud=115200, seconds=3.0):
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
    pr = sp.add_parser("probe")
    pr.add_argument("--port", required=True)
    pr.add_argument("--baud", type=int, default=int(os.getenv("MIK32_BAUD", "115200")))
    pr.add_argument("--seconds", type=float, default=3.0)
    a = p.parse_args()

    if a.cmd == "build":
        build()
    elif a.cmd == "flash":
        flash()
    elif a.cmd == "run-tests":
        run_tests(a.port, a.tests, a.out, baud=a.baud)
    else:
        probe(a.port, baud=a.baud, seconds=a.seconds)


if __name__ == "__main__":
    main()