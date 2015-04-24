#!/usr/bin/env python2.7

import os
import sys
import shutil
import re
import pprint; pp = pprint.pprint

from filetools import Buffer, FileBuffer, BufferReader

__all__ = 'select dump match'.split()

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
		(boxlen, boxcode) = buf[p:][">I4s"]
		contentoffset = 8
		
		# 64-bit atom sizes
		if boxlen == 1:
			boxlen = buf[p+8:][">Q"]
			contentoffset = 16

		if boxlen == 0: # extends to end of file
			boxlen = len(buf) - p

		box = buf[p+contentoffset : p+boxlen]
		
		yield boxcode, box
		
		p += boxlen

def select(selector, buf):
	if isinstance(selector, list):
		steps = list(selector)
	else:
		steps = [step for step in re.split('[/.]', selector) if step]
	
	if len(steps) == 0:
		yield buf
		return

	step = steps.pop(0)

	# move forwards
	if step[0] in "+":
		offset = int(step)
		buf = buf[offset:]
		
		for box in select(steps, buf):
			yield box
		
		return

	# filter for something
	m = crumbrex.match(step)
	assert m
	scode = m.group('code')
	spos = m.group('index')
	prefix = m.group('prefix')

	assert len(scode) <= 4, "implausible code requested"
	spos = int(spos) if (spos is not None) else None
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

		if (spos is not None):
			if spos == 0:
				found = True
				for box in select(steps, content):
					yield box
				break
			else:
				spos -= 1
		else:
			for box in select(steps, content):
				yield box

	if spos is not None:
		assert found, "atoms exhausted; no match found"

def dump(buf, outfile):
	try:
		shutil.copyfileobj(BufferReader(buf), outfile)
	except IOError, e:
		pass # probably just closed the pipe early

def match(selector, buf):
	for box in select(selector, buf):
		return True
	else:
		return False

# ----------------------------------------------------------------------

if __name__ == '__main__':
	domatch = False
	dodump = None
	
	args = []
	for arg in sys.argv[1:]:
		if arg.startswith('-'):
			if arg == '-m':
				domatch = True
			if arg == '-d':
				dodump = True
		else:
			args.append(arg)

	if (dodump is None) and domatch:
		dodump = False

	(selector, fname) = args

	filebuf = FileBuffer(fname)
	
	if dodump:
		for box in select(selector, filebuf):
			dump(box, sys.stdout)

	if domatch:
		matched = match(selector, filebuf)
		sys.exit(0 if matched else 1)
