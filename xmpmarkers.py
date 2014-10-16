#!/usr/bin/env python2.7
from __future__ import division
import re
import fractions
import pprint; pp = pprint.pprint
import lxml.etree as etree

__all__ = ['extract', 'timefmt', 'nsmap']

# http://effbot.org/zone/element-namespaces.htm
# http://lxml.de/tutorial.html#using-xpath-to-find-text

# ======================================================================

# my own definitions, *coincidentally* the same as in the XMP file, but logically they're distinct
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

# ======================================================================

def timefmt(seconds):
	hours, seconds = divmod(seconds, 3600)
	minutes, seconds = divmod(seconds, 60)
	
	return "%d:%02d:%06.3f" % (hours, minutes, seconds)

# ======================================================================

def xmpfrac(s):
	m = re.match(r'^(\d+)?f(\d+)$', s)
	(n,d) = m.groups()
	n = int(n) if n else 1 # missing numerator => not 0/d, but 1/d
	d = int(d)
	return fractions.Fraction(n, d)

def xpath_value(tree, path, dtype=None):
	res = tree.xpath(path, namespaces=nsmap)
	if len(res) != 1: return None
	(value,) = res
	return dtype(value) if (dtype is not None) else value

def extract(xmpdata):
	assert isinstance(xmpdata, str) or hasattr(xmpdata, 'read')

	data = {}

	tree = etree.parse(xmpdata)
	
	### GENERAL METADATA
	(metanode,) = tree.xpath("/x:xmpmeta/rdf:RDF/rdf:Description", namespaces=nsmap)

	data['format'] = xpath_value(metanode, "./@dc:format", unicode)
	data['frameWidth'] = framew = xpath_value(metanode, "./xmpDM:videoFrameSize/@stDim:w", int)
	data['frameHeight'] = frameh = xpath_value(metanode, "./xmpDM:videoFrameSize/@stDim:h", int)
	data['videoFrameRate'] = xpath_value(metanode, "./@xmpDM:videoFrameRate", float)
	PAR = xpath_value(metanode, "./@xmpDM:videoPixelAspectRatio", fractions.Fraction)
	DAR = PAR * fractions.Fraction(framew, frameh)
	data['PAR'] = "{0.numerator}/{0.denominator}".format(PAR)
	data['DAR'] = "{0.numerator}/{0.denominator}".format(DAR)
	timescale = xpath_value(metanode, './xmpDM:duration/@xmpDM:scale', fractions.Fraction)
	duration = xpath_value(metanode, './xmpDM:duration/@xmpDM:value', int) * timescale
	data['duration'] = float(duration)

	### GET TRACKS
	res = tree.xpath("/x:xmpmeta/rdf:RDF/rdf:Description/xmpDM:Tracks", namespaces=nsmap)
	if len(res) == 0:
		return data

	assert len(res) == 1, "multiple xmpDM:Tracks found!"
	(tracks,) = res

	### GET MARKER NODE
	res = tracks.xpath("./rdf:Bag/rdf:li/rdf:Description[@xmpDM:trackName='Markers']", namespaces=nsmap)
	(markernode,) = res
	markerframerate = xpath_value(markernode, "@xmpDM:frameRate", xmpfrac)

	### GET CHAPTER MARKERS
	chapters = []
	for node in markernode.xpath("./xmpDM:markers/rdf:Seq/rdf:li", namespaces=nsmap):
		# this is for CC 2013 formats
		descr = node.xpath("./rdf:Description", namespaces=nsmap)
		if descr: (node,) = descr
		
		itemtype = xpath_value(node, "./@xmpDM:type")
		if itemtype != "Chapter":
			continue
		
		chaptername = xpath_value(node, "./@xmpDM:name")
		
		starttime = float(xpath_value(node, "./@xmpDM:startTime", int) * markerframerate)
		
		duration = xpath_value(node, "./@xmpDM:duration", int)
		if duration is not None: duration = float(duration * markerframerate)
		
		chapters.append({
			'name': chaptername,
			'start': starttime,
			'duration': duration
		})

	data['chapters'] = chapters

	return data


if __name__ == '__main__':
	import os
	import sys
	import json
	
	(fname,) = sys.argv[1:]

	xmpdata = sys.stdin if (fname == '-') else fname

	data = extract(xmpdata)
	
	print json.dumps(data, sort_keys=True, indent=1)
