#!/usr/bin/env python2.7
from __future__ import division
import os
import sys
import math
import subprocess
import pprint; pp = pprint.pprint
from PIL import Image
import io
import json
import codecs
import time

# ======================================================================

class Database(object):
	def __init__(self):
		self.conn = None

	def __call__(self):
		if self.conn is None:
			from dbfuncs import db_connect
			self.conn = db_connect()
		
		return self.conn

database = Database()

# ======================================================================

goldenratio = (1 + math.sqrt(5)) / 2

suffixes = ['360p', 'ipod', '720p', '1080p', 'screencast']

def remove_suffixes(fname):
	#fname = os.path.splitext(fname)[0]

	while True:
		old = fname
		
		for suffix in suffixes:
			if fname.endswith(suffix):
				fname = fname[:-len(suffix)].rstrip('-_ ')
		
		if fname == old:
			break

	return fname

def common_prefix(a, b):
	diff = min([i for i,(u,v) in enumerate(zip(a,b)) if u != v] + [min(len(a), len(b))])
	return a[:diff]

def filestem(filenames):
	filenames = [
		remove_suffixes(os.path.splitext(fname)[0])
		for fname in filenames
	]
	
	filename = reduce(common_prefix, filenames)

	return filename.rstrip('-_ ')

def maxkeyval(d):
	return d[max(d)]

def get_frame(fname, position, height=None):
	if height is None:
		scaler = []
	else:
		# TODO: setsar=1 ok? used to be setdar=1
		scaler = ['-filter:v', 'scale=h={0}:w={0}*dar,setsar=1'.format(height)]
	
	data = subprocess.check_output([
		'ffmpeg',
		'-ss', '{0:.3f}'.format(position),
		'-i', fname,
		'-c:v', 'bmp',
		'-f', 'rawvideo',
		'-frames:v', '1',
	] + scaler + [
		'-'], stderr=open('/dev/null', 'w'))
	
	data = io.BytesIO(data)
	
	return Image.open(data)
	

# ======================================================================

def titlegen(vidpath, stem=None):
	assert os.path.exists(vidpath)

	if stem is None:
		stem = filestem([vidpath])

	titlepath = u"{0}-title.jpg".format(stem)

	#if not os.access(titlepath, os.W_OK):
	#	print "file can not be written: {0!r}".format(titlepath)
	#	continue

	# check meta.json
	metapath = u"{0}-meta.json".format(os.path.splitext(vidpath)[0])
	if not os.access(metapath, os.W_OK):
		raise IOError("file can not be written: {0!r}".format(metapath))
	
	if not os.path.exists(metapath):
		rv = subprocess.call(
			['ffprobe', '-of', 'json', '-show_format', '-show_streams', vidpath],
			stdout=open(metapath, 'wb'), stderr=open('/dev/null', 'w'))
		# really not important (otherwise use check_call())

	meta = json.load(codecs.open(metapath, encoding='utf-8'))

	if not any(stream['codec_type'] == 'video' for stream in meta['streams']):
		raise ValueError("not a video")

	if os.path.exists(titlepath):
		raise IOError("title file already exists")

	position = float(meta['format']['duration']) / goldenratio

	im = get_frame(vidpath, position, 360)

	#smallsize = (640, 360)
	#smallsize = aspect_resize(im.size, )
	#im = im.resize(smallsize, Image.ANTIALIAS)

	im.save(titlepath, quality=75)

	return titlepath

# ======================================================================

def title_for_lecture(lectureid):
	conn = database()

	videos = {} # (prio, videoid): path

	cursor = conn.cursor()
	cursor.execute('''
		select videos.id vid, videos.path vpath, formats.prio fprio
		from videos
		join formats on videos.video_format = formats.id
		where videos.lecture_id = %s
	''', lectureid)

	for row in cursor:
		vid = row['vid']
		vpath = row['vpath']
		fprio = row['fprio']
		videos[fprio,vid] = vpath

	bestvideo = maxkeyval(videos)
	stem      = filestem(videos.values())

	print u"(best of lecture {0:d})".format(lectureid)

	def callback(titlepath):
		c = conn.cursor()
		c.execute("UPDATE lectures SET titlefile = %s WHERE id = %s", [titlepath, lectureid])
		c.close()
		conn.commit()

	return (bestvideo, stem, callback)


def lectures_from_db():
	conn = database()
	cursor = conn.cursor()
	cursor.execute('''
		select lid from (
			select lectures.id lid, count(*) vidcount
			from lectures
			join videos on videos.lecture_id = lectures.id
			group by lid
			order by lid desc
		) sub
		where vidcount > 0
	''')

	for row in cursor:
		yield row['lid']


def apply_one((vidpath, stem, callback)):
	print u"{0!r}".format(vidpath)

	try:
		titlepath = titlegen(vidpath, stem=stem)

		print u"   -> {0!r}".format(titlepath)

		if callback is not None:
			callback(titlepath)

	except (IOError, ValueError), e:
		print e

	finally:
		print


# ======================================================================

if __name__ == '__main__':
	jobs = []

	for arg in sys.argv[1:]:
		jobs.append(
			(arg, filestem([arg]), None))

	if not jobs:
		jobs = (
			title_for_lecture(lectureid)
			for lectureid in lectures_from_db()
		)

	for job in jobs:
		apply_one(job)
