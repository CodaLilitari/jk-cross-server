"""Launch the four private JKWeb arena seats in a visible installed Chrome."""
import argparse
import asyncio
from collections import deque
import contextlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit


SEATS = ("lily", "boba", "jan", "yun")
SOFTWARE = re.compile(r"swiftshader|llvmpipe|softpipe|software|basic render|\bwarp\b|lavapipe", re.I)
DEVICE = re.compile(r"nvidia|geforce|quadro|radeon|intel|\bamd\b|adreno|mali|apple|powervr|qualcomm|vivante", re.I)


def read_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    origin = manifest["url"]
    parsed = urlsplit(origin)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port or origin != f"http://127.0.0.1:{parsed.port}":
        raise ValueError("The arena URL must be the service's literal IPv4 loopback origin.")
    if manifest["pages"] != {i: origin + "/bot/" + i for i in SEATS} or manifest["status"] != origin + "/status":
        raise ValueError("Arena pages and status must belong to this run.")
    tokens = {}
    for ident in SEATS:
        cred = json.loads((path.parent / "engines" / (ident + ".json")).read_text(encoding="utf-8-sig"))
        if cred.get("id") != ident or cred.get("url") != origin or not re.fullmatch(r"[A-Za-z0-9_-]{24,128}", cred.get("token", "")):
            raise ValueError("Engine credential does not match its seat and run.")
        tokens[ident] = cred["token"]
    return manifest, tokens


def check_view(status):
    seats = status.get("seats") or {}
    if status.get("joined_count") != 4 or any(not seats.get(i, {}).get("joined") for i in SEATS):
        return "waiting for four fresh engine states"
    own = [seats[i].get("self") or {} for i in SEATS]
    slots = [p.get("slot") for p in own]
    if any(type(slot) is not int for slot in slots) or set(slots) != set(range(4)) or slots[0] != 0:
        return "waiting for four distinct slots with Lily hosting"
    nets = {p.get("net_id") for p in own}
    if len(nets) != 4 or any(type(n) is not int or n <= 0 for n in nets):
        return "waiting for four distinct network players"
    view = seats["lily"].get("view") or {}
    if view.get("flags") != 7:
        return "waiting for Lily's accelerated third-person camera"
    expected = "dlil.3do" if status.get("custom_model") else "ky.3do"
    if view.get("model", "").replace("\\", "/").split("/")[-1].lower() != expected:
        return "waiting for rendered " + expected
    gl = seats["lily"].get("graphics") or {}
    renderer = gl.get("renderer") or ""
    if SOFTWARE.search(renderer + " " + (gl.get("vendor") or "")):
        return "software renderer reported: " + renderer
    if not DEVICE.search(renderer) or not gl.get("width") or not gl.get("height"):
        return "waiting for a named hardware WebGL renderer and drawable"
    if abs(gl["width"] * 9 - gl["height"] * 16) > 16:
        return "waiting for a 16:9 drawing buffer"
    return None


