#!/usr/bin/env python2
from __future__ import division
import os
import sys
import pprint; pp = pprint.pprint
import argparse

import cv2
import numpy as np

from filebuffer import *
import mp4select
import ffwriter

# https://wiki.multimedia.cx/index.php?title=Apple_QuickTime_RLE

def redraw(frame):
	if args.headless:
		return

	# reverse for opencv
	cv2.imshow("display", (frame[:,:,::-1]))

	#cv2.imshow("display", cv2.pyrDown(frame[:,:,::-1]))
	#cv2.imshow("alpha", cv2.pyrDown(frame[:,:,0]))

	while True:
		key = cv2.waitKey(1)
		if key == -1:
			break
		if key == 27:
			cv2.destroyWindow("display")
			sys.exit(0)

def get_chunks(buffer):
	while buffer.pos < len(buffer):
		chunksize = (buffer >> ">I")
		chunk = buffer[buffer.pos : buffer.pos - 4 + chunksize]
		header = chunk[0:2][">H"]
		#print "chunk @ {:x}, len {:08x}, header {:04x}".format(buffer.pos, chunksize, header)
		buffer.pos += chunksize-4
		yield chunk


def decode_chunk(frame, chunk, update=False):
	pixfmtstr = {'argb': '>BBBB', 'rgb24': '>BBB'}[pixfmt]

	chunk = chunk.copy()
	xmax = ymax = 0
	header = (chunk >> ">H") # header 0x0008 means decode starting at some line other than 0

	#print "size, header:", len(chunk)+4, header

	if header & 0x0008:
		(firstline, _, numlines, _) = (chunk >> ">HHHH")
		#print "header bit 3 set: update {} + {}".format(firstline, numlines)
	else:
		firstline = 0
		numlines = None

	#print "firstline", firstline, "numlines", numlines
	
	px = 0
	py = firstline
	
	skipused = False

	state = 0
	# 0: read skip code (how many pixels to skip into the current line)
	# 1: read RLE code

	#import pdb; pdb.set_trace()
	
	linecount = 0
	dispdelta = 20
	linecount = 0
	while True:
		#print "pos", chunk.pos, 'state', state
		
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
				if update and (linecount % dispdelta == 0):
					sys.stdout.write("{} of {} lines\r".format(linecount, numlines or height))
					redraw(frame)

				state = 0
				continue

			elif rlecode > 0:
				pixels = [(chunk >> pixfmtstr) for i in xrange(rlecode)]
				frame[py,px : px + rlecode] = pixels
				px += rlecode
				xmax = max(xmax, px)

			elif rlecode < -1:
				repeat = -rlecode
				pixel = (chunk >> pixfmtstr)
				frame[py, px : px+repeat] = pixel
				px += repeat
				xmax = max(xmax, px)

			else:
				assert False, "incomplete switch on rlecode {}".format(rlecode)


		else:
			assert False, "wrong state value {}!".format(state)
	
	# assert that whole chunk has been decoded
	assert chunk.pos == len(chunk), "chunk done after {} of {} bytes".format(chunk.pos, len(chunk))

	if update and linecount > 0:
		redraw(frame)
	
	is_fullframe = (firstline == 0 and (linecount == frame.shape[0]) and not skipused)

	if is_fullframe:
		print "that was a FULL FRAME"
	
	return (xmax, ymax, is_fullframe)

def tohms(secs):
	hours, secs = divmod(secs, 3600)
	minutes, secs = divmod(secs, 60)
	return (int(hours), int(minutes), secs)


pixfmts = { # -> channel/byte count
	'argb': 4,
	'rgb24': 3,
}

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument("infile", type=str, help="input video file")
	parser.add_argument("outfile", type=str, nargs='?', default=None, help="output video file")
	parser.add_argument('--size', dest='size', type=str, default=None, metavar="WxH", help="initial resolution")
	parser.add_argument('--pixfmt', dest='pixfmt', type=str, default='argb', help="aupported: argb, rgb24")
	parser.add_argument('--fps', dest='fps', type=float, default=25, nargs=1, help="frames per second")
	parser.add_argument('--headless', dest='headless', action="store_true", help="don't show output window")

	args = parser.parse_args()

	infname = args.infile
	outfname = args.outfile

	if outfname is None:
		outfname = "{}-decoded.mov".format(*os.path.splitext(infname))

	if args.size:
		width, height = map(int, args.size.split('x'))
	else:
		width = height = 0

	width  = width or 4096
	height = height or 2048

	pixfmt = args.pixfmt
	assert pixfmt in pixfmts
	nchannels = pixfmts[pixfmt]
	print "decoding as {}, {} bpp".format(pixfmt, 8*nchannels)


	buf = FileBuffer(infname)
	
	(mdat,) = mp4select.select("mdat", buf)

	frame = np.zeros((height, width, nchannels), dtype=np.uint8)

	fps = args.fps

	print "assuming {} fps".format(fps)

	if not args.headless:
		cv2.namedWindow("display", cv2.WINDOW_NORMAL)

	outfile = None

	# iterate chunks
	framecount = 0
	dobreak = False
	for chunk in get_chunks(mdat):
		print "decoding frame {} @ {:d}:{:02d}:{:06.3f}".format(framecount, *tohms(framecount / fps))
		try:
			(mx, my, isfull) = decode_chunk(frame, chunk, update=True)
		except Exception, e:
			print "Exception:", e
			dobreak = True

		# detect resolution
		if framecount == 0:
			print "detected resolution {0} x {1}".format(mx, my)
			assert mx <= width and my <= height
			(width, height) = (mx, my)
			frame = frame[:height, :width].copy()

			if (outfname is not None) and (outfile is None):
				outfile = ffwriter.FFWriter(outfname, fps, (width, height), pixfmt=pixfmt, codec='qtrle', moreflags='-g {}'.format(60*fps))
				assert outfile.isOpened()

		if outfile:
			outfile.write(frame)

		framecount += 1

		if dobreak:
			break
