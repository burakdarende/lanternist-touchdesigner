"""Runs inside TouchDesigner (run_tests.py starts it): loads the built component next to a
running Lanternist engine and checks what an artist would do with it. Writes PASS / FAIL lines
to the log (argv[2]) and ends TouchDesigner.

argv: [tox, log, osc port, oscquery port, Studio's Spout sender name]
"""

import ctypes
import json
import os
import socket
import struct
import sys
import time
import urllib.request

import td

TOX, LOG, OSC, QUERY, STUDIO_SENDER = sys.argv[1:6]
OSC, QUERY = int(OSC), int(QUERY)
results = []


def log(line):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def check(name, ok, detail=""):
    results.append(ok)
    log(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""))


def query(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{QUERY}{path}", timeout=2) as r:
        return json.loads(r.read().decode("utf-8"))


def osc_message(address, value):
    def pad(b):
        return b + b"\0" * (4 - len(b) % 4)
    return pad(address.encode()) + pad(b",f") + struct.pack(">f", value)


root = op("/project1")
comp = root.loadTox(TOX)
comp.par.Studio = "127.0.0.1"
comp.par.Oscport = OSC
comp.par.Queryport = QUERY
flash = root.create(td.constantTOP, "flash")
flash.par.resolutionw, flash.par.resolutionh = 64, 64
flash.par.outputresolution = "custom"
flash.par.colorr, flash.par.colorg, flash.par.colorb = 0.0, 1.0, 0.0
comp.par.Top1 = flash
comp.par.Method = "both"
comp.par.Receive = True
comp.par.Receivemethod = "spout"
comp.par.Receivename = STUDIO_SENDER

state = {"step": 0, "start": time.time()}


def opacity_par():
    for p in comp.customPars:
        if p.label.endswith("/opacity") and p.page.name == "Studio parameters":
            return p
    return None


def step():
    s = state["step"]
    t = time.time() - state["start"]
    if s == 0:
        if "Connected" in comp.par.Status.eval() or t > 20:
            check("connects to Studio", "Connected" in comp.par.Status.eval(), comp.par.Status.eval())
            pars = [p for p in comp.customPars if p.page.name == "Studio parameters"]
            check("reads Studio's parameters", len(pars) > 5, f"{len(pars)} parameters")
            state["step"], state["start"] = 1, time.time()
    elif s == 1:
        p = opacity_par()
        if p is None:
            check("an opacity parameter is mirrored", False)
            state["step"] = 9
            return
        state["par"] = p
        state["addr"] = p.label
        p.val = 0.25
        state["step"], state["start"] = 2, time.time()
    elif s == 2 and t > 1.0:
        value = query(state["addr"]).get("VALUE", [None])[0]
        check("a change in TouchDesigner reaches Studio", value is not None and abs(value - 0.25) < 1e-3,
              f"{state['addr']} = {value}")
        # Studio changes it (another controller): it comes back over LISTEN.
        s_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s_.sendto(osc_message(state["addr"], 0.75), ("127.0.0.1", OSC))
        s_.close()
        state["step"], state["start"] = 3, time.time()
    elif s == 3 and (abs(state["par"].eval() - 0.75) < 1e-3 or t > 3.0):
        check("a change in Studio reaches TouchDesigner", abs(state["par"].eval() - 0.75) < 1e-3,
              f"{state['par'].eval()}")
        # GO: run_tests.py finds the cue in the engine's log.
        log("GO sent")
        comp.par.Go.pulse()
        state["step"], state["start"] = 5, time.time()
    elif s == 5 and t > 1.0:
        sp, nd = comp.op("spout1"), comp.op("ndi1")
        check("sends TOP 1 over Spout", bool(sp.par.active.eval()) and not sp.errors(),
              f"{sp.par.sendername.eval()} {sp.errors()}")
        check("sends TOP 1 over NDI", bool(nd.par.active.eval()) and not nd.errors(),
              f"{nd.par.name.eval()} {nd.errors()}")
        state["step"], state["start"] = 6, time.time()
    elif s == 6:
        # Studio's output: once its Spout sender is up (it may start after this component).
        got = comp.op("out1")
        try:
            pixel = got.sample(x=got.width // 2, y=got.height // 2)
        except Exception as e:  # noqa: BLE001
            pixel = (0, 0, 0, 0)
            log(f"sample: {e}")
        ok = got.width > 16 and sum(pixel[:3]) > 0.01
        # A sender left behind by a program that was killed keeps its name; the running one
        # gets `_2`: after a few seconds, take the newest of that name.
        if not ok and t > 4.0:
            names = [n for n in comp.op("from_studio_spout").par.sendername.menuNames
                     if n.startswith(STUDIO_SENDER)]
            if names:
                comp.par.Receivename = names[-1]
        if ok or t > 20.0:
            sin = comp.op("from_studio_spout")
            check("receives Studio's output over Spout", ok,
                  f"{got.width}x{got.height} {pixel} wanted {sin.par.sendername.eval()!r} "
                  f"senders {sin.par.sendername.menuNames} {sin.errors()} {sin.warnings()}")
            state["step"] = 9
    if state["step"] == 9:
        log(f"DONE {sum(results)}/{len(results)}")
        os._exit(0 if all(results) else 1)


def frame_callback():
    try:
        step()
    except Exception as e:  # noqa: BLE001
        import traceback
        log("FAIL exception: " + traceback.format_exc())
        os._exit(1)
    run("args[0]()", frame_callback, delayFrames=5)


run("args[0]()", frame_callback, delayFrames=30)
