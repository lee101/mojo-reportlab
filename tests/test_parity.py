"""Behavioral and byte-level parity with ReportLab 5."""

from __future__ import annotations

import inspect
from io import BytesIO

import numpy as np
import pytest
from reportlab import rl_config
from reportlab.lib.rl_accel import fp_str as upstream_fp_str
from reportlab.lib.rl_accel import asciiBase85Encode as upstream_ascii85_encode
from reportlab.pdfbase import pdfdoc
from reportlab.pdfgen.canvas import Canvas as UpstreamCanvas
from reportlab.pdfgen.pathobject import PDFPathObject as UpstreamPath

from mojo_reportlab.lib.rl_accel import fp_str
from mojo_reportlab._lib import (
    _checked_size,
    ascii85_encode,
    ascii85_encode_bytes,
    encode_lines,
    encode_numbers,
    encode_path,
)
from mojo_reportlab.pdfgen.canvas import Canvas, _MojoBase85Encode
from mojo_reportlab.pdfgen.pathobject import PDFPathObject


def test_fp_str_published_style_values():
    values = (
        0,
        1,
        -1,
        1.5,
        0.000001,
        -0.000001,
        0.5,
        -0.5,
        9.9999999,
        99.999999,
        999999.9,
        1000000.4,
        0.123456789,
    )
    assert fp_str(*values) == upstream_fp_str(*values)


@pytest.mark.parametrize("scale", [1e-9, 1e-6, 1e-3, 1.0, 1e3, 1e6, 1e12])
def test_fp_str_random_exact_parity(scale):
    values = (np.random.default_rng(7).normal(size=10_003) * scale).tolist()
    assert fp_str(values) == upstream_fp_str(values)


def test_fp_str_extreme_fallback_and_empty_sequence():
    assert fp_str([]) == upstream_fp_str([])
    assert fp_str(10**20) == upstream_fp_str(10**20)


def test_number_binding_normalizes_dtype_and_stride():
    source = np.arange(20, dtype=np.int32)[::2]
    assert encode_numbers(source) == upstream_fp_str(source.astype(float).tolist())


@pytest.mark.parametrize("size", range(36))
def test_ascii85_simd_and_scalar_tails(size):
    values = np.random.default_rng(size).integers(0, 256, size=size, dtype=np.uint8)
    source = values.tobytes()
    assert ascii85_encode(source) == upstream_ascii85_encode(source)


def test_ascii85_zero_words():
    for source in (b"\0" * 17, b"abcd\0\0\0\0efghijk"):
        assert ascii85_encode(source) == upstream_ascii85_encode(source)


def test_ascii85_accepts_owned_and_borrowed_buffers():
    source = bytearray(range(31))
    assert ascii85_encode(source) == upstream_ascii85_encode(bytes(source))
    assert ascii85_encode(memoryview(source)[1::2]) == upstream_ascii85_encode(
        bytes(source[1::2])
    )
    assert ascii85_encode_bytes(source) == upstream_ascii85_encode(
        bytes(source)
    ).encode("ascii")


def test_ascii85_bytes_wrapping(monkeypatch):
    source = bytes(range(200))
    monkeypatch.setattr(rl_config, "wrapA85", 1)
    assert _MojoBase85Encode().encode(source) == pdfdoc.PDFBase85Encode.encode(
        source
    ).encode("ascii")


@pytest.mark.parametrize("size", [1_048_575, 1_048_579])
def test_ascii85_large_input_simd_tails(size):
    values = np.random.default_rng(91).integers(
        0, 256, size=size, dtype=np.uint8
    )
    source = values.tobytes()
    assert ascii85_encode(source) == upstream_ascii85_encode(source)


def build_path(path_class):
    path = path_class()
    path.moveTo(0.5, -0.5)
    path.lineTo(10, 20)
    path.curveTo(1, 2, 3, 4, 5, 6)
    path.rect(1, 2, 3, 4)
    path.close()
    return path


def test_path_basic_commands_exact_parity():
    assert build_path(PDFPathObject).getCode() == build_path(UpstreamPath).getCode()


def test_path_cache_is_invalidated_after_append():
    ours, theirs = PDFPathObject(), UpstreamPath()
    ours.moveTo(1, 2)
    theirs.moveTo(1, 2)
    assert ours.getCode() == theirs.getCode()
    ours.lineTo(3, 4)
    theirs.lineTo(3, 4)
    assert ours.getCode() == theirs.getCode()


def test_path_binding_normalizes_arrays_and_rejects_invalid_layout():
    ops = np.array([99, 1, 99, 2], dtype=np.int16)[1::2]
    values = np.array([1, 2, 3, 4], dtype=np.float32)
    assert encode_path(ops, values) == "n 1 2 m 3 4 l"
    with pytest.raises(ValueError, match="require 2 values"):
        encode_path(np.array([1]), np.array([1]))
    with pytest.raises(ValueError, match="unsupported path operator"):
        encode_path(np.array([9]), np.array([]))
    with pytest.raises(ValueError, match="separator"):
        encode_path(np.array([1]), np.array([1, 2]), "\N{SNOWMAN}")


