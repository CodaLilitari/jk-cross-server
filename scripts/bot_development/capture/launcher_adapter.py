"""Guarded diagnostics adapter for the pinned, unmodified Chrome launcher.

Changes only host capture diagnostics: headless mode, audio, log retention,
recording timestamps and rendered saber material reporting. Engine inputs and
runtime source are unchanged. Unknown launcher shapes fail before execution.
"""
from pathlib import Path
import types


def load_capture_launcher(checkout):
    checkout = Path(checkout)
    # Keep engine behavior unchanged; use invisible hardware Chrome and retain the full bounded trial log.
    source=(checkout/"web_bots/launch_chrome.py").read_text()
    if source.count("headless=False")!=1:raise RuntimeError("Unexpected launcher")
    module=types.ModuleType("private_headless_review");module.__file__=str(checkout/"web_bots/launch_chrome.py")
    if source.count("deque(maxlen=120)")!=1:raise RuntimeError("Unexpected console retention")
    source=source.replace("headless=False","headless=True").replace("deque(maxlen=120)","deque(maxlen=6000)")
    if source.count("executable_path=str(args.chrome), headless=True,")!=1: raise RuntimeError("Unexpected browser audio options")
    source=source.replace("executable_path=str(args.chrome), headless=True,", "executable_path=str(args.chrome), headless=True, ignore_default_args=['--mute-audio'],")
    recorder_line="                    report[\"recorder\"] = await lily.evaluate(\"s=>window.jkBot.startRecording(s)\", args.record_seconds)"
    if source.count(recorder_line)!=1:raise RuntimeError("Unexpected recorder entry point")
    source=source.replace(recorder_line,"                    report[\"console_clock_origin_monotonic\"] = started\n                    report[\"recording_start_monotonic\"] = time.monotonic()\n                    report[\"recorder\"] = await lily.evaluate(\"s=>window.jkBot.startRecording(s)\", args.record_seconds)\n                    report[\"recording_return_monotonic\"] = time.monotonic()\n                    if report[\"recorder\"].get(\"audio_tracks\") != 1:\n                        raise RuntimeError(\"Recording requires one game-audio track\")")
    appearance_js="""() => {
      const m=globalThis.Module, heap=m.HEAPU8 || globalThis.HEAPU8;
      const read=tip=>{const ptr=m._jkBotWebSaberMaterial(tip);
        if(!ptr || !heap || ptr<0 || ptr>=heap.length)return "";
        const data=heap.subarray(ptr,Math.min(ptr+1024,heap.length));const end=data.indexOf(0);
        return end<0 ? "" : new TextDecoder().decode(data.subarray(0,end));};
      return {side:read(0),tip:read(1)};
    }"""
    qualified_line='                report.update(phase="qualified", qualified=True)'
    if source.count(qualified_line)!=1: raise RuntimeError("Unexpected qualification entry point")
    source=source.replace(qualified_line,qualified_line+'\n                report["rendered_saber"] = await lily.evaluate('+repr(appearance_js)+')')
    exec(compile(source,module.__file__,"exec"),module.__dict__)
    return module
