from __future__ import with_statement

import pprint
import os
import struct

pp = pprint.pprint

def fmtslice(slice):
	width = slice.stop - slice.start
	start = slice.start or ''
	stop = slice.stop # if (slice.stop != width) else ''
	step = slice.step or None
	
	res = '%s:%s' % (start, stop)
	if step: res += ':%s' % step
	
	return res

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

def FileBuffer(fname, mode='rb'):
	fp = open(fname, mode)
	return Buffer(fp, slice(0, os.path.getsize(fname)))
	
class Buffer(object):
	def __init__(self, fp, range):
		self.fp = fp
		start, stop, step = range.start, range.stop, range.step
		start = (start or 0)
		assert stop is not None
		assert step in (None, 1)
		assert start <= stop
		
		self.slice = slice(start, stop, None)
	
	def __len__(self):
		res = self.slice.stop - self.slice.start
		assert res >= 0
		return res
	
	def length(self):
		return len(self)
	
	len = property(lambda self: len(self))
	
	start = property(lambda self: self.slice.start)
	stop = property(lambda self: self.slice.start + len(self))
	
	def str(self):
		#with Seekguard(self.fp):
		#if self.fp.tell() != self.slice.start:
		self.fp.seek(self.slice.start)
		width = self.slice.stop - self.slice.start
		assert(width >= 0)
		res = self.fp.read(width)
		return res

	def __str__(self):
		return "Buffer[%s]" % fmtslice(self.slice)
	
	def __repr__(self):
		additional = 16
		
		additional = ["%02x" % ord(self[i]) for i in xrange(min(additional, self.length()))] + (['...'] * (self.length() > additional))

		additional = " [%s]" % (' '.join(additional))
			
		#return '<Buffer %s, len %d [%s]%s>' % (repr(os.path.basename(self.fp.name)), self.length(), fmtslice(self.slice), additional)
		return '<Buffer, len %d [%s]%s>' % (self.length(), fmtslice(self.slice), additional)
	
	def __iter__(self):
		i = 0
		len = self.len
		while i < len:
			yield self[i]
			i += 1
	
	def __getitem__(self, key):
		#with Seekguard(self.fp):
		width = self.slice.stop - self.slice.start

		if isinstance(key, str):
			fmtlen = struct.calcsize(key)
			assert fmtlen <= len(self)
			rv = struct.unpack(key, self[:fmtlen].str())
			return rv[0] if len(rv) == 1 else rv

		elif isinstance(key, slice):
			assert (not key.step) or (key.step == 1)
			kstart = key.start
			kstop  = key.stop

			if kstart is None:
				start = 0
			else:
				if kstart < 0: kstart += width
				start = min(width, kstart)

			if kstop is None:
				stop = width
			else:
				if kstop < 0: kstop += width
				stop = min(width, kstop)

			if start > stop:
				stop = start

			assert 0 <= start <= width
			assert 0 <= stop <= width

			return Buffer(self.fp, slice(
				self.slice.start + start,
				self.slice.start + stop,
				None
			))
		
		else:
			# wrap-around behavior
			if key < 0:
				key += self.length()

			# bounds check
			assert 0 <= key < self.length()

			self.fp.seek(self.slice.start + key)
			return self.fp.read(1)

	def __setitem__(self, key, newval):
		width = self.slice.stop - self.slice.start
		
		if isinstance(key, str):
			if not isinstance(newval, tuple):
				newval = (newval,)

			formatted = struct.pack(key, *newval)
			
			assert len(formatted) <= len(self)
			
			self.fp.seek(self.start)
			self.fp.write(formatted)
			
		elif isinstance(key, slice):
			kstart = key.start
			kstop  = key.stop
			
			if kstart is None:
				start = 0
			else:
				if kstart < 0: kstart += width
				start = min(width, kstart)
			
			if kstop is None:
				stop = width
			else:
				if kstop < 0: kstop += width
				stop = min(width, kstop)
			
			if start > stop:
				stop = start
				
			assert 0 <= start <= width
			assert 0 <= stop <= width
			
			if not isinstance(newval, str):
				newval = str(newval)
			assert len(newval) == stop-start
			
			self.fp.seek(self.slice.start + start)
			self.fp.write(newval)
		
		else:
			assert isinstance(newval, str)
			assert len(newval) == 1
			
			if key < 0:
				k += self.length()
			
			assert 0 <= key < self.length()
			
			self.fp.seek(self.slice.start + key)
			self.fp.write(newval)
	

class BufferReader(object):
	def __init__(self, bufobj):
		self.bufobj = bufobj
		self.fptr = 0

	def read(self, n=None):
		if n is None:
			n = len(self.bufobj) - self.fptr
		else:
			assert n >= 0

		data = self.bufobj[self.fptr : self.fptr+n]
		self.fptr += len(data)
		return data.str()

