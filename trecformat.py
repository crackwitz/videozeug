import struct
import pprint; pp = pprint.pprint
from funcs import *
from filetools import *

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
		fixedwidth = True
		sublist = []
		p = 0
		while p < len(content):
			subblock = content[p:p+stride]
			p += stride
			sublist.append(subblock)

		content = rec.content = sublist

	# appears to be a list of variable-length blocks
	else:
		fixedwidth = False
		sublist = []
		p = 0
		while p < len(content):
			(blocklen,) = struct.unpack("<I", content[p:p+4].str())
			p += 4
			sublist.append(content[p:p+blocklen])
			p += blocklen
		content = rec.content = sublist
		
		# NOT an array of fixed-width structs
		# BUT a sequence of variable-length structs
		pass

	if uuid.startswith('2b7b6aef'):
		assert fixedwidth
		rec.description = "looks like another time table"
		rec.content = []
		for block in content:
			(f1, i1, i2, i3, i4) = struct.unpack("<diiii", block.str())
			rec.content.append((f1, i1, i2, i3, i4))
	
	if uuid.startswith('2b7b6af6'):
		assert fixedwidth
		rec.description = "recording dimensions and unknown data"
		rec.content = []
		for subblock in content:
			assert len(subblock) == 24
			(width,height) = struct.unpack("<II", subblock[16:24].str())
			rec.content.append(Record(width=width, height=height, other=subblock[:16]))

	if uuid.startswith('2b7b6af7'):
		assert fixedwidth
		rec.description = "time and position of focused window"
		rec.content = []
		for subblock in content:
			(f1,i1,i2,i3,i4) = struct.unpack("<diiII", subblock.str())
			rec.content.append((f1, i1,i2,i3,i4))
		pass
	
	if uuid.startswith('2b7b6af2'):
		assert fixedwidth
		rec.description = "cursor tracks"
		rec.content = []
		for subblock in content:
			(t, x, y) = struct.unpack("<dII", subblock.str())
			rec.content.append((t,x,y))
		
		# last time value looks very wrong, but the data looks right
		# definitely a 64 bit float
		# the x/y values seem to be 0
	
	if uuid.startswith("2b7b6af5"):
		assert fixedwidth
		rec.description = "might be time values, perhaps offsets"
		rec.content = [
			struct.unpack("<dd", subblock.str())
			for subblock in content
		]
	
	if uuid.startswith('2b7b6af0'):
		assert fixedwidth
		rec.description = "possibly mouse-down/up events"
		rec.content = []
		for block in content:
			(f1,i1) = struct.unpack("<dI", block.str())
			rec.content.append((f1,i1))
		
	if uuid.startswith('2b7b6af3'):
		assert fixedwidth
		rec.description = "some kind of marker list, sometimes empty. second value usually 1.0 or 0.0"
		rec.content = [
			struct.unpack("<dd", block.str())
			for block in content
		]
	
	if uuid.startswith('2b7b6af9'):
		assert not fixedwidth
		rec.description = "PPT slide content and timing"
		rec.content = []
		for block in content:
			(f1,) = struct.unpack("<d", block[0:8].str())
			text = block[8:].str()
			rec.content.append(Record(
				time = f1,
				text = text,
			))

	if uuid.startswith('2b7b6af8'):
		assert not fixedwidth
		rec.description = "PPT slide titles and timing"
		rec.content = []
		for block in content:
			(f1,) = struct.unpack("<d", block[0:8].str())
			text = block[8:].str()
			rec.content.append(Record(
				time = f1,
				text = text,
			))

	if uuid.startswith('2b7b6af1'):
		assert not fixedwidth
		rec.description = "cursor state"
		rec.content = []
		for block in content:
			(timeval, i1, i2, remlen) = struct.unpack("<dIII", block[0:20].str())
			block = block[20:]
			
			# either u64 or I don't know what
			assert i2 == 0
			
			picture = Record(
				time = timeval,
				cursorindex = (i1, i2),
			)
			rec.content.append(picture)
						
			if remlen:
				picture.center_BL = struct.unpack("<II", block[0:8].str())
				picture.cursor = block[8:remlen-4]
				
				# no clue what this is supposed to be
				assert block[remlen-4:].str() == '\x00' * 4
			
	return rec
