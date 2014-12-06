from __future__ import with_statement

import pprint
import os
import struct

from filebuffer import *

pp = pprint.pprint

def nsplit(s, n=1):
	for i in xrange(0, len(s), n):
		yield s[i:i+n]

def hexdump(s, offset=0, width=16, sep=4):
	def lineout(position, hex, clear):
		hexparts = []
		for i,c in enumerate(hex):
			if i % sep == 0:
				hexparts.append([])
			hexparts[-1].append("%02s" % c)
		
		hexpart = '  '.join(
			' '.join(part)
			for part in hexparts
		)
		
		asciiparts = []
		for i,c in enumerate(clear):
			if i % sep == 0:
				asciiparts.append('')
			asciiparts[-1] += ("%1s" % c if (32 <= ord(c) < 128) else '.')

		asciipart = ' '.join(asciiparts)
		
		print "%08x : %*s | %*s |" % (
			position,
			-(3*width-1 + ((width-1) // sep)),
			hexpart,
			-(1*width   + ((width-1) // sep)),
			asciipart
		)
	
	# position in input
	p = 0
	
	# line number
	q = offset - (offset % width)
	
	
	# first line
	munch = width - (offset % width)
	line = s[:munch]
	lineout(
		q,
		[' ']*(width-munch) + ["%02x" % ord(c) for c in line],
		[' ']*(width-munch) + list(line),
	)
	p += munch
	q += width
	
	# remaining lines
	while p < len(s):
		munch = min(len(s) - p, width)
		assert 0 <= munch <= width
		line = s[p:p+munch]
		lineout(
			q,
			["%02x" % ord(c) for c in line],
			list(line),
		)
		
		p += munch
		q += width

def int2bin(x, pad=0):
	res = []
	
	while x:
		res.append(x & 1)
		x >>= 1
	
	if len(res) < pad:
		res += [0] * (pad - len(res))
	
	return res
	
def bindump(s):
	print " ".join(
		''.join(str(b) for b in reversed(int2bin(ord(c), pad=8)))
		for c in s
	)

class Seekguard(object):
	def __init__(self, fp):
		self.fp = fp
		self.position = fp.tell()
	
	def __enter__(self):
		return self.fp

	def __exit__(self, exc_type, exc_value, traceback):
		self.fp.seek(self.position)

