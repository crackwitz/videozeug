#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import os
import sys
import json
import fractions
import re
import pprint; pp = pprint.pprint

# ----------------------------------------------------------------------
# https://www.ffmpeg.org/ffmpeg-formats.html#Metadata-1

def iround(x):
	return int(round(x))

def write_ffdata(chapters, outfile=sys.stdout):
	def escape_data(s):
		return re.sub(r'([\;#=])', (lambda m: "\\" + m.group(1)), s)

	timebase = fractions.Fraction(1, 1000)
	print >> outfile, ";FFMETADATA1"
	print >> outfile

	for chapter in chapters:
		print >> outfile, "[CHAPTER]"
		print >> outfile, "TIMEBASE=%d/%d" % (timebase.numerator, timebase.denominator)
		print >> outfile, "START=%d" % iround(chapter['start'] / timebase)
		print >> outfile, "END=%d" % iround((chapter['start']+chapter['duration']) / timebase)
		print >> outfile, "title=%s" % escape_data(chapter['name'].encode('utf8'))
		print >> outfile

def hmsformat(seconds, decimals=0):
	hours, seconds = divmod(seconds, 3600)
	minutes, seconds = divmod(seconds, 60)
	return "%d:%02d:%0*.*f" % (hours, minutes, 2+decimals+(decimals>0), decimals, seconds)

def write_jumplist(chapters, outfile=sys.stdout):
	for chapter in chapters:
		print >> outfile, "%s %s" % (hmsformat(chapter['start']), chapter['name'].encode('utf8'))

def dictmerge(d1, d2):
	res = d1.copy()
	for k in d2:
		res[k] = d2[k]
	return res

def write_webvtt(chapters, outfile=sys.stdout):
	print >> outfile, "WEBVTT"
	print >> outfile

	for chapter in chapters:
		# cue identifier is optional
		print >> outfile, "%s --> %s" % (
			hmsformat(chapter['start'], decimals=3),
			hmsformat(chapter['start'] + chapter['duration'], decimals=3),
		)
		if ('name' in chapter) and (chapter['name'] is not None):
			print >> outfile, chapter['name'].encode("utf-8")
		else:
			print >> outfile, "(no title)"

		print >> outfile

def chapters_fix(xmpdata):
	chapters = xmpdata.get('chapters', [])

	starts = [c['start'] for c in chapters] + [xmpdata['duration']]

	chapters = [
		dictmerge(c, {'duration': end - c['start']})
		for c,end in zip(chapters, starts[1:])
	]

	return chapters

# ----------------------------------------------------------------------

if __name__ == '__main__':
	if len(sys.argv) != 4:
		print "Takes XMP marker data in JSON and outputs human-readable data or suitable for ffmpeg"
		print
		print "Usage: ffmeta.py [ffmeta|jumplist|webvtt] <infile> <outfile>"
		print "       infile and outfile may be '-' for stdin and stdout respectively"
		print
		print "Usage in avconv and ffmpeg:"
		print "       avconv -i video.mp4 -i metafile -map_metadata 1 -c copy video-and-markers.mp4"

		sys.exit(0)

	# input
	(outtype, xmpdata, outfile) = sys.argv[1:]

	xmpdata = sys.stdin if (xmpdata == '-') else open(xmpdata)
	outfile = sys.stdout if (outfile == '-') else open(outfile, 'w')

	xmpdata = json.load(xmpdata)

	# fix chapter lengths
	chapters = chapters_fix(xmpdata)

	# output
	if outtype in ['ffmeta', 'ffmetadata']:
		write_ffdata(chapters, outfile)
	elif outtype == 'jumplist':
		write_jumplist(chapters, outfile)
	elif outtype == 'webvtt':
		write_webvtt(chapters, outfile)
	else:
		assert False, "%s is not an output format. try 'ffmeta' or 'jumplist'" % repr(outtype)

