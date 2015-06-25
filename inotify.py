#!/usr/bin/env python2.7

import os
import sys
import struct
import ctypes
import time

from funcs import *

# http://man7.org/linux/man-pages/man7/inotify.7.html

libc = ctypes.cdll.LoadLibrary('libc.so.6')

DEBUG = 0

# ======================================================================
# helper functions

def inmask(haystack, needle):
	return haystack & needle == needle


# ======================================================================
# syntactic sugar: attribute access for dicts

class attrdict(dict):
	def copy(self):
		return self.__class__(**self)

	def __getattr__(self, key):
		return self[key]

	def __setattr__(self, key, value):
		self[key] = value

	def __delattr__(self, key):
		del self[key]

	def __repr__(self):
		argstr = ', '.join(
			"%s=%s" % (key, repr(self[key]))
			for key in self
		)

		return "%s(%s)" % (self.__class__.__name__, argstr)

	def __str__(self):
		argstr = ',\n'.join(
			"    %-10s = %s" % (key, repr(self[key]))
			for key in self
		)

		return "%s(\n%s\n)" % (self.__class__.__name__, argstr)


# ======================================================================
# APIs via ctypes

# inotify

libc.inotify_init.argtypes = []
libc.inotify_init.restype = ctypes.c_int

libc.inotify_init1.argtypes = [ctypes.c_int]
libc.inotify_init1.restype = ctypes.c_int

libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
libc.inotify_add_watch.restype = ctypes.c_int

libc.inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_uint32]
libc.inotify_rm_watch.restype = ctypes.c_int


# read, close

libc.read.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
libc.read.restype = ctypes.c_int

def read(fd, count):
	buf = ctypes.create_string_buffer(count)
	res = libc.read(fd, buf, count)

	if res >= 0:
		return buf[:res]
	else:
		errno = ctypes.get_errno()
		raise OSError(errno, "read() returned -1. errno message: " + os.strerror(errno))

close = libc.close
close.argtypes = [ctypes.c_int]
close.restype = ctypes.c_int


# ======================================================================
# inotify constants

# Supported events suitable for MASK parameter of INOTIFY_ADD_WATCH.
IN_ACCESS        = 0x00000001     # File was accessed.
IN_MODIFY        = 0x00000002     # File was modified.
IN_ATTRIB        = 0x00000004     # Metadata changed.
IN_CLOSE_WRITE   = 0x00000008     # Writable file was closed.
IN_CLOSE_NOWRITE = 0x00000010     # Unwritable file closed.
IN_CLOSE         = (IN_CLOSE_WRITE | IN_CLOSE_NOWRITE) # Close.
IN_OPEN          = 0x00000020     # File was opened.
IN_MOVED_FROM    = 0x00000040     # File was moved from X.
IN_MOVED_TO      = 0x00000080     # File was moved to Y.
IN_MOVE          = (IN_MOVED_FROM | IN_MOVED_TO) # Moves.
IN_CREATE        = 0x00000100     # Subfile was created.
IN_DELETE        = 0x00000200     # Subfile was deleted.
IN_DELETE_SELF   = 0x00000400     # Self was deleted.
IN_MOVE_SELF     = 0x00000800     # Self was moved.

# NOTE: in the mask of a watch, IN_ISDIR has no effect.
#       both files and dirs are reported either way.

# Events sent by the kernel.
IN_UNMOUNT       = 0x00002000     # Backing fs was unmounted.
IN_Q_OVERFLOW    = 0x00004000     # Event queue overflowed.
IN_IGNORED       = 0x00008000     # File was ignored.

# Helper events.
IN_CLOSE         = (IN_CLOSE_WRITE | IN_CLOSE_NOWRITE)    # Close.
IN_MOVE          = (IN_MOVED_FROM | IN_MOVED_TO)          # Moves.

# Special flags.
IN_ONLYDIR       = 0x01000000     # Only watch the path if it is a directory.
IN_DONT_FOLLOW   = 0x02000000     # Do not follow a sym link.
IN_MASK_ADD      = 0x20000000     # Add to the mask of an already existing watch.
IN_ISDIR         = 0x40000000     # Event occurred against dir.
IN_ONESHOT       = 0x80000000     # Only send event once.

# All events which a program can wait on.
IN_ALL_EVENTS = (IN_ACCESS | IN_MODIFY | IN_ATTRIB | IN_CLOSE_WRITE  \
                 | IN_CLOSE_NOWRITE | IN_OPEN | IN_MOVED_FROM        \
                 | IN_MOVED_TO | IN_CREATE | IN_DELETE               \
                 | IN_DELETE_SELF | IN_MOVE_SELF)

