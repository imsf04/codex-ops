"""Minimal lossless protobuf field editing for the version-tested host protocol."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    number: int
    wire: int
    value: bytes | int
    raw: bytes


def varint(data, pos):
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(data):
            raise ValueError('Incomplete varint')
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, pos
    raise ValueError('Invalid varint')


def pack_varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _field_value(data, pos, wire):
    """Decode one wire value; the enclosing field owns bounds and original bytes."""
    if wire == 0:
        return varint(data, pos)
    if wire in (1, 5):
        size = 8 if wire == 1 else 4
    elif wire == 2:
        size, pos = varint(data, pos)
    else:
        raise ValueError('Unknown wire type')
    return data[pos:pos + size], pos + size


def fields(data):
    result, pos = [], 0
    while pos < len(data):
        start = pos
        tag, pos = varint(data, pos)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ValueError('Invalid protobuf field')
        value, pos = _field_value(data, pos, wire)
        if pos > len(data):
            raise ValueError('Incomplete field')
        result.append(Field(number, wire, value, data[start:pos]))
    return result


def replace(data, number, transform):
    result = []
    for field in fields(data):
        value = transform(field.value) if field.number == number and field.wire == 2 else field.value
        if value == field.value:
            result.append(field.raw)
        else:
            result.append(pack_varint((field.number << 3) | 2) + pack_varint(len(value)) + value)
    return b''.join(result)
