from __future__ import division
import os
import sys
import cv2
import numpy as np

imrgb = np.float32(cv2.imread(sys.argv[1])) / 255.0
imyuv = cv2.cvtColor(imrgb, cv2.COLOR_BGR2YCrCb)

imyuv[:,:,(1,2)] -= 0.5

cv2.namedWindow("controls")
cv2.namedWindow("corrected1", cv2.WINDOW_NORMAL)
cv2.namedWindow("corrected2", cv2.WINDOW_NORMAL)

mousepos = None

def onmouse(event, x, y, flags, userdata):
	global mousepos
	if event == cv2.EVENT_LBUTTONDOWN:
		print "onmouse", x, y
		mousepos = (userdata,x,y)

cv2.setMouseCallback("corrected1", onmouse, 1)
cv2.setMouseCallback("corrected2", onmouse, 2)


y_gain = 1.0
y_bias = 0
u_bias = 0
v_bias = 0

def on_y_gain(newpos):
	global y_gain
	y_gain = newpos / 100

def on_y_bias(newpos):
	global y_bias
	y_bias = (newpos-50) / 200

def on_u_bias(newpos):
	global u_bias
	u_bias = (newpos-50) / 200

def on_v_bias(newpos):
	global v_bias
	v_bias = (newpos-50) / 200

cv2.createTrackbar("y gain", "controls", 100, 400, on_y_gain)
cv2.createTrackbar("y bias", "controls", 50, 100, on_y_bias)
cv2.createTrackbar("u bias", "controls", 50, 100, on_u_bias)
cv2.createTrackbar("v bias", "controls", 50, 100, on_v_bias)

def correct_shit():
	res = imyuv.copy()
	res[:,:,1] += u_bias
	res[:,:,2] += v_bias
	res[:,:,:] *= y_gain
	res[:,:,0] += y_bias
	return res

def correct_good():
	res = imyuv.copy()
	res[:,:,1] += u_bias * res[:,:,0]
	res[:,:,2] += v_bias * res[:,:,0]
	res[:,:,:] *= y_gain
	res[:,:,0] += y_bias
	return res

while True:
	if mousepos is not None:
		(ms,mx,my) = mousepos
		(py,pu,pv) = imyuv[my, mx, :]

		if ms == 1:
			u_bias = -pu
			v_bias = -pv
		elif ms == 2:
			u_bias = -pu / py
			v_bias = -pv / py

		print "u bias", u_bias
		print "v bias", v_bias
		mousepos = None
		cv2.setTrackbarPos("u bias", "controls", int(0.5 + 50 + u_bias*200))
		cv2.setTrackbarPos("v bias", "controls", int(0.5 + 50 + v_bias*200))
	
	imyuv1 = correct_shit()
	imyuv1[:,:,(1,2)] += 0.5 # bias
	rgb = cv2.cvtColor(imyuv1, cv2.COLOR_YCrCb2BGR)
	cv2.imshow("corrected1", rgb)

	imyuv2 = correct_good()
	imyuv2[:,:,(1,2)] += 0.5 # bias
	rgb = cv2.cvtColor(imyuv2, cv2.COLOR_YCrCb2BGR)
	cv2.imshow("corrected2", rgb)

	
	key = cv2.waitKey(100)
	if key == -1: continue
	if key == 27: break

cv2.destroyAllWindows()
