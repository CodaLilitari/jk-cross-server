#!/usr/bin/env python3
"""Collect public YouTube seek previews for timestamped visual research.

These are sparse previews, not continuous footage or an input demonstration.
No account, browser cookies, private session, or downloaded game asset is used.
Keep the output directory private; publish observations and source links instead.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")


def video_id(value):
    if VIDEO_ID.fullmatch(value):
        return value
    parsed = urlparse(value)
    if parsed.scheme != "https":
        raise argparse.ArgumentTypeError("Use a video ID or HTTPS YouTube watch URL.")
    if parsed.hostname in ("youtube.com", "www.youtube.com") and parsed.path == "/watch":
        value = parse_qs(parsed.query).get("v", [""])[0]
    elif parsed.hostname == "youtu.be":
        value = parsed.path.lstrip("/")
    else:
        value = ""
    if not VIDEO_ID.fullmatch(value):
        raise argparse.ArgumentTypeError("Expected a single public YouTube video ID.")
    return value


def public_bytes(url, limit=16 * 1024 * 1024):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=25) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Public response exceeds the research helper's size bound.")
    return data


def collect(identity, output, start, end):
    url = "https://www.youtube.com/watch?v=" + identity
    html = public_bytes(url).decode("utf-8")
    marker = "ytInitialPlayerResponse = "
    if marker not in html:
        raise ValueError("Public player metadata is unavailable; no authentication attempted.")
    player, _ = json.JSONDecoder().raw_decode(html.split(marker, 1)[1])
    details = player["videoDetails"]
    if details["videoId"] != identity:
        raise ValueError("Player response does not identify the requested video.")
    duration = int(details["lengthSeconds"])
    end = min(duration, end if end is not None else duration)
    if not 0 <= start < end:
        raise ValueError("Requested interval does not overlap the video.")
    spec = player["storyboards"]["playerStoryboardSpecRenderer"]["spec"].split("|")
    width, height, count, cols, rows, interval, name, signature = spec[-1].split("#")
    width, height, count, cols, rows, interval = map(int, (width, height, count, cols, rows, interval))
    if min(width, height, count, cols, rows, interval) <= 0 or count > 100_000:
        raise ValueError("Unsupported storyboard dimensions or timing.")
    frames = []
    for index in range(count):
        seconds = index * interval / 1000
        if not start <= seconds < end:
            continue
        sheet, cell = divmod(index, cols * rows)
        row, col = divmod(cell, cols)
        frames.append(dict(frame=index, nominal_time_seconds=seconds, sheet=f"sheet_{sheet:03d}.jpg",
                           row=row, col=col))
    sheets = sorted({frame["frame"] // (cols * rows) for frame in frames})
    if not sheets or len(sheets) > 100:
        raise ValueError("Requested interval has no previews or exceeds 100 sheets.")
    target = output / identity
    target.mkdir(mode=0o700)
    hashes = {}
    for sheet in sheets:
        address = spec[0].replace("$L", str(len(spec) - 2)).replace("$N", name).replace("$M", str(sheet))
        parsed = urlparse(address)
        if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".ytimg.com"):
            raise ValueError("Unexpected preview origin; no request sent.")
        data = public_bytes(address + "&sigh=" + signature, limit=8 * 1024 * 1024)
        if not data.startswith(b"\xff\xd8"):
            raise ValueError("Preview response is not JPEG data.")
        filename = f"sheet_{sheet:03d}.jpg"
        (target / filename).write_bytes(data)
        hashes[filename] = hashlib.sha256(data).hexdigest()
    manifest = dict(schema=1, video_id=identity, url=url, title=details["title"],
                    uploader=details["author"], duration_seconds=duration,
                    collected_at_utc=datetime.now(timezone.utc).isoformat(),
                    method="Official seek previews; nominal timestamps, not continuous or frame-accurate playback.",
                    dimensions=dict(width=width, height=height, rows=rows, cols=cols),
                    interval_ms=interval, preview_sha256=hashes, frames=frames)
    (target / "index.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return dict(video_id=identity, frames=len(frames), sheets=len(sheets), index=str(target / "index.json"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", action="append", type=video_id, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New private directory")
    parser.add_argument("--start", type=float, default=0., help="First nominal preview timestamp in seconds")
    parser.add_argument("--end", type=float, help="Exclusive last timestamp, default video duration")
    args = parser.parse_args(argv)
    if (not math.isfinite(args.start) or args.start < 0
            or args.end is not None and (not math.isfinite(args.end) or args.end <= args.start)):
        parser.error("Expected a finite, positive time interval.")
    if len(args.video) != len(set(args.video)) or len(args.video) > 10:
        parser.error("Use at most ten distinct video IDs.")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for identity in args.video:
        print(json.dumps(collect(identity, args.output, args.start, args.end)), flush=True)


if __name__ == "__main__":
    main()
