#!/usr/bin/env python2.7

import os
import sys
import struct
import shutil
import re

from filetools import Buffer, FileBuffer, BufferReader

(selector, fname) = sys.argv[1:]

steps = [step for step in selector.split('/') if step]

buf = FileBuffer(fname)

crumbrex = re.compile(r'''
	(?P<code>\w+?)
	(?:(?P<prefix>[:$]\w+))?
	(?:\[(?P<index>\d+)\])?
	$
''', re.VERBOSE)

for step in steps:
	if step[0] in "+": # move back/forth
		offset = int(step)
		buf = buf[offset:]
		continue

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
	start = stop = 0
	found = False
	while stop < len(buf):
		start = stop
		(alen,acode) = struct.unpack(">I4s", buf[start:start+8].str())
		contentoffset = 8

		# 64-bit atom sizes
		if alen == 1:
			contentoffset = 16
			(alen,) = struct.unpack(">Q", buf[start+8:start+16].str())

		stop = start + alen
		if acode != scode: continue

		content = buf[start+contentoffset : stop]

		if prefix and (content[:len(prefix)].str() != prefix):
			continue

		if spos == 0:
			found = True
			buf = content
			break
		else:
			spos -= 1

	assert found, "atoms exhausted; no match found"

try:
	shutil.copyfileobj(BufferReader(buf), sys.stdout)
except IOError, e:
	pass # probably just closed the pipe early
