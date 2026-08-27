"""PDF numeric and path-command serialization kernels."""

from std.sys.info import simd_width_of

comptime FPtr = UnsafePointer[Float64, AnyOrigin[mut=True]]
comptime BPtr = UnsafePointer[UInt8, AnyOrigin[mut=True]]
comptime U32Ptr = UnsafePointer[UInt32, AnyOrigin[mut=True]]


def put_byte(dst: BPtr, pos: Int, value: Int) -> Int:
    dst[pos] = UInt8(value)
    return pos + 1


def put_uint(dst: BPtr, pos: Int, value: Int64) -> Int:
    var start = pos
    var p = pos
    var v = value
    if v == 0:
        return put_byte(dst, p, 48)
    while v > 0:
        p = put_byte(dst, p, 48 + Int(v % 10))
        v //= 10
    var left = start
    var right = p - 1
    while left < right:
        var t = dst[left]
        dst[left] = dst[right]
        dst[right] = t
        left += 1
        right -= 1
    return p


def put_number(dst: BPtr, pos: Int, value: Float64) -> Int:
    var magnitude = abs(value)
    if magnitude <= 0.0000001:
        return put_byte(dst, pos, 48)

    var decimals = 6
    if magnitude > 1.0:
        var decade = magnitude
        var exponent = 0
        while decade >= 10.0 and exponent < 6:
            decade /= 10.0
            exponent += 1
        decimals = max(0, 6 - exponent)

    var scale = Int64(1)
    for _ in range(decimals):
        scale *= 10
    var scaled = Int64(round(value * Float64(scale)))
    if scaled == 0:
        var zero_pos = pos
        if value < 0.0:
            zero_pos = put_byte(dst, zero_pos, 45)
        return put_byte(dst, zero_pos, 48)

    var p = pos
    var negative = scaled < 0
    if negative:
        p = put_byte(dst, p, 45)
        scaled = -scaled

    var whole = scaled // scale
    var fraction = scaled % scale
    if whole != 0 or negative:
        p = put_uint(dst, p, whole)
    if decimals > 0 and fraction != 0:
        p = put_byte(dst, p, 46)
        var divisor = scale // 10
        for _ in range(decimals):
            p = put_byte(dst, p, 48 + Int(fraction // divisor))
            fraction %= divisor
            if divisor > 1:
                divisor //= 10
        while dst[p - 1] == UInt8(48):
            p -= 1
    return p


def put_operator(dst: BPtr, pos: Int, op: Int64) -> Int:
    var p = pos
    if op == 1:
        p = put_byte(dst, p, 109)
    elif op == 2:
        p = put_byte(dst, p, 108)
    elif op == 3:
        p = put_byte(dst, p, 99)
    elif op == 4:
        p = put_byte(dst, p, 114)
        p = put_byte(dst, p, 101)
    else:
        p = put_byte(dst, p, 104)
    return p


def operator_arity(op: Int64) -> Int:
    if op == 1 or op == 2:
        return 2
    if op == 3:
        return 6
    if op == 4:
        return 4
    return 0


def put_ascii85_digits(dst: BPtr, pos: Int, value: UInt32):
    var temp = value
    var c5 = temp % 85
    temp //= 85
    var c4 = temp % 85
    temp //= 85
    var c3 = temp % 85
    temp //= 85
    var c2 = temp % 85
    var c1 = temp // 85
    dst[pos] = UInt8(c1 + 33)
    dst[pos + 1] = UInt8(c2 + 33)
    dst[pos + 2] = UInt8(c3 + 33)
    dst[pos + 3] = UInt8(c4 + 33)
    dst[pos + 4] = UInt8(c5 + 33)


def encode_ascii85_scalar_group(src: BPtr, dst: BPtr, group: Int):
    var src_pos = group * 4
    var dst_pos = group * 5
    var value = (
        (UInt32(src[src_pos]) << 24)
        | (UInt32(src[src_pos + 1]) << 16)
        | (UInt32(src[src_pos + 2]) << 8)
        | UInt32(src[src_pos + 3])
    )
    if value == 0:
        dst[dst_pos] = UInt8(122)
    else:
        put_ascii85_digits(dst, dst_pos, value)


def encode_ascii85_range(
    words: U32Ptr,
    src: BPtr,
    dst: BPtr,
    begin: Int,
    end: Int,
):
    comptime W = simd_width_of[DType.float64]()
    var i = begin
    var vector_end = end - (end - begin) % W
    while i < vector_end:
        var raw = words.load[width=W, alignment=1](i)
        var values = (
            ((raw & UInt32(0x000000FF)) << UInt32(24))
            | ((raw & UInt32(0x0000FF00)) << UInt32(8))
            | ((raw & UInt32(0x00FF0000)) >> UInt32(8))
            | ((raw & UInt32(0xFF000000)) >> UInt32(24))
        )
        var temp = values
        var c5 = temp % UInt32(85)
        temp //= UInt32(85)
        var c4 = temp % UInt32(85)
        temp //= UInt32(85)
        var c3 = temp % UInt32(85)
        temp //= UInt32(85)
        var c2 = temp % UInt32(85)
        var c1 = temp // UInt32(85)
        for lane in range(W):
            var dst_pos = (i + lane) * 5
            if values[lane] == 0:
                dst[dst_pos] = UInt8(122)
            else:
                dst[dst_pos] = UInt8(c1[lane] + 33)
                dst[dst_pos + 1] = UInt8(c2[lane] + 33)
                dst[dst_pos + 2] = UInt8(c3[lane] + 33)
                dst[dst_pos + 3] = UInt8(c4[lane] + 33)
                dst[dst_pos + 4] = UInt8(c5[lane] + 33)
        i += W
    while i < end:
        encode_ascii85_scalar_group(src, dst, i)
        i += 1


@export("mrl_fp_str")
def mrl_fp_str(values_addr: Int, count: Int, dst_addr: Int) abi("C") -> Int:
    var values = FPtr(unsafe_from_address=values_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    var p = 0
    for i in range(count):
        if i:
            p = put_byte(dst, p, 32)
        p = put_number(dst, p, values[i])
    return p


@export("mrl_encode_lines")
def mrl_encode_lines(coords_addr: Int, count: Int, dst_addr: Int) abi("C") -> Int:
    var coords = FPtr(unsafe_from_address=coords_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    var p = put_byte(dst, 0, 110)
    for i in range(count):
        p = put_byte(dst, p, 10)
        var base = i * 4
        p = put_number(dst, p, coords[base])
        p = put_byte(dst, p, 32)
        p = put_number(dst, p, coords[base + 1])
        p = put_byte(dst, p, 32)
        p = put_byte(dst, p, 109)
        p = put_byte(dst, p, 32)
        p = put_number(dst, p, coords[base + 2])
        p = put_byte(dst, p, 32)
        p = put_number(dst, p, coords[base + 3])
        p = put_byte(dst, p, 32)
        p = put_byte(dst, p, 108)
    p = put_byte(dst, p, 10)
    p = put_byte(dst, p, 83)
    return p


@export("mrl_encode_path")
def mrl_encode_path(
    ops_addr: Int,
    op_count: Int,
    values_addr: Int,
    dst_addr: Int,
    separator: Int,
) abi("C") -> Int:
    var ops = BPtr(unsafe_from_address=ops_addr)
    var values = FPtr(unsafe_from_address=values_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    if op_count == 0:
        return 0
    var p = put_byte(dst, 0, 110)
    var vi = 0
    for i in range(op_count):
        p = put_byte(dst, p, separator)
        var op = Int64(ops[i])
        var arity = operator_arity(op)
        for j in range(arity):
            if j:
                p = put_byte(dst, p, 32)
            p = put_number(dst, p, values[vi])
            vi += 1
        if arity:
            p = put_byte(dst, p, 32)
        p = put_operator(dst, p, op)
    return p


@export("mrl_ascii85_encode")
def mrl_ascii85_encode(
    src_addr: Int,
    count: Int,
    dst_addr: Int,
) abi("C") -> Int:
    var src = BPtr(unsafe_from_address=src_addr)
    var words = U32Ptr(unsafe_from_address=src_addr)
    var dst = BPtr(unsafe_from_address=dst_addr)
    var groups = count // 4
    encode_ascii85_range(words, src, dst, 0, groups)

    var first_zero = groups
    for group in range(groups):
        if dst[group * 5] == UInt8(122):
            first_zero = group
            break

    var p = first_zero * 5
    for group in range(first_zero, groups):
        var slot = group * 5
        if dst[slot] == UInt8(122):
            dst[p] = UInt8(122)
            p += 1
        else:
            for j in range(5):
                dst[p] = dst[slot + j]
                p += 1

    var remainder = count % 4
    if remainder:
        var src_pos = groups * 4
        var value = UInt32(src[src_pos]) << 24
        if remainder > 1:
            value |= UInt32(src[src_pos + 1]) << 16
        if remainder > 2:
            value |= UInt32(src[src_pos + 2]) << 8
        put_ascii85_digits(dst, p, value)
        p += remainder + 1
    p = put_byte(dst, p, 126)
    p = put_byte(dst, p, 62)
    return p
