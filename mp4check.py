#!/usr/bin/env python2.7

from __future__ import with_statement
import os, sys
import struct
import pprint; pp = pprint.pprint
import glob
import ctypes
import time, datetime, calendar
import numpy as np
from funcs import *
from filetools import *
import trecformat

# TODO: while parsing, allow access to tree, to query other atoms

# TODO: need a "table" type (around dict, list, ...) for display

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
	def __init__(self, start, length, type, content=None, buf=None):
		self.start   = start
		self.length  = length
		self.type    = type
		self.content = content
		self.buf     = buf
	
	def __repr__(self, indent=0, index=0):
		label = self.type if all(32 <= ord(c) < 128 for c in self.type) else repr(self.type)
		
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

# TODO: allow to specify context/path

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
def parse_elst(type, offset, content, path):
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#elst
	version = (content >> ">B")
	flags   = (content >> ">3B")
	count   = (content >> ">I")
	assert version == 0
	assert flags == (0,0,0)

	assert content.pos + 12*count == content.len

	entries = np.fromstring(content.read(), dtype='>i4,>i4,>i4'
		#[('duration', '>i4'), ('start', '>i4'), ('rate', '>i4')]
	)#.astype('i4,i4,f4')

	entries = [
		{'duration': duration, 'start': start, 'rate': rate / 2**16}
		for (duration, start, rate) in entries
	]
	#entries['f2'] /= 2**16
	#entries = map(tuple, entries)

	#entries = array.array("I", content[p:p+12*count].str())
	#entries.byteswap()
	#entries = zip(entries[0::3], entries[1::3], entries[2::3])
	#entries = abbrevlist(entries)
	#assert (len(entries) == count)
	
	return entries

def mactime(timestamp):
	epoch = datetime.datetime(1904, 1, 1, 0, 0, 0, 0, )
	d = epoch + datetime.timedelta(seconds=timestamp)
	unixtimestamp = calendar.timegm(d.timetuple())
	return unixtimestamp

@handler('mvhd')
def parse_mvhd(type, blockoffset, content, path):
	res = Record()
	
	# http://xhelmboyx.tripod.com/formats/mp4-layout.txt

	(res.version,) = struct.unpack(">B", content[0:1].str())
	res.flags = struct.unpack(">3B", content[1:4].str())
	p = 4
	
	if res.version == 1:
		# dates+durations = u64
		timefmt = ">Q"
		dp = 8
	else:
		timefmt = ">I"
		dp = 4
	
	(res.created,) = struct.unpack(timefmt, content[p:p+dp].str())
	res.created = mactime(res.created)
	p += dp
	(res.modified,) = struct.unpack(timefmt, content[p:p+dp].str())
	res.modified = mactime(res.modified)
	p += dp

	(res.timescale,) = struct.unpack(">I", content[p:p+4].str())
	p += 4
	(res.duration,) = struct.unpack(timefmt, content[p:p+dp].str())
	p += dp

	(res.prefrate,) = struct.unpack(">I", content[p:p+4].str())
	res.prefrate = float(res.prefrate) / 2**16
	p += 4

	(res.prefvol,) = struct.unpack(">H", content[p:p+2].str())
	res.prefvol = float(res.prefvol) / 2**8
	p += 2

	# 10 bytes reserved
	p += 10

	res.matrix = struct.unpack(">9I", content[p:p+36].str())
	res.matrix = [float(v) / 2**16 for v in res.matrix]
	p += 36

	# 24 bytes reserved
	p += 24
	
	return res

@handler('tkhd')
def parse_tkhd(type, offset, content, path):
	version = (content >> ">B")
	flags = byteint(content >> ">BBB")
	flags = Record(
		TrackEnabled   = bool(flags & 0x01),
		TrackInMovie   = bool(flags & 0x02),
		TrackInPreview = bool(flags & 0x04),
		TrackInPoster  = bool(flags & 0x08),
		other          = flags & ~0x0F
	)
	
	ctime = mactime(content >> (">Q" if (version == 1) else ">I"))
	mtime = mactime(content >> (">Q" if (version == 1) else ">I"))

	track_id = (content >> ">i")
	reserved = (content >> ">i")

	# in time units
	duration = (content >> (">Q" if (version == 1) else ">I"))

	reserved = (content >> ">i")

	assert (content >> ">i") == 0

	video_layer = (content >> ">h")

	qt_alternate = (content >> ">h")

	audio_volume = float(content >> ">H") / 2**8

	assert (content >> ">h") == 0

	matrix = [float(content >> ">i") / 2**16 for _ in xrange(9)]

	frame_size = [float(content >> ">i") / 2**16 for _ in xrange(2)]

	#print content.pos, len(content), repr(content[content.pos:])

	return Record(
		version=version,
		flags=flags,
		ctime=ctime,
		mtime=mtime,
		track_id=track_id,
		duration=duration,
		video_layer=video_layer,
		qt_alternate=qt_alternate,
		audio_volume=audio_volume,
		matrix = matrix,
		frame_size=frame_size
	)

