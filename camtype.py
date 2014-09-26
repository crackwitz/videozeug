#!/usr/bin/env python
from __future__ import division
from pystartup import *
import os
import re

# NOTICE: also used by mp2tcheck.py

# TODO: aufbohren, soll auch in dateien lesen

# ======================================================================
# file scoring

size_classes = [ # (lower, upper), any order
	( 650   * 192 * 2**14,  651   * 192 * 2**14), # canon hg20
	( 675   * 192 * 2**14,  676   * 192 * 2**14), # sony xr550
	(1361.0 * 192 * 2**14, 1362.5 * 192 * 2**14), # panasonic HC-V707
	(1362.5 * 192 * 2**14, 1364.0 * 192 * 2**14), # panasonic HDC-SD800
	# sony pj780 hat magic bytes / signaturen am anfang der datei
]

def get_size_class(size):
	for i,(u,v) in enumerate(size_classes):
		if u <= size < v:
			return i

	return None

mod_classes = [ # ascending
	192 * 32, # canon, panasonic
	192 * 512, # sony
]

def get_mod_class(size):
	# get largest class
	# wrong categorization by chance (larger class), p = 2**(5-9)
	
	candidates = [i for i,c in enumerate(mod_classes) if size % c == 0]
	if candidates:
		return max(candidates)
	else:
		return None

# ----------------------------------------------------------------------

signatures = {
	"Sony XR550": re.compile(".{,2000}HDR-.XR55.0VE", re.DOTALL),
	"Sony PJ780": re.compile(".{,2000}HDR-.PJ78.0VE", re.DOTALL),
	"Sony HDR-CX200E": re.compile(".{,2000}HDR-.CX20.0E", re.DOTALL),
	"Sony HDR-PJ330E": re.compile(".{,2000}HDR-.PJ33.0E", re.DOTALL),
}

cam_classes = { # (size, mod)
	(0,0): "Canon HG20",
#	(1,1): "Sony XR550",
	(2,0): "Panasonic HC-V707",
	(3,0): "Panasonic HDC-SD800",
#	(-1,-1): "Sony PJ780",
}

# ======================================================================
# bundle scoring

def valuemax(d):
	return max(d, key=(lambda k: (d[k], k)))

def scoredmax(d):
	n = sum(d[k] for k in d if k is not None)

	if d.get(None,0) > n:
		return None

	res = valuemax(d)

	if (d < n) and (n//2 + d[res] <= n): # "half" with rounding error
		return None
	else:
		return res

def score_bundle(bundle):
	size_class = histo(map(get_size_class, bundle))
	mod_class = histo(map(get_mod_class, bundle))

	if 0:
		print sorted(bundle)
		pp(size_class)
		pp(mod_class)
		print

	size_class = scoredmax(size_class)
	mod_class  = scoredmax(mod_class)

	return (size_class, mod_class)

def get_type(fpath):
	fsize = os.path.getsize(fpath)
	score = score_bundle([fsize])
	match = cam_classes.get(score, "<no match>")

	fhead = open(fpath, 'rb').read(4096)
	
	for cam in signatures:
		if signatures[cam].match(fhead):
			match = cam
			break
	
	return match

# ======================================================================
# main

if __name__ == '__main__':
	# build bundle
	files = []
	for arg in sys.argv[1:] or ['.']:
		if os.path.isdir(arg):
			files += [os.path.join(arg, f) for f in os.listdir(arg) if f.endswith(".MTS")]
		elif os.path.isfile(arg):
			assert arg.endswith('.MTS')
			files.append(arg)
		else:
			# try globbing
			files += glob.glob(arg)
	
	files.sort()

	if not files:
		print "<no files given>"
	else:
		for f in files:
			match = get_type(f)
			
			print "%-19s : %s" % (match, f)
