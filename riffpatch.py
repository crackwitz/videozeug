#!/usr/bin/env python2.7

from __future__ import division
import os
import sys
import json
import re
import wave

from riffcheck import *

dopatch = True

rounded_digits = 3
sampling_rate = 48000

def iround(x):
	return int(round(x))

def parse_point(definition, cues):
	m = re.match(r'#?([+-]?\d+)$', definition)
	if m:
		index = int(m.group(1))
		if index < 0:
			return cues[index]
		elif index >= 1:
			return cues[index-1]
		else:
			assert False
	
	m = re.match(r'(\d+)[:h](\d+)[:m](\d+(?:\.\d+)?)s?$', definition)
	if m:
		h,m,s = m.groups()
		h = int(h)
		m = int(m)
		s = float(s)

		if cues:
			start = time.localtime(min(cues))
			cue = time.mktime((
				start.tm_year,
				start.tm_mon,
				start.tm_mday,
				h, m, 0,
				0, 0, start.tm_isdst
			)) + s
		else:
			cue = int(h) * 3600 + int(m) * 60 + float(s)
		

		return cue
	
	raise ValueError("can't parse this", definition)

def packchunk(type, *datalist):
	datastr = ''.join(
		data if isinstance(data, str) else ''.join(data)
		for data in datalist
	)
	
	datalen = len(datastr)
	npadding = (-datalen) % 2

	return struct.pack("4sI", type, datalen) + datastr + ("\x00" * npadding)

def packlabl(id, text):
	return packchunk('labl',
		struct.pack("I", id) + text + "\x00"
	)


audiofile = sys.argv[1]
markerfile = sys.argv[2]
audiopoint = sys.argv[3]
markerpoint = sys.argv[4]

# get audio cues
sampling_rate = wave.open(audiofile).getframerate()
print "sampling rate:", sampling_rate

assert os.path.isfile(audiofile)
fb = FileBuffer(audiofile, 'r+b' if dopatch else 'rb')
fp = fb.fp # needed for patching
tree = parse_riff_file(fb)

labelchunks = tree.getchunks(('LIST', 'adtl'), ('list', 'adtl'))
# TODO: explain
assert all( not tree.query(lambda ch: ch.start > labelchunk.start) for labelchunk in labelchunks )

cuechunks = tree.getchunks("cue ")
if not cuechunks:
	audiocues = []
	audiolabels = []
else:
	assert len(cuechunks) == 1
	audiocues = cuechunks[0].content
	audiocues = [c[4].value for i,c in audiocues.items()]
	
	audiolabels = sorted([(l[1]['name'], l[1]['data']) for l in labelchunks[0].content if l[0] == 'labl'])
	audiolabels = zip(*audiolabels)[1]

# get marker cues
assert os.path.isfile(markerfile)

markers = map(json.loads, open(markerfile))
markercues = [m['timestamp'] for m in markers]
markerlabels = [m['type'].encode('utf8') for m in markers]


# parse sync points

audiopoint = parse_point(audiopoint, audiocues)
markerpoint = parse_point(markerpoint, markercues)

offset = audiopoint - markerpoint

# shift marker cues
markercues = [round(c + offset, rounded_digits) for c in markercues]

# audiocues (+labels), markercues + offset (+markerlabels)

mergedcues = dict((c,"[%s] %s:" % (i+1, repr(t))) for i,(c,t) in enumerate(zip(markercues, markerlabels)))
for c,l in zip(audiocues, audiolabels):
	if c not in mergedcues:
		mergedcues[c] = l
	else:
		mergedcues[c] += " / " + l

if audiopoint in mergedcues:
	mergedcues[audiopoint] += " / sync"
else:
	mergedcues[audiopoint] = "sync"

print
for k,v in sorted(mergedcues.items()):
	print "%8.3f s -> %s" % (k, v)
print

# patch into audio file
icues = [iround(c * sampling_rate) for c,l in sorted(mergedcues.items())]
ilabels = [l for c,l in sorted(mergedcues.items())]

cuechunk = packchunk("cue ",
	struct.pack("I", len(icues)),
	(
		struct.pack("II4sIII", i+1, v, 'data', 0, 0, v)
		for i,v in enumerate(icues)
	)
)
adtlchunk = packchunk("LIST", "adtl",
	[
		packlabl(i+1, l)
		for i,l in enumerate(ilabels)
	]
)

# JUNK-out old chunks, append new, update RIFF chunk size

if dopatch:
	raw_input("hit enter to continue")

	# just overwrite outdated chunks
	tokill = tree.getchunks('cue ', ('LIST', 'adtl'), ('list', 'adtl'))
	for chunk in tokill:
		fp.seek(chunk.start)
		fp.write(packchunk("JUNK", (chunk.length - 8) * '\x00'))

	fp.seek(4)
	(oldlen,) = struct.unpack("I", fp.read(4))
	fp.seek(0, os.SEEK_END)
	assert oldlen == fp.tell() - 8

	fp.write(cuechunk)
	fp.write(adtlchunk)
	newlen = fp.tell()
	fp.seek(4)
	fp.write(struct.pack("I", newlen - 8))

# TODO
#	* open as r+ for patching
#	* chunk += "modified" flag, set/reset
#	* riff chunk un/serializable (write back if modified)
#	* UI
#		* show markers in file
#		* imported markers
#		* synchronize (give equal times -> offset)
#		* merge markers, |ta-tb| < dt = 0.01s ?

#	* re-layouting for chunks that grew or shrank: move chunk if needed (read+write), insert JUNK
#		* fixed and moving chunks -> if it's rewritten anyway, move freely
