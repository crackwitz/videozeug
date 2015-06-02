from __future__ import division
import os
import sys

if os.name == 'nt':
	import wmi # pip install wmi

	class DiskEvents(object):
		def __init__(self):
			ctx = wmi.WMI()

			self.watch = ctx.Win32_LogicalDisk.watch_for(DriveType=2)
			# watch = ctx.Win32_VolumeChangeEvent.watch_for() # EventType=2

		def __iter__(self):
			return self

		def next(self, timeout=None):
			if timeout is None:
				timeout_ms = 1000 # for KeyboardInterrupt
			else:
				timeout_ms = int(timeout*1000)

			while True:
				try:
					event = self.watch(timeout_ms=timeout_ms)
					break
				except wmi.x_wmi_timed_out:
					if timeout is None:
						continue
					else:
						raise TimeoutError

			#print event

			if event.FileSystem is None:
				return {
					'path': event.DeviceID,
					'present': False,
				}

			else:
				total = int(event.Size)
				free = int(event.FreeSpace)

				return {
					'path': event.DeviceID,
					'present': True,
					'bytestotal': total,
					'bytesused': total - free,
					'filesystem': event.FileSystem,
					'volumename': event.VolumeName,
					'serialno': event.VolumeSerialNumber,
				}

else:
	class DiskEvents(object):
		pass

	raise NotImplemented("not implemented for linux (yet)")

if __name__ == '__main__':
	import pprint

	for event in DiskEvents():
		pprint.pprint(event)
