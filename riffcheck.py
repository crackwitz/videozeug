#!/usr/bin/env python2.7
# written by christoph.rackwitz@gmail.com

# http://www.kk.iij4u.or.jp/~kondo/wave/mpidata.txt

from __future__ import with_statement
from __future__ import division
import os
import sys
import struct
import pprint; pp = pprint.pprint
import time
import glob
from funcs import *
from filetools import *
from socket import gethostname

# TODO: read/write support
#   * chunks know to read and write themselves (and command their content to do so)
#   * positioned chunks
#   * consistency check for positions and lengths
#   * re-layout to squeeze air out or make room
#   * support for in-place patching of files
#     -> chunks know their origin and "current" position

# ======================================================================

sig = " -- RIFF check"

statuses = {
	0: "GOOD",
	1: "INCOMPLETE"
}

# ======================================================================
# RIFF definitions

riff_info_subchunks = 'IARL IART ICMS ICMT ICOP ICRD ICRP IDIM IDPI IENG IGNR IKEY ILGT IMED INAM IPLT IPRD ISBJ ISFT ISHP ISRC ISRF ITCH'.split()

riff_country_codes = {
	  0: 0,
	  1: "USA",
	  2: "Canada",
	  3: "Latin America",
	 30: "Greece",
	 31: "Netherlands",
	 32: "Belgium",
	 33: "France",
	 34: "Spain",
	 39: "Italy",
	 41: "Switzerland",
	 43: "Austria",
	 44: "United Kingdom",
	 45: "Denmark",
	 46: "Sweden",
	 47: "Norway",
	 49: "West Germany",
	 52: "Mexico",
	 55: "Brazil",
	 61: "Australia",
	 64: "New Zealand",
	 81: "Japan",
	 82: "Korea",
	 86: "Peoples Republic of China",
	 88: "Taiwan",
	 90: "Turkey",
	351: "Portugal",
	352: "Luxembourg",
	354: "Iceland",
	358: "Finland",
}

riff_lang_dialects = {
	(0,  0): (0, 0),
	(1,  1): "Arabic",
	(2,  1): "Bulgarian",
	(3,  1): "Catalan",
	(4,  1): "Traditional Chinese",
	(4,  2): "Simplified Chinese",
	(5,  1): "Czech",
	(6,  1): "Danish",
	(7,  1): "German",
	(7,  2): "Swiss German",
	(8,  1): "Greek",
	(9,  1): "US English",
	(9,  2): "UK English",
	(10, 1): "Spanish",
	(10, 2): "Spanish Mexican",
	(11, 1): "Finnish",
	(12, 1): "French",
	(12, 2): "Belgian French",
	(12, 3): "Canadian French",
	(12, 4): "Swiss French",
	(13, 1): "Hebrew",
	(14, 1): "Hungarian",
	(15, 1): "Icelandic",
	(16, 1): "Italian",
	(16, 2): "Swiss Italian",
	(17, 1): "Japanese",
	(18, 1): "Korean",
	(19, 1): "Dutch",
	(19, 2): "Belgian Dutch",
	(20, 1): "Norwegian - Bokmal",
	(20, 2): "Norwegian - Nynorsk",
	(21, 1): "Polish",
	(22, 1): "Brazilian Portuguese",
	(22, 2): "Portuguese",
	(23, 1): "Rhaeto-Romanic",
	(24, 1): "Romanian",
	(25, 1): "Russian",
	(26, 1): "Serbo-Croatian (Latin)",
	(26, 2): "Serbo-Croatian (Cyrillic)",
	(27, 1): "Slovak",
	(28, 1): "Albanian",
	(29, 1): "Swedish",
	(30, 1): "Thai",
	(31, 1): "Turkish",
	(32, 1): "Urdu",
	(33, 1): "Bahasa",
}

# ======================================================================

def riffpad(x):
	words = x // 2
	
	if x % 2 > 0:
		words += 1
	
	return words*2

riffindent = lambda n: n*'    '

# ======================================================================
# exceptions

