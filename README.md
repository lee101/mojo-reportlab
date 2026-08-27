# mojo-reportlab

`mojo-reportlab` accelerates PDF path content-stream generation with Mojo while
preserving ReportLab's Python API for the covered operations. It is a focused
port of the compute-heavy serialization layer, not a rewrite of ReportLab's
document model. The supplied `Canvas` subclasses ReportLab's canvas, so it
still produces ordinary ReportLab PDFs and remains compatible with its page,
font, image, annotation, encryption, and metadata machinery.

The implementation is tested against the ReportLab version locked by
`pixi.lock` (currently ReportLab 5.0.0), runs on Linux, and is licensed under
MIT.

## Coverage

The Mojo-backed subset is:

- `mojo_reportlab.lib.rl_accel.fp_str`, including ReportLab's compact
  six-significant-digit PDF number format
- `mojo_reportlab.pdfgen.pathobject.PDFPathObject`: `moveTo`, `lineTo`,
  `curveTo`, `arc`, `arcTo`, `rect`, `ellipse`, `circle`, `roundRect`, `close`,
  and `getCode`
- `mojo_reportlab.pdfgen.canvas.Canvas`: `line`, `lines`, `grid`, `bezier`,
  `arc`, `rect`, `ellipse`, `wedge`, `circle`, `roundRect`, `beginPath`,
  `drawPath`, and `clipPath`

For these methods, signatures, numeric output, operator ordering, and
whitespace are checked against upstream. Tests exercise every method listed
above, including exact content-stream comparisons and byte-identical
uncompressed and compressed PDFs. Other `Canvas` APIs remain available through
the ReportLab base class but do not run in Mojo.

Text shaping, font subsetting, image encoding, PDF object assembly, encryption,
and compression are not reimplemented. ReportLab remains a runtime dependency
for those facilities. This package does not replace the wider
`reportlab.lib`, Platypus, graphics, or renderers APIs.

## Install

This repository currently supports a source install through Pixi; it does not
ship a prebuilt shared library or a standalone ReportLab replacement. From a
checkout, install the locked Mojo and Python dependencies, then build:

```bash
pixi install
pixi run build
```

Run the parity suite with:

```bash
pixi run test
```

Because the shared library is loaded from `dist/`, run examples from the
checkout (or set `PYTHONPATH` to its `python/` directory).

## Usage

The constructor and covered drawing calls have the same signatures as
`reportlab.pdfgen.canvas.Canvas`; only the import changes:

```python
from mojo_reportlab.pdfgen.canvas import Canvas

canvas = Canvas("example.pdf")
canvas.lines([
    (36, 36, 576, 36),
    (36, 36, 36, 756),
    (36, 756, 576, 756),
    (576, 36, 576, 756),
])

path = canvas.beginPath()
path.moveTo(72, 100)
path.curveTo(144, 250, 360, 20, 504, 180)
canvas.drawPath(path)

canvas.drawString(72, 720, "ReportLab document, Mojo path stream")
canvas.save()
```

`drawString` in this example is inherited from ReportLab; the line and path
operators are serialized by Mojo.

## Benchmarks

Measured with `pixi run bench` on an Intel Xeon E5-2697 v4 at 2.30 GHz,
Linux 6.8.0-136-generic. Times are the best of three warm runs. Speedup is
ReportLab time divided by mojo-reportlab time, and every benchmark asserts that
both implementations returned identical bytes or text before printing.

| case | mojo-reportlab | ReportLab | speedup |
|---|---:|---:|---:|
| fp_str (1M numbers) | 120.55 ms | 933.99 ms | 7.75x |
| Canvas.lines (200k) | 135.41 ms | 1073.57 ms | 7.93x |
| PDFPathObject (100k points) | 74.75 ms | 297.06 ms | 3.97x |
| compressed PDF page (200k lines) | 1069.76 ms | 3448.73 ms | 3.22x |

The compressed-page result includes ReportLab's unchanged document assembly
and zlib work. Its ASCII85 stage uses native-width SIMD for independent
four-byte groups with a scalar remainder. It stays serial because profiling
shows native zlib dominates this workload and the remaining independent stage
is too small to repay thread-launch overhead.

No GPU path is included. The covered work is variable-length byte
serialization with low floating-point arithmetic intensity, while compression
is stream-dependent and already handled by native zlib. Neither can repay GPU
transfer and launch overhead.

## How it works

Python validates shapes and operators, converts coordinates into contiguous
`float64` arrays, and owns both input and output memory for the full duration
of each synchronous call. Buffer addresses and element counts cross a small C
ABI as 64-bit integers; Mojo reconstructs pointers using
`AnyOrigin[mut=True]`. Empty inputs do not cross as pointers, returned lengths
are checked against destination capacities, and no Mojo allocation crosses the
boundary. Non-finite or out-of-range numeric inputs fall back to ReportLab's
formatter.

One Mojo compilation unit writes ASCII numbers, PDF operators, and compressed
stream ASCII85 directly into pre-sized `uint8` buffers. Bulk `Canvas.lines`
data is encoded in one FFI call. `PDFPathObject` accumulates operators and
coordinates in dense buffer-backed containers, then exposes zero-copy NumPy
views to one Mojo call at `getCode`. ASCII85 reads zlib's immutable Python
buffer zero-copy across the FFI boundary and returns its final bytes directly
to ReportLab, avoiding a decode/re-encode round trip. The shared library is
built by `build/build.sh` as `dist/libmojo-reportlab.so` and loaded with
`ctypes`.
