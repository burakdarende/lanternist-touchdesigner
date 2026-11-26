"""Runs inside TouchDesigner: saves te_test.tox, the component the TouchEngine tests load
(argv: [out .tox, log]): a constant TOP whose green is the custom parameter Green, to an Out TOP."""

import os
import sys
import traceback

import td

OUT, LOG = sys.argv[1], sys.argv[2]
try:
    comp = op("/project1").create(td.baseCOMP, "te_test")
    page = comp.appendCustomPage("Test")
    green = page.appendFloat("Green", label="Green")[0]
    green.default = 1.0
    green.val = 1.0
    green.normMin, green.normMax = 0.0, 1.0
    c = comp.create(td.constantTOP, "colour")
    c.par.outputresolution = "custom"
    c.par.resolutionw, c.par.resolutionh = 64, 64
    c.par.colorr = 0.0
    c.par.colorg.expr = "parent().par.Green"
    c.par.colorb = 0.0
    o = comp.create(td.outTOP, "out1")
    o.inputConnectors[0].connect(c)
    comp.save(OUT)
    open(LOG, "a").write("saved\n")
except Exception:
    open(LOG, "a").write(traceback.format_exc())
    os._exit(1)
os._exit(0)
