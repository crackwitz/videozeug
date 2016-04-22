from __future__ import division
import os
import sys
import struct


def fmtslice(slice):
	width = slice.stop - slice.start
	start = slice.start or ''
	stop = slice.stop # if (slice.stop != width) else ''
	step = slice.step or None
	
	res = '%s:%s' % (start, stop)
	if step: res += ':%s' % step
	
	return res


def FileBuffer(fname, mode='rb'):
	fp = open(fname, mode)
	return Buffer(fp, slice(0, os.path.getsize(fname)))
	

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


class Buffer(object):
	def __init__(self, fp, range):
		self.fp = fp
		self.pos = 0
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
	
	def reset(self):
		self.pos = 0

	def read(self, nbytes=None):
		if nbytes is None:
			nbytes = len(self) - self.pos
		else:
			if self.pos + nbytes > len(self):
				nbytes = len(self) - self.pos

		assert nbytes >= 0
		assert self.pos + nbytes <= len(self)

		result = self[self.pos : self.pos + nbytes].str()
		self.pos += nbytes

		return result

	def write(self, data):
		nbytes = len(data)
		assert self.pos + nbytes <= len(self)

		self.fp.seek(self.start + self.pos)
		self.fp.write(data)
		self.pos += nbytes

	def str(self):
		self.fp.seek(self.slice.start)
		width = self.slice.stop - self.slice.start
		assert(width >= 0)
		res = self.fp.read(width)
		return res

	def szstr(self):
		result = self.str()
		try:
			return result[:result.index('\x00')]
		except ValueError:
			return result

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
	
	def __rshift__(self, fmt):
		fmtlen = struct.calcsize(fmt)
		assert self.pos + fmtlen <= len(self)
		res = self[self.pos:][fmt]
		self.pos += fmtlen
		return res

	def copy(self):
		return self[:]

	def __getitem__(self, key):
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
