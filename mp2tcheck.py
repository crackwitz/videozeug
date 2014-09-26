#!/usr/bin/env python

from __future__ import division
from __future__ import with_statement

import os
import sys
import time
import getopt
import random
import struct
import pprint; pp = pprint.pprint
import glob
import ctypes
from funcs import *
from filetools import *

import camtype

# ======================================================================

altsig = " -- M2TS check"
sig = " -- MP2T check"

statuses = {
	0: "OK",
	1: "INCOMPLETE",
	2: "BROKEN",
	3: "STRANGE"
}


# ======================================================================

clearline = "\033[2K"
# Erases part of the line. If n is zero (or missing), clear from cursor
# to the end of the line. If n is one, clear from cursor to beginning of
# the line. If n is two, clear entire line. Cursor position does not
# change.


# ======================================================================

class MP2TIncomplete(Exception):
	def __init__(self, packetstart, packetend, realend):
		self.packetstart = packetstart
		self.packetend   = packetend
		self.realend     = realend
	
	def __str__(self):
		return 'Packet @0x%X: Should end at 0x%X, does end at 0x%X (%d bytes missing)' % (
			self.packetstart,
			self.packetend,
			self.realend,
			self.packetend - self.realend
		)

def decode_PCR(block):
	#hexdump(block)
	#print "decode_PCR:", bindump(block)
	
	# apparently 48 = [33 + padding with ones + 9]
	
	bytes = map(ord, block)
	
	ext = 0
	ext |= bytes[5]       << 0
	ext |= (bytes[4] & 1) << 8
	
	base = 0
	base |= bytes[0] << 25
	base |= bytes[1] << 17
	base |= bytes[2] << 9
	base |= bytes[3] << 1
	base |= bytes[4] >> 7
	
	# padding
	assert bytes[4] & 0x7E == 0x7E

	return (base, ext)

def parse_adaption_field(block):
	header = struct.unpack(">BB", block[0:2].str())
	res = Record()
	
	res.length = header[0]
	assert res.length >= 1 # 0 can't be because of the flags byte
	remainder = block[1+res.length:]
	
	# flags
	res.discontinuity       = (header[1] >> 7) & 1
	res.random_access       = (header[1] >> 6) & 1
	res.ES_priority         = (header[1] >> 5) & 1
	res.has_PCR             = (header[1] >> 4) & 1
	res.has_OPCR            = (header[1] >> 3) & 1
	res.has_splicing_point  = (header[1] >> 2) & 1
	res.has_private_data    = (header[1] >> 1) & 1
	res.has_field_extension = (header[1] >> 0) & 1
	
	flagcount = (
		res.has_PCR +
		res.has_OPCR +
		res.has_splicing_point +
		res.has_private_data +
		res.has_field_extension
	)
	
	assert flagcount <= 1
	
	if flagcount and not res.has_PCR:
		pp(res)
		import pdb
		pdb.set_trace()
	
	if res.has_PCR:
		res.PCR = decode_PCR(block[2:8])
	
	if res.has_OPCR:
		res.OPCR = decode_PCR(block[2:8])
	
	if res.has_private_data:
		assert 0, "wikipedia didn't specify that"
	
	if res.has_field_extension:
		assert 0, "wikipedia didn't specify that"
	
	if res.has_splicing_point:
		# they said it can be negative
		(res.splice_countdown,) = struct.unpack(">b", block[2])
	
	return (res, remainder)
	

def parse_packet(packet):
	# http://en.wikipedia.org/wiki/MPEG_transport_stream#Important_elements_of_a_transport_stream
	
	header = struct.unpack(">BBBB", packet[0:4].str())
	
	res = Record()
	
	# sync byte
	assert header[0] == 0x47 # ASCII 'G'
	
	res.transport_error    = bitslice(header[1], 7)
	res.payload_unit_start = bitslice(header[1], 6)
	res.transport_priority = bitslice(header[1], 5)
	
	res.packet_ID = (bitslice(header[1], 0, 5) << 8) | header[2]
	
	res.scrambling_control = bitslice(header[3], 6, 2)
	res.has_adaption_field = bitslice(header[3], 5)
	res.has_payload        = bitslice(header[3], 4)
	res.continuity_counter = bitslice(header[3], 0, 4)
	
	# this'll get sliced up
	data = packet[4:]
	
	if res.has_adaption_field:
		(res.adaption_field, data) = parse_adaption_field(data)
	
	if res.has_payload:
		res.payload = data
		data = data[data.len:]
	
	if data.len:
		res.slack = data
	
	return res
	
