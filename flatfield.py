from __future__ import division
import numpy as np
import cv2
import os
import sys
import time
import json

class Framecache(object):
	def __init__(self, readfn, size=100):
		self.cachesize = size
		self.readfn = readfn
		self.frames = {} # index -> [timestamp, frame]
	
	def drop_oldest(self):
		keys = sorted(self.frames, key=(lambda key: self.frames[key][0]))
		while len(keys) > self.cachesize:
			key = keys.pop(0)
			del self.frames[key]
	
	def __getitem__(self, key):
		if key not in self.frames:
			frame = self.readfn(key)
			self.drop_oldest()
			self.frames[key] = [None, frame]
		
		row = self.frames[key]
		row[0] = time.time()
		return row[1]

def read_frame(vid):
	pos_vid = [0]
	
	def sub(pos):
		if pos != pos_vid[0]:
			vid.set(cv2.cv.CV_CAP_PROP_POS_FRAMES, pos)
			
		(rv,im) = vid.read()
		pos_vid[0] = pos+1
		if not rv:
			return None
		return im
		
	return sub

# TODO: gamma-aware average
gamma = 2.2

(fname,) = sys.argv[1:]

# TODO: different decoder, different color space
vid = cv2.VideoCapture(fname)
framecache = Framecache(read_frame(vid))
nframes = vid.get(cv2.cv.CV_CAP_PROP_FRAME_COUNT)
fps = vid.get(cv2.cv.CV_CAP_PROP_FPS)
framew = int(vid.get(cv2.cv.CV_CAP_PROP_FRAME_WIDTH))
frameh = int(vid.get(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT))

marked = {} # frameno -> -1, +1
markmode = 0
override = False

def read_marks():
	global marked
	if os.path.exists(fname + ".json"):
		marked = json.load(file(fname + ".json"))
		marked = {int(k): marked[k] for k in marked}

def write_marks():
	json.dump(marked, file(fname + ".json", 'w'), indent=1, sort_keys=True)

read_marks()

pos_frame = 0 # index of curframe
pos_vid = 0 # index in vid
curframe = None
playback = False

VK_LEFT  = 0x250000
VK_RIGHT = 0x270000
VK_UP    = 0x260000
VK_DOWN  = 0x280000

def seek_frame(pos):
	global pos_vid, pos_frame
	global curframe

	#if pos == pos_frame and (curframe is not None):
	#	return
	
	#if pos_vid != pos:
	#	vid.set(cv2.cv.CV_CAP_PROP_POS_FRAMES, pos)
	#	
	#(rv,curframe) = vid.read()
	pos_frame = pos
	pos_vid = pos+1
	
	curframe = framecache[pos]

def goto_frame(pos):
	cv2.setTrackbarPos("position", "video", pos)

def display_frame(pos=None):
	if pos is None:
		pos = pos_frame
	else:
		seek_frame(pos)
	
	if curframe is None:
		return
	
	global markmode
	
	if override:
		if markmode == 0:
			if pos in marked:
				del marked[pos]
		else:
			marked[pos] = markmode
	else:
		markmode = marked.get(pos, 0)

	display = curframe.copy()
	
	cv2.line(display, (0, 10), (framew, 10), color=(128, 128, 128))
	
	for mpos in marked:
		mark = marked[mpos]
		color = (255,0,255) if mark == -1 else (255,255,0)
		xpos = int(framew * mpos / nframes)
		cv2.line(display, (xpos, 5), (xpos, 15), color)
	
	xpos = int(framew * pos / nframes)
	cv2.line(display, (xpos, 0), (xpos, 20), (255, 0, 255), thickness=2)
	
	cv2.putText(display, "mark mode [BWC]: %+d, override [O]: %s" % (markmode, override), (10, 50), cv2.FONT_HERSHEY_PLAIN, 2, (255,255,255), thickness=2)

	cv2.putText(display, "A: load, S: save, R: render flats", (10, 80), cv2.FONT_HERSHEY_PLAIN, 2, (255,255,255), thickness=2)
	
	cv2.imshow("video", display)
	
def setpos_callback(newpos):
	display_frame(newpos)
	cv2.waitKey(1)

cv2.namedWindow('video', cv2.WINDOW_NORMAL)
cv2.createTrackbar('position', 'video', 0, int(nframes), setpos_callback)

def mouse_callback(event, mx, my, flags, param):
	if my > 100:
		return

	if (event == cv2.EVENT_LBUTTONDOWN) or (event == cv2.EVENT_MOUSEMOVE and flags & 1):
		pos = int(nframes * mx / framew)
		display_frame(pos)
		cv2.waitKey(1)

cv2.setMouseCallback('video', mouse_callback)

display_frame(0)

while True:
	if playback:
		goto_frame(pos_frame+1)

	key = cv2.waitKey(int(1000/fps) if playback else 100)
	
	if key == -1:
		continue
	
	if key == 27:
		break
	
	if key == 32:
		playback = not playback
	
	if key == ord('w'):
		markmode = +1
		marked[pos_frame] = +1
		display_frame()
		
	if key == ord('b'):
		markmode = -1
		marked[pos_frame] = -1
		display_frame()

	if key == ord('c'):
		markmode = 0
		if pos_frame in marked: del marked[pos_frame]
		display_frame()

	if key == ord('o'):
		override = not override
		display_frame()
	
	if key == ord('s'):
		write_marks()
	
	if key == ord('a'):
		read_marks()

	if key == ord('r'):
		fbase = os.path.splitext(fname)[0]

		blackframe = np.zeros((frameh,framew,3), np.float32)
		blackcount = 0
		whiteframe = np.zeros((frameh,framew,3), np.float32)
		whitecount = 0
		
		print "averaging..."
		for i,key in enumerate(sorted(marked)):
			if marked[key] == +1:
				whiteframe += framecache[key]
				whitecount += 1
			elif marked[key] == -1:
				blackframe += framecache[key]
				blackcount += 1
			else:
				assert False
			
			print "%d of %d" % (i+1, len(marked))
		print "done"
		
		blackframe /= 255*blackcount
		whiteframe /= 255*whitecount
		rangeframe = whiteframe - blackframe
		hival = 2**16 - 1
		valtype = np.uint16
		
		cv2.imwrite(fbase + "-black.png", valtype(np.clip(0.0 + blackframe*hival, 0, hival)))
		cv2.imwrite(fbase + "-white.png", valtype(np.clip(0.0 + whiteframe*hival, 0, hival)))
		cv2.imwrite(fbase + "-range.png", valtype(np.clip(0.0 + rangeframe*hival, 0, hival)))
		
		np.save(fbase + "-black.npy", blackframe)
		np.save(fbase + "-white.npy", whiteframe)
		np.save(fbase + "-range.npy", rangeframe)

	if key == VK_LEFT:
		goto_frame(pos_frame-1)
		continue
	
	elif key == VK_RIGHT:
		goto_frame(pos_frame+1)
		continue

	print key, hex(key)

cv2.destroyAllWindows()