@pytest.mark.parametrize(
    "method,args",
    [
        ("arc", (1, 2, 101, 52, 17, 211)),
        ("arcTo", (1, 2, 101, 52, -20, -185)),
        ("ellipse", (1, 2, 100, 50)),
        ("circle", (20, 30, 12)),
        ("roundRect", (10, 20, 100, 60, 8)),
        ("roundRect", (10, 20, -100, -60, (1, 2, 3, 4))),
    ],
)
def test_path_geometry_exact_parity(method, args):
    ours, theirs = PDFPathObject(), UpstreamPath()
    if method == "arcTo":
        ours.moveTo(0, 0)
        theirs.moveTo(0, 0)
    getattr(ours, method)(*args)
    getattr(theirs, method)(*args)
    assert ours.getCode() == theirs.getCode()


def test_path_must_start_with_move_or_rect():
    with pytest.raises(AssertionError, match="path must start"):
        PDFPathObject().lineTo(1, 2)


def test_extreme_path_coordinate_uses_exact_fallback():
    ours, theirs = PDFPathObject(), UpstreamPath()
    ours.moveTo(1e20, -1e20)
    theirs.moveTo(1e20, -1e20)
    assert ours.getCode() == theirs.getCode()


def test_path_can_append_into_external_code_list():
    ours, theirs = [], []
    op, rp = PDFPathObject(ours), UpstreamPath(theirs)
    op.moveTo(1, 2)
    op.lineTo(3, 4)
    rp.moveTo(1, 2)
    rp.lineTo(3, 4)
    assert ours == theirs


def canvas_content(canvas_class, drawing):
    buffer = BytesIO()
    canvas = canvas_class(buffer, invariant=1, pageCompression=0)
    drawing(canvas)
    return canvas.getCurrentPageContent()


@pytest.mark.parametrize(
    "drawing",
    [
        lambda c: c.line(0.5, 1, 20, 30),
        lambda c: c.lines([(1, 2, 3, 4), (5.5, 6, 7, 8)]),
        lambda c: c.grid([1, 2, 4], [10, 20, 30, 40]),
        lambda c: c.bezier(1, 2, 3, 4, 5, 6, 7, 8),
        lambda c: c.rect(1, 2, 30, 40, stroke=1, fill=1),
        lambda c: c.arc(1, 2, 101, 52, 10, 230),
        lambda c: c.ellipse(1, 2, 101, 52, stroke=0, fill=1),
        lambda c: c.wedge(1, 2, 101, 52, 10, -120, stroke=1, fill=1),
        lambda c: c.circle(20, 30, 12, stroke=1, fill=0),
        lambda c: c.roundRect(10, 20, 100, 60, 8, stroke=1, fill=1),
    ],
)
def test_canvas_drawing_stream_exact_parity(drawing):
    assert canvas_content(Canvas, drawing) == canvas_content(UpstreamCanvas, drawing)


def test_line_binding_normalizes_dtype_and_rejects_invalid_shape():
    coords = np.arange(16, dtype=np.int16).reshape(4, 4)[::2]
    ours = encode_lines(coords)
    expected = canvas_content(UpstreamCanvas, lambda c: c.lines(coords.tolist()))
    assert ours == expected
    with pytest.raises(ValueError, match="four columns"):
        encode_lines(np.ones((2, 3)))


def test_native_output_lengths_are_checked():
    assert _checked_size(3, 3, "test") == 3
    with pytest.raises(RuntimeError, match="invalid output length"):
        _checked_size(-1, 3, "test")
    with pytest.raises(RuntimeError, match="invalid output length"):
        _checked_size(4, 3, "test")


def draw_complex_path(canvas):
    path = canvas.beginPath()
    path.moveTo(10, 10)
    path.lineTo(90, 10)
    path.curveTo(100, 20, 100, 80, 90, 90)
    path.close()
    canvas.drawPath(path, stroke=1, fill=1)


def test_canvas_begin_and_draw_path_exact_parity():
    assert canvas_content(Canvas, draw_complex_path) == canvas_content(
        UpstreamCanvas, draw_complex_path
    )


def test_canvas_clip_path_exact_parity():
    def drawing(canvas):
        path = canvas.beginPath()
        path.rect(1, 2, 30, 40)
        canvas.clipPath(path, stroke=0, fill=0)

    assert canvas_content(Canvas, drawing) == canvas_content(UpstreamCanvas, drawing)


def render_pdf(canvas_class, page_compression=0):
    destination = BytesIO()
    canvas = canvas_class(
        destination, invariant=1, pageCompression=page_compression
    )
    canvas.setTitle("parity")
    canvas.lines([(i, i % 17, i + 1, (i * 3) % 29) for i in range(100)])
    draw_complex_path(canvas)
    canvas.showPage()
    canvas.save()
    return destination.getvalue()


def test_complete_pdf_is_byte_identical():
    assert render_pdf(Canvas) == render_pdf(UpstreamCanvas)


def test_complete_compressed_pdf_is_byte_identical():
    assert render_pdf(Canvas, 1) == render_pdf(UpstreamCanvas, 1)


def test_covered_signatures_match_upstream():
    for name in (
        "line",
        "lines",
        "grid",
        "bezier",
        "rect",
        "arc",
        "ellipse",
        "wedge",
        "circle",
        "roundRect",
        "beginPath",
        "drawPath",
        "clipPath",
    ):
        assert inspect.signature(getattr(Canvas, name)) == inspect.signature(
            getattr(UpstreamCanvas, name)
        )
    for name in (
        "moveTo",
        "lineTo",
        "curveTo",
        "arc",
        "arcTo",
        "rect",
        "ellipse",
        "circle",
        "roundRect",
        "close",
    ):
        assert inspect.signature(getattr(PDFPathObject, name)) == inspect.signature(
            getattr(UpstreamPath, name)
        )
