"""Mojo-backed implementation of ReportLab's PDF path object."""

from __future__ import annotations

from array import array

import numpy as np
from reportlab.pdfgen import pdfgeom
from reportlab.pdfgen.pathobject import PDFPathObject as _UpstreamPath

from mojo_reportlab._lib import _encode_path_arrays


class PDFPathObject:
    """Accumulates path geometry and serializes it in one Mojo call."""

    def __init__(self, code=None):
        self._delegate = _UpstreamPath(code=code) if code is not None else None
        self._ops = bytearray()
        self._values = array("d")
        self._cache: str | None = None

    def getCode(self):
        if self._delegate is not None:
            return self._delegate.getCode()
        if self._cache is None:
            ops = np.frombuffer(self._ops, dtype=np.uint8)
            values = np.frombuffer(self._values, dtype=np.float64)
            self._cache = _encode_path_arrays(ops, values)
        return self._cache

    def _get_canvas_code(self):
        if self._delegate is not None:
            return self._delegate.getCode()
        ops = np.frombuffer(self._ops, dtype=np.uint8)
        values = np.frombuffer(self._values, dtype=np.float64)
        return _encode_path_arrays(ops, values, "\n")

    def moveTo(self, x, y):
        if self._delegate is not None:
            return self._delegate.moveTo(x, y)
        self._ops.append(1)
        self._values.append(x)
        self._values.append(y)
        self._cache = None

    def lineTo(self, x, y):
        if self._delegate is not None:
            return self._delegate.lineTo(x, y)
        assert self._ops, "path must start with a moveto or rect"
        self._ops.append(2)
        self._values.append(x)
        self._values.append(y)
        self._cache = None

    def curveTo(self, x1, y1, x2, y2, x3, y3):
        if self._delegate is not None:
            return self._delegate.curveTo(x1, y1, x2, y2, x3, y3)
        assert self._ops, "path must start with a moveto or rect"
        self._ops.append(3)
        append = self._values.append
        append(x1)
        append(y1)
        append(x2)
        append(y2)
        append(x3)
        append(y3)
        self._cache = None

    def arc(self, x1, y1, x2, y2, startAng=0, extent=90):
        self._curves(pdfgeom.bezierArc(x1, y1, x2, y2, startAng, extent))

    def arcTo(self, x1, y1, x2, y2, startAng=0, extent=90):
        self._curves(
            pdfgeom.bezierArc(x1, y1, x2, y2, startAng, extent), "lineTo"
        )

    def rect(self, x, y, width, height):
        if self._delegate is not None:
            return self._delegate.rect(x, y, width, height)
        self._ops.append(4)
        append = self._values.append
        append(x)
        append(y)
        append(width)
        append(height)
        self._cache = None

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
        assert self._ops, "path must start with a moveto or rect"
        self._ops.append(5)
        self._cache = None


__all__ = ["PDFPathObject"]