class RIFFIncomplete(Exception):
	def __init__(self, type, chunkstart, chunkend, realend):
		self.type       = type
		self.chunkstart = chunkstart
		self.chunkend   = chunkend
		self.realend    = realend
	
	def __str__(self):
		return 'Chunk %s @%d Should extend to %d, ends at %d (%d missing)' % (repr(self.type), self.chunkstart, self.chunkend, self.realend, self.chunkend - self.realend)

class RIFFUnknownChunkType(Exception):
	def __init__(self, type, chunkstart, chunkend):
		self.type       = type
		self.chunkstart = chunkstart
		self.chunkend   = chunkend
	
	def __str__(self):
		return 'Unknown Chunk type %s @%d:%d' % (repr(self.type), self.chunkstart, self.chunkend)

# ======================================================================
# tree structure

class RIFFChunk(object):
	def __init__(self, type, start, length, tag=None, parent=None, root=None):
		self.type        = type # riff, list, fmt, ...
		self.tag         = tag # wave, adtl, ...
		self.start       = start
		self.length      = length
		self.content     = None
		self.contenttype = 'data' # 'chunks' or 'data'
		self.parent      = parent
		self.root        = root
		self.abbreviated = False
		
	def query(self, filterfunc, recursive=False):
		res = []
		
		if filterfunc(self):
			res.append(self)

		if recursive and self.contenttype == 'chunks':
			for chunk in self.content:
				res += chunk.query(filterfunc, recursive=recursive)
			
		return res
	
	def getchunks(self, *types):
		def pred(chunk):
			for type in types:
				if isinstance(type, tuple):
					ckey = (chunk.type, chunk.tag)
				else:
					ckey = chunk.type
				
				if ckey == type:
					return True
			return False
		return self.query(pred, recursive=True)
	
	def getchunk(self, *types):
		(chunk,) = self.getchunks(*types)
		return chunk
	
	def __repr__(self, indent=0, index=0):
		label = self.type
		if self.tag:
			label += " " + repr(self.tag)
		
		if self.contenttype == 'chunks':
			sublabel = " // %d subchunks..." % len(self.content)
		else:
			sublabel = " // data..."
		
		#res = [riffindent(indent) + '(%d) %s  [@%d + %d]%s\n' % (
		res = [riffindent(indent) + '%s  [@%d + %d]%s\n' % (
			label,
			self.start,
			self.length,
			sublabel
		)]
		
		res.append(riffindent(indent) + "{\n")

		if self.contenttype == 'chunks':
			if self.abbreviated:
				res.append(riffindent(indent+1) + "// not shown\n")
			else:
				for i,item in enumerate(self.content):
					res.append(item.__repr__(indent+1, index=i))
		else:
			contentrepr = pprint.pformat(self.content)
			contentrepr = blockindent(4*(indent+1), contentrepr)
			res += [line + "\n" for line in contentrepr.split('\n')]

		res.append(riffindent(indent) + "}\n")
		
		return ''.join(res)
		

class RIFFRoot(RIFFChunk):
	pass

# ======================================================================
# parsing

# (chunk, block, indent)
riff_handlers = {}

# (chunk, indent)
riff_posthandlers = {}

# dispatch
def call_handler(key, chunk, block, indent):
	if isinstance(key, tuple):
		(type,tag) = key
		label = "%s %s" % (type, repr(tag))
	else:
		type = key
		label = "%s" % (type,)

	print riffindent(indent) + "%s  [@%d + %d]" % (label, chunk.start, chunk.length)
	
	if key not in riff_handlers:
		key = None
		#raise RIFFUnknownChunkType(chunk.type, chunk.start, chunk.start + chunk.length)
		
	res = riff_handlers[key](chunk, block, indent=indent)

	return res

def call_posthandler(key, chunk, indent):
	if isinstance(key, tuple):
		(type,tag) = key
		label = "%s %s" % (type, repr(tag))
	else:
		type = key
		label = "%s" % (type,)

	if key not in riff_posthandlers:
		key = None

	return riff_posthandlers[key](chunk, indent=indent)

# decorator for registering handlers
def chunkhandler(*types):
	def sub(fn):
		for type in types:
			riff_handlers[type] = fn
		return fn
	return sub

