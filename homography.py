import os
import sys
import json
import numpy as np
import numexpr as ne
import cv2
import pprint; pp = pprint.pprint
import ffwriter

headless = False

corners = sys.argv[1]
invidname = sys.argv[2]
outvidname = sys.argv[3]

data = json.load(open(corners))
(inw,inh) = insize = tuple(data['source'])
outsize = tuple(data['canvas'])
src,dst = np.float32(zip(*data['points']))

# need inverse -> switch params now
H = cv2.getPerspectiveTransform(dst, src)

# todo: center anchor

imin = np.float32(0.0)
imax = np.float32(255.0)
(imin, imax) = np.float32(data['range'])
scale = np.float32(255) / (imax-imin)

invid = cv2.VideoCapture(invidname)
#outvid = cv2.VideoWriter(outvidname, -1, 25, outsize)
outvid = ffwriter.FFWriter(outvidname, 25, outsize, pixfmt='bgra', codec='qtrle', moreflags='-g 250 -loglevel 32')

assert invid.isOpened()
assert outvid.isOpened()

assert inw == int(invid.get(cv2.CAP_PROP_FRAME_WIDTH))
assert inh == int(invid.get(cv2.CAP_PROP_FRAME_HEIGHT))

if not headless:
	cv2.namedWindow("straight", cv2.WINDOW_NORMAL)
	cv2.resizeWindow("straight", outsize[0] // 2, outsize[1] // 2)

#inframe = np.zeros(outsize[::-1] + (3,), dtype=np.uint8)
outframe = np.zeros(outsize[::-1] + (4,), dtype=np.uint8)
scaledframe = np.zeros(insize[::-1], dtype=np.float32)
straightframe = np.zeros(outsize[::-1], dtype=np.float32)
framecount = 0
try:
	while True:
		(rv,inframe) = invid.read()
		if not rv: break
		framecount += 1
		pos_msec = invid.get(cv2.CAP_PROP_POS_MSEC)

		redplane = inframe[:,:,2]
		ne.evaluate("(redplane - imin) * scale", out=scaledframe)

		cv2.warpPerspective(src=scaledframe, M=H, dsize=outsize, dst=straightframe, flags=cv2.INTER_LINEAR) # inverted above: | cv2.WARP_INVERSE_MAP)

		np.clip(straightframe, 0.0, 255.0, out=straightframe)
		outframe[:,:,2] = outframe[:,:,3] = straightframe

		outvid.write(outframe)

		if not headless and framecount % 10 == 0:
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
