"""Export only the world data needed by the local replay."""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from bots.map_audit import parse_jkl


def write_geometry(jkl, output_path):
    text = jkl.read_text(encoding="latin-1")
    rows = [" ".join(line.partition("#")[0].lower().split()) for line in text.splitlines()]
    rows = [row for row in rows if row]

    def section(name):
        index = next(i for i, row in enumerate(rows) if re.fullmatch(rf"world {name} \d+", row))
        return index + 1, int(rows[index].split()[-1])

    def contents(index):
        return rows[index].split(":", 1)[1].strip()

    with output_path.open("w") as output:
        def emit(*values):
            print(*values, file=output)

        start, count = section("vertices")
        emit(count)
        for i in range(start, start + count):
            emit(contents(i))
        start, count = section("adjoins")
        emit(count)
        for i in range(start, start + count):
            flags, mirror, *_ = contents(i).split()
            emit(int(flags, 16), mirror)
        start, count = section("surfaces")
        emit(count)
        for i in range(start, start + count):
            fields = contents(i).split()
            vertices = int(fields[8])
            indices = [pair.split(",")[0] for pair in fields[9:9 + vertices]]
            emit(int(fields[1], 16), fields[6], vertices, *indices, contents(i + count))
        start, count = section("sectors")
        emit(count)
        starts = [i for i in range(start, len(rows)) if re.fullmatch(r"sector \d+", rows[i])][:count]
        for first in starts:
            last = next(i for i in range(first, len(rows)) if rows[i].startswith("surfaces "))
            fields = {line.split()[0]: line.split()[1:] for line in rows[first:last + 1]}
            emit(int(fields["flags"][0], 16), *fields["boundbox"], int("collidebox" in fields),
                 *fields.get("collidebox", [0] * 6), *fields["center"], *fields["surfaces"])
        things = parse_jkl(text)["things"]
        emit(max(things) + 1)
        for index in range(max(things) + 1):
            thing = things.get(index)
            if not thing:
                emit(0, 0, 0, 0, 0, "_")
                continue
            kind = {"player": 10, "item": 5}.get(thing["properties"].get("type"), 0)
            emit(kind, thing["sector"], *thing["position"], thing["template"])
