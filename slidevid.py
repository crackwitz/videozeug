#!/usr/bin/env python2.7
from __future__ import division

import os
import sys
import cv2
import numpy as np; np.set_printoptions(suppress=True)
import json
import re
import glob
import pprint; pp = pprint.pprint

import quaxlist

def waitKeys():
	while True:
		key = cv2.waitKeyEx(1)
		
		if key == -1: break
		
		yield key

class SlideCache(object):
	def __init__(self, framesize, filenames):
		self.framesize = framesize
		self.filenames = filenames

		self.cur_index = None
		self.cur_slide = None
		
		self.warn_colorspace = set()
	
	def __contains__(self, key):
		return 0 <= key < len(self.filenames)
	
	def _load(self, index):
		fname = self.filenames[index]
		#print "\nloading [%s] %s" % (index, repr(fname))
		im = cv2.imread(fname)
		imh,imw = im.shape[:2]

		# checking black/white present
		if im.min() != 0 or im.max() != 255:
			print "WARNING:", "black", im.min(), "white", im.max(), "in [%d]" % index, repr(fname)
			self.warn_colorspace.add(fname)

		# maintaining aspect ratio
		(framew,frameh) = self.framesize
		
		scale = min(framew/imw, frameh/imh)
		scaled = cv2.resize(src=im, dsize=(0,0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
		sh,sw = scaled.shape[:2]

		assert sw <= framew
		assert sh <= frameh

		if sw < framew or sh < frameh:
			offx = int(round(framew/2 - sw/2))
			offy = int(round(frameh/2 - sh/2))
			imout = np.zeros((frameh,framew,3), dtype=np.uint8)
			imout[offy:offy+sh, offx:offx+sw] = scaled
		else:
			imout = scaled

		return imout
	
	def at(self, key):
		return key == self.cur_index

	def __getitem__(self, key):
		if key != self.cur_index:
			self.cur_index = key
			self.cur_slide = self._load(key)
			
		return self.cur_slide
	

class MarkerList(object):
	def __init__(self, markers):
		assert markers == sorted(markers)
		self.markers = np.array(markers, dtype=[('time', 'f8'), ('slide', 'i4')])

	def __getitem__(self, timeindex):
		if isinstance(timeindex, slice):
			return self.markers[timeindex]

		offset = np.searchsorted(self.markers['time'], timeindex)

		if offset < len(self.markers) and timeindex == self.markers[offset]['time']:
			offset += 1

		if offset == 0:
			return None
		else:
			return self.markers[offset-1]
	
	def __len__(self):
		return len(self.markers)
	
	def values(self):
		return [v for u,v in self.markers]
	
	def keys(self):
		return [u for u,v in self.markers]


if __name__ == '__main__':
	# INIT
	
	fvideo = None
	novid = False
	fmarkers = None
	ftitles = None
	fgslides = [] # list of glob patterns

	headless = False
	fourcc = cv2.VideoWriter_fourcc(*"MJPG")
	fourcc = -1
	fourcc = cv2.VideoWriter_fourcc(*"LAGS")
	#fourcc = cv2.cv.FOURCC(*"TSCC")
	fps = 25
	minlastslide = 300.0
	#framesize = (1024,768)
	framesize = (1280,960)
	#framesize = (1920, 1080)

	# all unrecognized stuff	
	args = []

	# COLLECTING PARAMETERS

	i = 1
	while i < len(sys.argv):
		arg = sys.argv[i]
		
		if not arg.startswith('-'):
			args.append(arg)
		
		elif arg == '-vid':
			i += 1
			fvideo = sys.argv[i]
		
		elif arg == '-novid':
			novid = True
		
		elif arg == '-markers':
			i += 1
			fmarkers = sys.argv[i]
		
		elif arg == '-slides':
			i += 1
			fgslides.append(sys.argv[i])
		
		elif arg == '-titles':
			i += 1
			ftitles = sys.argv[i]
		
		elif arg == '-headless':
			headless = True

		elif arg == '-fourcc':
			i += 1
			fourcc = sys.argv[i]
			if fourcc == '-1':
				fourcc = -1
			else:
				assert len(fourcc) == 4
				fourcc = cv2.VideoWriter_fourcc(*fourcc)
		
		elif arg == '-fps':
			i += 1
			fps = float(sys.argv[i])
		
		elif arg == '-overtime':
			i += 1
			minlastslide = float(sys.argv[i])

		elif arg == '-wh':
			framesize = int(sys.argv[i+1]), int(sys.argv[i+2])
			i += 2

		i += 1


	#assert fvideo is not None, "expecting -vid"
	assert fmarkers is not None, "expecting -markers"

	(framew,frameh) = framesize

	# SLIDE TRANSITIONS
	markerlist = MarkerList(quaxlist.read_file(open(fmarkers)))
	print "markers:", min(markerlist.values()), '..', max(markerlist.values())

	duration = max(markerlist.keys()) + minlastslide
	print "duration: %d markers, %.3f secs" % (len(markerlist), duration)

	# COLLECT SLIDES (PICTURES)
	slides = []
	for x in fgslides:
		slides += glob.glob(x)
	if len(slides) == 0:
		print >> sys.stdout, "WARNING: expecting -slides <glob>"
	assert slides == sorted(slides)
	print "#slides:", len(slides)
	cache = SlideCache(framesize, slides)

	assert all(index-1 in cache for index in markerlist.values()), [index for index in markerlist.values() if index-1 not in cache]
	
	# DUMP CHAPTER MARKERS, IF AVAILABLE
	if ftitles is not None:
		titles = json.load(open(ftitles))
		titles = {int(k) : v for k,v in titles.iteritems()}
		
		chapters = []
		prevchapter = None # slideno
		for t,slideno in markerlist.markers:
			if slideno == prevchapter:
				continue
			if slideno not in titles:
				continue
			chapters.append({
				'name': titles[slideno],
				'start': t,
				'slide': slideno,
			})
			prevchapter = slideno
		
		data = {
			'chapters': chapters,
			'duration': duration,
		}
		
		fchapters = "{0}-chapters.json".format(os.path.splitext(fvideo)[0])
		assert not os.path.exists(fchapters), "file exists: {0}".format(fchapters)
		json.dump(data, open(fchapters, 'w'), sort_keys=True, indent=1)
		print "dumped chapter markers to", fchapters

	# BUILDING VIDEO
	if (fvideo is not None) and (not novid):
		assert not os.path.exists(fvideo)
		vid = cv2.VideoWriter(fvideo, fourcc, fps, framesize)
		assert vid.isOpened()
		blackframe = np.zeros((frameh, framew, 3), np.uint8)

		fstart = 0
		#fstart = int(4500 * fps)
		fend   = int(duration * fps)

		if not headless:
			cv2.namedWindow("display", cv2.WINDOW_NORMAL)
			cv2.resizeWindow("display", 800, 600)

		print

		try:
			aspect_warned = False

			for fno in xrange(fstart, fend):
				now = fno / fps

				lookup = markerlist[now]

				do_update = True

				if lookup is None:
					print "lookup failed for %.3f" % now
					im = blackframe
				else:
					(slidetime, slideno) = lookup
					do_update = not cache.at(slideno-1)
					im = cache[slideno-1]

				# check aspect ratio
				imh,imw = im.shape[:2]
				if (not aspect_warned) and abs((imw/imh) / (framew/frameh) - 1) > 1e-2:
					aspect_warned = True
					raw_input("aspect ratios don't match for slide %d: %d/%d=%.3f vs. %d/%d=%.3f" % (slideno, imw, imh, imw/imh, framew, frameh, framew/frameh))

				vid.write(im)

				if do_update and not headless:
					cv2.imshow("display", im)

				if fno % fps == 0:
					sys.stdout.write("\r%5.1f%% @ %.2f secs..." % (100 * now / duration, now))
					sys.stdout.flush()

					if not headless:
						keys = list(waitKeys())
						if 27 in keys:
							print "aborted"
							raise KeyboardInterrupt

						elif keys:
							print "waitkey ->", keys

			# fix for lagarith nullframes and playback.
			# this should force one last keyframe.
			vid.write(blackframe)

			print
			print "done"

			if cache.warn_colorspace:
				print "WARNING: colorspace possibly wrong in:"
				for fname in sorted(cache.warn_colorspace):
					print "    %s" % fname


		except:
			vid.release()
			#os.unlink(fvideo)

			raise

		finally:
			if not headless:
				cv2.destroyWindow("display")
			vid.release()

