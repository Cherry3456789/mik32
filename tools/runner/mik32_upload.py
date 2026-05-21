import os
from pathlib import Path
import shlex
import subprocess
import sys


def pio_package_dir(name: str) -> Path:
    pio_home = Path(os.getenv("PLATFORMIO_CORE_DIR", Path.home() / ".platformio"))
    return pio_home / "packages" / name


def find_elbear_uploader() -> Path | None:
    if os.getenv("ELBEAR_UPLOADER"):
        return Path(os.getenv("ELBEAR_UPLOADER"))

    local_app_data = os.getenv("LOCALAPPDATA")
    if not local_app_data:
        return None

    tools_dir = Path(local_app_data) / "Arduino15" / "packages" / "Elron" / "tools" / "elbear_uploader"
    candidates = sorted(tools_dir.glob("*/elbear_uploader.exe"), reverse=True)
    return candidates[0] if candidates else None


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m tools.runner.mik32_upload <firmware.bin>")
    fw = str(Path(sys.argv[1]))
    cmd = os.getenv("MIK32_UPLOAD_CMD")
    if cmd:
        full = [part.format(firmware=fw) for part in shlex.split(cmd)]
        if not any(fw == part for part in full):
            full.append(fw)
    elif os.getenv("MIK32_UPLOAD_PORT"):
        uploader = find_elbear_uploader()
        if not uploader:
            raise SystemExit(
                "ELBEAR uploader not found. Set ELBEAR_UPLOADER to elbear_uploader.exe"
            )
        full = [
            str(uploader),
            fw,
            f"--com={os.getenv('MIK32_UPLOAD_PORT')}",
            f"--baudrate={os.getenv('MIK32_UPLOAD_BAUD', '230400')}",
        ]
    else:
        uploader_dir = pio_package_dir("tool-mik32-uploader")
        openocd_dir = pio_package_dir("tool-openocd")
        uploader = uploader_dir / "mik32_upload.py"
        openocd = openocd_dir / "bin" / ("openocd.exe" if os.name == "nt" else "openocd")
        openocd_scripts = openocd_dir / "openocd" / "scripts"
        openocd_target = uploader_dir / "openocd-scripts" / "target" / "mik32.cfg"
        openocd_interface = Path(__file__).resolve().parent / "openocd" / "sipeed-rv-debugger.cfg"

        full = [
            sys.executable,
            str(uploader),
            fw,
            "--openocd-exec",
            str(openocd),
            "--adapter-speed",
            os.getenv("MIK32_UPLOAD_SPEED", "500"),
            "--openocd-scripts",
            str(openocd_scripts),
            "--openocd-target",
            str(openocd_target),
            "--run-openocd",
            "--mcu-type",
            os.getenv("MIK32_MCU_TYPE", "MIK32V2"),
            "--openocd-interface",
            str(openocd_interface),
        ]
    print("[upload]", " ".join(full))
    subprocess.check_call(full)


if __name__ == "__main__":
    main()