#decorator for registering postprocessing handler
def postprocessor(*types):
	def sub(fn):
		for type in types:
			riff_posthandlers[type] = fn
		return fn
	return sub

def parse_riff_file(fileblock):
	rootchunk = RIFFRoot(
		type="root", start=0, length=fileblock.length(),
		tag=None, parent=None, root=None)
	
	rootchunk.root = rootchunk
	rootchunk.contenttype = 'chunks'
	rootchunk.content = []
	
	parse_chunk_sequence(rootchunk, 0, fileblock, indent=0)
	
	return rootchunk

def parse_chunk(chunk, block, indent=0):
	key = chunk.type
	
	call_handler(key, chunk, block, indent=indent)
	call_posthandler(key, chunk, indent=indent)
	
def parse_chunk_sequence(chunk, base, block, indent=0):
	p = 0
	while p < block.length():
		# parse type, length
		if p + 8 > block.length():
			raise RIFFIncomplete(None, base+p, base+p+8, base+block.length())

		(type, length) = struct.unpack("4sI", block[p:p+8].str())
		
		if type == '\x00\x00\x00\x00' and length == 0:
			raise Exception("@%d expected chunk, found nulls" % p)
		
		length += 8

		if block.length() < p + length:
			raise RIFFIncomplete(type, base+p, base+p+length, base+block.length())

		subchunk = RIFFChunk(type, base+p, length,
			tag=None, parent=chunk, root=chunk.root)
		chunk.content.append(subchunk)
		
		parse_chunk(subchunk, block[p:p+length], indent=indent)
		
		p += riffpad(length)
	
	assert p == block.length()

@chunkhandler(None)
def parse_unknown(chunk, block, indent):
	chunk.content     = block[8:]

@postprocessor(None)
def postparse_unknown(chunk, indent):
	pass

# LIST: INFO
@chunkhandler(*riff_info_subchunks)
def parse_stringchunk(chunk, block, indent):
	content = block[8:]
	chunk.content = content.str().rstrip('\x00')

@postprocessor(("LIST", "INFO"))
def post_list_info(chunk, indent):
	# consolidate subchunks containing single strings
	chunk.contenttype = 'data'
	chunk.content = Record(
		(sub.type, sub.content)
		for sub in chunk.content
	)
	pass
	
@postprocessor(("LIST", "adtl"), ("list", "adtl"))
def post_list_adtl(chunk, indent):
	chunk.contenttype = 'data'
	chunk.content = [
		(sub.type, odict(sub.content))#(sub.type, sub.content.name, sub.content.data)
		for sub in chunk.content
	]
	return
	chunk.content = Record(
		(i, sub.content) # (sub.content.name, sub.content.data)
		for i,sub in enumerate(chunk.content)
	)

@chunkhandler('labl', 'note')
def parse_adtl_lablnote(chunk, block, indent):
	content = block[8:]
	(name,) = struct.unpack("i", content[0:4].str())
	data = content[4:].str().rstrip('\x00')
	chunk.content = odict([('name', name), ('data', data)]) # todo: ordered record?

@chunkhandler('file')
def parse_adtl_file(chunk, block, indent):
	content = block[8:]
	
	(cuename, medtype) = struct.unpack("II", content[0:8].str())
	chunk.content = Record(
		_cuename = cuename,
		_medtype = medtype,
		filedata = content[8:]
	)
	
@chunkhandler('ltxt')
def parse_adtl_ltxt(chunk, block, indent):
	content = block[8:]
	fields = struct.unpack("ii4shhhh", content[0:20].str())
	data = content[20:].str()
	#<dwName:DWORD>
	#<dwSampleLength:DWORD>
	#<dwPurpose:DWORD>
	
	#<wCountry:WORD>
	#<wLanguage:WORD>
	#<wDialect:WORD>
	#<wCodePage:WORD>
	#<data:BYTE>...
	
	chunk.content = Record(
		name         = fields[0],
	)

	if fields[1]:
		chunk.content.samplelength = fields[1]
	if fields[2]:
		chunk.content.purpose      = fields[2]
	if fields[3]:	
		country = fields[3]
		country = riff_country_codes.get(country, country)
		chunk.content.country      = country
	if fields[4] or fields[5]:
		lang_dialect = (fields[4], fields[5])
		lang_dialect = riff_lang_dialects.get(lang_dialect, lang_dialect)
		chunk.content.lang_dialect = lang_dialect
	if fields[6]:
		chunk.content.codepage     = fields[6]
	if data:
		chunk.content.data         = data