offsetrange = 16
striderange = 32

def thorough_scan(info, file, skip, stride, with_timecode, max_dtc=1000000):
	if not stride:
		stride = info.stride

	if info:	
		prefixlen = info.structure[0]
	else:
		prefixlen = [0,4][with_timecode > 0]

	with_timecode = (prefixlen >= 4)
	
	# assuming stride, prefixlen, with_timecode
	state = Record()
	state.p = skip
	state.tc = None
	state.old_tc = None
	state.dtc = None
	state.old_dtc = None
	state.goodpackets = 0
	state.lastsync = None
	
	# timecodes are 27 MHz
	# PCR every 0.1s
	if with_timecode:
		tc_mod = 1 << with_timecode
	else:
		tc_mod = 1 << 32

	def scan_sig():
		while not (file[state.p] == 'G' and file[state.p+stride] == 'G'):
			state.p += 1
	
	def get_tc():
		if state.p - 4 >= 0:
			state.old_tc = state.tc
			(state.tc,) = struct.unpack("!I", file[state.p-4:state.p].str())

			state.old_dtc = state.dtc
			if state.old_tc is not None:
				state.dtc = (state.tc - state.old_tc) % tc_mod
			else:
				state.dtc = None

	# scan
	i = 0
	while state.p < file.len:
		i += 1
		if sys.stderr.isatty() and (i % 10000 == 0):
			sys.stderr.write("scanning @%d (%6.2f %sB)...\r" % ((state.p,) + metric(state.p))); sys.stderr.flush()
			
		# check packet
		if (file[state.p] == 'G'):
			state.goodpackets += 1
			if with_timecode:
				get_tc()
				if (not state.old_tc) or not (0 <= state.dtc <= max_dtc):
					if sys.stdout.isatty():
						sys.stderr.write(clearline); sys.stderr.flush()
					print "packet @%d has timecode %d (prev %s, delta %s)" % (state.p, state.tc, state.old_tc, state.dtc)

			state.p += stride
			continue
		
		else:
			if sys.stdout.isatty():
				sys.stderr.write(clearline); sys.stderr.flush()

			if state.goodpackets:
				assert state.goodpackets >= 1
				print "%d good packets" % (state.goodpackets-1)

			print "no sig @%d ->" % state.p,
			# back up if already synced (don't tread in place)
			state.p = max(0, state.p - stride + 1)
			
			scan_sig()

			print "found sig @%d" % state.p
			
			if state.lastsync is not None:
				print "last sync %d bytes ago" % (state.p - state.lastsync)
			
			state.lastsync = state.p
			
			state.tc = state.old_tc = None
			state.goodpackets = 0
			
			if sys.stdout.isatty():
				#time.sleep(0.1)
				pass
			
			continue
	
	assert state.p >= file.len
	
	if state.p > file.len:
		state.goodpackets -= 1
	
	if state.goodpackets:
		print "%d good packets" % (state.goodpackets)
	
	if state.p > file.len:
		print "last packet truncated"

	print "end of file"


def parse_packetstream(file):
	info = streaminfo(file)
	(prefixlen, packetlen, suffixlen) = info.structure
	
	for i in xrange(info.npackets):
		block = file[info.stride*i : info.stride*(i+1)]
		packet = block[prefixlen:][:188]
		yield (i*info.stride + prefixlen, packet)
		
