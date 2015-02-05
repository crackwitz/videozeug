#!/usr/bin/env python2

import os
import sys
import mmap
import struct
import numpy as np
import cv2
import re
import time
from fractions import Fraction

from filebuffer import *

# https://github.com/rfbproto/rfbproto/blob/master/rfbproto.rst#765hextile-encoding

# TODO: FileBuffer-like object (struct.unpack only) for serial reading
#       wrapper to join multiple Buffers for linear read

def hexdump(s):
	return " ".join("%02x" % ord(c) for c in s)

def abbrev(n, s):
	if len(s) > n:
		return "{0}...".format(s[:n-3])
	else:
		return s

def padup(n, k):
	return n + ((-n) % k)

class Chunkgen(object):
	def __init__(self, sourcebuf):
		self.buf = sourcebuf
		
		self.peeked = False
		self.nextchunk = None
		
		self.pos = 0
	
	def _parse_chunk(self):
		p = self.pos
		buf = self.buf

		if p >= len(buf):
			return None
		
		bytecount = buf[p:][">I"]
		p += 4
		
		chunk = buf[p:p+bytecount]
		bytecount = padup(bytecount, 4)
		p += bytecount
		timestamp = buf[p:][">I"]
		p += 4
		
		self.pos = p
		
		return (timestamp, chunk)

	def peek(self):
		if not self.peeked:
			self.peeked = True
			self.nextchunk = self._parse_chunk()
		
		if self.nextchunk:
			return self.nextchunk[0]
		else:
			return None
	
	def next(self):
		if not self.peeked:
			self.peek()

		res = self.nextchunk
		self.nextchunk = None
		self.peeked = False
		return res

class BytesSource(object):
	def __init__(self, firstbuf, chunkgen):
		self.chunk = firstbuf
		self.chunkgen = chunkgen
	
	def read(self, toread):
		res = []
		
		while toread > 0:
			if self.chunk is None:
				self.chunk = self.chunkgen.next()
				
				if self.chunk is None:
					break
				else:
					(ts,buf) = self.chunk
					self.chunk = buf

			if toread >= len(self.chunk):
				res.append(self.chunk)
				toread -= len(self.chunk)
				self.chunk = None
			else:
				buf = self.chunk[:toread]
				self.chunk = self.chunk[toread:]
				res.append(buf)
				toread -= len(buf)
				assert toread == 0

		return "".join(buf.str() for buf in res)
	
	def __rshift__(self, fmt):
		fmtlen = struct.calcsize(fmt)
		data = self.read(fmtlen)
		assert len(data) == fmtlen
		res = struct.unpack(fmt, data)
		if len(res) == 1:
			(res,) = res
		return res

def parse_pixel(pixeldata):
	assert bitsperpixel == 32
	assert pixeldepth == 24
	(value,) = struct.unpack(("<>"[isbigendian]) + "I", pixeldata)

	red   = (value >> redshift) & 0xff
	green = (value >> greenshift) & 0xff
	blue  = (value >> blueshift) & 0xff
	
	return (blue, green, red)

message_handlers = {}

def message(number):
	def decorator(fn):
		message_handlers[number] = fn
		return fn
	return decorator
	