@chunkhandler('slnt')
def parse_slnt(chunk, block, indent):
	content = block[8:]
	(nsamples,) = struct.unpack("I", content[0:4].str())
	chunk.content = Record(
		nsamples=nsamples
	)

@chunkhandler("RIFF", "LIST", "list")
def parse_rifflist(chunk, block, indent=0):
	if chunk.length < 12:
		raise RIFFIncomplete(chunk.type, chunk.start, chunk.start+12, chunk.start+chunk.length)

	if chunk.length != block.length():
		raise RIFFIncomplete(chunk.type, chunk.start, chunk.start+chunk.length, chunk.start+block.length())
	
	(tag,) = struct.unpack("4s", block[8:12].str())
	
	chunk.tag = tag

	recurse = call_handler((chunk.type,tag), chunk, block, indent=indent)
	
	if recurse is not False:
		chunk.contenttype = 'chunks'
		chunk.content = []
		parse_chunk_sequence(chunk, chunk.start+12, block[12:], indent=indent+1)
	else:
		chunk.contenttype = 'data'
		chunk.content = block[12:]
	
	call_posthandler((chunk.type,tag), chunk, indent=indent)

@chunkhandler(("LIST", 'movi'), ("list", "movi"))
def parse_movi(chunk, block, indent):
	return False

@chunkhandler('fmt ')
def parse_fmt(chunk, block, indent):
	content = block[8:]

	common = struct.unpack("hhiih", content[0:14].str())

	format = common[0]
	data = Record()
	data.format     = common[0]
	data.channels   = common[1]
	data.samplerate = common[2]
	data.byterate   = common[3]
	data.blockalign = common[4]

	if format == 0x0001: # PCM
		(bitspersample,) = struct.unpack("h", content[14:16].str())
		data.bitspersample = bitspersample
		data.specific = content[16:]
	else:
		data.specific = content[14:]

	chunk.content = data	

@chunkhandler('plst')
def parse_plst(chunk, block, indent):
	content = block[8:]
	(nsegments,) = struct.unpack("I", content[0:4].str())
	
	content = content[4:]
	chunk.content = []
	for i in xrange(nsegments):
		(cuename, nsamples, nloops) = struct.unpack("III", content[12*i, 12*(i+1)].str())
		
		chunk.content.append(
			Record([('cue', cuename), ('nsamples', nsamples), ('nloops', nloops)])
		)


# iround(cue time * samplerate) -> Position/SampleOffset

@chunkhandler('cue ')
def parse_cue(chunk, block, indent):
	# http://www.neurophys.wisc.edu/auditory/riff-format.txt
	# http://www.sonicspot.com/guide/wavefiles.html#cue

	content = block[8:]
	
	fmt = chunk.root.getchunk('fmt ').content
	
	(cuecount,) = struct.unpack("I", content[:4].str())
	content = content[4:]

	chunk.content = Record()
	for i in xrange(cuecount):
		# DWORD  dwName;
		# DWORD  dwPosition;
		# FOURCC fccChunk;
		# DWORD  dwChunkStart;
		# DWORD  dwBlockStart;
		# DWORD  dwSampleOffset;
		cue = struct.unpack("II4sIII", content[24*i:24*(i+1)].str())

		# (1,        0, 'data', 0, 0, 35947872)
		# (1, 35947872, 'data', 0, 0, 35947872)

		assert cue[0] == i+1
		# cue[1]
		assert cue[2] == 'data' # chunk
		assert cue[3] == 0 # chunkstart
		assert cue[4] == 0 # blockstart
		# cue[5]

		# cue[1,5]: sampleoffset in frames (bitspersample * channels)

		assert cue[0] not in chunk.content
		
		chunk.content[cue[0]] = (
			HumanTime(float(cue[1]) / fmt.samplerate),
			cue[2],
			cue[3],
			cue[4],
			HumanTime(float(cue[5]) / fmt.samplerate)
		)
	
	if gethostname() == 'videoag':
		if 0 not in chunk.content:
			chunk.content[0] = "FEED ME A STRAY CAT"
			chunk.content[max(chunk.content)+1] = "STIMMEN SIE **FUER** PYTHON AUF SCHNITTRECHNERN"

	
