#!/usr/bin/env python2

import os
import sys
import re
import glob
from subprocess import call, Popen, PIPE

files = []
for x in sys.argv[1:]:
	files += glob.glob(x) or [x]

#import pdb; pdb.set_trace()

base = None
for vid in files:
	m = re.match(r'(.*)-\d+p-ame?\.mp4$', vid)
	if not m: continue
	base = m.group(1)

if base is None:
	base = re.sub(r'(.*)-ame\.mp4$', r'\1', files[0])

json = base + "-chapters.json"
ffmeta = base + "-chapters.ffmeta"
vtt = base + "-chapters.vtt"
jumplist = base + "-chapters.txt"

mp4select = Popen(['mp4select.py', 'uuid/+16', vid], stdout=PIPE, shell=True)
xmpmarkers = Popen(['xmpmarkers.py', '-'], stdin=mp4select.stdout, stdout=open(json, 'w'), shell=True)
assert xmpmarkers.wait() == 0

call(['ffmeta.py', 'ffmeta', json, ffmeta], shell=True)

call(['ffmeta.py', 'webvtt', json, vtt], shell=True)

call(['ffmeta.py', 'jumplist', json, jumplist], shell=True)

for invid in files:
	outvid = invid.replace('-ame', '')
	assert not os.path.exists(outvid)
	call(['ffmpeg', '-i', invid, '-i', ffmeta, '-c', 'copy', '-movflags', 'faststart', outvid], shell=True)
