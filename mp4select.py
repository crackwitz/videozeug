#!/usr/bin/env python2.7

import os
import sys
import struct
import shutil
import re
import pprint; pp = pprint.pprint

from filetools import Buffer, FileBuffer, BufferReader

# ----------------------------------------------------------------------

containerboxes = ''.split()

uuidboxes = 'uuid DATA'.split()

crumbrex = re.compile(r'''
	(?P<code>\w+?)
	(?:(?P<prefix>[:$]\w+))?
	(?:\[(?P<index>\d+)\])?
	$
''', re.VERBOSE)

def walk_boxes(buf):
	p = 0
	while p < len(buf):
		(boxlen, boxcode) = struct.unpack(">I4s", buf[p:p+8].str())
		contentoffset = 8
		
		# 64-bit atom sizes
		if boxlen == 1:
			(boxlen,) = struct.unpack(">Q", buf[p+8:p+16].str())
			contentoffset = 16

		box = buf[p+contentoffset : p+boxlen]
		
		yield boxcode, box
		
		p += boxlen

def select(selector, buf):
	steps = [step for step in re.split('[/.]', selector) if step]
	
	for step in steps:
		# move forwards
		if step[0] in "+":
			offset = int(step)
			buf = buf[offset:]
			continue

		# filter for something
		m = crumbrex.match(step)
		assert m
		scode = m.group('code')
		spos = m.group('index')
		prefix = m.group('prefix')

		assert len(scode) <= 4, "implausible code requested"
		spos = int(spos) if (spos is not None) else 0
		if prefix:
			assert prefix[0] in ':$'
			if prefix[0] == '$': prefix = prefix[1:].decode('hex')
			elif prefix[0] == ':': prefix = prefix[1:]

		# walk atoms
		found = False
		for acode, content in walk_boxes(buf):
			if acode != scode:
				continue

			if prefix:
				if content[:len(prefix)].str() == prefix:
					pass
					#content = content[16:] # skip uuid
				else:
					continue
				

			if spos == 0:
				found = True
				buf = content
				break
			else:
				spos -= 1

		assert found, "atoms exhausted; no match found"

	return buf

def dump(buf, outfile):
	try:
		shutil.copyfileobj(BufferReader(buf), outfile)
	except IOError, e:
		pass # probably just closed the pipe early

# ----------------------------------------------------------------------

if __name__ == '__main__':
	(selector, fname) = sys.argv[1:]

	buf = FileBuffer(fname)

	buf = select(selector, buf)

	dump(buf, sys.stdout)
