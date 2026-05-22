import argparse
import csv
import json
import random
from pathlib import Path

MAGIC = b"MKT1"


def _select_npz_array(npz, preferred):
    if preferred:
        return npz[preferred]
    for key in ("x", "X", "features", "vectors", "images", "data", "inputs", "texts", "text", "arr_0"):
        if key in npz:
            return npz[key]
    return npz[npz.files[0]]


def _select_npz_labels(npz, preferred):
    if preferred:
        return npz[preferred]
    for key in ("y", "Y", "labels", "label", "target", "targets", "arr_1"):
        if key in npz:
            return npz[key]
    return None


def text_to_vector(text, vec_len: int) -> bytes:
    raw = str(text).encode("utf-8", errors="ignore")
    out = bytearray(vec_len)
    for i, b in enumerate(raw):
        out[i % vec_len] = (out[i % vec_len] + b) & 0xFF
    return bytes(out)


def load_vectors(inp: Path, vec_len: int, npz_key=None):
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
        loaded = np.load(inp)
        arr = _select_npz_array(loaded, npz_key) if inp.suffix.lower() == ".npz" else loaded
        if arr.dtype.kind in ("U", "S", "O"):
            flat = arr.reshape(-1)
            return [text_to_vector(x, vec_len) for x in flat]
        if arr.ndim == 1:
            arr = arr[None, :]
        if arr.ndim > 2:
            arr = arr.reshape((arr.shape[0], -1))
        arr = arr.astype("uint8")
        out = []
        for row in arr:
            b = bytes(row.tolist()[:vec_len])
            b += b"\x00" * (vec_len - len(b))
            out.append(b)
        return out
    except Exception as exc:
        raise RuntimeError(f"Unsupported input {inp}; use CSV or install numpy for NPY: {exc}")


def load_labels(inp: Path, npz_label_key=None, limit=None):
    if inp.suffix.lower() != ".npz":
        return None
    try:
        import numpy as np
        loaded = np.load(inp)
        labels = _select_npz_labels(loaded, npz_label_key)
        if labels is None:
            return None
        labels = labels.reshape(-1).astype("int64").tolist()
        return labels[:limit] if limit else labels
    except Exception:
        return None


def write_mktest(vectors, out: Path, seed: int, vec_len: int, labels=None):
    with out.open("wb") as f:
        f.write(MAGIC)
        f.write((1).to_bytes(2, "little"))
        f.write(len(vectors).to_bytes(4, "little"))
        f.write(vec_len.to_bytes(2, "little"))
        for row in vectors:
            f.write(row)
    manifest = {"seed": seed, "count": len(vectors), "vec_len": vec_len}
    if labels is not None:
        manifest["labels"] = labels[: len(vectors)]
    out.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2))


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
    g.add_argument("--npz-key")
    g.add_argument("--npz-label-key")

    i = sp.add_parser("inspect")
    i.add_argument("--input", required=True)

    a = p.parse_args()
    if a.cmd == "inspect":
        inspect(Path(a.input))
        return


    random.seed(a.seed)
    if a.input:
        vectors = load_vectors(Path(a.input), a.vec_len, npz_key=a.npz_key)
        if a.count:
            vectors = vectors[: a.count]
        labels = load_labels(Path(a.input), npz_label_key=a.npz_label_key, limit=len(vectors))
    else:
        vectors = [bytes(random.randint(0, 255) for _ in range(a.vec_len)) for _ in range(a.count)]
        labels = None
    write_mktest(vectors, Path(a.output), a.seed, a.vec_len, labels=labels)


if __name__ == "__main__":
    main()