#!/usr/bin/env python2

import os
import sys
import re
import glob
from subprocess import call, Popen, PIPE

import json
import mp4select
import xmpmarkers
import ffmeta

files = []
for x in sys.argv[1:]:
	files += glob.glob(x) or ([x] if os.path.exists(x) else [])

#import pdb; pdb.set_trace()

base = None
for vid in files:
	m = re.match(r'(.*)[_-]\d+p[_-]ame?\.mp4$', vid)
	if not m: continue
	base = m.group(1)

if base is None:
	base = re.sub(r'(.*)-ame\.mp4$', r'\1', files[0])

jsonfile = base + "-chapters.json"
ffmetafile = base + "-chapters.ffmeta"
vtt = base + "-chapters.vtt"
jumplist = base + "-chapters.txt"

videobuf = mp4select.FileBuffer(vid)
chunks = list(mp4select.select("uuid/+16", videobuf))
if len(chunks) == 0:
	sys.exit(-1)

(xmpchunk,) = chunks
xmpdata = xmpmarkers.extract(xmpchunk)

chapters = ffmeta.chapters_fix(xmpdata)

json.dump(obj=xmpdata, fp=open(jsonfile, 'w'), sort_keys=True, indent=1)
ffmeta.write_ffdata(chapters, open(ffmetafile, 'w'))
ffmeta.write_webvtt(chapters, open(vtt, 'w'))
ffmeta.write_jumplist(chapters, open(jumplist, 'w'))

for invid in files:
	outvid = invid.replace('-ame', '')
	assert not os.path.exists(outvid)
	call(['ffmpeg', '-i', invid, '-i', ffmetafile, '-c', 'copy', '-movflags', 'faststart', outvid])
