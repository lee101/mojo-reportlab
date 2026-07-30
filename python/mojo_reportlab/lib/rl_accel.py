"""Covered subset of :mod:`reportlab.lib.rl_accel`."""

from __future__ import annotations

import numpy as np
from reportlab.lib.rl_accel import fp_str as _upstream_fp_str

from mojo_reportlab._lib import encode_numbers


def fp_str(*a):
    """Convert numbers to ReportLab's compact PDF fixed-point representation."""
    values = a
    if len(a) == 1 and not isinstance(a[0], (int, float)):
        values = a[0]
    array = np.ascontiguousarray(values, dtype=np.float64)
    return encode_numbers(array)


__all__ = ["fp_str"]
