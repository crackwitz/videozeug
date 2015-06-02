import threading
import Queue


class AsyncResult(object):
	def __init__(self):
		self.ready = threading.Event()
		self.value = None

	def set(self, value):
		self.value = value
		self.ready.set()

	def get(self):
		self.ready.wait()
		return self.value

	def __repr__(self):
		return "<AsyncResult {0}: {1!r}>".format("ready" if self.ready.is_set() else "pending", self.value)


class ThreadPool(object):
	def __init__(self, numworkers):
		self.numworkers = numworkers
		self.queue = Queue.Queue()
		self.workers = [
			threading.Thread(target=self._worker, args=(i,))
			for i in xrange(numworkers)
		]
		for w in self.workers:
			w.start()

	def _worker(self, index):
		while True:
			item = self.queue.get()
			if item is None:
				self.queue.put(item)
				break

			(asyncres, func, args, kwargs) = item
			result = func(*args, **kwargs)
			asyncres.set(result)
			# do nothing with result

	def join(self):
		# token to end all workers
		self.queue.put(None)

		for w in self.workers:
			w.join()

		token = self.queue.get()
		assert token is None
		assert self.queue.empty()

	def apply_async(self, func, args=None, kwds=None):
		asyncres = AsyncResult()
		self.queue.put((asyncres, func, args or (), kwds or {}))
		return asyncres


# shamelessly stolen from python's threading.py
# then extended for my purposes
class Delayed(threading.Thread):
	"""Call a function a specified number of seconds after the last update:

		t = Delayed(30.0, f, args=[], kwargs={})
		t.start()
		t.update()     # optional, resets the "countdown"
		t.cancel()     # stop the timer's action if it's still waiting

	"""

	def __init__(self, interval, function, args=[], kwargs={}):
		threading.Thread.__init__(self)
		self.updated = time.time()
		self.interval = interval
		self.function = function
		self.args = args
		self.kwargs = kwargs
		self.finished = threading.Event()
		self.start()

	def cancel(self):
		"""Stop the timer if it hasn't finished yet"""
		if self.finished.is_set():
			return None

		self.finished.set()
		
		time_left = (self.updated + self.interval) - time.time()
		return time_left

	def update(self, timestamp=None):
		self.updated = time.time() if (timestamp is None) else timestamp

	def run(self):
		while True:
			delay = (self.updated + self.interval) - time.time()
		
			if delay > 0:
				self.finished.wait(delay)
			else:
				break

		if not self.finished.is_set():
			self.function(*self.args, **self.kwargs)
			self.finished.set()


# TODO: ein Timer fuer alle delays
class Timers(object):
	def __init__(self):
		pass


class RefCounter(object):
	def __init__(self):
		self.cond = threading.Condition()
		self.count = 0

	def wait_zero(self):
		self.cond.acquire()
		while self.count > 0:
			self.cond.wait()
		self.cond.release()

	def acquire(self):
		self.cond.acquire()
		self.count += 1
		self.cond.notifyAll()
		self.cond.release()

	def release(self):
		self.cond.acquire()
		self.count -= 1
		self.cond.notifyAll()
		self.cond.release()

