#!/usr/bin/env python

import os
import sys
import struct
import re

from filetools import Buffer, FileBuffer

(selector, fname) = sys.argv[1:]

steps = [step for step in selector.split('/') if step]

buf = FileBuffer(fname)

for step in steps:
	if step[0] in "+": # move back/forth
		offset = int(step)
		buf = buf[offset:]
		continue

	m = re.match(r'(\w+)(?:\[(\d+)\])?$', step)
	assert m
	(scode,spos) = m.groups()
	assert len(scode) <= 4, "implausible code requested"
	spos = int(spos) if (spos is not None) else 0

	# walk atoms
	start = stop = 0
	while stop < len(buf):
		start = stop
		(alen,acode) = struct.unpack(">I4s", buf[start:start+8].str())
		contentoffset = 8
		if alen == 1:
			contentoffset = 16
			(alen,) = struct.unpack(">Q", buf[start+8:start+16].str())

		stop = start + alen
		if acode != scode: continue

		content = buf[start+contentoffset : stop]

		if spos == 0:
			buf = content
			break
		else:
			spos -= 1

sys.stdout.write(buf.str())
