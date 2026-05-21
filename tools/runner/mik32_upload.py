import os
import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m tools.runner.mik32_upload <firmware.bin>")
    fw = sys.argv[1]
    cmd = os.getenv("MIK32_UPLOAD_CMD")
    if cmd:
        full = cmd.split() + [fw]
    else:
        full = ["openocd", "-f", "interface/cmsis-dap.cfg", "-f", "target/riscv.cfg", "-c", f"program {fw} verify reset exit"]
    print("[upload]", " ".join(full))
    subprocess.check_call(full)


if __name__ == "__main__":
    main()