eventnames = '''
	IN_ACCESS IN_MODIFY IN_ATTRIB IN_CLOSE_WRITE IN_CLOSE_NOWRITE IN_OPEN IN_MOVED_FROM IN_MOVED_TO IN_CREATE IN_DELETE IN_DELETE_SELF IN_MOVE_SELF
	IN_UNMOUNT IN_Q_OVERFLOW IN_IGNORED
	IN_CLOSE IN_MOVE
	IN_ONLYDIR IN_DONT_FOLLOW IN_MASK_ADD IN_ISDIR IN_ONESHOT
'''.split()
eventmap = dict((globals()[key], key) for key in eventnames)

def parse_eventmask(mask):
	res = []
	p = 1
	while p <= mask:
		if (mask & p) and (p in eventmap):
			res.append(eventmap[p])
			mask ^= p
		p <<= 1
	
	if mask:
		res.append(mask)
	
	return res


# ======================================================================
# inotify_struct

def parse_cstr(buffer):
	return buffer[:buffer.find('\x00')]

def parse_inotify_struct(buffer):
	(wd, mask, cookie, length) = struct.unpack("iIII", buffer[:16])
	name = parse_cstr(buffer[16:16+length])

	assert len(buffer) >= 16 + length
	
	remainder = buffer[16+length:]
	
	res = inotify_event(
		wd     = wd,
		mask   = mask,
		cookie = cookie,
		length = length,
		name   = name,
	)
	
	return (res, remainder)


# ======================================================================
# inotify classes

class inotify_watch(attrdict):
	"data associated with an inotify watch"
	def __init__(self, wd, pathname, mask, recursive=False, parent=None):
		self.wd        = wd
		self.pathname  = pathname
		self.mask      = mask
		self.recursive = recursive
		self.parent    = parent


class inotify_event(attrdict):
	"data associated with an inotify event"
	def __init__(self, wd, mask, cookie, length, name):
		self.wd     = wd
		self.mask   = mask
		self.cookie = cookie
		self.length = length
		self.name   = name

	def __str__(self):
		return repr(self)

	def __repr__(self):
		fields = []
		
		fields.append("{1}".format(
			self, "|".join(
				x[3:] if isinstance(x, str) else str(x)
				for x in parse_eventmask(self.mask)
			)
		))
		if self.cookie: fields.append("cookie {0.cookie}".format(self))
		fields.append("{0.name!r}".format(self))
		fields.append("wd {0.wd}".format(self))
		
		return "<event {0}>".format(", ".join(fields))



