from __future__ import division

import os
import sys
import cv2
import numpy
import json
import re
import glob
import pprint; pp = pprint.pprint

def waitKeys():
	while True:
		key = cv2.waitKey(1)
		
		if key == -1: break
		
		yield key

def read_plaintext(fname):
	rex = re.compile(r'([0-9]+)\.([0-9]+): (\d+)')
	# peculiarity in Walter Unger's script
	# "0.90" is 0.090, not 0.900

	res = {}
	
	for line in open(fname):
		m = rex.match(line)
		assert m
		(secs, msecs, slide) = m.groups()
		time = int(secs) + int(msecs) * 0.001

		assert all(k <= time for k in res)
		res[time] = int(slide)
	
	return res

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
		im = cv2.resize(im, self.framesize, interpolation=cv2.INTER_AREA)
		if im.min() != 0 or im.max() != 255:
			print "WARNING:", "black", im.min(), "white", im.max(), "in [%d]" % index, repr(fname)
			self.warn_colorspace.add(fname)
		return im
	
	def at(self, key):
		return key == self.cur_index

	def __getitem__(self, key):
		if key != self.cur_index:
			self.cur_index = key
			self.cur_slide = self._load(key)
			
		return self.cur_slide
	

class MarkerList(object):
	def __init__(self, markers):
		self.markers = markers
	
	def __getitem__(self, timeindex):
		candidates = [(t,k) for (t,k) in self.markers.iteritems() if t < timeindex]
		candidates.sort()
		if not candidates:
			return None
			
		return candidates[-1]
	
	def __len__(self):
		return len(self.markers)
	
	def values(self):
		return self.markers.values()
	
	def keys(self):
		return self.markers.keys()
	

fourcc = cv2.cv.FOURCC(*"MJPG")
fourcc = -1
#fourcc = cv2.cv.FOURCC(*"TSCC")
fps = 25
#duration = 5400.0
duration = 0.0
minlastslide = 300.0
#framesize = (1024,768)
#framesize = (1280,960)

# collecting parameters

fvideo = sys.argv[1]

framesize = tuple(map(int, sys.argv[2].split('x')))
(framew,frameh) = framesize

fmarkers = sys.argv[3]
markerlist = MarkerList(read_plaintext(fmarkers))

slides = []
for x in sys.argv[4:]:
	slides += glob.glob(x)
assert len(slides) > 0
assert slides == sorted(slides)
print "#slides:", len(slides)
cache = SlideCache(framesize, slides)

assert all(index-1 in cache for index in markerlist.values()), [index for index in markerlist.values() if index-1 not in cache]

print "markers:", min(markerlist.values()), '..', max(markerlist.values())

# init
duration = max(duration, max(markerlist.markers) + minlastslide)
print "duration: %d markers, %.3f secs" % (len(markerlist), duration)

assert not os.path.exists(fvideo)
vid = cv2.VideoWriter(fvideo, fourcc, fps, framesize)
assert vid.isOpened()
blackframe = numpy.zeros((frameh, framew, 3), numpy.uint8)

fstart = 0
#fstart = int(4500 * fps)
fend   = int(duration * fps)

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
		
		if do_update:
			cv2.imshow("display", im)
			
		if fno % fps == 0:
			sys.stdout.write("\r%5.1f%% @ %.2f secs..." % (100 * now / duration, now))
			sys.stdout.flush()

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
	os.unlink(fvideo)
	
	raise

finally:
	cv2.destroyWindow("display")
	vid.release()
	
