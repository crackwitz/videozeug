#!/usr/bin/env python2
import os
import sys
import pprint; pp = pprint.pprint

import cv2
import numpy as np

from filebuffer import *
import mp4select

# http://wiki.multimedia.cx/index.php?title=Apple_QuickTime_RLE

def redraw(frame):
	cv2.imshow("display", (frame[:,:,::-1]))
	#cv2.imshow("display", cv2.pyrDown(frame[:,:,::-1]))
	#cv2.imshow("alpha", cv2.pyrDown(frame[:,:,0]))
	while True:
		key = cv2.waitKey(1)
		if key == -1:
			break
		if key == 27:
			sys.exit(0)

def get_chunks(buffer):
	while buffer.pos < len(buffer):
		chunksize = (buffer >> ">I")
		chunk = buffer[buffer.pos : buffer.pos - 4 + chunksize]
		buffer.pos += chunksize-4
		yield chunk


def decode_chunk(frame, chunk, update=False):
	chunk = chunk.copy()
	xmax = ymax = 0
	header = (chunk >> ">H")

	#print "size, header:", len(chunk)+4, header

	if header & 0x0008:
		(firstline, _, numlines, _) = (chunk >> ">HHHH")
	else:
		firstline = 0
		numlines = None

	#print "firstline", firstline, "numlines", numlines
	
	px = 0
	py = firstline
	
	skipused = False

	state = 0
	# 0: read skip code
	# 1: read RLE code

	#import pdb; pdb.set_trace()
	
	dispcount = 0
	dispdelta = 20
	linecount = 0
	while True:
		#print "pos", chunk.pos
		
		if state == 0:
			skipcode = (chunk >> ">B")
			
			state = 1

			if skipcode == 0: # done with this frame
				break

			px += skipcode-1

			if skipcode - 1 > 0:
				skipused = True

			continue

		elif state == 1:
			rlecode = (chunk >> ">b")
			#print "rlecode", rlecode

			if rlecode == 0:
				state = 0
				continue

			elif rlecode == -1:
				py += 1
				ymax = max(ymax, py)
				px = 0
				
				linecount += 1

				#print "y", py
				dispcount += 1
				if update and (dispcount % dispdelta == 0):
					redraw(frame)

				state = 0
				continue

			elif rlecode > 0:
				pixels = [(chunk >> ">BBBB") for i in xrange(rlecode)]
				frame[py,px : px + rlecode] = pixels
				px += rlecode
				xmax = max(xmax, px)

			elif rlecode < -1:
				pixel = (chunk >> ">BBBB")
				frame[py, px : px-rlecode] = pixel
				px += -rlecode
				xmax = max(xmax, px)


		else:
			assert False
	
	if update:
		redraw(frame)
	
	is_fullframe = (firstline == 0 and (linecount == frame.shape[0]) and not skipused)

	if is_fullframe:
		print "that was a FULL FRAME"
	
	return (xmax, ymax, is_fullframe)

if __name__ == '__main__':
	cv2.namedWindow("display", cv2.WINDOW_NORMAL)

	width, height = sys.argv[1:3]
	width = int(width) or 4096
	height = int(height) or 2048

	infname = sys.argv[3]

	outvid = (len(sys.argv[1:]) > 3) and sys.argv[4]

	buf = FileBuffer(infname)
	
	(mdat,) = mp4select.select("mdat", buf)
	
	frame = np.zeros((height, width, 4), dtype=np.uint8)

	# iterate chunks
	framecount = 0
	for chunk in get_chunks(mdat):
		print "decoding frame", framecount		
		(mx, my, isfull) = decode_chunk(frame, chunk, update=True)

		# detect resolution
		if framecount == 0:
			print "detected resolution {0} x {1}".format(mx, my)
			assert mx <= width and my <= height
			(width, height) = (mx, my)
			frame = frame[:height, :width]

			if outvid is not False:
				outvid = cv2.VideoWriter(outvid, -1, 25, (width, height))
				assert outvid.isOpened()

		if outvid:
			outvid.write(frame[:,:,::-1])

		framecount += 1