@handler('mdhd')
def parse_mdhd(type, offset, content, path):
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#mdhd
	
	version = (content >> ">B")
	flags   = (content >> ">BBB")

	assert version in (0, 1)
	assert flags == (0,0,0)

	if version == 0:
		(ctime, mtime, scale, duration) = (content >> ">IIII")
	elif version == 1:
		(ctime, mtime, scale, duration) = (content >> ">QQIQ")

	(language, quality) = (content >> ">HH")
	
	return Record(
		version = version,
		ctime = ctime,
		mtime = mtime,
		scale = scale,
		duration = duration,
		language = language,
		quality = quality,
	)

@handler('dref')
def handle_dref(type, offset, content, path):
	# https://developer.apple.com/library/mac/documentation/QuickTime/QTFF/QTFFChap2/qtff2.html
	version = (content >> ">B")
	flags = (content >> ">BBB")
	numentries = (content >> ">I")
	assert flags == (0,0,0)

	entries = []
	for i in xrange(numentries):
		oldpos = content.pos
		esize = (content >> ">I")
		etype = (content >> ">4s")
		eversion = (content >> ">B")
		eflags = (content >> ">BBB")

		data = content[content.pos : oldpos+esize]

		content.pos = oldpos + esize

		entries.append(Record(
			type=etype,
			version=eversion,
			flags=eflags,
			data=data.str()
		))

	assert content.pos == content.len

	return Record(
		version=version,
		entries=entries
	)

def nibbles(value, n=0):
	while value >> (4*n):
		n += 1
	return [(value >> 4*k) & 0x0f for k in xrange(n-1, -1, -1)]

def byteint(values):
	res = 0
	for b in values:
		res <<= 8
		res |= b
	return res

@handler('stsd')
def parse_stsd(type, offset, content, path):
	# https://developer.apple.com/library/mac/documentation/QuickTime/QTFF/QTFFChap2/qtff2.html

	version = nibbles(content >> ">B", 2)
	flags = byteint(content >> ">BBB")
	numdescr = (content >> ">I")

	descriptions = []

	for i in xrange(numdescr):
		start = content.pos
		descrlen = (content >> ">I")
		descrformat = (content >> ">4s")
		data = content[content.pos:start+descrlen]
		content.pos += descrlen

		# https://developer.apple.com/library/content/documentation/QuickTime/QTFF/QTFFChap2/qtff2.html#//apple_ref/doc/uid/TP40000939-CH204-61112
		reserved = (data >> ">6B")
		dataref = (data >> ">H")

		# https://developer.apple.com/library/content/documentation/QuickTime/QTFF/QTFFChap3/qtff3.html#//apple_ref/doc/uid/TP40000939-CH205-74522
		version, revision = (data >> ">HH")
		vendor = (data >> ">4s") # FFMP

		record = Record(
			format = descrformat,
			dataref = dataref,
			vendor = vendor,
			version = (version, revision),
		)
		descriptions.append(record)

		if descrformat in ('rle ',): # 'mp4v', 'avc1', 'encv', 's263'):
			(
				record.quality_temporal,
				record.quality_spatial
			) = (data >> ">II") # 0..1024

			width, height = (data >> ">HH")
			record.size = (width, height)

			ppih, ppiv = (data >> ">II")
			record.ppi = (ppih * 2**-16, ppiv * 2**-16)

			datasize = (data >> ">I")
			assert datasize == 0

			frames_per_sample = (data >> ">H")
			record.frames_per_sample = frames_per_sample

			compressor_name = (data >> "32p")
			record.compressor_name = compressor_name

			pixeldepth = (data >> ">H")
			is_monochrome = (pixeldepth > 32)
			if is_monochrome:
				pixeldepth -= 32
			record.is_monochrome = is_monochrome
			record.pixeldepth = pixeldepth

			colortableid = (data >> ">h")
			assert colortableid == -1

			if data.read(8) == '\x00\x00\x00\x0Afiel':
				record.fields = (data >> ">BB")

		elif descrformat in ('mp4a',): # 'enca', 'samr', 'sawb'):
			pass

			if record.version[0] == 2:
				assert (data >> ">H") == 3
				assert (data >> ">H") == 16
				assert (data >> ">h") == -2
				assert (data >> ">h") == 0
				assert (data >> ">I") == 0x10000

				record.sizeOfStructOnly   = (data >> ">I")
				record.audioSampleRate    = (data >> ">d")
				record.numAudioChannels   = (data >> ">I")
				assert (data >> ">I") == 0x7F000000

				record.constBitsPerChannel = (data >> ">I")
				record.formatSpecificFlags = (data >> ">I")
				record.constBytesPerAudioPacket = (data >> ">I")
				record.constLPCMFramesPerAudioPacket = (data >> ">I")

			elif record.version[0] == 1:
				record.audio_channels = (data >> ">H")
				record.audio_sample_size = (data >> ">H")
				record.audio_compression_id = (data >> ">h")
				record.audio_packet_size = (data >> ">h")
				record.audio_sample_rate = (data >> ">I") * 2**-16

				record.samples_per_packet = (data >> ">I")
				record.bytes_per_packet   = (data >> ">I")
				record.bytes_per_frame    = (data >> ">I")
				record.bytes_per_sample   = (data >> ">I")

			elif record.version[0] == 0:
				record.audio_channels = (data >> ">H")
				record.audio_sample_size = (data >> ">H")
				record.audio_compression_id = (data >> ">h")
				record.audio_packet_size = (data >> ">h")
				record.audio_sample_rate = (data >> ">I") * 2**-16

			else:
				assert False, "STSD {} version {} unexpected".format(record.format, record.version)



			# elif res.format in ('mp4s', 'encs'):
			# 	pass

			# res.remainder = content[content.pos:]

		remainder = data[data.pos:]
		if remainder:
			record.remainder = remainder

	return descriptions


