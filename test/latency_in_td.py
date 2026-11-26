"""TouchDesigner's side of the latency measurement (latency.py starts it).

argv: [mode, log, name, seconds]
  send_spout / send_ndi: a 64 x 64 picture that turns light and dark every half second, sent
      under `name`; logs when each change is set.
  recv_spout / recv_ndi: receives `name` and logs when its middle turns light or dark (one look
      a frame, 60 a second).
Log lines: `<unix time ns> <0|1>`.
"""

import ctypes
import os
import sys
import time

import td

MODE, LOG, NAME, SECONDS = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])


def now_ns():
    ft = ctypes.c_ulonglong()
    ctypes.windll.kernel32.GetSystemTimePreciseAsFileTime(ctypes.byref(ft))
    return (ft.value - 116444736000000000) * 100


root = op("/project1")
out = open(LOG, "w", encoding="utf-8")
start = time.time()
state = {"last": None}

if MODE.startswith("send"):
    flash = root.create(td.constantTOP, "flash")
    flash.par.outputresolution = "custom"
    flash.par.resolutionw, flash.par.resolutionh = 64, 64
    if MODE == "send_spout":
        sender = root.create(td.syphonspoutoutTOP, "send")
        sender.par.sendername = NAME
    else:
        sender = root.create(td.ndioutTOP, "send")
        sender.par.name = NAME
    sender.inputConnectors[0].connect(flash)
else:
    if MODE == "recv_spout":
        receiver = root.create(td.syphonspoutinTOP, "recv")
        receiver.par.sendername = NAME
    else:
        receiver = root.create(td.ndiinTOP, "recv")
        receiver.par.name = NAME
    probe = root.create(td.nullTOP, "probe")
    probe.inputConnectors[0].connect(receiver)


def tick():
    if time.time() - start > SECONDS:
        out.close()
        os._exit(0)
    if MODE.startswith("send"):
        light = int((time.time() - start) / 0.5) % 2 == 1
        if light != state["last"]:
            v = 1.0 if light else 0.0
            flash.par.colorr = flash.par.colorg = flash.par.colorb = v
            out.write(f"{now_ns()} {int(light)}\n")
            state["last"] = light
    else:
        try:
            g = probe.sample(x=probe.width // 2, y=probe.height // 2)[1]
        except Exception:  # noqa: BLE001
            g = 0.0
        light = g > 0.5
        if light != state["last"]:
            out.write(f"{now_ns()} {int(light)}\n")
            state["last"] = light
    run("args[0]()", tick, delayFrames=1)


run("args[0]()", tick, delayFrames=10)
