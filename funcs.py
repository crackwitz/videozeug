from __future__ import division
import os
import sys
import stat
import math
import re
import threading
import pprint
from odict import odict

xnsplit = lambda s, n=2: (s[i:i+n] for i in xrange(0, len(s), n))
nsplit = lambda s, n=2: list(xnsplit(s, n))
iround = lambda x: int(round(x))

# ======================================================================

metric_quant = {
	1000: {
		-12: 'p',
		 -9: 'n',
		 -6: 'u',
		 -3: 'm',
		  0: '',
		  3: 'k',
		  6: 'M',
		  9: 'G',
		 12: 'T',
		 15: 'P',
		 18: 'E',
	},
	1024: {
		  0: '',
		  3: 'Ki',
		  6: 'Mi',
		  9: 'Gi',
		 12: 'Ti',
		 15: 'Pi',
		 18: 'Ei',
	}
}

def metric(x, minimum=None, maximum=None, digits=None, step=1000):
	if step in metric_quant:
		quant = metric_quant[step]
	else:
		quant = metric_quant[1000]
	
	if (minimum is not None) and (maximum is not None):
		assert(minimum <= maximum)
	
	if (x == 0):
		return (x, quant[0])

	p = 0
	s = (x > 0) - (x < 0)
	x = abs(x)
	
	while (x >= step) and ((maximum is None) or (p < maximum)) and (p+3 <= max(quant)):
		p += 3
		x /= float(step)
	while (x < 1) and ((minimum is None) or (p > minimum)) and (p-3 >= min(quant)):
		p -= 3
		x *= step
	
	if digits is None:
		return (s*x, quant[p])
	else:
		return (digitfmt(s*x, digits), quant[p])

def digitfmt(value, ndigits):
	assert ndigits >= 1
	
	aval = abs(value)
	
	if aval > 0:
		left = int(math.ceil(math.log10(int(aval)+1)))
	else:
		left = 1
		
	left = max(left, 1)
	left = min(left, ndigits)

	right = ndigits-left
	
	return "%*.*f" % (left, right, value)


# ======================================================================

def to_hms(seconds):
	ts = seconds
	th,ts = divmod(ts, 3600)
	tm,ts = divmod(ts, 60)
	
	return (th, tm, ts)

def timefmt(s):
	return to_hms(s)

def from_hms(*pieces):
	h = m = s = 0.0
	if   len(pieces) == 1: [      s] = pieces
	elif len(pieces) == 2: [   m, s] = pieces
	elif len(pieces) == 3: [h, m, s] = pieces
	else: assert 0
	
	return 3600*h + 60*m + s

class HumanTime(object):
	def __init__(self, arg, *dnc):
		# Do Not Care about DNC
		
		if isinstance(arg, (str, unicode)):
			arg = map(float, arg.split(":"))

		if isinstance(arg, (list, tuple)):
			arg = from_hms(*arg)

		if isinstance(arg, (int, float)):
			arg = float(arg)
		else:
			assert 0
		
		self.value = arg
		
	def __str__(self):
		(h,m,s) = to_hms(self.value)
		res = []
		#if h:
		res.append("%d" % h)
		#if h or m:
		res.append("%02d" % m)
		#if h or m or s:
		res.append("%06.3f" % s)
		
		return ':'.join(res)
	
	def __repr__(self):
		return "%s(%s, %s)" % (self.__class__.__name__, repr(self.value), repr(str(self)))

def normalize_int(x):
	p = 0
	while not x & 1:
		x >>= 1
		p += 1
	
	return (x, p)

def bitslice(n, p=0, w=1):
	"bitslice(n, p, w=1) -> bits [p;p+w) of integer n"
	
	assert p >= 0
	assert w >= 0
	
	n >>= p
	n &= (1 << w)-1
	
	return n

# ======================================================================

#def boolchoice(msg):
#	inp = raw_input("%s [y/n] " % msg).strip().lower()
#	return (inp in ['y', 'yes', '1', 'true'])

def avg(s):
	return sum(s) / len(s)

# ======================================================================
# ein dictionary, mit Attributzugriff als syntactic sugar
# zeigt sich ausserdem augenfreundlich an
#
# Beispiel:
#   >>> x = Record()
#   >>> x.foo = 10
#   >>> x.bar = [1,2,3]
#   >>> x
#   Record(
#       foo        = 10,
#       bar        = [1, 2, 3]
#   )

# TODO: proper ordered record (no special case for startswith('_'))

# TODO: table type for proper repr (list of lists/records/odicts), maybe with header?

def blockindent(level, s):
	lines = s.split('\n')
	
	return '\n'.join(
		(' '*level) + line
		for line in lines
	)

