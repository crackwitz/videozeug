#!/usr/bin/env python2
from __future__ import division
import os
import sys
import json
import re
import uuid
import pprint; pp = pprint.pprint

from lxml import etree

import mp4check

# ----------------------------------------------------------------------

# movmark: takes trecmarkers output and patches it into the XMP_ box of a .mov file
# 
# the .mov file has to have:
# * moov.udta.XMP_ box
# * ... at the end of the file
# * "Chapters" track in the XMP data
# 
# add a *chapter* marker to the mov file within Premiere to make this happen.


# ----------------------------------------------------------------------
# definitions and utils

xpacket_start = u'<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>'.encode('utf8')
xpacket_end   = u'<?xpacket end="w"?>'.encode('utf8')

def xmppad(n, w=100):
	res = []
	while n >= w:
		res.append(' ' * (w-1) + '\n')
		n -= w
	
	res.append(' ' * n)
	
	return ''.join(res)

# http://effbot.org/zone/element-namespaces.htm
# http://lxml.de/tutorial.html#using-xpath-to-find-text

# my own definitions, *coincidentally* the same as in the XMP data, but logically they're distinct
nsmap = {
	"x": "adobe:ns:meta/",
	"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
	"xmp": "http://ns.adobe.com/xap/1.0/",
	"xmpDM": "http://ns.adobe.com/xmp/1.0/DynamicMedia/",
	"stDim": "http://ns.adobe.com/xap/1.0/sType/Dimensions#",
	"xmpMM": "http://ns.adobe.com/xap/1.0/mm/",
	"stEvt": "http://ns.adobe.com/xap/1.0/sType/ResourceEvent#",
	"stRef": "http://ns.adobe.com/xap/1.0/sType/ResourceRef#",
	"bext": "http://ns.adobe.com/bwf/bext/1.0/",
	"creatorAtom": "http://ns.adobe.com/creatorAtom/1.0/",
	"dc": "http://purl.org/dc/elements/1.1/",
}

def deNS(text):
	for key in nsmap:
		prefix = key + ":"
		text = text.replace(prefix, "{%s}" % nsmap[key])
	
	return text

def iround(x):
	return int(round(x))

# ----------------------------------------------------------------------

if __name__ == '__main__':
	(markersfname, movfname) = sys.argv[1:]

	assert movfname.endswith('.mov')
	
	# read markers (json) from stdin or file
	markers = json.load(sys.stdin if (markersfname == '-') else open(markersfname))
	
	# ----------------------------------------------------------------------
	# parse, check box positions

	# open output file
	filebuf = mp4check.FileBuffer(movfname, 'r+b')
	root = mp4check.parse(filebuf)
	
	# locate moov
	assert root[-1].type == 'moov'
	moovbox = root[-1]
	moovcontent = moovbox.content
	
	# locate udta
	assert moovbox.content[-1].type == 'udta'
	udtabox = moovbox.content[-1]
		
	# locate XMP_
	assert udtabox.content[-1].type == 'XMP_'
	xmpbox = udtabox.content[-1]
	
	# XMP data really is at end of file	
	xmpbuf = xmpbox.content
	assert xmpbuf.stop == filebuf.stop, "there must not be more data after the XMP_ atom!"

	# get at the XML
	xmpdata = xmpbuf.str()
	xmptree = etree.XML(xmpdata)
	
	# reset instance ID
	(node,) = xmptree.xpath("/x:xmpmeta/rdf:RDF/rdf:Description", namespaces=nsmap)
	node.set(
		deNS("xmpMM:InstanceID"),
		"xmp.iid:{0}".format(uuid.uuid4())) # random UUID
	
	# find a track named "Chapters"
	chaptertracks = xmptree.xpath("/x:xmpmeta/rdf:RDF/rdf:Description/xmpDM:Tracks/rdf:Bag/rdf:li/rdf:Description[@xmpDM:trackName='Chapter']", namespaces=nsmap)
	assert chaptertracks
	(chaptertrack,) = chaptertracks

	# TODO: create chapters track if not found
	
	(framerate,) = chaptertrack.xpath('@xmpDM:frameRate', namespaces=nsmap)
	framerate = int(re.match(r'f(\d+)$', framerate).group(1))
	
	# this is the list of markers within the chapters track
	(chapterseq,) = chaptertrack.xpath('xmpDM:markers/rdf:Seq', namespaces=nsmap)
	
	# to prevent duplication
	existing = {
		(
			int(node.get(deNS('xmpDM:startTime'))),
			node.get(deNS('xmpDM:name'))
		)
		for node
		in chapterseq.xpath("rdf:li/rdf:Description", namespaces=nsmap)
	}

	# ----------------------------------------------------------------------
	# add markers
	
	for marker in markers['chapters']:
		markername = marker['name']
		markertime = marker['start']
		timeindex = iround(markertime * framerate)
		#error = timeindex / framerate - markertime
		
		if (timeindex, markername) in existing:
			print "exists:", marker
			continue

		# insert marker
		item = etree.SubElement(chapterseq, deNS("rdf:li"))
		descr = etree.SubElement(item, deNS("rdf:Description"))
		
		descr.set(deNS('xmpDM:startTime'), str(timeindex))
		descr.set(deNS('xmpDM:name'), markername)

		existing.add((timeindex, markername))
	
	# ----------------------------------------------------------------------
	# serialize and patch
	
	xmpdata = etree.tostring(xmptree, encoding='utf8')
	
	# before: len(xmpbuf)
	# now:
	payload = len(xmpdata) + len(xpacket_start) + len(xpacket_end)

	# padding...
	padlen = 0
	if payload < len(xmpbuf):
		padlen = len(xmpbuf) - payload
	
	padlen = max(8000, padlen)
	payload += padlen
	
	# for adjusting moov+udta+XMP_ box lengths
	delta = payload - len(xmpbuf)

	assert delta >= 0
	# if not, padding must have gone wrong
	
	# this will be written
	xmpdata = xpacket_start + xmpdata + xmppad(padlen) + xpacket_end

	# only handle 32-bit box lengths
	assert moovbox.buf[">I"] >= 8
	assert udtabox.buf[">I"] >= 8
	assert xmpbox.buf[">I"] >= 8
	# if 1, a 64 bit value follows the tag
	# if 0, box extends to end of file

	# patch moov length
	moovbox.buf[">I"] += delta
	# patch udta length
	udtabox.buf[">I"] += delta
	# patch XMP_ length
	xmpbox.buf[">I"] += delta

	filebuf.fp.seek(xmpbuf.start)
	filebuf.fp.write(xmpdata)

	filebuf.fp.flush()
