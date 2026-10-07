"""Launch X-AnyLabeling 4.0.6 with the shared-boundary extension."""

import os
import sys
from importlib.metadata import version
from pathlib import Path


def prepare_work_directory():
    """Keep settings outside the checkout; an explicit CLI path takes priority."""
    if any(arg == "--work-dir" or arg.startswith("--work-dir=") for arg in sys.argv[1:]):
        return
    configured = os.environ.get("XANYLABELING_SHARED_WORK_DIR")
    directory = Path(configured).expanduser() if configured else Path.home() / "X-AnyLabeling-SharedBoundary"
    directory.mkdir(parents=True, exist_ok=True)
    sys.argv[1:1] = ["--work-dir", str(directory)]


def main():
    installed = version("x-anylabeling-cvhub")
    if installed != "4.0.6":
        raise RuntimeError(f"This extension requires X-AnyLabeling 4.0.6; installed: {installed}")
    import onnxruntime as ort

    # The CPU wheel and older runtimes may not expose this GPU helper.
    if "CUDAExecutionProvider" in ort.get_available_providers() and hasattr(ort, "preload_dlls"):
        ort.preload_dlls(directory="")
    prepare_work_directory()
    from shared_boundary import install

    install()
    from anylabeling.app import main as app_main

    app_main()


if __name__ == "__main__":
    main()
