"""Assembles "Lanternist Studio for TouchDesigner" inside TouchDesigner and saves it as a .tox.

Run by make.py (TouchDesigner's start script calls it with: output .tox, log file). Uses only
TouchDesigner's Python API; the component's logic comes from ../src.
"""

import os
import pathlib
import sys
import traceback

import td

OUT, LOG = sys.argv[1], sys.argv[2]
HERE = pathlib.Path(__file__).resolve().parent.parent
SRC = HERE / "src"
VERSION = (HERE / "VERSION").read_text().strip()
SLOTS = 4


def log(*parts):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(str(p) for p in parts) + "\n")


def text_dat(comp, name, text, x, y):
    d = comp.create(td.textDAT, name)
    d.text = text
    d.nodeX, d.nodeY = x, y
    return d


def build():
    root = op("/project1")
    comp = root.create(td.baseCOMP, "lanternist_studio")
    comp.color = (0.93, 0.62, 0.12)
    comp.comment = f"Lanternist Studio for TouchDesigner {VERSION}"

    # ---- parameters ----
    page = comp.appendCustomPage("Studio")
    page.appendStr("Studio", label="Studio address (empty: find it)")
    page.appendInt("Oscport", label="OSC port")[0].val = 8000
    page.appendInt("Queryport", label="OSCQuery port")[0].val = 8001
    page.appendPulse("Reconnect", label="Find Studio again")
    status = page.appendStr("Status", label="Status")[0]
    status.readOnly = True
    page.appendPulse("Go", label="GO")
    page.appendPulse("Back", label="BACK")
    page.appendStr("Cue", label="Cue (name or number)")
    page.appendPulse("Gotocue", label="Go to cue")
    about = page.appendStr("Version", label="Version")[0]
    about.val = VERSION
    about.readOnly = True

    send = comp.appendCustomPage("Send to Studio")
    method = send.appendMenu("Method", label="Send over")[0]
    method.menuNames = ["spout", "ndi", "both"]
    method.menuLabels = ["Spout (this computer)", "NDI (the network)", "Spout and NDI"]
    method.val = "spout"
    send.appendStr("Name", label="Sender name (empty: TD - project)")
    send.appendPulse("Showinstudio", label="Show in Studio (this computer)")
    for i in range(1, SLOTS + 1):
        on = send.appendToggle(f"Send{i}", label=f"Send TOP {i}")[0]
        on.val = i == 1
        send.appendTOP(f"Top{i}", label=f"TOP {i}")

    recv = comp.appendCustomPage("From Studio")
    recv.appendToggle("Receive", label="Receive a Studio output")
    rm = recv.appendMenu("Receivemethod", label="Over")[0]
    rm.menuNames = ["spout", "ndi"]
    rm.menuLabels = ["Spout (this computer)", "NDI (the network)"]
    recv.appendStr("Receivename", label="Studio's sender name")[0].val = "Lanternist - output"

    # ---- sending: Spout and NDI per TOP ----
    for i in range(1, SLOTS + 1):
        y = -150 * i
        sel = comp.create(td.selectTOP, f"top{i}")
        sel.par.top.expr = f"parent().par.Top{i}.eval()"
        sel.nodeX, sel.nodeY = 0, y
        sp = comp.create(td.syphonspoutoutTOP, f"spout{i}")
        sp.inputConnectors[0].connect(sel)
        sp.par.active = False
        sp.nodeX, sp.nodeY = 200, y
        nd = comp.create(td.ndioutTOP, f"ndi{i}")
        nd.inputConnectors[0].connect(sel)
        nd.par.active = False
        nd.nodeX, nd.nodeY = 400, y

    # ---- receiving a Studio output ----
    sin = comp.create(td.syphonspoutinTOP, "from_studio_spout")
    sin.nodeX, sin.nodeY = 700, -150
    nin = comp.create(td.ndiinTOP, "from_studio_ndi")
    nin.par.active = False
    nin.nodeX, nin.nodeY = 700, -300
    sw = comp.create(td.switchTOP, "from_studio")
    sw.inputConnectors[0].connect(sin)
    sw.inputConnectors[1].connect(nin)
    sw.nodeX, sw.nodeY = 900, -220
    out = comp.create(td.outTOP, "out1")
    out.inputConnectors[0].connect(sw)
    out.nodeX, out.nodeY = 1100, -220

    # ---- talking to Studio ----
    osc = comp.create(td.oscoutDAT, "osc_out")
    osc.par.address = "127.0.0.1"
    osc.par.port = 8000
    osc.nodeX, osc.nodeY = 0, 200

    cb = text_dat(comp, "callbacks", (SRC / "callbacks.py").read_text(encoding="utf-8"), 200, 400)
    ws = comp.create(td.websocketDAT, "listen")
    ws.par.netaddress = "127.0.0.1"
    ws.par.port = 8001
    ws.par.active = False
    ws.par.callbacks = cb
    ws.nodeX, ws.nodeY = 200, 200

    readme = text_dat(comp, "readme", (SRC / "readme_in_td.txt").read_text(encoding="utf-8"), 600, 200)
    readme.comment = "How to use it"

    # ---- logic: the extension, then what calls it ----
    text_dat(comp, "extension", (SRC / "extension.py").read_text(encoding="utf-8"), 0, 400)
    comp.par.ext0object = "op('./extension').module.LanternistStudio(me)"
    comp.par.ext0name = "LanternistStudio"
    comp.par.ext0promote = True

    pe = comp.create(td.parameterexecuteDAT, "on_parameters")
    pe.par.op = ".."
    pe.par.pars = "*"
    pe.par.valuechange = True
    pe.par.onpulse = True
    pe.par.custom = True
    pe.par.builtin = False
    pe.text = ("def onValueChange(par, prev):\n\tparent().OnValueChange(par)\n\n"
               "def onPulse(par):\n\tparent().OnPulse(par)\n")
    pe.nodeX, pe.nodeY = 400, 400

    ex = comp.create(td.executeDAT, "every_frame")
    ex.par.framestart = True
    ex.text = "def onFrameStart(frame):\n\tparent().Tick()\n"
    ex.nodeX, ex.nodeY = 600, 400
    return comp


try:
    c = build()
    # The extension starts once: problems in it show here, before saving.
    c.par.reinitextensions.pulse()
    for o in [c] + list(c.children):
        for problem in (o.scriptErrors(), o.errors()):
            if problem:
                log("problem", o.path, problem)
    c.save(OUT)
    log("saved", OUT)
except Exception:
    log(traceback.format_exc())
    os._exit(1)
os._exit(0)
