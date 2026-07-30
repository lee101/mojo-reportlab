"""ReportLab Canvas with Mojo-backed path content generation."""

from __future__ import annotations

import numpy as np
from reportlab import rl_config
from reportlab.pdfbase import pdfdoc
from reportlab.pdfbase.pdfutils import _wrap
from reportlab.pdfgen.canvas import (
    FILL_EVEN_ODD,
    PATH_OPS,
    Canvas as _ReportLabCanvas,
)

from mojo_reportlab._lib import ascii85_encode, encode_lines, encode_path
from mojo_reportlab.pdfgen.pathobject import PDFPathObject


def _path_code(ops, values, separator=" "):
    return encode_path(
        np.ascontiguousarray(ops, dtype=np.int64),
        np.ascontiguousarray(values, dtype=np.float64),
        separator,
    )


class _MojoBase85Encode:
    pdfname = "ASCII85Decode"

    def encode(self, text):
        if isinstance(text, str):
            text = text.encode("latin1")
        result = ascii85_encode(text)
        return _wrap(result) if rl_config.wrapA85 else result

    def decode(self, text):
        return pdfdoc.asciiBase85Decode(text)


_MOJO_BASE85_ENCODE = _MojoBase85Encode()


class _MojoPDFPage(pdfdoc.PDFPage):
    def check_format(self, document):
        super().check_format(document)
        filters = getattr(self.Contents, "filters", None)
        if filters and filters[0] is pdfdoc.PDFBase85Encode:
            filters[0] = _MOJO_BASE85_ENCODE


class Canvas(_ReportLabCanvas):
    """Drop-in Canvas whose covered drawing operators serialize in Mojo."""

    def line(self, x1, y1, x2, y2):
        coords = np.ascontiguousarray([[x1, y1, x2, y2]], dtype=np.float64)
        self._code.append(encode_lines(coords).replace("\n", " "))

    def lines(self, linelist):
        coords = np.ascontiguousarray(linelist, dtype=np.float64)
        if coords.size == 0:
            coords = np.empty((0, 4), dtype=np.float64)
        if coords.ndim != 2 or coords.shape[1] != 4:
            raise ValueError("linelist must contain (x1, y1, x2, y2) rows")
        self._code.append(encode_lines(coords))

    def showPage(self):
        super().showPage()
        self._doc.Pages.pages[-1].__class__ = _MojoPDFPage

    def grid(self, xlist, ylist):
        assert len(xlist) > 1, "x coordinate list must have 2+ items"
        assert len(ylist) > 1, "y coordinate list must have 2+ items"
        x = np.asarray(xlist, dtype=np.float64)
        y = np.asarray(ylist, dtype=np.float64)
        coords = np.empty((x.size + y.size, 4), dtype=np.float64)
        coords[: x.size, 0] = x
        coords[: x.size, 1] = y[0]
        coords[: x.size, 2] = x
        coords[: x.size, 3] = y[-1]
        coords[x.size :, 0] = x[0]
        coords[x.size :, 1] = y
        coords[x.size :, 2] = x[-1]
        coords[x.size :, 3] = y
        self._code.append(encode_lines(coords))

    def bezier(self, x1, y1, x2, y2, x3, y3, x4, y4):
        code = _path_code(
            [1, 3], [x1, y1, x2, y2, x3, y3, x4, y4]
        )
        self._code.append(code + " S")

    def rect(self, x, y, width, height, stroke=1, fill=0):
        code = _path_code([4], [x, y, width, height])
        self._code.append(code + " " + PATH_OPS[stroke, fill, self._fillMode])

    def beginPath(self):
        return PDFPathObject()

    def drawPath(self, aPath, stroke=1, fill=0, fillMode=None):
        if fillMode is None:
            fillMode = getattr(aPath, "_fillMode", self._fillMode)
        self._code.append(str(aPath.getCode()))
        self._strokeAndFill(stroke, fill, fillMode)

    def clipPath(self, aPath, stroke=1, fill=0, fillMode=None):
        if fillMode is None:
            fillMode = getattr(aPath, "_fillMode", self._fillMode)
        clip = " W* " if fillMode == FILL_EVEN_ODD else " W "
        self._code.append(
            f"{aPath.getCode()}{clip}{PATH_OPS[stroke, fill, fillMode]}"
        )

    def _draw_mojo_path(self, path, stroke, fill):
        self._code.append(path._get_canvas_code())
        self._strokeAndFill(stroke, fill)

    def arc(self, x1, y1, x2, y2, startAng=0, extent=90):
        path = PDFPathObject()
        path.arc(x1, y1, x2, y2, startAng, extent)
        self._draw_mojo_path(path, 1, 0)

    def ellipse(self, x1, y1, x2, y2, stroke=1, fill=0):
        path = PDFPathObject()
        path.ellipse(x1, y1, x2 - x1, y2 - y1)
        self._draw_mojo_path(path, stroke, fill)

    def wedge(self, x1, y1, x2, y2, startAng, extent, stroke=1, fill=0):
        path = PDFPathObject()
        path.moveTo(0.5 * (x1 + x2), 0.5 * (y1 + y2))
        path.arcTo(x1, y1, x2, y2, startAng, extent)
        path.close()
        self._draw_mojo_path(path, stroke, fill)

    def circle(self, x_cen, y_cen, r, stroke=1, fill=0):
        self.ellipse(
            x_cen - r, y_cen - r, x_cen + r, y_cen + r, stroke, fill
        )

    def roundRect(self, x, y, width, height, radius, stroke=1, fill=0):
        path = PDFPathObject()
        path.roundRect(x, y, width, height, radius)
        self._draw_mojo_path(path, stroke, fill)


__all__ = ["Canvas"]