@message(0)
def handle_FramebufferUpdate(timestamp, buf, chunkgen):
	buf = buf[2:] # skip type code and padding
	data = BytesSource(buf, chunkgen)

	numrects = (data >> ">H")

	for irect in xrange(numrects):
		(rx, ry, rw, rh, renc) = (data >> ">HHHHi")
		
		subbuf = framebuf[ry : ry+rh, rx : rx+rw]
		
		#print "Framebuffer Update: @x{0} y{1} w{2} h{3} enc{4}".format(rx, ry, rw, rh, renc)
		# pixel data follows

		if renc == 0: # raw
			assert pixeldepth == 24
			assert bitsperpixel == 32
			
			for v in xrange(h):
				for u in xrange(w):
					i = w*v + u
					subbuf[v,u] = parse_pixel(data >> "4s")
		
		elif renc == 1: # copyrect
			(sx, sy) = (data >> ">HH")
			subbuf[:,:] = framebuf[sy:sy+rh, sx:sx+rw]

		elif renc == 2: # rre
			subrects = (data >> ">I")
			
			bgpixel = parse_pixel(data >> "4s")
			
			subbuf[:,:] = bgpixel

			for i in xrange(subrects):
				(subpixel, subx, suby, subw, subh) = (data >> ">4sHHHH")
				subbuf[suby : suby+subh, subx : subx+subw] = bgpixel

		elif renc == 4: # corre
			subrects = (data >> ">I")
			
			bgpixel = parse_pixel(data >> "4s")
			
			subbuf[:,:] = bgpixel

			for i in xrange(subrects):
				(subpixel, subx, suby, subw, subh) = (data >> ">4sBBBB")
				subbuf[suby : suby+subh, subx : subx+subw] = bgpixel

		elif renc == 5: # hextile
			bgpixel = None
			fgpixel = None
			for v in xrange(0, rh, 16):
				tileheight = min(16, rh - v)
				for u in xrange(0, rw, 16):
					#print "tile start {0}:{1} in rect xywh {2} {3} {4} {5}".format(u,v, rx,ry,rw,rh)
					tilewidth = min(16, rw - u)
					tilebuf = subbuf[v : v+tileheight, u : u+tilewidth]
					
					mask = (data >> ">B")
					israw       = mask & 0b00001
					bgspecd     = mask & 0b00010
					fgspecd     = mask & 0b00100
					anysubrects = mask & 0b01000
					subcolored  = mask & 0b10000
					
					#print "flags: {0:05b}".format(mask)
					#print "data pos: {0}".format(data.start + data.pos)
					
					if israw:
						assert mask == 0b00001
						bgpixel = None
						fgpixel = None
						for ty in xrange(tileheight):
							for tx in xrange(tilewidth):
								tilebuf[ty,tx] = parse_pixel(data >> "4s")
					
					else:
						if subcolored:
							fgpixel = None
						
						if bgspecd:
							bgpixel = parse_pixel(data >> "4s")
							#print "BG", bgpixel

						if fgspecd:
							fgpixel = parse_pixel(data >> "4s")
							#print "FG", fgpixel
							assert not subcolored
						
						if anysubrects:
							numsubrects = (data >> ">B")
							assert numsubrects > 0
						else:
							numsubrects = 0

						if bgpixel is None:
							import pdb; pdb.set_trace()
						tilebuf[:,:] = bgpixel
						
						for i in xrange(numsubrects):
							if subcolored:
								(col,xy,wh) = (data >> "4sBB")
								col = parse_pixel(col)
							else:
								col = fgpixel
								(xy,wh) = (data >> "BB")

							(x,y) = divmod(xy, 16)

							(w,h) = divmod(wh, 16)
							(w,h) = (w+1,h+1)
							
							tilebuf[y:y+h, x:x+w] = col

							#print "xy {0} {1}".format(x,y), "wh {0} {1}".format(w,h), "=", col
							
			

		else:
			assert False

@message(3)
def handle_ServerCutText(timestamp, buf, chunkgen):
	# https://github.com/rfbproto/rfbproto/blob/master/rfbproto.rst#754servercuttext
	
	buf = buf[2:] # skip type code and padding
	data = BytesSource(buf, chunkgen)

	textlen = (data >> ">I")
	assert textlen == 0
	
	textlen = (data >> ">H")
	text = data.read(textlen)
	
	assert len(text) == textlen

	assert (data.chunk is None)
	#import pdb; pdb.set_trace()
	
	print "ServerCutText: {0}".format(abbrev(80, repr(text[:100])))

message(1)("SetColourMapEntries")
message(2)("Bell")
message(4)("ResizeFrameBuffer")
message(5)("KeyFrameUpdate")
message(15)("ResizeFrameBuffer")
message(150)("EndOfContinuousUpdates")


