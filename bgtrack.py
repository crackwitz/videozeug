from __future__ import division

import os
import sys
import math
import numpy as np
import cv2
from multiprocessing.pool import ThreadPool
from collections import deque

lk_params = dict(
	winSize = (15,15),
	maxLevel = 2,
	criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
)

feature_params = dict(
	maxCorners = 500,
	qualityLevel = 0.3,
	minDistance = 7,
	blockSize = 7
)

def meanshift(p, radius, points):
	while True:
		pold = p
		inliers = (np.linalg.norm(points - p, axis=1) <= radius)
		p = np.mean(points[inliers], axis=0)
		shift = np.linalg.norm(p - pold)
		if shift < radius * 0.1:
			break

	return p

def clustering(radius, points):
	centroids = np.zeros((0,2), dtype=np.float32)
	labels = np.zeros((len(points),), dtype=np.int0)
	labels[:] = -1
	for i,pt in enumerate(points):
		pt1 = meanshift(pt, radius, points)
		# find nearest centroid
		if len(centroids) == 0:
			labels[i] = 0
			centroids = np.vstack([centroids, pt1])
		else:
			d = np.linalg.norm(centroids - pt1, axis=1)
			imin = np.argmin(d)
			if d[imin] < radius:
				labels[i] = imin
			else:
				labels[i] = len(centroids)
				centroids = np.vstack([centroids, pt1])

	return (centroids, labels)

class DummyTask:
    def __init__(self, fn, args):
        self.data = fn(*args)
    def ready(self):
        return True
    def get(self):
        return self.data

def to_f8(array):
	return tuple(np.rint(array * 256).astype('int'))

def scale_frame(frame):
	frame = cv2.resize(frame, None, fx=framescale, fy=framescale, interpolation=cv2.INTER_AREA)
	framegray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
	return framegray


def flow_frame(tracks, prevframe, curframe):
	assert prevframe is not None and curframe is not None

	vis = cv2.cvtColor(curframe, cv2.COLOR_GRAY2BGR)

	if len(tracks) > 0:
		if 0:
			p0 = np.float32([tr[-1] for tr in tracks]).reshape(-1, 1, 2)
		else:
			nx,ny = 20,15
			p0 = np.concatenate(np.indices((nx,ny)).swapaxes(0,2), axis=0)
			p0 = ((p0 + 0.5) * (capw / nx, caph / ny)).astype(np.float32)
			tracks = [[pt] for pt in p0]
			p0.shape = (-1, 1, 2)

		p1, st, err = cv2.calcOpticalFlowPyrLK(prevframe, curframe, p0, None, **lk_params)
		p0r, st, err = cv2.calcOpticalFlowPyrLK(curframe, prevframe, p1, None, **lk_params)
		d = abs(p0-p0r).reshape(-1, 2).max(-1)
		good = (d < 1)

		new_tracks = []
		for tr, (x,y), good_flag in zip(tracks, p1.reshape(-1, 2), good):
			if not good_flag:
				continue

			tr.append((x,y))
			if len(tr) > tracklen:
				del tr[0]

			new_tracks.append(tr)
			cv2.circle(vis, (x, y), 2, (0, 255, 0), -1)

		tracks = new_tracks
		#cv2.polylines(vis, [np.int32(tr) for tr in tracks], False, (0, 255, 0), thickness=1)

		delta = p1 - p0
		p1 = p0 + delta * 5

		p0 = p0[good].reshape((-1, 2))
		p1 = p1[good].reshape((-1, 2))
		delta = p1 - p0
		p0[:,:] = (capw/2, caph/2)
		p0 += delta
		p1 = p0

		if len(delta):
			#import pdb; pdb.set_trace()
			clusterradius = 20.0
			(centroids, labels) = clustering(clusterradius, delta)
			h = {}
			for i in labels:
				if i not in h: h[i] = 0
				h[i] += 1

			best = max(h, key=lambda k: h[k])
			(bestx, besty) = np.int32(centroids[best] + (capw/2, caph/2))

			#p1 = p0 + delta * 1
			#import pdb; pdb.set_trace()
			cv2.polylines(vis, np.concatenate([p0.reshape((-1, 1, 2)),p1.reshape((-1, 1, 2))], axis=1).astype(np.int32), False, (0, 0, 255), thickness=3)

			cv2.line(vis, (bestx - 10, besty), (bestx + 10, besty), (255, 255, 0))
			cv2.line(vis, (bestx, besty - 10), (bestx, besty + 10), (255, 255, 0))
			cv2.circle(vis, (bestx, besty), int(clusterradius), (255, 255, 0), thickness=2)


	# todo: find more tracks
	mask = np.zeros_like(curframe)
	mask[:] = 255
	for x, y in [np.int32(tr[-1]) for tr in tracks]:
		cv2.circle(mask, (x, y), 5, 0, -1)
	p = cv2.goodFeaturesToTrack(curframe, mask=mask, **feature_params)
	if p is not None:
		for x, y in np.float32(p).reshape(-1, 2):
			tracks.append([(x, y)])

	return (tracks, vis)



if __name__ == '__main__':
	source = 'V:\\Video AG\\archiv\\14ws-infin-141014\\14ws-infin-141014-dozent.mp4'
	source = 0
	# 0:12:40

	framescale = 1 #0.5
	prevframe = None
	curframe = None
	tracks = []
	tracklen = 10

	numthreads = cv2.getNumberOfCPUs()

	scalerpool = ThreadPool(processes=1)
	qscaling = deque()

	flowpool = ThreadPool(processes=1) # must be serial!
	qflow = deque()

	vid = cv2.VideoCapture(source)
	#vid.set(cv2.CAP_PROP_FPS, 15)
	if isinstance(source, str):
		vid.set(cv2.CAP_PROP_POS_MSEC, 1000 * (12*60 + 40))

	capw = vid.get(cv2.CAP_PROP_FRAME_WIDTH)
	caph = vid.get(cv2.CAP_PROP_FRAME_HEIGHT)

	cv2.namedWindow("source", cv2.WINDOW_NORMAL)
	cv2.resizeWindow("source", int(capw * framescale), int(caph * framescale))

	while True:
		#print "c1:", len(qscaling) < scalerpool._processes
		if len(qscaling) < scalerpool._processes:
			(rv, frame) = vid.read()
			task = scalerpool.apply_async(scale_frame, (frame,))
			qscaling.append(task)

		#print "c2a:", len(qscaling) > 0, len(qscaling) > 0 and qscaling[0].ready()
		#print "c2b:", len(qflow) < flowpool._processes
		while len(qscaling) > 0 and qscaling[0].ready() and len(qflow) < flowpool._processes:
			prevframe = curframe
			curframe = qscaling.popleft().get()
			if prevframe is not None and curframe is not None:
				task = flowpool.apply_async(flow_frame, (tracks, prevframe, curframe))
				qflow.append(task)

		#print "c3:", len(qflow) > 0, len(qflow) > 0 and qflow[0].ready()
		while len(qflow) > 0 and qflow[0].ready():
			(tracks, vis) = qflow.popleft().get()
			cv2.imshow("source", vis)

		key = cv2.waitKey(1)
		if key == -1: continue
		if key == 27: break

	cv2.destroyAllWindows()
