import os
import sys
import json
import numpy as np
import numexpr as ne
import cv2
import pprint; pp = pprint.pprint

headless = False

corners = sys.argv[1]
invidname = sys.argv[2]
outvidname = sys.argv[3]

data = json.load(open(sys.argv[1]))
outsize = tuple(data['canvas'])
src,dst = np.float32(zip(*data['points']))

# need inverse -> switch params now
H = cv2.getPerspectiveTransform(dst, src)

imin = np.float32(0.0)
imax = np.float32(255.0)
(imin, imax) = np.float32(data['range'])
scale = np.float32(255) / (imax-imin)

invid = cv2.VideoCapture(invidname)
outvid = cv2.VideoWriter(outvidname, -1, 25, outsize)

assert invid.isOpened()
assert outvid.isOpened()

if not headless:
	cv2.namedWindow("straight", cv2.WINDOW_NORMAL)

inframe = np.zeros(outsize[::-1] + (3,), dtype=np.uint8)
outframe = np.zeros(outsize[::-1] + (3,), dtype=np.uint8)
scaledframe = np.zeros(outsize[::-1], dtype=np.float32)
straightframe = np.zeros(outsize[::-1], dtype=np.float32)
framecount = 0
try:
	while True:
		(rv,_) = invid.read(inframe)
		if not rv: break
		assert _ is inframe
		framecount += 1
		pos_msec = invid.get(cv2.cv.CV_CAP_PROP_POS_MSEC)

		redplane = inframe[:,:,2]
		ne.evaluate("(redplane - imin) * scale", out=scaledframe)

		cv2.warpPerspective(src=scaledframe, M=H, dsize=outsize, dst=straightframe, flags=cv2.INTER_LINEAR) # inverted above: | cv2.WARP_INVERSE_MAP)

		straightframe += 0.5
		np.clip(straightframe, 0, 255, out=straightframe)

		outframe[:,:,2] = straightframe

		outvid.write(outframe)

		sys.stdout.write("\rframe {0} at {1:.1f} secs".format(framecount-1, pos_msec * 1e-3))
		sys.stdout.flush()

		if not headless and framecount % 5 == 0:
			cv2.imshow("straight", outframe)
			key = cv2.waitKey(1)
			if key == -1: continue
			elif key == 27: break
			else:
				print "key", key

except KeyboardInterrupt:
	pass

if not headless:
	cv2.destroyWindow("straight")
outvid.release()