class inotify(object):
	eventbufsize = 8192
	
	# TODO: manage race conditions
	#       rm_watch for a path that has CREATE_ISDIRs in queue
	#       (handler would not find the wd they belong to?)
	#       can that even happen?
	#         CANNOT happen for automatic rm_watch
	#         CAN happen if user does rm_watch while create_isdirs are in queue
	#
	# rm_watch causes IN_IGNORED -> react to that instead
	#   but IN_IGNORED causes rm_watch... loop?

	def __repr__(self):
		return "<inotify fd=%d>" % (self.fd,)
	
	def __init__(self):
		self.fd = libc.inotify_init()
		self.cookies = {} # cookie -> list of related events
		self.watches = {}
	
	def close(self):
		if self.fd:
			if DEBUG: print "%s.close()" % repr(self)
			close(self.fd)
			self.fd = None

	def __del__(self):
		self.close()
	
	def get_root(self, wd):
		seen = set()
		while self.watches[wd].parent:
			assert wd not in seen
			seen.add(wd)
			wd = self.watches[wd].parent
		
		return wd

	def add_watch(self, pathname, mask, recursive=False, _parent=None, hardfail=True, rcallback=None):
		pathname = os.path.abspath(pathname)
		count = 0
		
		# TODO: deal with IN_Q_OVERFLOW, wd == -1 -> see _handle_event()
		# TODO: deal with IN_UNMOUNT (how to test?)
		
		if not os.access(pathname, os.R_OK | os.X_OK):
			if hardfail:
				# todo: try again on attrib changes...
				raise OSError, ("access denied", pathname)
			else:
				return False
		
		_mask = mask
		if recursive:
			# IN_ISDIR has no effect here
			
			_mask |= IN_CREATE  # so we notice new subdirs -> add watches
			_mask |= IN_MOVED_FROM | IN_MOVED_TO  # watched subdir has moved (we can't see where roots move to...)
			
		if DEBUG: print "add_watch(\n\tpathname=%s,\n\tmask=%s,\n\trecursive=%s,\n\t_parent=%s\n) ->" % (
			repr(pathname),
			parse_eventmask(mask),
			recursive,
			_parent,
		),
		
		wd = libc.inotify_add_watch(self.fd, pathname, _mask)
		assert wd > 0, "ERROR: add_watch failed, we have {0} watches already".format(len(self.watches))
		
		if DEBUG: print wd

		self.watches[wd] = inotify_watch(
			wd        = wd,
			pathname  = pathname,
			mask      = mask,
			recursive = recursive,
			parent    = _parent,
		)
		count += 1

		if rcallback:
			rcallback(self.watches[wd])

		if recursive:
			for item in os.listdir(pathname):
				subpath = os.path.join(pathname, item)
				
				if not os.path.isdir(subpath):
					continue

				if os.path.islink(subpath):
					print "not following symlink {0!r}".format(subpath)
					continue

				assert os.path.exists(subpath)

				count += self.add_watch(subpath,
					mask=mask,
					recursive=True,
					_parent=wd,
					hardfail=False,
					rcallback=rcallback
				)
		
		return count
		
	
	def rm_watch(self, wd, justdrop=False):
		if not justdrop:
			res = libc.inotify_rm_watch(self.fd, wd)
			assert res == 0, str(res)
		
		del self.watches[wd]
		
		if DEBUG: print "rm_watch(%d)" % wd
	
	def run(self):
		buffer = ''
		
		while self.watches:
			buffer += read(self.fd, self.eventbufsize)
			
			while buffer:
				# assuming the buffer contains whole structs
				(event, buffer) = parse_inotify_struct(buffer)
				
				# this might return something for the user, or not
				item = self._handle_event(event)
				
				# user gets event and watch objects
				if item:
					yield item
				

	def _handle_event(self, _event):
		res = None
		
		# event belongs to watch
		_watch = self.watches.get(_event.wd, None)
		
		_event_pretty = _event.copy()
		_event_pretty.mask = parse_eventmask(_event.mask)
		
		if _event.mask & IN_Q_OVERFLOW:
			print "event mask: IN_Q_OVERFLOW: Queue overflow!"
			#sys.exit(-1)
			return (_event, None)

		if _watch is None:
			# TODO/FIXME
			print "event for unknown watch %s: %s" % (_event.wd, repr(_event_pretty))
			return None
		
		# dedup events that happen on [parent watch: contents] AND [child watch: self]
		# NOTE: more event types might be applicable
		if (_watch is not None) and (_watch.parent is not None) and (_event.name == '') and (_event.mask & (IN_OPEN|IN_CLOSE)):
			assert (_event.mask & IN_ISDIR)
			return None
		
		if DEBUG: print "_handle_event @", time.strftime("%Y-%m-%d %H:%M:%S")
		if DEBUG: print "    %s" % repr(_watch)
		if DEBUG: print "    %s" % repr(_event_pretty)

		# rewrite events on a subwatch
		# create "cleaned up" event/watch
		# the raw inputs are called  _event/_watch
		if _watch.parent is None:
			(event, watch) = (_event, _watch)
		else:
			# find root watch
			rootwd = self.get_root(_event.wd)
			rootwatch = self.watches[rootwd]
			watch = rootwatch

			# path relative to root watch
			abspath = os.path.join(_watch.pathname, _event.name)
			relpath = os.path.relpath(abspath, rootwatch.pathname)

			# new event, relative to root watch
			event = _event.copy()
			event.wd = rootwd
			event.name = relpath
		
		# subdir creation
		if _watch.recursive and inmask(_event.mask, IN_CREATE | IN_ISDIR):
			self.add_watch(
				pathname  = os.path.join(_watch.pathname, _event.name),
				mask      = _watch.mask,
				recursive = True, # _watch.recursive == True
				_parent   = _event.wd,
				hardfail  = False
			)
		
		# oneshot event -> remove watch
		if _watch.mask & IN_ONESHOT:
			self.rm_watch(_watch.wd, justdrop=True)
			# there will be no IN_IGNORED
			# there just aren't any more events after the first
		
		# a watched dir is deleted (event is fired also on rm_watch)
		if _event.mask & IN_IGNORED:
			# rm this watch, if it hasn't been already
			if _event.wd in self.watches:
				self.rm_watch(_event.wd, justdrop=True)

			# rm immediate child watches (this is recursive via IN_IGNORED)
			for _wd in list(self.watches):
				try:
					if self.watches[_wd].parent == _event.wd:
						self.rm_watch(_wd)
				except KeyError, e:
					print "KeyError", e
					pass

		# handle renames/moves
		# use IN_MOVED_FROM/_TO + cookie
		if inmask(event.mask, IN_MOVED_FROM | IN_ISDIR):
			assert event.cookie not in self.cookies
			self.cookies[event.cookie] = event
			
		if inmask(event.mask, IN_MOVED_TO | IN_ISDIR):
			assert event.cookie in self.cookies
			prevevent = self.cookies.pop(event.cookie)
			
			rnfr = os.path.join(watch.pathname, prevevent.name)
			rnto = os.path.join(watch.pathname, event.name)
			
			# update watches
			# (MOVE_SELF will be ignored)
			for wd in self.watches:
				if self.watches[wd].pathname.startswith(rnfr):
					oldname = self.watches[wd].pathname
					suffix = os.path.relpath(oldname, rnfr) # might be empty -> might be just '.'
					newname = os.path.abspath(os.path.join(rnto, suffix))
					self.watches[wd].pathname = newname
					break
			else:
				# create watch because it's clearly a dir, but not watched yet
				# handle just like subdir creation
				if _watch.recursive and inmask(_event.mask, IN_ISDIR):
					self.add_watch(
						pathname  = rnto,
						mask      = _watch.mask,
						recursive = True, # _watch.recursive == True
						_parent   = _event.wd,
						hardfail  = False
					)

		# drop all kinds of events that happened on a subwatch
		if (event.name != '') and (event.mask & (IN_MOVE_SELF | IN_IGNORED | IN_DELETE_SELF)):
			return None


		# impl() is used so the user doesn't get events we requested, unless they asked for it
		impl = lambda flag: not (_event.mask & flag) or (_watch.mask & flag)
		# returns true if the flag isn't in the event anyway
		# only does someting if the event contains that flag
		
		# decide what events reach the user
		if impl(IN_CREATE) and impl(IN_MOVED_FROM) and impl(IN_MOVED_TO):
			return (event, watch)

		# nothing for the user
		return None