async def launch(args):
    from playwright.async_api import async_playwright

    manifest, tokens = read_manifest(args.run_json)
    out = Path(tempfile.mkdtemp(prefix="chrome-qa-", dir=args.run_json.parent))
    receipt = out / "qualification.json"
    print(f"Qualification receipt: {receipt}", flush=True)
    logs = {i: deque(maxlen=120) for i in SEATS}
    navigation = {i: deque(maxlen=80) for i in SEATS}
    samples = deque(maxlen=360)
    report = {"room": manifest["room"], "phase": "launch", "qualified": False}
    pages = {}
    host_room = asyncio.Event()
    started = time.monotonic()

    def redact(value):
        for token in tokens.values():
            value = value.replace(token, "[redacted]")
        return value

    def log(ident, kind, message):
        entry = [round(time.monotonic() - started, 2), kind, redact(str(message))[:700]]
        logs[ident].append(entry)
        if "BOT_NAV_READY " in entry[2] or "BOT_NAV_COVERAGE " in entry[2]:
            navigation[ident].append(entry)
        if ident == "lily" and "BOT_WEB_HOST " in str(message):
            host_room.set()

    def save():
        data = {**report, "samples": list(samples), "console": {i: list(v) for i, v in logs.items()},
                "navigation": {i: list(v) for i, v in navigation.items()}}
        temp = out / "qualification.tmp"
        temp.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
        os.replace(temp, receipt)

    async def snapshot(tag):
        for ident, page in pages.items():
            try:
                await page.screenshot(path=out / (ident + "-" + tag + ".png"), timeout=4500)
            except Exception as exc:
                log(ident, "screenshot", exc)

    async def status():
        res = await pages["lily"].request.get(manifest["status"], timeout=4000)
        try:
            if not res.ok:
                raise RuntimeError("Arena status returned HTTP " + str(res.status))
            result = await res.json()
        finally:
            await res.dispose()
        report["latest"] = result
        samples.append({"seconds": round(time.monotonic() - started, 2),
                        "joined": result["joined_count"],
                        "players": {i: s.get("self") for i, s in result["seats"].items()},
                        "lily_view": result["seats"]["lily"].get("view")})
        return result

    async def wait_for(what, timeout, predicate):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = await status()
            reason = predicate(result)
            report["waiting"] = reason
            save()
            if reason is None:
                return result
            if reason.startswith("software renderer reported"):
                raise RuntimeError(reason)
            if any(s["stage"] == "failed" for s in result["seats"].values()):
                raise RuntimeError("Browser engine reported startup failure.")
            await asyncio.sleep(1)
        raise RuntimeError(f"{what} timed out: {report.get('waiting')}")

    async def open_seat(browser, ident):
        # Keep the observed seat large; the three unrecorded players need much
        # less raster work while they continue ordinary game simulation.
        viewport = {"width": 1100, "height": 780} if ident == "lily" else {"width": 640, "height": 400}
        ctx = await browser.new_context(viewport=viewport, device_scale_factor=1)
        page = await ctx.new_page()
        pages[ident] = page
        await page.add_init_script(
            "if(window===top && location.href===" + json.dumps(manifest["pages"][ident])
            + ") window.__JK_BOT_TOKEN=" + json.dumps(tokens[ident]) + ";"
        )
        page.on("console", lambda msg: log(ident, msg.type, msg.text))
        page.on("pageerror", lambda exc: log(ident, "pageerror", exc))
        await page.goto(manifest["pages"][ident], wait_until="domcontentloaded", timeout=30000)

    save()
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                executable_path=str(args.chrome), headless=False,
                args=["--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                      "--disable-backgrounding-occluded-windows", "--autoplay-policy=no-user-gesture-required"],
            )
            try:
                await open_seat(browser, "lily")
                report["phase"] = "host"
                await wait_for("Host creation", args.timeout, lambda s: None if host_room.is_set()
                               or s["seats"]["lily"]["joined"] else "waiting for relay host")
                report["phase"] = "joining"
                await asyncio.gather(*(open_seat(browser, i) for i in SEATS[1:]))
                lily = pages["lily"]
                await lily.bring_to_front()
                await wait_for("Qualification", args.timeout, check_view)
                report.update(phase="qualified", qualified=True)
                save()
                print("Four live seats, Lily's third-person model and hardware WebGL verified.", flush=True)
                await snapshot("joined")
                await lily.bring_to_front()
                if args.record_seconds:
                    report.update(phase="warmup", warmup_seconds=args.warmup_seconds)
                    save()
                    deadline = time.monotonic() + args.warmup_seconds
                    while time.monotonic() < deadline:
                        await status()
                        save()
                        await asyncio.sleep(min(1, max(0, deadline - time.monotonic())))
                    await lily.bring_to_front()
                    await wait_for("Capture readiness", args.timeout, check_view)
                    report["phase"] = "recording"
                    report["recorder"] = await lily.evaluate("s=>window.jkBot.startRecording(s)", args.record_seconds)
                    save()

                    def capture_wait(s):
                        cap = s.get("capture") or {}
                        if cap.get("status") == "aborted":
                            raise RuntimeError("The browser aborted the recording.")
                        if cap.get("status") != "saved":
                            return "waiting for saved WebM"
                        if cap.get("duration_seconds", 0) < args.record_seconds - 1:
                            raise RuntimeError("Saved WebM is shorter than the requested wall-clock recording.")
                        name = cap.get("filename", "")
                        if not re.fullmatch(r"canyon-[0-9a-f]+\.webm", name):
                            raise RuntimeError("The recorder did not return a saved arena filename.")
                        path = args.run_json.parent / name
                        with path.open("rb") as recording:
                            if recording.read(4) != b"\x1a\x45\xdf\xa3" or path.stat().st_size != cap.get("bytes"):
                                raise RuntimeError("Saved recording size or WebM header differs from the receipt.")
                        return None

                    await wait_for("Recording", args.record_seconds + 60, capture_wait)
                    report["phase"] = "recorded"
                    save()
                    await snapshot("recorded")
                    await lily.bring_to_front()
                if (args.hold_seconds is None and not args.record_seconds) or args.hold_seconds:
                    report["phase"] = "holding"
                    deadline = time.monotonic() + args.hold_seconds if args.hold_seconds else float("inf")
                    print("Browser stays open for companion control.", flush=True)
                    while time.monotonic() < deadline:
                        await status()
                        save()
                        await asyncio.sleep(min(2, max(0, deadline - time.monotonic())))
                report["phase"] = "complete"
            except BaseException as exc:
                report.update(phase="stopped", error=redact(str(exc) or type(exc).__name__))
                save()
                with contextlib.suppress(Exception):
                    await snapshot("stopped")
                raise
            finally:
                await browser.close()
    except BaseException as exc:
        if report["phase"] != "stopped":
            report.update(phase="stopped", error=redact(str(exc) or type(exc).__name__))
        raise
    finally:
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", required=True, type=Path, help="Installed Google Chrome or Chromium executable.")
    parser.add_argument("--run-json", required=True, type=Path, help="Private arena run.json from web_bots.serve.")
    parser.add_argument("--timeout", type=int, default=150, help="Seconds allowed for host creation and for joins.")
    parser.add_argument("--record-seconds", type=int, default=0, help="Record 1..240 seconds after qualification.")
    parser.add_argument("--warmup-seconds", type=int, default=20, help="Sample live gameplay for this many seconds before recording (default 20).")
    parser.add_argument("--hold-seconds", type=int, default=None, help="Keep the browsers open after qualification or capture. Without capture, the default is until interrupted.")
    args = parser.parse_args()
    if not args.chrome.is_file() or not args.run_json.is_file() or not 0 <= args.record_seconds <= 240 or args.timeout <= 0 or args.warmup_seconds < 0 or (args.hold_seconds is not None and args.hold_seconds < 0):
        parser.error("Supply existing files, positive timeout, 0..240 recording seconds and nonnegative warmup and hold times.")
    try:
        asyncio.run(launch(args))
    except KeyboardInterrupt:
        return 130
    except Exception:
        print("Arena launch failed. See the private qualification receipt for details.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
