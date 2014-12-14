#!/usr/bin/env python2
import os
import sys

def block_lines(lines, starter):
	block = []
	gotblock = False
	for line in lines:
		if starter(line):
			if gotblock:
				yield block
			block = []
			gotblock = False
		else:
			block.append(line)
			gotblock = True
	
	if gotblock:
		yield block

def parse_lines(lines):
	for block in block_lines(lines, lambda line: line.startswith('BookmarkBegin')):
		try:
			block = dict(line.split(": ", 1) for line in block)
		except:
			print block
			raise
		yield {
			'title': block['BookmarkTitle'],
			'page': int(block['BookmarkPageNumber']),
			'level': int(block['BookmarkLevel']),
		}

def per_page(bookmarks):
	pages = {}
	
	for b in bookmarks:
		page = b['page']
		title = b['title']
		level = b['level']
		
		if page not in pages:
			pages[page] = {}
		
		pages[page][level] = title
	
	return {
		page: ": ".join(titles[level] for level in sorted(titles))
		for page, titles
		in pages.iteritems()
	}

if __name__ == '__main__':
	import subprocess
	import json
	
	(infname,) = sys.argv[1:]
	
	p = subprocess.Popen(['pdftk', infname, 'dump_data_utf8'], stdout=subprocess.PIPE)
	
	inlines = p.stdout

	lines = (line.decode('utf8').rstrip() for line in inlines if line.startswith("Bookmark"))
	data = list(parse_lines(lines))
	data = per_page(data)
	json.dump(data, sys.stdout, sort_keys=True, indent=1)
