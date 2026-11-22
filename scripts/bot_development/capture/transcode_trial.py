#!/usr/bin/env python3
"""Encode a qualified arena capture, then fully decode its video and game audio.

Qualification covers recording integrity and the requested presentation. It does
not establish competitive bot quality. Source game audio remains unaltered apart
from AAC encoding, resampling and stereo output.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_video(path, seconds, ffmpeg):
    base = [ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-xerror"]
    decoded = subprocess.run([*base, "-progress", "pipe:1", "-i", str(path),
                              "-map", "0:v:0", "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"],
                             capture_output=True, text=True, check=True, timeout=300)
    values = dict(line.split("=", 1) for line in decoded.stdout.splitlines() if "=" in line)
    if values.get("progress") != "end":
        raise ValueError("Full decode did not finish")
    frames = int(values["frame"])
    num_samples = int(re.findall(r"n_samples:\s*(\d+)", decoded.stderr)[-1])
    mean_db = float(re.search(r"mean_volume:\s*([-\w.]+) dB", decoded.stderr)[1])
    peak_db = float(re.search(r"max_volume:\s*([-\w.]+) dB", decoded.stderr)[1])
    audio_duration = num_samples / (48000 * 2)
    if not (seconds - 1 <= frames / 30 <= seconds + 1.5
            and seconds - 1 <= audio_duration <= seconds + 1.5):
        raise ValueError(f"Decoded durations disagree with requested capture: {frames=} {audio_duration=}")
    if not math.isfinite(mean_db) or not math.isfinite(peak_db) or mean_db < -75 or peak_db < -55:
        raise ValueError(f"Game audio is effectively silent: mean={mean_db} peak={peak_db} dBFS")
    return {"frames": frames, "decoded_video_seconds": frames / 30,
            "decoded_audio_seconds": audio_duration, "mean_volume_dbfs": mean_db,
            "peak_volume_dbfs": peak_db, "full_decode_exit": 0}


def transcode(args, ffmpeg):
    result = json.loads(args.result.read_text(encoding="utf-8"))
    run = (args.run_dir or Path(result["runtime"])).resolve()
    seconds = result["capture_seconds_requested"]
    if (result["qualified"] is not True or result["phase"] != "complete"
            or result["joined"] != 4 or not 30 <= seconds <= 240):
        raise ValueError("Expected a completed, qualified four-seat 30..240-second run")
    receipt = (args.qualification or Path(result["receipt"])).resolve()
    if receipt.name != "qualification.json" or receipt.parent.parent != run:
        raise ValueError("Qualification receipt is outside this run")
    qualification = json.loads(receipt.read_text(encoding="utf-8"))
    expected_saber = {"side": args.expected_saber_side, "tip": args.expected_saber_tip}
    if qualification.get("rendered_saber") != expected_saber:
        raise ValueError("Rendered saber differs from the requested material pair")
    arena, cap = qualification["latest"], result["capture"]
    if (arena["capture"] != cap or cap["status"] != "saved" or cap["audio_tracks"] != 1
            or not seconds - 1 <= cap["duration_seconds"] <= seconds + 1.5
            or arena["mode"] != args.mode
            or arena["seats"]["lily"]["view"] != {"flags": 7, "model": args.expected_model}
            or not re.fullmatch(r"canyon-[0-9a-f]+\.webm", cap["filename"])):
        raise ValueError("Unexpected capture, audio track, mode or third-person model")
    source = (run / cap["filename"]).resolve()
    if source.parent != run or source.stat().st_size != cap["bytes"]:
        raise ValueError("Capture file differs from its receipt")
    output = args.output.resolve()
    receipt_output = args.receipt_output.resolve() if args.receipt_output else output.with_suffix(".json")
    if output.exists() or receipt_output.exists() or output == receipt_output:
        raise FileExistsError("Use new, distinct video and receipt outputs")
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="arena-encode-", dir=output.parent) as temporary:
        encoded = Path(temporary) / "capture.mp4"
        base = [ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-xerror"]
        subprocess.run([*base, "-loglevel", "error", "-n", "-i", str(source),
                        "-map", "0:v:0", "-map", "0:a:0", "-map_metadata", "-1",
                        "-vf", "fps=30,scale=960:540:flags=lanczos,setsar=1", "-c:v", "libx264",
                        "-preset", "medium", "-crf", "23", "-maxrate", "1400k", "-bufsize", "2800k",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-ac", "2",
                        "-movflags", "+faststart", str(encoded)], check=True, timeout=600)
        decoded = inspect_video(encoded, seconds, ffmpeg)
        qa = {"label": result["label"], "build": result["build"],
              "shipped_wasm_sha256": result["shipped_wasm_sha256"], "runtime": str(run),
              "receipt": str(receipt), "source": str(source), "source_sha256": digest(source),
              "mp4": str(output), "bytes": encoded.stat().st_size, "sha256": digest(encoded),
              "capture": cap, "video_codec": "h264", "width": 960, "height": 540,
              "encoding_fps": 30, "audio_codec": "aac", "channels": 2, "audio_hz": 48000,
              "rendered_saber": qualification["rendered_saber"], "transcode_exit": 0, **decoded}
        # No-clobber publication on one filesystem; retain source until success.
        os.link(encoded, output)
        with receipt_output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(qa, indent=2) + "\n")
    return qa


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", help="FFmpeg executable; otherwise PATH or imageio-ffmpeg")
    parser.add_argument("--result", type=Path, help="record_trial.py review-result.json")
    parser.add_argument("--run-dir", type=Path, help="Override runtime location after copying a run")
    parser.add_argument("--qualification", type=Path, help="Override qualification.json location after copying a run")
    parser.add_argument("--output", type=Path, help="New .mp4 path")
    parser.add_argument("--receipt-output", type=Path, help="New .json path; defaults to output with .json suffix")
    parser.add_argument("--expected-model", default="dlil.3do")
    parser.add_argument("--expected-saber-side", default="saberred1.mat")
    parser.add_argument("--expected-saber-tip", default="saberred0.mat")
    parser.add_argument("--mode", default="ff-guns")
    parser.add_argument("--inspect-only", type=Path, help="Fully decode an existing 30 fps, 48 kHz stereo trial MP4")
    parser.add_argument("--seconds", type=int, default=240, help="Expected duration for --inspect-only")
    args = parser.parse_args()
    if not args.inspect_only and (not args.result or not args.output):
        parser.error("Supply --result and --output, or use --inspect-only")
    if not 30 <= args.seconds <= 240:
        parser.error("Expected duration must be 30..240 seconds")
    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if args.inspect_only:
        result = {**inspect_video(args.inspect_only, args.seconds, ffmpeg),
                  "sha256": digest(args.inspect_only), "bytes": args.inspect_only.stat().st_size}
    else:
        result = transcode(args, ffmpeg)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
