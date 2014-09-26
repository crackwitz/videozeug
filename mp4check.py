#!/usr/bin/env python

from __future__ import with_statement
import os, sys
import struct
import pprint; pp = pprint.pprint
import glob
import array
import ctypes
from funcs import *
from filetools import *

# ======================================================================
# MP4/MOV constants
# http://developer.apple.com/library/mac/#documentation/QuickTime/QTFF/QTFFChap1/qtff1.html#//apple_ref/doc/uid/TP40000939-CH203-BBCGDDDF

# some info on mvhd atom
# http://www.koders.com/c/fid7340F6A06EE399155C40FEAD653B61D43AC72C8C.aspx
# http://www.koders.com/c/fidC79D25A829F98C03F813CCB72649A0B62825F6AA.aspx

#toplevels = [
#	'moov',
#	'mdat',
#	'free',
#	'junk',
#	'pnot',
#	'skip',
#	'wide',
#	'pict',
#	'ftyp',
#	'uuid', # Used by Sony's MSNV brand of MP4
#]

# ======================================================================

class AtomIncomplete(Exception):
	def __init__(self, atomtype, atomstart, atomend, realend):
		self.atomtype  = atomtype
		self.atomstart = atomstart
		self.atomend   = atomend
		self.realend   = realend
	
	def __str__(self):
		return 'Atom %s@%d Should end at %d, does end at %d (%d missing)' % (self.atomtype, self.atomstart, self.atomend, self.realend, self.atomend - self.realend)



lineindent = lambda n: n * '    '

def blockindent(n, text):
	lines = text.split('\n')

	return '\n'.join(
		(lineindent(n) + line) if line else (line)
		for line in lines
	)

class Atom(object):
	def __init__(self, start, length, type, content=None):
		self.start   = start
		self.length  = length
		self.type    = type
		self.content = content
	
	def __repr__(self, indent=0, index=0):
		label = self.type
		
		sublabel = ''
		
		if (self.content is not None) and isinstance(self.content, list):
			sublabel = ' // %d children...' % len(self.content)
		
		res = [lineindent(indent) + '[%d] %s  [@%d + %d]%s' % (
			index+1,
			label,
			self.start,
			self.length,
			sublabel
		)]
		
		if self.content is not None:
			multiline = False
			
			if isinstance(self.content, list):
				multiline = True
			elif '\n' in repr(self.content):
				multiline = True
			
			if multiline:
				res.append('\n')
				res.append(lineindent(indent) + '{\n')

				if isinstance(self.content, list):
					for i,item in enumerate(self.content):
						if isinstance(item, Atom):
#							if item.type == 'skip':
#								import pdb
#								pdb.set_trace()
							res.append(item.__repr__(indent+1, index=i))
						else:
							res.append(blockindent(indent+1, ('[%d] ' % (i+1)) + repr(item) + "\n"))
				else:
					res.append(blockindent(indent+1, repr(self.content) + '\n'))

				res.append(lineindent(indent) + '}\n')

			else:
				res.append(' { ')
				res.append(repr(self.content))
				res.append(' }\n')
			
		
		return ''.join(res)

# ======================================================================

class abbrevlist(list):
	def __repr__(self):
		if len(self) <= 7:
			return repr(list(self))
		
		inner  = ', '.join(map(repr, self[:3]))
		inner += ', ... (%d total) ..., ' % len(self)
		inner += ', '.join(map(repr, self[-3:]))
			
		return '[%s]' % inner

# ======================================================================

handlers = {}

def handler(*types):
	def decorate(fn):
		for type in types:
			assert (type not in handlers)
			handlers[type] = fn
		return fn
	return decorate

#def handle(type):
#	assert type in handlers
#	def sub(offset, type, size, content):
#		return Atom(
#			offset,
#			size,
#			type,
#			handlers[type](offset, type, size, content)
#		)
##		return (
##			offset,
##			type,
##			size,
##			handlers[type](offset, type, size, content)
##		)
#	return sub

@handler('elst')
def parse_elst(type, offset, content, indent):
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#elst
	p = 0
	(version,) = struct.unpack('>B', content[p:p+1].str()); p += 1
	flags      = struct.unpack('>3B', content[p:p+3].str()); p += 3
	(count,)   = struct.unpack('>I', content[p:p+4].str()); p += 4

	assert p + 12*count <= content.len
	entries = array.array("I", content[p:p+12*count].str())
	entries.byteswap()
	entries = zip(entries[0::3], entries[1::3], entries[2::3])
	entries = abbrevlist(entries)
	assert (len(entries) == count)
	p += 12*count
	
	children = parse_sequence(None, offset + p, content[p:], indent=indent+1)

	return [
		("edit list",
			version, flags,
			entries
		),
	] + children

