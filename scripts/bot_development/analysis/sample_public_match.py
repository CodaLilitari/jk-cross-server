"""Extract a short interval from a public match recording and index 1 Hz frames.

Requires Python 3.11+, yt-dlp and ffmpeg on PATH. An explicit ffmpeg executable
or private installation of yt-dlp can be supplied to the command line.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="public video URL")
    parser.add_argument("start", type=int, help="start time in source seconds")
    parser.add_argument("end", type=int, help="exclusive end time in source seconds")
    parser.add_argument("output", type=Path, help="new output directory")
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"))
    parser.add_argument("--deps", type=Path, help="directory containing yt_dlp")
    args = parser.parse_args()
    if args.start < 0 or not 1 <= args.end - args.start <= 300 or not 144 <= args.height <= 1080:
        parser.error("Use a 1..300 second interval, a nonnegative start and height 144..1080.")
    if not args.ffmpeg:
        parser.error("ffmpeg is required")
    ffmpeg = str(Path(args.ffmpeg).resolve())
    folder = args.output.resolve()
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = os.environ.copy()
    if args.deps:
        env["PYTHONPATH"] = str(args.deps.resolve()) + os.pathsep + env.get("PYTHONPATH", "")
    ffargs = [ffmpeg, "-nostdin", "-v", "error"]
    cmd = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-cache-dir", "--no-playlist",
           "--no-progress", "--socket-timeout", "15", "--retries", "0", "--extractor-retries", "0",
           "--ffmpeg-location", ffmpeg, "--force-keyframes-at-cuts", "--download-sections",
           f"*{args.start}-{args.end}", "-f", f"bestvideo[height<={args.height}]/best[height<={args.height}]",
           "-o", str(folder / "clip.%(ext)s"), args.url]
    status = subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                            timeout=90 + 6 * (args.end - args.start))
    if status.returncode:
        reason = next((label for label in ("HTTP Error 403", "403 Forbidden", "Sign in", "HTTP Error 429")
                       if label in status.stderr), f"download exit {status.returncode}")
        sys.exit(f"Public media retrieval failed ({reason}).")
    clips = [p for p in folder.glob("clip.*") if p.is_file() and p.suffix != ".part"]
    if len(clips) != 1:
        sys.exit("Could not identify one completed video.")
    frames = folder / "frames"
    frames.mkdir()
    duration = args.end - args.start
    subprocess.run(ffargs + ["-i", str(clips[0]), "-vf", "fps=1:start_time=0", "-frames:v", str(duration),
                             "-q:v", "2", str(frames / "frame_%03d.jpg")], check=True, timeout=90)
    recorded = sorted(frames.glob("frame_*.jpg"), key=lambda f:int(f.stem.split("_")[-1]))
    if len(recorded) != duration:
        sys.exit(f"Expected {duration} one-second samples, decoded {len(recorded)}.")
    subprocess.run(ffargs + ["-framerate", "1", "-i", str(frames / "frame_%03d.jpg"),
                             "-vf", "scale=320:-2,tile=2x5:margin=2:padding=2", "-q:v", "3",
                             str(folder / "contact_%02d.jpg")], check=True, timeout=90)
    with clips[0].open("rb") as stream:
        clip_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = {
        "source_url": args.url, "start_s": args.start, "end_s_exclusive": args.end,
        "clip": clips[0].name, "clip_bytes": clips[0].stat().st_size, "sample_fps": 1,
        "clip_sha256": clip_hash,
        "timing": "Nominal 1 Hz sample time. A sampled still cannot establish a subsecond action.",
        "sheet_cols": 2, "sheet_rows": 5, "cell_coordinates": "zero-based, origin top-left",
        "frames": [{"file": f.relative_to(folder).as_posix(), "source_s": args.start + i,
                    "sheet": f"contact_{i // 10 + 1:02d}.jpg", "row": i % 10 // 2, "col": i % 2}
                   for i, f in enumerate(recorded)],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{clips[0].name}: {manifest['clip_bytes']} bytes. {len(recorded)} samples.", flush=True)


if __name__ == "__main__":
    main()
