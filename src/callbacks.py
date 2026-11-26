# Lanternist Studio for TouchDesigner: the WebSocket DAT's callbacks (OSCQuery LISTEN).
# MIT licence, (c) Lanternist. Everything is handled by the component's extension.

def onConnect(dat):
	parent().OnConnect(dat)

def onDisconnect(dat):
	parent().OnDisconnect(dat)

def onReceiveText(dat, rowIndex, message):
	parent().OnText(dat, message)

def onReceiveBinary(dat, contents):
	parent().OnBinary(dat, contents)

def onReceivePing(dat, contents):
	dat.sendPong(contents)

def onReceivePong(dat, contents):
	return

def onMonitorMessage(dat, message):
	return