def blockprefix(prefix, s):
	lines = s.split('\n')
	
	return '\n'.join(
		prefix + line
		for line in lines
	)
	

class Record(odict):
	def copy(self):
		return Record(dict.copy(self))
	
	@staticmethod
	def make(**kw):
		return Record(kw)
	
	def __getattr__(self, key):
		return self[key]
	
	def __setattr__(self, key, value):
		if key.startswith('_'):
			odict.__setattr__(self, key, value)
		else:
			self[key] = value
	
	def __delattr__(self, key):
		if key.startswith('_'):
			odict.__delattr__(self, key)
		else:
			del self[key]
	
	def __str__(self):
		return self.__repr__(multiline=False)

	def __repr__(self, multiline=True):
		repritems = [
			(
				key,
				key if isinstance(key, str) else repr(key),
				pprint.pformat(value)
			)
			for key, value in sorted(self.iteritems())
		]

		maxkeylen = max([len(key) for key,rkey,value in repritems]) if repritems else 0
		
		multiline |= any('\n' in rv for k,rk,rv in repritems)
		
		args = []
		for (key, reprkey, reprvalue) in repritems:
			if multiline:
				if '\n' in reprvalue:
					reprvalue = '\n' + blockindent(4, reprvalue)
				w = -maxkeylen*('\n' not in reprvalue)*((-1)**(isinstance(key, int)))
				reprpair = blockindent(4, "%*s = %s" % (w, reprkey, reprvalue))
			else:
				reprpair = "%s=%s" % (reprkey, reprvalue)

			args.append(reprpair)

		if multiline:
			argstr = '\n%s\n' % (',\n'.join(args))
		else:
			argstr = ', '.join(args)
			
		res = "Record(%s)" % argstr
		
		return res


# ======================================================================

#	style_reset=$'%{\e[0m%}'
#
#	style_red=$'%{\e[0;31;40m%}'
#	style_green=$'%{\e[0;32;40m%}'
#	style_yellow=$'%{\e[0;33;40m%}'
#	style_blue=$'%{\e[0;34;40m%}'
#	style_cyan=$'%{\e[0;36;40m%}'
#	style_white=$'%{\e[0;37;40m%}'
#
#	style_boldred=$'%{\e[1;31;40m%}'
#	style_boldgreen=$'%{\e[1;32;40m%}'
#	style_boldyellow=$'%{\e[1;33;40m%}'
#	style_boldblue=$'%{\e[1;34;40m%}'
#	style_boldcyan=$'%{\e[1;36;40m%}'
#	style_boldwhite=$'%{\e[1;37;40m%}'
#
#	style_faintwhite=$'%{\e[1;30;40m%}'

def colorcode(code):
	return "\033[%dm" % code

def stripcode(s):
	return re.sub(r'\033\[[^m]+m', r'', s)
	
def color(code=0, text=None, bg=None, font=None):
	res = colorcode(code)
	
	if font is not None:
		res += colorcode(font + 10)
	
	if text is not None:
		res += colorcode(text + 30)
	
	if bg is not None:
		res += colorcode(bg + 40)
	
	return res
	
COLOR_RESET     = 0
COLOR_BOLD      = 1
COLOR_UNBOLD    = 22
COLOR_UNDERLINE = 4
COLOR_INVERT    = 7

COLOR_BLACK     = 0
COLOR_RED       = 1
COLOR_GREEN     = 2
COLOR_YELLOW    = 3
COLOR_BLUE      = 4
COLOR_MAGENTA   = 5
COLOR_CYAN      = 6
COLOR_WHITE     = 7

# ======================================================================

def spawn(fn, args=None, kwargs=None):
	t = threading.Thread(
		target=fn,
		args=(args or ()),
		kwargs=(kwargs or {}),
	)
	t.start()
	return t


# ======================================================================


def natsortkey(x):
	convert = lambda v: int(v, 10) if v.isdigit() else v
	return map(convert, re.split(r'(\d+)', x))


# ======================================================================


def hexdump(a, width=16, blockwidth=None):
	res = ''
	
	offset = 0
	
	indexwidth = math.log(len(a), 256) if len(a) else 1
	indexwidth = 2*int(math.ceil(indexwidth))
	
	while offset < len(a):
		line = [ord(c) for c in a[offset:offset+width]]
		line += [None] * (width - len(line))
		
		hexline   = ["%02X" % c if (c is not None) else "  " for c in line]
		plainline = ["%c" % chr(c) if (32 <= c < 127) else "." for c in line]
		
		res += "%0*x : %s | %s\n" % (
			indexwidth,
			offset,
			'  '.join(' '.join(block) for block in nsplit(hexline, blockwidth or width)),
			' '.join(''.join(block) for block in nsplit(plainline, blockwidth or width)),
			
		)
		
		offset += width

	return res