# ======================================================================

class InplaceWriter(object):
	def __init__(self):
		self.pos = 0
	
	def write(self, text):
		sys.stdout.write(('\b' * self.pos) + text)
		sys.stdout.flush()
		self.pos = len(text)
	
	def finish(self):
		sys.stdout.write('\b' * self.pos)
		sys.stdout.flush()

def abbrev(s, length):
	if len(s) > length:
		return s[:length-3] + '...'
	else:
		return s

# ======================================================================

empty_watch = inotify_watch(
	wd        = -1,
	pathname  = "",
	mask      = 0,
	recursive = False,
	parent    = None,
)

if __name__ == '__main__':
	import time
	import pwd
	import stat
	
	#DEBUG = 1
	inh = inotify()
	
	if sys.argv[1:]:
		watches = sys.argv[1:]
	else:
		watches = [
			'.',
		]
	
	sys.stdout.write("adding...\n"); sys.stdout.flush()
	for wdir in watches:
		sys.stdout.write("+ %s\n" % repr(wdir)); sys.stdout.flush()
		inh.add_watch(
			wdir,
			#IN_CLOSE_WRITE,
			IN_ALL_EVENTS & ~IN_MODIFY & ~IN_ACCESS & ~IN_OPEN & ~IN_CLOSE_NOWRITE,
			recursive=True
		)
		
	sys.stdout.write("ready\n\n"); sys.stdout.flush()
	
	for (event, watch) in inh.run():
		event_pretty = event.copy()
		event_pretty.mask = parse_eventmask(event.mask)
		
		if watch is None:
			watch = empty_watch
		
		watch_pretty = watch.copy()
		#watch_pretty.mask = parse_eventmask(watch.mask)
		
		#if event.mask & IN_Q_OVERFLOW: continue
		
 		if event.mask & IN_ATTRIB: continue

		path = os.path.join(watch.pathname, event.name)
		
		sys.stdout.write("%s%s%s %s\n" % (
			color(COLOR_BOLD, text=COLOR_BLACK),
			time.strftime("%Y-%m-%d %H:%M:%S"),
			color(COLOR_RESET),
			repr(path),
		))
		
		handled = False
		
 		if event.mask & IN_MOVED_FROM:
			sys.stdout.write("    RNFR: %s\n" % event.name)
			handled = True
		if event.mask & IN_MOVED_TO:
			sys.stdout.write("    RNTO: %s\n" % event.name)
			handled = True

		if event.mask & IN_DELETE:
			sys.stdout.write("    deleted\n")
			handled = True

		if event.mask & IN_CREATE:
			try:
				stat = os.stat(path)
				uid = stat.st_uid
				user = pwd.getpwuid(uid).pw_name
				sys.stdout.write("    created. owner: %s (%d)\n" % (user, uid))
				handled = True
			except Exception, e:
				print e

		if event.mask & IN_CLOSE_WRITE:
			try:
				sys.stdout.write("    size %8.2f %sB (%d Bytes)\n" % (
					metric(os.path.getsize(path)) + (os.path.getsize(path),)
				))
				sys.stdout.flush()
			except OSError:
				pass

		if (not handled):
			sys.stdout.write("    ignored %s\n" % event_pretty.mask)
			#print repr(watch_pretty)
			#print repr(event_pretty)

		print