def streaminfo(block):
	# http://en.wikipedia.org/wiki/MPEG_transport_stream

	def find_sigs(offsetrange=offsetrange, striderange=striderange):
		for sig1 in xrange(offsetrange+1):
			if block[sig1] != 'G':
				continue

			for sig2 in xrange(sig1 + 188, sig1 + 188 + striderange+1):
				if sig2 >= block.len:
					continue
					
				if block[sig2] != 'G':
					continue

				yield (sig1, sig2)

	def check_guess(npackets, prefixlen, suffixlen, count=100):
		stride = prefixlen + 188 + suffixlen
		
		results = []
		
		# check random packets
		for i in xrange(count):
			p = random.randrange(npackets)
			if block[stride*p + prefixlen] != 'G':
				sys.stdout.write(" no sig at %d (packet %d)\n" % (stride*p + prefixlen, p)); sys.stdout.flush()
				return False
			
			results.append(p)

		return True
	
	
	# if file contains less than 2 packets...
	# no packets
	if block.len < 1*188:
		assert block.len == 0, "file contains less than one full packet"
		return None

	# one packet
	if block.len < 2*188:
		# find signature, check length
		for sig1 in (0, 4):
			if block[sig1] == 'G':
				if block.len == sig1 + 188:
					return None
				else:
					raise MP2TIncomplete(
						0,
						sig1 + 188,
						block.len
					)

		assert 0, "could not find packet signature"
	

	# scan for first two signatures
	# then check
	for (sig1, sig2) in find_sigs():
		stride = sig2 - sig1
		
		prefixlen = sig1
		suffixlen = stride - 188 - prefixlen
		if suffixlen < 0:
			continue
		
		# guess packet count
		npackets = block.len // stride
		
		print "found stride = %d = (%d + 188 + %d)..." % (stride, prefixlen, suffixlen),
		sys.stdout.flush()
		
		checkres = check_guess(npackets, prefixlen, suffixlen)
		print ["FAIL", "OK"][checkres]
		
		if checkres:
			break
	else:
		assert 0, "found no consistent packet size"

	# check that last packet is complete	
	if (block.len % stride != 0):
		raise MP2TIncomplete(
			stride * npackets,
			stride * (npackets+1),
			block.len
		)

	return Record(
		stride    = stride,
		structure = (prefixlen, 188, suffixlen),
		npackets  = npackets,
	)

# ======================================================================

if __name__ == '__main__':
	thorough = False
	stride = None
	with_timecode = False
	skip = 0
	
	opts, args = getopt.gnu_getopt(sys.argv[1:], '', ['thorough', 'stride=', 'with_timecode=', 'skip=', 'nostatus'])
	for o,a in opts:
		if o == '--thorough':
			thorough = True

		if o == '--with_timecode':
			with_timecode = int(a)

		if o == '--stride':
			stride = int(a)

		if o == '--skip':
			skip = int(a)
	
	fnames = []
	for globbable in args:
		fnames += glob.glob(globbable)

	for fname in fnames:
		assert os.path.isfile(fname)

		print fname

		fb = FileBuffer(fname)
		
		this_camtype = camtype.get_type(fname)
		
		print "camera type:", this_camtype
		
		status = 0
		info = None
		exception = None

		try:
			info = streaminfo(fb)
		except MP2TIncomplete, exception:
			print "MP2TIncomplete:", exception
			status = 1
		except AssertionError, exception:
			print "AssertionError:", exception or "<no message>"
			status = 2

		if thorough:
			info = thorough_scan(info, fb, skip, stride, with_timecode)

		if (status == 0):
			pp(info)

		print "file looks", statuses[status]

		# clean up previous statuses
		for x in glob.glob(os.path.abspath(fname) + altsig + "*"):
			os.unlink(x)
		for x in glob.glob(os.path.abspath(fname) + sig + "*"):
			os.unlink(x)

		# write new status
		#if status != 0:
		if 1:
			# status 0 does not guarantee a complete file	
			x = os.path.abspath(fname) + sig + " result %s" % statuses[status]
			try:
				with open(x, 'w') as fh:
					fh.write("camera type: " + this_camtype + "\n")
					
					if info:
						fh.write(pprint.pformat(info))
					
					if exception:
						fh.write('%s: %s\n' % (exception.__class__.__name__, exception))
				os.chmod(x, 0664)
			except IOError, e:
				print "IOError", e

		print

		if len(fnames) == 1:
			sys.exit(status)
