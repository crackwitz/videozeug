#!/usr/bin/env python2.7
from __future__ import division

import os
import sys
import glob
import subprocess
import re
import collections
import socket
from itertools import *
import pprint; pp = pprint.pprint

# this shit needs astats, which didn't exist in 2013
if socket.gethostname() == 'video-main':
	ffmpeg = '/home/crackwitz/portalhome/.local/bin/ffmpeg'
else:
	ffmpeg = 'ffmpeg'

def common_prefix(strings):
	def sub(a, b):
		diff = [i for i,(u,v) in enumerate(zip(a,b)) if u != v]
		return a[:min(diff)]

	return reduce(sub, strings)

def get_astats(fname):
	output = subprocess.check_output([ffmpeg, '-i', fname, '-filter:a', 'astats', '-vn', '-f', 'null', 'dummy'], stderr=subprocess.STDOUT)

	lines = (line.rstrip() for line in output.split('\n') if 'Parsed_astats_0' in line)
	
	lines = dropwhile(lambda line: "Overall" not in line, lines)
	
	lines = (re.match(r'\[[^]]*\] ([^:]+): (.*)$', line) for line in lines)
	
	lines = (line.groups() for line in lines if line)
	
	return dict(lines)

def get_rms_peak(fname):
	astats = get_astats(fname)
	rmspeak = float(astats['RMS peak dB'])
	return rmspeak

def transcode(inputs, output, gain=0):
	command = [ffmpeg, '-async', '1']
	
	for i in inputs: command += ['-i', i]

	# assuming 1 video and 1 audio stream per file
	command += ['-filter_complex',
		' '.join("[{0}:v][{0}:a]".format(i) for i,inp in enumerate(inputs)) +
		'concat=n={0}:v=1:a=1'.format(len(inputs)) + ' [v][aj];' + 
		'[aj] volume=volume={0:+f}dB [a]'.format(gain)
	]
	command += ['-map', '[v]']
	command += ['-map', '[a]']
	
	command += ['-c:a', 'libvo_aacenc', '-b:a', '64k']
	command += ['-c:v', 'libx264', '-profile:v', 'main', '-crf', '20', '-g', '125']
	command += ['-aspect:v', '4:3', '-movflags', 'faststart']
	#command += ['-threads', '4']
	command += [output]
	
	print command
	rv = subprocess.call(command)

	return rv

def group_files(inpattern, outpattern, files):
	buckets = collections.defaultdict(lambda: [])

	for f in files:
		m = re.match(inpattern, f)
		assert m, (inpattern, f)
		groups = m.groups()
		outkey = outpattern.format(f, *groups)
		buckets[outkey].append(f)
	
	return dict(buckets)

if __name__ == '__main__':
	target = float(sys.argv[1])
	inpattern = sys.argv[2]
	outpattern = sys.argv[3]
	
	assert not os.path.exists(inpattern)
	assert not os.path.exists(outpattern)

	infiles = []
	for arg in sys.argv[4:]:
		infiles += glob.glob(arg) or [arg]

	groups = group_files(inpattern, outpattern, infiles)
	
	pp(groups)
	
	if raw_input("proceed? ").strip() not in ('y', ''):
		sys.exit(-1)
	
	for outfile in sorted(groups):
		print

		if os.path.exists(outfile):
			print "<- {0}".format(outfile)
			if raw_input("file exists. skip? (y/n) ") in ("", 'y'):
				continue

		infiles = groups[outfile]

		peaks = []
		for f in infiles:
			peak = get_rms_peak(f)
			peaks.append(peak)
			print "-> {0}, peak {1:+.3f} dB".format(f, peak)

		peak = max(peaks)
		print "<- {0} peak, {1:+.3f} dB".format(outfile, peak)

		gain  = target - peak
		if gain <= 0: gain = 0
		print "   gain {1:+.3f} dB".format(peak, gain)
		
		rv = transcode(infiles, outfile, gain=gain)
		assert rv == 0
		
# sinf-transcode.py -9.0 'source/2003-SS-CG1.([VU]\d+)([ab]?).20(\d{2})-(\d{2})-(\d{2}).rmvb' '03ss-cg1-{3}{4}{5}-{1}-sd.mp4' source/*.rmvb
