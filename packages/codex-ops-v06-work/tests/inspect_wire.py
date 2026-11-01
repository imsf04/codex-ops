"""Bounded protobuf wire inventory for owned fixture traces; not schema inference proof."""
import json
from pathlib import Path
import sys


def varint(data, pos):
    number = 0
    for shift in range(0, 70, 7):
        byte = data[pos]
        pos += 1
        number |= (byte & 127) << shift
        if byte < 128:
            return number, pos
    raise ValueError('Invalid varint')


def fields(data):
    pos = 0
    values = []
    while pos < len(data):
        tag, pos = varint(data, pos)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError('Invalid field')
        if wire == 0:
            value, pos = varint(data, pos)
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            value, pos = data[pos:pos + size], pos + size
        elif wire == 2:
            size, pos = varint(data, pos)
            value, pos = data[pos:pos + size], pos + size
        else:
            raise ValueError('Unsupported wire type')
        if pos > len(data):
            raise ValueError('Incomplete field')
        values.append((number, wire, value))
    return values


def describe(data, depth=0):
    result = []
    for number, wire, value in fields(data)[:20]:
        item = {'field': number, 'wire': wire}
        if isinstance(value, int):
            item['value'] = value
        else:
            item['bytes'] = len(value)
            try:
                if depth >= 6 or not value or (value.decode('utf-8', errors='replace').isprintable()):
                    raise ValueError()
                item['nestedCandidate'] = describe(value, depth + 1)
            except (ValueError, IndexError):
                item['textPrefix'] = value.decode('utf-8', errors='replace')[:160]
        result.append(item)
    return result


if __name__ == '__main__':
    for frame in json.loads(Path(sys.argv[1]).read_text()):
        if frame['direction'] == 'from_host':
            print(json.dumps({'method': frame['method'], 'fields': describe(bytes.fromhex(frame['hex']))}, ensure_ascii=False))
