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
	maxCorners = 100,
	qualityLevel = 0.3,
	minDistance = 7,
	blockSize = 7
)

class DummyTask:
    def __init__(self, fn, args):
        self.data = fn(*args)
    def ready(self):
        return True
    def get(self):
        return self.data

def to_f8(array):
	return tuple(np.rint(array * 256).astype('int'))

def process_frame(frame):
	scale = 1#0.5
	frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
	framegray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
	#framegray = cv2.resize(framegray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

	goodfeatures = cv2.goodFeaturesToTrack(framegray, **feature_params)
	goodfeatures.shape = (-1, 2)
	#goodfeatures /= scale

	points = [
		cv2.KeyPoint(x, y, 20)
		for x,y in goodfeatures
	]
	cv2.drawKeypoints(frame, points, frame, color=(0,0,255), flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)

	if 0:
		(dx,dy) = goodfeatures.mean(axis=0)

		fh,fw = frame.shape[:2]

		p0 = np.float32([fw/2, fh/2])
		p1 = np.float32((dx,dy))
		cv2.arrowedLine(frame, to_f8(p0), to_f8(p1), shift=8, color=(255, 255, 0), thickness=2, line_type=cv2.LINE_AA)

	return frame


if __name__ == '__main__':
	numthreads = cv2.getNumberOfCPUs()
	pool = ThreadPool(processes = numthreads)
	pending = deque()

	cv2.namedWindow("source") #, cv2.WINDOW_NORMAL)

	source = 'V:\\Video AG\\archiv\\14ws-infin-141014\\14ws-infin-141014-dozent.mp4'
	source = 0
	# 0:12:40
	vid = cv2.VideoCapture(source)
	if isinstance(source, str):
		vid.set(cv2.CAP_PROP_POS_MSEC, 1000 * (12*60 + 40))

	while True:
		if len(pending) < numthreads:
			(rv,frame) = vid.read()
			task = pool.apply_async(process_frame, (frame,))
			#task = DummyTask(process_frame, (frame,))
			pending.append(task)

		while len(pending) > 0 and pending[0].ready():
			result = pending.popleft().get()
			cv2.imshow("source", result)

		key = cv2.waitKey(1)
		if key == -1: continue
		if key == 27: break

	cv2.destroyAllWindows()
