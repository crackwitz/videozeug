#!/usr/bin/env python
from __future__ import division
import os
import sys
import glob
import re
import time
import math
import pprint; pp = pprint.pprint
import subprocess

blocksize = 2**23

formats = {
	'mp4': ".mp4",
	'mpegts': ".m2ts"
}

format = 'mpegts'

prefix = "video"
use_tempfile = False

def natsortkey(x):
	convert = lambda v: int(v, 10) if v.isdigit() else v
	return map(convert, re.split(r'(\d+)', x))

def unix2wintime(unixtime):
	filetime = (unixtime * 10000000) + 116444736000000000
	return int(filetime)

def alleq(s):
	try:
		v = s.next()
	except StopIteration:
		return True

	for x in s:
		if x != v:
			return False
	return True

def backstep(s):
	return s + "\b" * len(s)

def cat(srcnames, dest):
	written = 0
	total = sum(map(os.path.getsize, srcnames))
	
	for srcname in srcnames:
		#print ": ", srcname,
		src = open(srcname, 'rb')
		try:
			while True:
				data = src.read(blocksize)
				if not data: break
				dest.write(data)
				written += len(data)

				sys.stdout.write("\r%6.2f%%, %.2f GB (%s) " % (
					100.0 * written / total,
					written / 1e9,
					os.path.basename(srcname)
				))
				sys.stdout.flush()
		
		finally:
			src.close()

	print
	
try:

	infiles = []
	i = 1
	while i < len(sys.argv):
		item = sys.argv[i]

		if item.startswith('-'):
			if item == '-f':
				i += 1
				format = sys.argv[i]
				assert format in formats
			elif item == '--prefix':
				i += 1
				prefix = sys.argv[i]
			elif item == '--use-temp':
				use_tempfile = True
			elif item == '--no-temp':
				use_tempfile = False
		else:
			infiles += glob.glob(item)

		i += 1

	rex = re.compile(r'^(.*?)(-\d{1,2})?\.MTS$')
	bunches = {}
	for f in infiles:
		(u,v) = rex.match(f).groups()
		if u not in bunches: bunches[u] = []
		bunches[u].append(f)

	if len(bunches) >= 2 and all(len(bunches[b]) == 1 for b in bunches):
		bunches = {
			os.path.join(os.path.dirname(infiles[0]), prefix):
				[bunches[b][0] for b in sorted(bunches)]
		}

	for key in sorted(bunches, key=natsortkey):
		# -f format
		outfile = key + formats[format]

		bunch = bunches[key]
		bunch.sort(key=natsortkey)
		totalsize = sum(map(os.path.getsize, bunch))

		pp(bunch)

		print "=>", outfile, "(%.2f GB)" % (totalsize / 1e9)

		if use_tempfile:
			tempfile = outfile + ".MTS"
			assert not os.path.exists(tempfile), "tempfile already exists! " + tempfile

			ftmp = open(tempfile, 'wb')
			try:
				cat(bunch, ftmp)
				ftmp.close()
			except:
				ftmp.close()
				os.unlink(tempfile)
				raise

			try:
				p = subprocess.Popen(
					["ffmpeg", "-y", "-i", tempfile, "-c", "copy",
					"-f", format,
					 outfile])
				# shell=True assumes that cmd[0] need not be searched for in PATH

				rv = p.wait()
			finally:
				if rv == 0:
					os.unlink(tempfile)
				else:
					print "temp file not removed; ffmpeg returned", rv

		elif 1:
			p = subprocess.Popen(
				["ffmpeg", "-y", "-i", "concat:{0}".format("|".join(bunch)), "-c", "copy", "-f", format, outfile])

			rv = p.wait()

		elif 0:
			p = subprocess.Popen(
				["ffmpeg", "-y", "-i", "pipe:0", "-c", "copy", "-f", format, outfile],
				#shell=True,
				stdin=subprocess.PIPE)

			cat(bunch, p.stdin)

			p.stdin.close()
			rv = p.wait()

		print "returned", rv

		if rv == 0:

			ctime = os.path.getctime(bunch[0])
			mtime = os.path.getmtime(bunch[-1])
			if os.name in ('nt',):
				import win32file
				try:
					fhandle = win32file.CreateFile(outfile, win32file.FILE_GENERIC_WRITE, 0, None, win32file.OPEN_ALWAYS, 0, None)
				except:
					print "error opening file", outfile
					raise
				win32file.SetFileTime(fhandle, ctime, None, mtime)
				win32file.CloseHandle(fhandle)
			else:
				os.utime(outfile, (mtime, mtime))

		print

except Exception, e:
	print e
	
finally:
	if os.name in ('nt',):
		pass
		#raw_input()
		