@handler('mdhd')
def parse_mdhd(type, offset, content, indent):
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#mdhd
	
	p = 0
	(version,) = struct.unpack('>B', content[p:p+1].str()); p += 1
	(flags,)   = struct.unpack('>3s', content[p:p+3].str()); p += 3
	
	if version == 0:
		(ctime, mtime, scale, duration) = struct.unpack(">IIII", content[p:p+16].str()); p += 16
	elif version == 1:
		(ctime, mtime, scale, duration) = struct.unpack(">QQIQ", content[p:p+28].str()); p += 28
	else:
		assert 0

	(language, quality) = struct.unpack(">HH", content[p:p+4].str()); p += 4
	
	return Record(
		version = version,
		flags = flags,
		ctime = ctime,
		mtime = mtime,
		scale = scale,
		duration = duration,
		language = language,
		quality = quality,
	)
	
@handler('co64')
def parse_co64(type, offset, content, indent):
	return content
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#co64

@handler('stco')
def parse_stco(type, offset, content, indent):
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#stco
	# http://atomicparsley.sourceforge.net/mpeg-4files.html
	
	# multiple stco atoms may exist
	# thsese chunks (offsets) need to be adjusted when relocating the 'moov' atom
	
	p = 0
	(version,) = struct.unpack('>B', content[p:p+1].str()); p += 1
	(flags,)   = struct.unpack('>3s', content[p:p+3].str()); p += 3
	(count,)   = struct.unpack('>I', content[p:p+4].str()); p += 4
	
	assert p + 4*count <= content.len
	chunks = array.array("I", content[p:p+4*count].str())
	chunks.byteswap()
	chunks = abbrevlist(chunks)
	assert (len(chunks) == count)
	p += 4*count
	
	children = parse_sequence(None, offset + p, content[p:], indent=indent+1)

	return [
		Record(
			version = version,
			flags = flags,
			chunks = chunks
		)
	] + children


@handler('stss')
def parse_stss(type, offset, content, indent):
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#stss
	
	p = 0
	(version,) = struct.unpack('>B', content[p:p+1].str()); p += 1
	(flags,)   = struct.unpack('>3s', content[p:p+3].str()); p += 3
	(count,)   = struct.unpack('>I', content[p:p+4].str()); p += 4
	
	assert p + 4*count <= content.len
	chunks = array.array("I", content[p:p+4*count].str())
	chunks.byteswap()
	chunks = abbrevlist(chunks)
	assert (len(chunks) == count)
	p += 4*count
	
	children = parse_sequence(None, offset + p, content[p:], indent=indent+1)

	return [
		Record(
			version = version,
			flags = flags,
			chunks = chunks
		)
	] + children


@handler('stsz')
def parse_stsz(type, offset, content, indent):
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#stsz
	
	p = 0
	(version,)    = struct.unpack('>B',  content[p:p+1].str()); p += 1
	(flags,)      = struct.unpack('>3s', content[p:p+3].str()); p += 3
	(samplesize,) = struct.unpack('>I',  content[p:p+4].str()); p += 4
	(count,)      = struct.unpack('>I',  content[p:p+4].str()); p += 4
	
	if samplesize == 0:
		assert p + 4*count <= content.len
		sizes = array.array("I", content[p:p+4*count].str())
		sizes.byteswap()
		sizes = abbrevlist(sizes)
		assert(len(sizes) == count)
		p += 4*count
	else:
		sizes = abbrevlist()
	
	children = parse_sequence(None, offset + p, content[p:], indent=indent+1)
	
	return [
		Record(
			version = version,
			flags = flags,
			samplesize = samplesize,
			count = count,
			sizes = sizes
		)
	] + children


@handler('ftyp')
def parse_ftyp(type, offset, content, indent):
	brand = content[0:4].str()
	version = struct.unpack(">BBBB", content[4:8].str())
	compatibles = [
		content[p:p+4].str()
		for p in xrange(8, content.len, 4)
	]
	
	# replace content
	return (brand, version, compatibles)
	return Record(
		brand=brand,
		version=version,
		compatibles=compatibles
	)

@handler('meta')
def parse_meta(type, blockoffset, block, indent):
	return parse_sequence(type, blockoffset+4, block[4:], indent)

@handler('data')
def parse_data(type, blockoffset, content, indent):
	p = 0
	(version,) = struct.unpack('>B', content[p:p+1].str()); p += 1
	(flags,)   = struct.unpack('>3s', content[p:p+3].str()); p += 3
	
	p += 4 # NULL space
	
	return Record(
		version = version,
		flags = flags,
		content = content[p:].str()
	)

