#!/usr/bin/env python2.7
from __future__ import division

import os
import sys
import glob
import subprocess
import re
import collections
import socket # gethostname
import json
from itertools import *
import pprint; pp = pprint.pprint

# this shit needs astats, which didn't exist in 2013
if socket.gethostname() == 'video-main':
	ffmpeg = '/home/crackwitz/portalhome/.local/bin/ffmpeg'
	ffprobe = '/home/crackwitz/portalhome/.local/bin/ffprobe'
else:
	ffmpeg = 'ffmpeg'
	ffprobe = 'ffprobe'

def common_prefix(strings):
	def sub(a, b):
		diff = [i for i,(u,v) in enumerate(zip(a,b)) if u != v]
		return a[:min(diff)]

	return reduce(sub, strings)

def get_stream_counts(fname):
	output = subprocess.check_output([ffprobe, fname, '-of', 'json', '-show_streams'])
	
	data = json.loads(output)
	
	streams = data['streams']
	
	return (
		sum(s['codec_type'] == 'audio' for s in streams),
		sum(s['codec_type'] == 'video' for s in streams),
	)
	

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

def transcode(inputs, output, dar, gain=0):
	assert os.path.splitext(output)[1] in ('.m4a', '.mp4', '.mov'), "output file extension not what I expected"
	
	command = [ffmpeg, '-async', '1']
	
	for i in inputs: command += ['-i', i]
	
	# assuming 1 video and 1 audio stream per file
	n = len(inputs)
	na = 1
	nv = 1
	# defaults
	
	# detect stream counts
	streamcounts = map(get_stream_counts, inputs)
	nas, nvs = zip(*streamcounts)
	assert len(set(nas)) == 1, ('audio stream counts differ:', nas)
	assert len(set(nvs)) == 1, ('video stream counts differ:', nvs)
	na = nas[0]
	nv = nvs[0]

	chains = []

	if nv > 0:
		chains += [
			'[{0}:v] setdar=dar={1}/{2} [{0}aspect]'.format(i, dar[0], dar[1])
			for i in xrange(len(inputs))
		]
	
	chains.append(
		# inputs
		' '.join(''.join(["[{0}aspect]".format(i)] * (nv > 0) + ["[{0}:a] ".format(i)] * (na > 0)) for i,inp in enumerate(inputs)) +
		# body
		'concat=n={n}:v={nv}:a={na}'.format(n=n, na=na, nv=nv) +
		# outputs
		' [vj]' * (nv > 0) +
		' [aj]' * (na > 0)
	)
	
	if na > 0:
		chains.append(
			'[aj] volume=volume={0:+f}dB [ag]'.format(gain)
		)
	
	command += ['-filter_complex', '; '.join(chains)]
	
	if nv > 0: command += ['-map', '[vj]']
	if na > 0: command += ['-map', '[ag]']
	
	if na > 0:
		command += ['-c:a', 'libvo_aacenc', '-b:a', '64k']
	if nv > 0:
		command += ['-c:v', 'libx264', '-profile:v', 'main', '-crf', '20', '-g', '125']
		command += ['-aspect:v', '{0}:{1}'.format(dar[0], dar[1])]
	
	command += ['-movflags', 'faststart']
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
	settings = {
		'target': [-9.0,   lambda s: float(s)],
		'dar':    [(4,3),  lambda s: tuple(map(int, s.split(':')))],
		'in':     [None,   lambda s: s],
		'out':    [None,   lambda s: s],
		'skip':   [None,   lambda s: eval(s)],
	}
	
	while sys.argv[1:] and '=' in sys.argv[1]:
		arg = sys.argv.pop(1)
		(k,v) = arg.split('=', 1)
		assert k in settings
		settings[k][0] = settings[k][1](v)
	
	assert settings['in'][0] is not None
	assert settings['out'][0] is not None

	infiles = []
	for arg in sys.argv[1:]:
		infiles += glob.glob(arg) or [arg]

	groups = group_files(settings['in'][0], settings['out'][0], infiles)
	
	print json.dumps({key: map(os.path.basename, groups[key]) for key in groups}, indent=1, sort_keys=True)
	
	if raw_input("proceed? ").strip() not in ('y', ''):
		sys.exit(-1)
	
	for outfile in sorted(groups):
		print

		if os.path.exists(outfile):
			if settings['skip'][0] is None:
				print "<- {0}".format(outfile)
				if raw_input("file exists. skip? (y/n) ") in ("", 'y'):
					continue
			elif settings['skip'][0]:
				continue
			elif not settings['skip'][0]:
				pass

		infiles = groups[outfile]

		peaks = []
		for f in infiles:
			peak = get_rms_peak(f)
			peaks.append(peak)
			print "-> {0}, peak {1:+.3f} dB".format(f, peak)

		peak = max(peaks)
		print "<- {0} peak, {1:+.3f} dB".format(outfile, peak)

		gain  = settings['target'][0] - peak
		if gain <= 0: gain = 0
		print "   gain {1:+.3f} dB".format(peak, gain)
		
		rv = transcode(infiles, outfile, gain=gain, dar=settings['dar'][0])
		assert rv == 0
		
	print json.dumps({key: map(os.path.basename, groups[key]) for key in groups}, indent=1, sort_keys=True)
	
# sinf-transcode.py -9.0 'source/2003-SS-CG1.([VU]\d+)([ab]?).20(\d{2})-(\d{2})-(\d{2}).rmvb' '03ss-cg1-{3}{4}{5}-{1}-sd.mp4' source/*.rmvb
