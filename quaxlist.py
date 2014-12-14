#!/usr/bin/env python2
from __future__ import division
import os
import sys
import re

linerex = re.compile(r'([0-9]+)\.([0-9]+): (\d+)')

def parse_line(line):
	m = linerex.match(line)
	assert m
	(secs, msecs, slide) = m.groups()
	
	slide = int(slide)

	# peculiarity in Walter Unger's script
	# "0.90" is 0.090, not 0.900
	time = int(secs) + int(msecs) * 0.001

	return (time, slide)

def pairs(s):
	s = list(s)
	return zip(s[:-1], s[1:])

def read_file(fileobj):
	lines = map(parse_line, fileobj)

	times = [u for u,v in lines]
	assert all(t1 < t2 for t1,t2 in pairs(times))
	
	return lines


if __name__ == '__main__':
	import json
	
	inf = sys.stdin
	outf = sys.stdout
	
	if len(sys.argv) >= 2 and sys.argv[1] != '-':
		inf = open(sys.argv[1])
	
	if len(sys.argv) >= 3 and sys.argv[2] != '-':
		outf = open(sys.argv[2])
	
	markers = read_file(inf)
	
	data = {
		'duration': max(u for u,v in markers) + 300,
		'chapters': [
			{
				'name': "Slide {0}".format(slideno),
				'start': t,
			}
			for t,slideno in markers
		]
	}
	
	json.dump(data, outf, sort_keys=True, indent=1)
