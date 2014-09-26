#!/usr/bin/env python
from __future__ import division
import re
import pprint; pp = pprint.pprint
import lxml.etree as etree

__all__ = ['extract', 'timefmt', 'nsmap']

# http://effbot.org/zone/element-namespaces.htm
# http://lxml.de/tutorial.html#using-xpath-to-find-text

# ======================================================================

# my own definitions, *coincidentally* the same as in the XMP file, but logically they're distinct
nsmap = {
	'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
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

def extract(xmpdata):
	assert isinstance(xmpdata, str) or hasattr(xmpdata, 'read')

	data = {}

	tree = etree.parse(xmpdata)
	
	(duration,) = tree.xpath('//rdf:RDF/rdf:Description/xmpDM:duration/@xmpDM:value', namespaces=nsmap)
	(timescale,) = tree.xpath('//rdf:RDF/rdf:Description/xmpDM:duration/@xmpDM:scale', namespaces=nsmap)
	m = re.match(r'^(\d+)/(\d+)$', timescale)
	(num,denom) = m.groups()
	duration = int(duration) * int(num) / int(denom)

	data['duration'] = duration

	(denom,) = tree.xpath(".//rdf:Description[@xmpDM:trackName='Markers']/@xmpDM:frameRate", namespaces=nsmap)
	m = re.match(r'f(\d+)', denom)
	markerframerate = int(m.group(1))

	chapters = []

	for node in tree.xpath("//xmpDM:markers/rdf:Seq/rdf:li", namespaces=nsmap):
		(itemtype,) = node.xpath("./@xmpDM:type", namespaces=nsmap)
		assert itemtype == "Chapter"
		
		(chaptername,) = node.xpath("./@xmpDM:name", namespaces=nsmap)
		(starttime,) = node.xpath("./@xmpDM:startTime", namespaces=nsmap)
		(duration,) = node.xpath("./@xmpDM:duration", namespaces=nsmap)
		starttime = int(starttime) / markerframerate
		duration = int(duration) / markerframerate
		
		#print "Kapitel:", chaptername
		#print "    Start %s, Laenge %s" % (timefmt(starttime), timefmt(duration))
		#print

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
