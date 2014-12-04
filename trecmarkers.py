#!/usr/bin/env python2
from __future__ import division
import os
import sys
import json
import pprint; pp = pprint.pprint

import mp4select
import mp4check
import trecformat

def getdata(uuid):
	(box,) = mp4select.select("TSCM/DATA$" + uuid, filebuf)
	boxdata = trecformat.parse_TSCMDATA(uuid, box[16:])
	return boxdata.content
	
(fname,) = sys.argv[1:]
filebuf = mp4select.FileBuffer(fname)

dimensions, = getdata('2b7b6af6')
titles      = getdata('2b7b6af8')

data = {}
data['frameWidth'] = dimensions.width
data['frameHeight'] = dimensions.height

atoms = mp4check.parse(filebuf)
mvhd = mp4check.select(atoms, 'moov mvhd'.split())
data['duration'] = duration = mvhd.duration / mvhd.timescale

titles = [
	{
		'name': rec.text,
		'start': rec.time,
		#'duration': duration # we don't have that here
	}
	for rec in titles
]

data['chapters'] = titles

print json.dumps(data, sort_keys=True, indent=1)