#@handler('mvhd')
#def parse_mvhd(type, blockoffset, content, indent):
	#	u8  version;
	#	u24 flags;
	#	u32 creation_time; // in mac UTC time, epoch starts 1904 ends 2040, >>> datetime.datetime(1904, 1, 1) + datetime.timedelta(seconds=value)
	#	u32 modification_time;
	#	u32 time_scale;
	#	u32 duration;
	#	f32 preferred_rate;
	#	f16 preferred_volume;
	#	char reserved[10];
	#	quicktime_matrix_t matrix; (9 * fixed32)
	#	u32 preview_time;
	#	u32 preview_duration;
	#	u32 poster_time;
	#	u32 selection_time;
	#	u32 selection_duration;
	#	u32 current_time;
	#	u32 next_track_id;
#	pass

@handler('ilst')
def parse_ilst(type, blockoffset, block, indent):
	res = []

	for atom in parse_sequence(type, blockoffset, block, indent):
		(type, position, content) = (atom.type, atom.start, atom.content)
		
		if (type == 'trkn') or (type[0] == '\xa9'):
			content = parse_sequence(type, position, content, indent+1)
			
			assert len(content) == 1
			
#			if type == 'trkn':
#				# http://code.activestate.com/recipes/496984/
#				(_a, _b, _c) = content[0] # atom = content[0]; _c = atom.content, which should be a buffer
#				assert _a == 'data'
#
#				import pdb
#				pdb.set_trace()
#
#				_c.content = struct.unpack(">II", _c.content.str())
			
		res.append(
			Atom(position, atom.length, type, content)
			#(type, position, content)
		)
	
	return res

@handler(None, 'moov', 'trak', 'edts', 'mdia', 'minf', 'stbl', 'udta')
def parse_sequence(type, blockoffset, block, indent=0):
	start = 0
	
	res = []
	
	# 'type' argument not used?
	# ... standard handler arglist ...

	while start < block.len:
		if not (start+8 <= block.len):
			raise AtomIncomplete(None, blockoffset+start, blockoffset+start+8, blockoffset+block.len)
			
		(size, type) = struct.unpack(">I4s", block[start:start+8].str())
		contentoffset = 8
		
		if size >= 8:
			pass # normal
			
		elif size == 1: # 64 bit atom
			contentoffset = 16
			(size,) = struct.unpack(">Q", block[start+8:start+16].str())
		
		elif size == 0:	# -> extends to end of file		
			size = block.len - start
		
		else:
			assert 0

		content = block[start+contentoffset : start+size]
		
		if not (content.len == size-contentoffset):
			raise AtomIncomplete(type, blockoffset+start, blockoffset+start+size, blockoffset+start+contentoffset+content.len)

		print lineindent(indent) + "%s  [@%d + %d]" % (type, blockoffset+start, size)
		
		if type in handlers:
			content = handlers[type](
				type,
				blockoffset+start+contentoffset,
				content,
				indent+1
				)

		res.append(
			Atom(blockoffset+start, size, type, content)
			#(type, blockoffset+start, content)
		)

		start += size

	assert start == block.len
	
	return res
	

def parse(buffer, offset=0):
	return handlers[None](None, 0, buffer)

# ======================================================================

sig = " -- MP4 check"

statuses = {
	0: "GOOD",
	1: "INCOMPLETE",
	3: "INDEX NOT AT BEGINNING"
}

fnames = []

#fnames.append('mp4 parsing\\8Juv1MVa-483.mp4')
#fnames.append('mp4 parsing\\8Juv1MVa-483 - Copy.mp4')

for globbable in sys.argv[1:]:
	fnames += glob.glob(globbable)

for fname in fnames:
	assert os.path.isfile(fname)
	
	print fname
	#print
	
	fb = FileBuffer(fname)

	status = 0
	atoms = None
	exception = None
	try:
		atoms = parse(fb)
	except AtomIncomplete, exception:
		print exception
		status = 1
	
	# check position of index
	if atoms:
		for atom in atoms:
			if atom.start > 1e6:
				# no index found below 1 MB
				status = 3
				print "index not at beginning of file!"
				break

			if atom.type == 'moov':
				# index found, done here
				break
	
	if status == 0:
		print "file looks okay"
		#print

	try:	
		# clean up previous statuses
		for x in glob.glob(os.path.abspath(fname) + sig + '*'):
			os.unlink(x)
	except OSError, e:
		if e.errno == 13:
			print "could not clean up check result files"
		else:
			raise
	
	# write new status
	x = os.path.abspath(fname) + sig + " result %s" % statuses[status]
	try:
		with open(x, 'w') as fh:
			if atoms:
				for i, atom in enumerate(atoms):
					fh.write(atom.__repr__(index=i))
					fh.write('\n')
			if exception:
				fh.write('%s: %s\n' % (exception.__class__.__name__, exception))
		os.chmod(x, 0664)
	except IOError, e:
		if e.errno == 13:
			print "could not write check result file"
		else:
			raise
	
	if len(fnames) == 1:
		sys.exit(status)
	
	print
