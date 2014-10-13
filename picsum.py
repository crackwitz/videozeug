#!/usr/bin/env python
from __future__ import division

import os
import sys
import glob
import numpy as np
import cv2
import pprint; pp = pprint.pprint

def pairs(s):
	return zip(s[:-1], s[1:])

gamma = 2.2

args = []
for x in sys.argv[1:]:
	args += glob.glob(x) or [x]

output = []

for fname in args:
	im = cv2.imread(fname, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_GRAYSCALE)
	(h,w) = im.shape[:2]
	ch = im.shape[2] if im.shape[2:] else 1
	
	iml = (np.float32(im)/255) ** gamma
	
	total = iml.sum() / (w*h*ch)
	
	print "%10.6f" % total, fname
	
	output.append({
		'file': fname,
		'sum': total
	})

lum = np.array([x['sum'] for x in output])

alpha = 0.5
beta = (231/255)**2.2

ilum = np.array([((1-alpha+alpha*v)*beta)**(1/2.2) * 255 for v in lum])

print ilum[[1,2]]
#pp(sorted([abs(v-u) for u,v in pairs(ilum)]))
