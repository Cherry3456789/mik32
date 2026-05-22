from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def patch_cppmath(root: Path):
    path = root / "mik32_tinyml_firmware/lib/tflite-micro/tensorflow/lite/kernels/internal/cppmath.h"
    if not path.exists():
        print(f"skip, not found: {path}")
        return

    text = path.read_text()
    old = "#define TF_LITE_GLOBAL_STD_PREFIX std"
    new = "#ifndef TF_LITE_GLOBAL_STD_PREFIX\n#define TF_LITE_GLOBAL_STD_PREFIX\n#endif"
    if old in text:
        text = text.replace(old, new, 1)
        path.write_text(text)
        print(f"patched {path}")
    else:
        print(f"already patched or unexpected content: {path}")


def ensure_ruy_profiler_stub(root: Path):
    path = root / "mik32_tinyml_firmware/lib/tflite-micro/ruy/profiler/instrumentation.h"
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#ifndef RUY_RUY_PROFILER_INSTRUMENTATION_H_\n"
        "#define RUY_RUY_PROFILER_INSTRUMENTATION_H_\n"
        "\n"
        "namespace ruy {\n"
        "namespace profiler {\n"
        "\n"
        "class ScopeLabel {\n"
        "public:\n"
        "    template <typename... Args>\n"
        "    explicit ScopeLabel(Args...) {}\n"
        "    ~ScopeLabel() {}\n"
        "};\n"
        "\n"
        "}  // namespace profiler\n"
        "}  // namespace ruy\n"
        "\n"
        "#endif  // RUY_RUY_PROFILER_INSTRUMENTATION_H_\n"
    )
    print(f"created {path}")


def main():
    root = repo_root()
    patch_cppmath(root)
    ensure_ruy_profiler_stub(root)


if __name__ == "__main__":
    main()