@handler('co64')
def parse_co64(type, offset, content, path):
	return content
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#co64

@handler('stco')
def parse_stco(type, offset, content, path):
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#stco
	# http://atomicparsley.sourceforge.net/mpeg-4files.html
	
	# multiple stco atoms may exist
	# thsese chunks (offsets) need to be adjusted when relocating the 'moov' atom
	
	version = (content >> '>B')
	flags   = (content >> '>BBB')
	count   = (content >> '>I')

	assert flags == (0,0,0)
	
	offsets = np.fromstring(content.read(), dtype=np.uint32).byteswap()
	assert (len(offsets) == count)
	
	return Record(
		version = version,
		offsets = offsets
	)


@handler('stss')
def parse_stss(type, offset, content, path):
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#stss
	
	version = (content >> '>B')
	flags   = (content >> ">BBB")
	count   = (content >> ">I")

	assert flags == (0,0,0)
	
	assert content.pos + 4*count == content.len

	chunks = np.fromstring(content.read(), dtype=np.uint32).byteswap()
	assert (len(chunks) == count)
	
	return Record(
		version = version,
		chunks = chunks
	)

@handler('stts')
def parse_stss(type, offset, content, path):
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#stss
	
	version = (content >> '>B')
	flags   = (content >> ">BBB")
	count   = (content >> ">I")

	assert version == 0
	assert flags == (0,0,0)

	# (count,duration) tuples
	entries = np.fromstring(content.read(), dtype=np.uint32).byteswap().reshape((-1, 2))
	assert len(entries) == count

	return entries


@handler('stsz')
def parse_stsz(type, offset, content, path):
	# http://wiki.multimedia.cx/index.php?title=QuickTime_container#stsz
	
	version    = (content >> '>B')
	flags      = (content >> '>BBB')
	samplesize = (content >> '>I')
	count      = (content >> '>I')

	assert flags == (0,0,0)

	if samplesize == 0: # different sizes
		sizes = np.fromstring(content.read(), dtype=np.uint32).byteswap()
		assert(len(sizes) == count)

	else: # all same size
		sizes = None
	
	return Record(
		version = version,
		samplesize = samplesize,
		sizes = sizes
	)


@handler('ftyp')
def parse_ftyp(type, offset, content, path):
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

@handler('vmhd')
def parse_vmhd(type, offset, content, path):
	version = nibbles(content >> ">B", 2)

	flags = byteint(content >> ">BBB")

	quickdraw = (content >> ">H")
	quickdraw = {
		0x0000: 'copy',
		0x0040: 'dither copy',
		0x0100: 'straight alpha',
		0x0103: 'composition dither copy',
		0x0020: 'blend',
		0x0101: 'premul white alpha',
		0x0102: 'premul black alpha',
		0x0024: 'transparent',
		0x0104: 'straight alpha blend',

	}.get(quickdraw, quickdraw)

	mode_color = (content >> ">HHH")

	return Record(
		version=version,
		flags=flags,
		quickdraw=quickdraw,
		mode_color=mode_color,
	)

@handler('meta')
def parse_meta(type, offset, content, path):
	if path == 'moov.udta.meta'.split('.'):
		assert content.fp.name.endswith('.mp4') # should happen in MP4 files only
		assert content[0:4].str() == '\x00'*4
		return parse_sequence(type, offset+4, content[4:], path)
	else:
		# anything else: just a container
		return parse_sequence(type, offset, content, path)

