"""mojo-reportlab against ReportLab on identical content streams."""

from __future__ import annotations

import math
import os
import platform
import sys
import time
from io import BytesIO

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

from mojo_reportlab.lib.rl_accel import fp_str  # noqa: E402
from mojo_reportlab.pdfgen.canvas import Canvas  # noqa: E402
from mojo_reportlab.pdfgen.pathobject import PDFPathObject  # noqa: E402
from reportlab.lib.rl_accel import fp_str as reportlab_fp_str  # noqa: E402
from reportlab.pdfgen.canvas import Canvas as ReportLabCanvas  # noqa: E402
from reportlab.pdfgen.pathobject import PDFPathObject as ReportLabPath  # noqa: E402


def timeit(function, repeat=3):
    best = math.inf
    result = None
    for _ in range(repeat):
        start = time.perf_counter()
        result = function()
        best = min(best, time.perf_counter() - start)
    return best, result


def cpu_name():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as source:
            for line in source:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown CPU"


def make_path(path_class, count, x, y):
    path = path_class()
    path.moveTo(x[0], y[0])
    for i in range(1, count):
        path.lineTo(x[i], y[i])
    return path.getCode()


def make_canvas(canvas_class, lines):
    destination = BytesIO()
    canvas = canvas_class(destination, invariant=1, pageCompression=0)
    canvas.lines(lines)
    return canvas.getCurrentPageContent()


def make_pdf(canvas_class, lines):
    destination = BytesIO()
    canvas = canvas_class(destination, invariant=1, pageCompression=1)
    canvas.lines(lines)
    canvas.showPage()
    canvas.save()
    return destination.getvalue()


def main():
    rng = np.random.default_rng(42)
    values = (rng.normal(size=1_000_000) * 10_000).tolist()
    coords = rng.normal(size=(200_000, 4)) * 500
    lines = [tuple(row) for row in coords]
    x = np.arange(100_000, dtype=np.float64) * 0.1
    y = np.sin(x / 50) * 100

    cases = [
        (
            "fp_str (1M numbers)",
            lambda: fp_str(values),
            lambda: reportlab_fp_str(values),
        ),
        (
            "Canvas.lines (200k)",
            lambda: make_canvas(Canvas, lines),
            lambda: make_canvas(ReportLabCanvas, lines),
        ),
        (
            "PDFPathObject (100k points)",
            lambda: make_path(PDFPathObject, x.size, x, y),
            lambda: make_path(ReportLabPath, x.size, x, y),
        ),
        (
            "compressed PDF page (200k lines)",
            lambda: make_pdf(Canvas, lines),
            lambda: make_pdf(ReportLabCanvas, lines),
        ),
    ]

    print(f"Machine: {cpu_name()}; {platform.system()} {platform.release()}")
    print()
    print("| case | mojo-reportlab | ReportLab | speedup |")
    print("|---|---:|---:|---:|")
    for name, mojo_case, reference_case in cases:
        mojo_case()
        mojo_time, mojo_result = timeit(mojo_case)
        reference_time, reference_result = timeit(reference_case)
        if mojo_result != reference_result:
            raise AssertionError(f"benchmark outputs differ for {name}")
        print(
            f"| {name} | {mojo_time * 1e3:.2f} ms | "
            f"{reference_time * 1e3:.2f} ms | {reference_time / mojo_time:.2f}x |"
        )


if __name__ == "__main__":
    main()
