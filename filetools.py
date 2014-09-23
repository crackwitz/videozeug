# written by christoph.rackwitz@gmail.com

from __future__ import with_statement

import pprint
import os

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
			

#def hexdump(s, offset=0):
#	i = offset
#	n = 0
#	for i, line in enumerate(nsplit(s, 16)):
#		print "%04x : %*s | %*s |" % (
#			16*i + offset,
#			-3*16-1, ' '.join("%02x" % ord(c) for c in line),
#			-16,     ''.join(c if (32 <= ord(c) < 128) else '.' for c in line)
#		)

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
		assert(stop is not None)
		
		self.slice = slice(start, stop, step)
	
	def length(self):
		return (self.slice.stop - self.slice.start) // (self.slice.step or 1)
	
	len = property(lambda self: self.length())
	
	def __len__(self):
		return self.length()
	
	def str(self):
		with Seekguard(self.fp):
			self.fp.seek(self.slice.start)
			width = self.slice.stop - self.slice.start
			assert(width >= 0)
			res = self.fp.read(width)
			if self.slice.step and (self.slice.step != 1):
				res = res[::self.slice.step]
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
		with Seekguard(self.fp):
			width = self.slice.stop - self.slice.start

			if isinstance(key, slice):
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
					self.slice.step
				))

			else:
				# wrap-around behavior
				if key < 0:
					key += self.length()

				# bounds check
				assert 0 <= key < self.length()
				
				self.fp.seek(self.slice.start + key // (self.slice.step or 1))
				return self.fp.read(1)

	# TODO: setitem, etc

def floordiv(a, b):
	return a // b

def ceildiv(a, b):
	return a // b + (a % b != 0)

def filesize(fp):
	with Seekguard(fp) as fp:
		fp.seek(0, os.SEEK_END)
		return fp.tell()
		
class Cached(object):
	"doesn't improve the situation. OS cache is faster than manual caching"

	def __init__(self, fp, bufsize = 2**14, nbuffers=10):
		assert(fp.tell() == 0)
		self.fp = fp
		self.cache = {}
		self.bufsize = bufsize
		self.nbuffers = nbuffers
		self.pos = 0
		self.readcount = 0
		self.filesize = filesize(fp)
		self.name = fp.name
	
	def tell(self):
		return self.pos
	
	def seek(self, offset, whence=os.SEEK_SET):
		if whence == os.SEEK_SET:
			self.pos = offset
		elif whence == os.SEEK_CUR:
			self.pos = min(self.pos + offset, self.fp.filesize)
		elif whence == os.SEEK_END:
			self.pos = self.filesize + offset
		else:
			raise Exception("invalid argument for whence!")
	
	def _fetch(self, block):
		if block not in self.cache:
			self.fp.seek(block * self.bufsize)
			data = self.fp.read(self.bufsize)
			self.cache[block] = [0, data]
		
		self.readcount += 1
		self.cache[block][0] = self.readcount

		return self.cache[block][1]
	
	def _getrange(self, start, stop):
		res = []

		a = floordiv(start, self.bufsize)
		b = ceildiv(stop, self.bufsize)
		
		for block in xrange(a, b):
			data = self._fetch(block)
			u,v = block*self.bufsize, (block+1)*self.bufsize

			res.append(
				data[max(0, start-u):min(self.bufsize, stop-u)]
			)

		assert(sum(map(len, res)) == stop - start)

		self._prunecache()
		
		return ''.join(res)
	
	def _prunecache(self, maxkilled=2):
		for i in xrange(maxkilled):
			if len(self.cache) < self.nbuffers:
				break
			del self.cache[min(self.cache, key=(lambda x: self.cache[x][0]))]
	
	def read(self, nbytes):
		res = self._getrange(self.pos, self.pos+nbytes)
		self.pos += len(res)
		return res

#if __name__ == '__main__':		
#	fname = r'Q:\video AG\released\ss08\LA\08ss-LA-080506.avi'
#	fp = Cached(open(fname, 'rb'))
#	fb = FileBuffer(fname)