@handler('hdlr')
def parse_hdlr(type, offset, content, path):
	if path[-2:] != ['meta', 'hdlr']:
		return None # unhandled, use default

	#import pdb; pdb.set_trace()
	version = (content >> ">B")

	flags = (content >> ">BBB")
	assert flags == (0,0,0)

	predef = (content >> ">I")
	assert predef == 0

	htype = (content >> "4s")
	assert htype == 'mdta'

	reserved = (content >> ">3I")
	assert reserved == (0,0,0)

	name = content[content.pos:].szstr()

	return Record(
		version=version,
		name=name
	)

@handler('keys')
def parse_keys(type, offset, content, path):
	version = (content >> ">B")
	
	flags = (content >> ">BBB")
	assert flags == (0,0,0)

	numentries = (content >> ">I")

	entries = {}
	index = 1
	while content.pos < content.len:
		keysize = (content >> ">I")
		namespace = (content >> ">4s")
		value = content.read(keysize-8)
		entries[index] = (namespace, value)
		index += 1

	return Record(
		version=version,
		entries=entries
	)

@handler('ilst')
def parse_ilst(type, offset, content, path):
	return parse_sequence(type, offset, content, path)

# TODO: do this right
def parse_ilst(type, offset, content, path):
	res = Record()

	def visit(key, offset, content, path):
		key_index, = struct.unpack(">I", key)
		
		item = Record()

		children = parse_sequence(None, offset, content, path=path+[key_index])

		# optional item_info atom
		assert not any(c.type == 'itif' for c in children)

		# optional name atom
		assert not any(c.type == 'name' for c in children)

		# value
		value, = [c for c in children if c.type == 'data']
		item.value = value

		atom.key_index = key_index
		return atom
	
	return {
		atom.key_index: atom
		for atom
		in parse_sequence(type, offset, content, path, use_handler=visit)
	}

def parse_ilst_old(type, blockoffset, block, path):
	res = []

	for atom in parse_sequence(type, blockoffset, block, path):
		(type, position, content) = (atom.type, atom.start, atom.content)
		
		if (type == 'trkn') or (type[0] == '\xa9'):
			content = parse_sequence(type, position, content, path=path+[type])
			
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

@handler('data')
def parse_data(type, offset, content, path):
	p = 0
	(version,) = struct.unpack('>B', content[p:p+1].str()); p += 1
	(flags,)   = struct.unpack('>3s', content[p:p+3].str()); p += 3
	
	p += 4 # NULL space
	
	return Record(
		version = version,
		flags = flags,
		content = content[p:].str()
	)

def UUID(buffer):
	s = str(buffer).encode('hex')
	return "%s-%s-%s-%s-%s" % (s[0:8], s[8:12], s[12:16], s[16:20], s[20:32])

@handler('uuid', 'DATA')
def parse_uuid(type, blockoffset, content, path):
	(uuid,) = struct.unpack('>16s', content[:16].str())
	
	uuid = UUID(uuid)
	
	result = Record(
		uuid = uuid,
		content = content[16:]
	)
	
	if uuid.endswith('11e2-83d0-0017f200be7f'):
		result = trecformat.parse_TSCMDATA(result.uuid, result.content)
	
	return result

@handler(None, 'moov', 'trak', 'edts', 'mdia', 'dinf', 'minf', 'stbl', 'udta', 'TSCM')
def parse_sequence(type, blockoffset, block, path=[], use_handler=True):
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

		if verbose:
			label = type if all(32 <= ord(c) < 128 for c in type) else repr(type)
			print lineindent(len(path)) + "%s  [@%d + %d]" % (label, blockoffset+start, size)

		newcontent = None		

		if use_handler is True:
			if type in handlers:
				newcontent = handlers[type](
					type,
					blockoffset+start+contentoffset,
					content,
					path+[type]
				)
		elif use_handler:
			newcontent = use_handler(
				type,
				blockoffset+start+contentoffset,
				content,
				path+[type]
			)

		if newcontent is not None:
			content = newcontent

		item = Atom(blockoffset+start, size, type, content, buf=block[start:start+size])
		res.append(item)

		start += size

	assert start == block.len
	
	return res
	

def parse(buffer, offset=0):
	return handlers[None](None, 0, buffer)

def select(data, path):
	for edge in path:
		# find edge
		for atom in data:
			if atom.type == edge:
				break
		else:
			assert False, "edge %s not found at this place in the tree" % repr(edge)
		
		data = atom.content
	
	return data

# ======================================================================

verbose = False

if __name__ == '__main__':
	verbose = True
	
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
