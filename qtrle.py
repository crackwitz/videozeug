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
	cv2.imshow("display", cv2.pyrDown(frame[:,:,::-1]))
	cv2.imshow("alpha", cv2.pyrDown(frame[:,:,0]))
	while True:
		key = cv2.waitKey(1)
		if key == -1:
			break
		if key == 27:
			sys.exit(0)


def decode_chunk(frame, chunk):
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
				px = 0
				
				linecount += 1

				#print "y", py
				dispcount += 1
				if dispcount % dispdelta == 0:
					redraw(frame)

				state = 0
				continue

			elif rlecode > 0:
				pixels = [(chunk >> ">BBBB") for i in xrange(rlecode)]
				frame[py,px : px + rlecode] = pixels
				px += rlecode

			elif rlecode < -1:
				pixel = (chunk >> ">BBBB")
				frame[py, px : px-rlecode] = pixel
				px += -rlecode


		else:
			assert False
	
	redraw(frame)
	
	if firstline == 0 and (linecount == frame.shape[0]) and not skipused:
		print "that was a KEYFRAME"
	




if __name__ == '__main__':
	(fname,) = sys.argv[1:]

	buf = FileBuffer(fname)
	
	(mdat,) = mp4select.select("mdat", buf)
	
	width, height = 1440, 900
	frame = np.zeros((height, width, 4), dtype=np.uint8)
	
	# iterate chunks
	framecount = 0
	while mdat.pos < len(mdat):
		#if framecount == 27: import pdb; pdb.set_trace()
		chunksize = (mdat >> ">I")
		chunk = mdat[mdat.pos : mdat.pos + chunksize-4]
		mdat.pos += chunksize-4

		print "decoding frame", framecount		
		decode_chunk(frame, chunk)

		framecount += 1