@chunkhandler('bext')
def parse_bext(chunk, block, indent):
	content = block[8:]
	
	# http://tech.ebu.ch/docs/tech/tech3285.pdf
	keys = '''
		CHAR   Description[256];  /* ASCII : "Description of the sound sequence" */ 
		CHAR   Originator[32];  /* ASCII : "Name of the originator" */ 
		CHAR   OriginatorReference[32]; /* ASCII : "Reference of the originator" */ 
		CHAR   OriginationDate[10];  /* ASCII : "yyyy:mm:dd" */ Broadcast Wave Format Specification  Tech 3285 v2
		CHAR   OriginationTime[8];  /* ASCII : "hh:mm:ss" */ 
		#DWORD  TimeReferenceLow;  /* First sample count since midnight, low word 
		#DWORD  TimeReferenceHigh;  /* First sample count since midnight, high word 
		#WORD   Version;  /* Version of the BWF; unsigned binary number */
		#BYTE   UMID;  /* Binary byte 0..63 of SMPTE UMID */ 
		#WORD   LoudnessValue;  /* WORD : "Integrated Loudness Value of the file in LUFS (multiplied by 100) " */ 
		#WORD   LoudnessRange;  /* WORD : "Loudness Range of the file in LU (multiplied by 100) " */ 
		#WORD   MaxTruePeakLevel;  /* WORD : "Maximum True Peak Level of the file expressed as dBTP (multiplied by 100) " */ 
		#WORD   MaxMomentaryLoudness;  /* WORD : "Highest value of the Momentary Loudness Level of the file in LUFS (multiplied by 100) " */ 
		#WORD   MaxShortTermLoudness;  /* WORD : "Highest value of the Short-Term Loudness Level of the file in LUFS (multiplied by 100) " */ 
	'''
	
	keys = re.findall(r'^\s*\w+\s+(\w+)', keys, re.M)
	
	fmtstr = "256s32s32s10s8s" # IIH64sHHHHH180s"
	fixedlen = struct.calcsize(fmtstr)
	# supposed to be 602, not 604
	fixedpart = struct.unpack(fmtstr, content[:fixedlen].str())
	
	unknown = content[fixedlen:602] #BYTE   Reserved[180];  /* 180 bytes, reserved for future use, set to "NULL" */ 

	codinghistory = content[602:].str().rstrip('\x00') #CHAR  CodingHistory[];  /* ASCII : " History coding " */ 
	
	chunk.content = Record()
	for k,v in zip(keys, fixedpart):
		chunk.content[k] = v.rstrip('\x00') if isinstance(v, str) else v

	chunk.content.unknown = unknown
	chunk.content.CodingHistory = codinghistory

# ======================================================================
# MAIN

if __name__ == '__main__':
	fnames = []
	for globbable in sys.argv[1:]:
		fnames += glob.glob(globbable)

	for fname in fnames:
		assert os.path.isfile(fname)

		print fname
		#print

		fb = FileBuffer(fname)

		status = 0
		tree = None
		exception = None

		try:
			tree = parse_riff_file(fb)
		except RIFFIncomplete, exception:
			print exception
			status = 1

		if status == 0:
			print 'file looks okay'
			#print

		# clean up previous statuses
		for x in glob.glob(os.path.abspath(fname) + sig + "*"):
			os.unlink(x)

		# write new status
		x = os.path.abspath(fname) + sig + " result %s" % statuses[status]
		if tree.getchunks('_PMX'):
			x += ", with XMP chunk"
		
		try:
			with open(x, 'w') as fh:
				fh.write(repr(tree))
				if exception:
					fh.write('%s: %s\n' % (exception.__class__.__name__, exception))
			os.chmod(x, 0664)

		except IOError, e:
			print "IOError", e

		if len(fnames) == 1:
			sys.exit(status)

		print
