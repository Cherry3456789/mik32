import argparse
import csv
import json
import random
from pathlib import Path

MAGIC = b"MKT1"


def load_vectors(inp: Path, vec_len: int):
    if inp.suffix.lower() == ".csv":
        rows = []
        with inp.open("r", newline="") as f:
            for r in csv.reader(f):
                if not r:
                    continue
                row = [max(0, min(255, int(x))) for x in r[:vec_len]]
                row += [0] * (vec_len - len(row))
                rows.append(bytes(row))
        return rows

    try:
        import numpy as np
        arr = np.load(inp)
        if arr.ndim == 1:
            arr = arr[None, :]
        arr = arr.astype("uint8")
        out = []
        for row in arr:
            b = bytes(row.tolist()[:vec_len])
            b += b"\x00" * (vec_len - len(b))
            out.append(b)
        return out
    except Exception as exc:
        raise RuntimeError(f"Unsupported input {inp}; use CSV or install numpy for NPY: {exc}")


def write_mktest(vectors, out: Path, seed: int, vec_len: int):
    with out.open("wb") as f:
        f.write(MAGIC)
        f.write((1).to_bytes(2, "little"))
        f.write(len(vectors).to_bytes(4, "little"))
        f.write(vec_len.to_bytes(2, "little"))
        for row in vectors:
            f.write(row)
    out.with_suffix(".manifest.json").write_text(json.dumps({"seed": seed, "count": len(vectors), "vec_len": vec_len}, indent=2))


def inspect(path: Path):
    b = path.read_bytes()
    assert b[:4] == MAGIC
    ver = int.from_bytes(b[4:6], "little")
    cnt = int.from_bytes(b[6:10], "little")
    ln = int.from_bytes(b[10:12], "little")
    print(f"version={ver} count={cnt} vec_len={ln}")


def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)

    g = sp.add_parser("generate")
    g.add_argument("--input")
    g.add_argument("--output", required=True)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--count", type=int, default=32)
    g.add_argument("--vec-len", type=int, default=784)

    i = sp.add_parser("inspect")
    i.add_argument("--input", required=True)

    a = p.parse_args()
    if a.cmd == "inspect":
        inspect(Path(a.input))
        return

    random.seed(a.seed)
    if a.input:
        vectors = load_vectors(Path(a.input), a.vec_len)
    else:
        vectors = [bytes(random.randint(0, 255) for _ in range(a.vec_len)) for _ in range(a.count)]
    write_mktest(vectors, Path(a.output), a.seed, a.vec_len)


if __name__ == "__main__":
    main()
