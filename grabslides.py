# http://timgolden.me.uk/python/win32_how_do_i/catch_system_wide_hotkeys.html
# After a post to c.l.py by Richie Hindle:
# http://groups.google.com/groups?th=80e876b88fabf6c9

# SendKeys: http://win32com.goermezer.de/content/view/136/284/

import os
import sys
import re
import time
import glob
from PIL import Image, ImageGrab
import StringIO
import ctypes
from ctypes import wintypes
import win32con
import win32com.client

shell = win32com.client.Dispatch("WScript.Shell")

def getscreen():
	try:
		return ImageGrab.grab()
	except IOError:
		return False

byref = ctypes.byref
user32 = ctypes.windll.user32

HOTKEYS = {
	1 : (win32con.VK_F3, win32con.MOD_WIN),
	2 : (win32con.VK_F4, win32con.MOD_WIN)
}

(prefix,) = sys.argv[1:]

slidecounter = 1

def handle_win_f3():
	global slidecounter
	#now = time.strftime("%y%m%d-%H%M%S", time.gmtime(time.time()))
	screen = getscreen()
	if screen:
		fname = "{0}-{1:03d}.png".format(prefix, slidecounter)
		screen.save(fname)
		slidecounter += 1
		print "saved {0!r}".format(fname)
		shell.SendKeys("{RIGHT}", 0)
	else:
		user32.PostQuitmessage(0)


def handle_win_f4():
	user32.PostQuitMessage (0)

HOTKEY_ACTIONS = {
	1 : handle_win_f3,
	2 : handle_win_f4
}

#
# RegisterHotKey takes:
#  Window handle for WM_HOTKEY messages (None = this thread)
#  arbitrary id unique within the thread
#  modifiers (MOD_SHIFT, MOD_ALT, MOD_CONTROL, MOD_WIN)
#  VK code (either ord ('x') or one of win32con.VK_*)
#
for id, (vk, modifiers) in HOTKEYS.items ():
	print "Registering id", id, "for key", vk
	if not user32.RegisterHotKey (None, id, modifiers, vk):
		print "Unable to register id", id

#
# Home-grown Windows message loop: does
#  just enough to handle the WM_HOTKEY
#  messages and pass everything else along.
#
try:
	msg = wintypes.MSG ()
	while user32.GetMessageA (byref (msg), None, 0, 0) != 0:
		if msg.message == win32con.WM_HOTKEY:
			action_to_take = HOTKEY_ACTIONS.get (msg.wParam)
			if action_to_take:
				action_to_take ()

		user32.TranslateMessage (byref (msg))
		user32.DispatchMessageA (byref (msg))

finally:
	for id in HOTKEYS.keys ():
		user32.UnregisterHotKey (None, id)


