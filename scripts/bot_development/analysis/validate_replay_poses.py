#!/usr/bin/env python3
"""Conservatively validate declared replay spheres in an owned map's sectors.

This audits map planes without running a controller. It does not establish a
reachable bank, a valid live capture, or a successful traversal. Retail geometry
stays in a temporary local file; the receipt contains only case IDs and margins.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "native/tests/stock_water_replay"))
from geometry import write_geometry


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binary32(value):
    result = struct.unpack("f", struct.pack("f", float(value)))[0]
    if not math.isfinite(result):
        raise ValueError("Pose values must be finite binary32 numbers")
    return result


def enum_value(text, name):
    match = re.search(rf"\b{re.escape(name)}\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)\b", text)
    if not match:
        raise ValueError(f"Missing explicit engine flag: {name}")
    return int(match[1], 0)


def load_planes(path):
    lines = iter(path.read_text().splitlines())
    vertices = [list(map(binary32, next(lines).split())) for _ in range(int(next(lines)))]
    adjoins = [list(map(int, next(lines).split())) for _ in range(int(next(lines)))]
    surfaces = []
    for _ in range(int(next(lines))):
        row = next(lines).split()
        count = int(row[2])
        surfaces.append({"flags": int(row[0]), "adjoin": int(row[1]),
                         "vertex": int(row[3]),
                         "normal": list(map(binary32, row[3 + count:]))})
    sectors = [next(lines).split() for _ in range(int(next(lines)))]
    return vertices, adjoins, surfaces, sectors


def plane_clearance(position, point, normal):
    """Bound native binary32 subtraction, multiplication and sum roundoff.

    Using absolute coordinate terms remains conservative when cancellation
    makes the final dot product small. The floor also covers near-zero clipping
    and subnormal error. This deliberately may reject very large coordinates.
    """
    distance = sum(n * (p - q) for n, p, q in zip(normal, position, point))
    unit = 2 ** -24
    gamma = 12 * unit / (1 - 12 * unit)
    allowance = 1e-5 + gamma * sum(abs(n) * (abs(p) + abs(q))
                                  for n, p, q in zip(normal, position, point))
    return distance, allowance


def validate(source, map_path, cases_path, radius=.065):
    if not math.isfinite(radius) or not 0 < radius <= 1:
        raise ValueError("Radius must be a finite value in (0,1]")
    surface_header = source / "src/World/sithSurface.h"
    enums_header = source / "src/types_enums.h"
    surface_text = surface_header.read_text()
    collision = enum_value(surface_text, "SITH_SURFACE_HAS_COLLISION")
    movement = enum_value(surface_text, "SITHSURF_ADJOIN_ALLOW_MOVEMENT")
    water = enum_value(enums_header.read_text(), "SITH_SECTOR_UNDERWATER")
    with tempfile.TemporaryDirectory(prefix="lily-pose-planes-") as temporary:
        numeric = Path(temporary) / "map.numeric"
        write_geometry(map_path, numeric)
        vertices, adjoins, surfaces, sectors = load_planes(numeric)
    with cases_path.open(newline="") as stream:
        cases = list(csv.DictReader(stream, delimiter="\t"))
    seen, results = set(), []
    # The engine may accept its inner collidebox directly. Requiring all relevant
    # planes here is a stricter sufficient condition. The error bound avoids
    # claiming bit-identical arithmetic with C's float operations.
    for case in cases:
        identity = case["case"]
        if not identity or identity in seen:
            raise ValueError("Replay case IDs must be nonempty and unique")
        seen.add(identity)
        sector_id = int(case["start_sector"])
        if not 0 <= sector_id < len(sectors):
            raise ValueError("Replay start sector is outside the map")
        sector = sectors[sector_id]
        position = [binary32(case[key]) for key in ("x", "y", "z")]
        first, count = map(int, sector[-2:])
        distances = []
        for surface in surfaces[first:first + count]:
            adjoin = surface["adjoin"]
            if surface["flags"] & collision or (adjoin >= 0 and adjoins[adjoin][0] & movement):
                point = vertices[surface["vertex"]]
                distances.append(plane_clearance(position, point, surface["normal"]))
        if not distances or not int(sector[0]) & water:
            raise ValueError("Expected a bounded underwater sector")
        minimum = min(distance for distance, _ in distances)
        conservative = min(distance - allowance for distance, allowance in distances)
        results.append({"case": identity, "start_sector": sector_id,
                        "plane_count": len(distances), "minimum_plane_distance": minimum,
                        "radius_clearance": minimum - radius,
                        "maximum_rounding_allowance": max(allowance for _, allowance in distances),
                        "conservative_radius_clearance": conservative - radius,
                        "center_inside": conservative > 0,
                        "sphere_inside": conservative - radius > 0,
                        "yaw_trials": len(case["yaw_offsets"].split(","))})
    inputs = [surface_header, enums_header, source / "src/Engine/sithIntersect.c"]
    return {"schema": 1, "map_sha256": digest(map_path), "cases_sha256": digest(cases_path),
            "helper_sha256": digest(Path(__file__)),
            "engine_input_sha256": {str(p.relative_to(source)): digest(p) for p in inputs},
            "method": "all engine collision/movement sector planes; binary32 inputs, Python distance with a conservative native roundoff bound",
            "radius": radius, "rounding_allowance": "1e-5 + gamma(12, binary32) * sum(abs(normal) * (abs(position) + abs(plane_vertex)))",
            "all_spheres_inside": bool(results) and all(r["sphere_inside"] for r in results),
            "pose_groups": len(results), "yaw_trials": sum(r["yaw_trials"] for r in results),
            "cases": results,
            "limitation": "Geometry-only sufficient check; no controller outcomes or reachability inferred."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = validate(args.source.resolve(), args.map.resolve(), args.cases.resolve())
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in ("cases_sha256", "all_spheres_inside", "pose_groups", "yaw_trials")}))
    return 0 if receipt["all_spheres_inside"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
