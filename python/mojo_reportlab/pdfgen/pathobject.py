"""Mojo-backed implementation of ReportLab's PDF path object."""

from __future__ import annotations

import numpy as np
from reportlab.pdfgen import pdfgeom
from reportlab.pdfgen.pathobject import PDFPathObject as _UpstreamPath

from mojo_reportlab._lib import encode_path


class PDFPathObject:
    """Accumulates path geometry and serializes it in one Mojo call."""

    def __init__(self, code=None):
        self._delegate = _UpstreamPath(code=code) if code is not None else None
        self._ops: list[int] = []
        self._values: list[float] = []
        self._cache: str | None = None

    def _append(self, op: int, values=()):
        if self._delegate is not None:
            raise RuntimeError("internal append used for a delegated path")
        if not self._ops:
            assert op in (1, 4), "path must start with a moveto or rect"
        self._ops.append(op)
        self._values.extend(values)
        self._cache = None

    def getCode(self):
        if self._delegate is not None:
            return self._delegate.getCode()
        if self._cache is None:
            ops = np.ascontiguousarray(self._ops, dtype=np.int64)
            values = np.ascontiguousarray(self._values, dtype=np.float64)
            self._cache = encode_path(ops, values)
        return self._cache

    def _get_canvas_code(self):
        if self._delegate is not None:
            return self._delegate.getCode()
        ops = np.ascontiguousarray(self._ops, dtype=np.int64)
        values = np.ascontiguousarray(self._values, dtype=np.float64)
        return encode_path(ops, values, "\n")

    def moveTo(self, x, y):
        if self._delegate is not None:
            return self._delegate.moveTo(x, y)
        self._append(1, (x, y))

    def lineTo(self, x, y):
        if self._delegate is not None:
            return self._delegate.lineTo(x, y)
        self._append(2, (x, y))

    def curveTo(self, x1, y1, x2, y2, x3, y3):
        if self._delegate is not None:
            return self._delegate.curveTo(x1, y1, x2, y2, x3, y3)
        self._append(3, (x1, y1, x2, y2, x3, y3))

    def arc(self, x1, y1, x2, y2, startAng=0, extent=90):
        self._curves(pdfgeom.bezierArc(x1, y1, x2, y2, startAng, extent))

    def arcTo(self, x1, y1, x2, y2, startAng=0, extent=90):
        self._curves(
            pdfgeom.bezierArc(x1, y1, x2, y2, startAng, extent), "lineTo"
        )

    def rect(self, x, y, width, height):
        if self._delegate is not None:
            return self._delegate.rect(x, y, width, height)
        self._append(4, (x, y, width, height))

    def ellipse(self, x, y, width, height):
        self._curves(pdfgeom.bezierArc(x, y, x + width, y + height, 0, 360))

    def _curves(self, curves, initial="moveTo"):
        getattr(self, initial)(*curves[0][:2])
        for curve in curves:
            self.curveTo(*curve[2:])

    def circle(self, x_cen, y_cen, r):
        self.ellipse(x_cen - r, y_cen - r, 2 * r, 2 * r)

    def roundRect(self, x, y, width, height, radius):
        m = 0.4472
        xlo, xhi = min(x, x + width), max(x, x + width)
        ylo, yhi = min(y, y + height), max(y, y + height)
        if isinstance(radius, (list, tuple)):
            r = [max(0, item) for item in radius]
            if len(r) < 4:
                r += (4 - len(r)) * [0]
            self.moveTo(xlo + r[2], ylo)
            self.lineTo(xhi - r[3], ylo)
            if r[3] > 0:
                t = m * r[3]
                self.curveTo(xhi - t, ylo, xhi, ylo + t, xhi, ylo + r[3])
            self.lineTo(xhi, yhi - r[1])
            if r[1] > 0:
                t = m * r[1]
                self.curveTo(xhi, yhi - t, xhi - t, yhi, xhi - r[1], yhi)
            self.lineTo(xlo + r[0], yhi)
            if r[0] > 0:
                t = m * r[0]
                self.curveTo(xlo + t, yhi, xlo, yhi - t, xlo, yhi - r[0])
            self.lineTo(xlo, ylo + r[2])
            if r[2] > 0:
                t = m * r[2]
                self.curveTo(xlo, ylo + t, xlo + t, ylo, xlo + r[2], ylo)
        else:
            t = m * radius
            self.moveTo(xlo + radius, ylo)
            self.lineTo(xhi - radius, ylo)
            self.curveTo(xhi - t, ylo, xhi, ylo + t, xhi, ylo + radius)
            self.lineTo(xhi, yhi - radius)
            self.curveTo(xhi, yhi - t, xhi - t, yhi, xhi - radius, yhi)
            self.lineTo(xlo + radius, yhi)
            self.curveTo(xlo + t, yhi, xlo, yhi - t, xlo, yhi - radius)
            self.lineTo(xlo, ylo + radius)
            self.curveTo(xlo, ylo + t, xlo + t, ylo, xlo + radius, ylo)
        self.close()

    def close(self):
        if self._delegate is not None:
            return self._delegate.close()
        self._append(5)


__all__ = ["PDFPathObject"]
