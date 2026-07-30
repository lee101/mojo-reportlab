"""ctypes binding for the Mojo content-stream kernels."""

from __future__ import annotations

import ctypes
import os
import subprocess

import numpy as np
from reportlab.lib.rl_accel import fp_str as _upstream_fp_str

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "dist", "libmojo-reportlab.so")

I = ctypes.c_int64
_SIGNATURES = {
    "mrl_fp_str": ([I, I, I], I),
    "mrl_encode_lines": ([I, I, I], I),
    "mrl_encode_path": ([I, I, I, I, I], I),
    "mrl_ascii85_encode": ([I, I, I], I),
}

_library: ctypes.CDLL | None = None


class BuildError(RuntimeError):
    pass


def build(force: bool = False) -> str:
    source = os.path.join(ROOT, "src", "kernels.mojo")
    if not force and os.path.exists(LIB) and os.path.getmtime(LIB) >= os.path.getmtime(source):
        return LIB
    proc = subprocess.run(
        ["pixi", "run", "--manifest-path", os.path.join(ROOT, "pixi.toml"), "build"],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if proc.returncode or not os.path.exists(LIB):
        raise BuildError((proc.stderr or proc.stdout).strip()[:4000])
    return LIB


def lib() -> ctypes.CDLL:
    global _library
    if _library is None:
        _library = ctypes.CDLL(build())
        for name, (argtypes, restype) in _SIGNATURES.items():
            fn = getattr(_library, name)
            fn.argtypes = argtypes
            fn.restype = restype
    return _library


def addr(array: np.ndarray) -> int:
    address = int(array.ctypes.data)
    if not address:
        raise ValueError("cannot pass a null NumPy buffer to Mojo")
    return address


def _checked_size(size: int, capacity: int, operation: str) -> int:
    if size < 0 or size > capacity:
        raise RuntimeError(
            f"{operation} returned invalid output length {size} "
            f"for a {capacity}-byte buffer"
        )
    return size


def _fast_path_safe(values: np.ndarray) -> bool:
    return not values.size or (
        np.isfinite(values).all() and np.abs(values).max() <= 9e18
    )


def encode_numbers(values: np.ndarray) -> str:
    values = np.ascontiguousarray(values, dtype=np.float64).reshape(-1)
    if not values.size:
        return ""
    if not _fast_path_safe(values):
        return _upstream_fp_str(values.tolist())
    destination = np.empty(values.size * 32, dtype=np.uint8)
    size = _checked_size(
        lib().mrl_fp_str(addr(values), values.size, addr(destination)),
        destination.size,
        "mrl_fp_str",
    )
    return destination[:size].tobytes().decode("ascii")


def encode_lines(coords: np.ndarray) -> str:
    coords = np.ascontiguousarray(coords, dtype=np.float64)
    if coords.size == 0:
        return "n\nS"
    if coords.ndim != 2 or coords.shape[1] != 4:
        raise ValueError("coords must be a two-dimensional array with four columns")
    if not _fast_path_safe(coords):
        commands = ["n"]
        for x1, y1, x2, y2 in coords:
            commands.append(
                f"{_upstream_fp_str(x1, y1)} m {_upstream_fp_str(x2, y2)} l"
            )
        commands.append("S")
        return "\n".join(commands)
    destination = np.empty(coords.shape[0] * 132 + 3, dtype=np.uint8)
    size = _checked_size(
        lib().mrl_encode_lines(addr(coords), coords.shape[0], addr(destination)),
        destination.size,
        "mrl_encode_lines",
    )
    return destination[:size].tobytes().decode("ascii")


def encode_path(ops: np.ndarray, values: np.ndarray, separator: str = " ") -> str:
    ops = np.ascontiguousarray(ops, dtype=np.int64).reshape(-1)
    values = np.ascontiguousarray(values, dtype=np.float64).reshape(-1)
    if len(separator) != 1 or not separator.isascii():
        raise ValueError("separator must be one ASCII character")
    if not ops.size:
        if values.size:
            raise ValueError("path values were supplied without operators")
        return ""
    arities = {1: 2, 2: 2, 3: 6, 4: 4, 5: 0}
    try:
        expected_values = sum(arities[int(op)] for op in ops)
    except KeyError as error:
        raise ValueError(f"unsupported path operator {error.args[0]}") from None
    if values.size != expected_values:
        raise ValueError(
            f"path operators require {expected_values} values, got {values.size}"
        )
    if not _fast_path_safe(values):
        operators = {
            1: ("m", 2),
            2: ("l", 2),
            3: ("c", 6),
            4: ("re", 4),
            5: ("h", 0),
        }
        commands = ["n"]
        offset = 0
        for raw_op in ops:
            operator, arity = operators[int(raw_op)]
            command = _upstream_fp_str(values[offset : offset + arity].tolist())
            commands.append(f"{command} {operator}" if arity else operator)
            offset += arity
        return separator.join(commands)
    destination = np.empty(values.size * 32 + ops.size * 5 + 1, dtype=np.uint8)
    size = _checked_size(
        lib().mrl_encode_path(
            addr(ops), ops.size, addr(values), addr(destination), ord(separator)
        ),
        destination.size,
        "mrl_encode_path",
    )
    return destination[:size].tobytes().decode("ascii")


def ascii85_encode(source: bytes) -> str:
    if not isinstance(source, bytes):
        source = bytes(source)
    if not source:
        return "~>"
    values = np.frombuffer(source, dtype=np.uint8)
    destination = np.empty(((values.size + 3) // 4) * 5 + 2, dtype=np.uint8)
    size = _checked_size(
        lib().mrl_ascii85_encode(addr(values), values.size, addr(destination)),
        destination.size,
        "mrl_ascii85_encode",
    )
    return destination[:size].tobytes().decode("ascii")
