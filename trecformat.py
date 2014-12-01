import struct
import pprint; pp = pprint.pprint
from funcs import *
from filetools import *

__all__ = ['parse_TSCMDATA']

# ----------------------------------------------------------------------

# uuid -> fn
fnmap = {} # fn -> uuid/prefix
handlers = {}
descriptions = {}
# supposed to be a map function applied to elements of a list

def onuuid(uuid, description):
	descriptions[uuid] = description
	def decorator(fn):
		fnmap[fn] = uuid
		assert uuid not in handlers
		handlers[uuid] = fn
		return fn
	return decorator

# suffix -7a1f-11e2-83d0-0017f200be7f

# ----------------------------------------------------------------------

@onuuid('2b7b6aef', "looks like another time table")
def map_ef(block):
	return struct.unpack("<diiii", block.str())

@onuuid('2b7b6af0', "possibly mouse-down/up events")
def map_f0(block):
	return struct.unpack("<dI", block.str())

@onuuid('2b7b6af1', "cursor icons")
def map_f1(block):
	(timeval, i1, i2, remlen) = struct.unpack("<dIII", block[0:20].str())

	# either i1 is u64 or I don't know what this means
	assert i2 == 0

	picture = Record(
		time = timeval,
		cursorindex = (i1, i2),
	)

	if remlen > 0:
		block = block[20:]
		picture.center_BL = struct.unpack("<II", block[0:8].str())

		picture.cursor = block[8:remlen-4]

		# no clue what this is supposed to be
		(i3,) = struct.unpack("<I", block[remlen-4:].str())
		assert i3 == 0
	
	return picture

@onuuid('2b7b6af2', "cursor tracks")
def map_f2(block):
	return struct.unpack("<dII", block.str()) # t, x, y
	# last time value looks very wrong, but the data looks right
	# definitely a 64 bit float
	# the x/y values seem to be 0

@onuuid('2b7b6af3', "some kind of marker list, sometimes empty. second value usually 1.0 or 0.0")
def map_f3(block):
	return struct.unpack("<dd", block.str())

@onuuid("2b7b6af5", "command key strokes (VK_*), no text")
def map_f5(block):
	(time, keycode, dc1, modifier, const1) = struct.unpack("<dIHBB", block.str())
	assert dc1 == 0
	assert const1 == 64
	return (time, keycode, modifier)
	# see http://msdn.microsoft.com/en-us/library/windows/desktop/dd375731(v=vs.85).aspx

@onuuid('2b7b6af6', "recording dimensions and unknown data")
def map_f6(block):
	assert len(block) == 24
	(width,height) = struct.unpack("<II", block[16:24].str())
	return Record(width=width, height=height, other=block[:16])

@onuuid('2b7b6af7', "time and position of focused window")
def map_f7(block):
	return struct.unpack("<diiII", block.str())

@onuuid('2b7b6af8', "PPT slide titles and timing")
@onuuid('2b7b6af9', "PPT slide content and timing")
def map_f8f9(block):
	(f1,) = struct.unpack("<d", block[0:8].str())
	text = block[8:].str()
	return Record(
		time = f1,
		text = text,
	)

@onuuid('2b7b6afa', "looks like speaker notes")
def map_fa(block):
	(t,) = struct.unpack("<d", block[0:8].str())
	return (t, block[8:].str())

# ----------------------------------------------------------------------

def parse_TSCMDATA(uuid, content):
	# result data set
	rec = Record(
		uuid = uuid,
		content = content
	)
	
	(one,stride) = struct.unpack("<II", content[0:8].str())
	assert one == 1
	content = content[8:]
	
	# appears to be an array of structs
	if stride > 0:
		sublist = []
		p = 0
		while p < len(content):
			sublist.append(content[p:p+stride])
			p += stride

		content = rec.content = sublist

	# appears to be a list of variable-length blocks
	else:
		sublist = []
		p = 0
		while p < len(content):
			(blocklen,) = struct.unpack("<I", content[p:p+4].str())
			p += 4
			sublist.append(content[p:p+blocklen])
			p += blocklen

		content = rec.content = sublist
		
	# search handlers for prefix match
	candidates = [p for p in handlers if uuid.startswith(p)]
	if candidates:
		(k,) = candidates # must be exactly one (for now)
		fn = handlers[k]
		rec.description = descriptions[k]
		rec.content = map(fn, rec.content)
			
	return rec