if __name__ == '__main__':
	cv2.namedWindow("display", cv2.WINDOW_NORMAL)

	(fname,outfname) = sys.argv[1:]
	
	cropw = 1366
	croph = 768
	

	buf = FileBuffer(fname)
	
	t0 = time.time()
	
	signature = buf[0:12].str()
	(major,minor) = map(int, re.match(r'^FBS (\d+)\.(\d+)\n$', signature).groups())
	pos = 12
	
	chunkgen = Chunkgen(buf[12:])

	print "Frame Buffer Stream, v{0}.{1}".format(major, minor)
	
	### ProtocolVersion
	(timestamp, chunk) = chunkgen.next()
	m = re.match(r'^RFB (\d{3})\.(\d{3})\n$', chunk.str())
	assert m
	(major, minor) = map(int, m.groups())
	print "RFB v{0}.{1}".format(major, minor)

	assert (major,minor) == (3,3)

	### Security
	(timestamp, chunk) = chunkgen.next()
	# for v3.7+, not implemented
	# for 3.3:
	(sectype,) = struct.unpack(">I", chunk.str())
	assert sectype == 1 # no security

	### ServerInit
	(timestamp, chunk) = chunkgen.next()
	(fbwidth, fbheight, pixfmt, namelen) = struct.unpack(">HH16sI", chunk.str())
	
	assert cropw <= fbwidth
	assert croph <= fbheight

	print "ServerInit: frame buffer {0}x{1}".format(
		fbwidth, fbheight
	)
	
	# parsing pixel format
	(
		bitsperpixel, pixeldepth,
		isbigendian, istruecolor,
		redmax, greenmax, bluemax,
		redshift, greenshift, blueshift,
		padding
	) = struct.unpack(">" "BBBB" "HHH" "BBB" "3s", pixfmt)
	
	istruecolor = (istruecolor > 0)
	isbigendian = (isbigendian > 0)
	
	print "pixel format: {0}-bit width, {1}-bit depth".format(bitsperpixel, pixeldepth)
	print "big endian? {0}, true color? {1}".format(isbigendian > 0, istruecolor > 0)
	print "ranges: RGB {0} {1} {2}".format(redmax, greenmax, bluemax)
	print "shifts: RGB {0} {1} {2}".format(redshift, greenshift, blueshift)
	
	assert bitsperpixel % 8 == 0
	assert pixeldepth % 8 == 0
	assert istruecolor
	assert redmax == greenmax == bluemax == 255
	assert pixeldepth == 24
	assert bitsperpixel == 32

	framebuf = np.zeros((fbheight, fbwidth, 3), dtype=np.uint8)
	
	cv2.resizeWindow("display", cropw, croph)
	
	### name
	(timestamp, chunk) = chunkgen.next()
	namestring = chunk[:namelen].str()
	
	print "display name: {0!r}".format(namestring)

	def dispatch_chunk(timestamp, chunk, chunkgen):
		print "{0:8.3f}s: {1:-5d} bytes @ {2}: {3}".format(
			timestamp/1e3,
			len(chunk),
			chunk.start,
			abbrev(80, hexdump(chunk[:40].str())))

		messagetype = chunk[0:][">B"]
		
		assert messagetype in message_handlers
		if isinstance(message_handlers[messagetype], str):
			print message_handlers[messagetype]
		message_handlers[messagetype](timestamp, chunk, chunkgen)

		cv2.imshow("display", framebuf[:croph,:cropw])
		while True:
			key = cv2.waitKey(1)
			if key == -1:
				break

	fps = Fraction(25)
	fourcc = -1
	fourcc = cv2.cv.CV_FOURCC(*"LAGS")
	outvid = cv2.VideoWriter(outfname, fourcc, 25, (cropw, croph))
	currentframe = 0
	
	running = True
	while running:
		print "collecting for frame {0} at {1:.3f}s".format(currentframe, float(currentframe / fps))

		while chunkgen.peek() <= currentframe / fps * 1000:
			(timestamp, chunk) = chunkgen.next()

			if len(chunk) == 0: # appears to end the stream
				running = False
				break

			dispatch_chunk(timestamp, chunk, chunkgen)
		
		outvid.write(framebuf[:croph,:cropw])
		currentframe += 1

# TODO:
#  1) pull chunks LEQ given timestamp
#  2) render chunks
#  3) framebuf -> video file

