#! /usr/bin/env python

import pyccn
import threading, Queue, sys

import utils

class Receiver(pyccn.Closure):
	queue = Queue.Queue(20)
	caps = None

	def __init__(self, uri):
		self._handle = pyccn.CCN()
		self._uri = pyccn.Name(uri)
		self._name_segments = self._uri.append('segments')
		self._name_frames = self._uri.append('frames')
		self._segment = 0

	def fetch_stream_info(self):
		name = self._uri.append('stream_info')

		print "Fetching stream_info from %s ..." % name

		co = self._handle.get(name)
		if not co:
			print "Unable to fetch %s" % name
			sys.exit(10)

		self.caps = co.content

		return self.caps

#	def fetch_seek_query(self, 

	def start(self):
		self._receiver_thread = threading.Thread(target=self.run)
		self._running = True
		self._receiver_thread.start()
		self.next_interest()

	def stop(self):
		self._running = False
		self._handle.setRunTimeout(0)
		self._receiver_thread.join()

	def run(self):
		print "Running ccn loop"
		self._handle.run(-1)
		print "Finished running ccn loop"

	def next_interest(self):
		name = self._name_segments.appendSegment(self._segment)
		self._segment += 1

		#interest = Interest.Interest(name=name)
		#print "Issuing an interest for: %s" % name
		self._handle.expressInterest(name, self)

	def upcall(self, kind, info):
		if kind == pyccn.UPCALL_FINAL:
			return pyccn.RESULT_OK

		elif kind == pyccn.UPCALL_CONTENT:
			if not hasattr(self, 'segbuf'):
				self.segbuf = []

			last, content = utils.packet2buffer(info.ContentObject.content)
			self.segbuf.append(content)
			if last == 0:
				res = self.segbuf[0]
				for e in self.segbuf[1:]:
					res = res.merge(e)
				self.segbuf = []
				self.queue.put(res)

			self.next_interest()
			return pyccn.RESULT_OK

		elif kind == pyccn.UPCALL_INTEREST_TIMED_OUT:
			print "timeout - reexpressing"
			return pyccn.RESULT_REEXPRESS

		print "kind: %d" % kind

		return pyccn.RESULT_ERR

if __name__ == '__main__':
	import pygst
	pygst.require("0.10")
	import gst
	import gobject

	gobject.threads_init()

	from src import CCNSrc

	#def on_eos(bus, msg):
	#	mainloop.quit()
	def on_dynamic_pad(dbin, pad):
		global decoder
		print "Linking dynamically!"
		pad.link(decoder.get_pad("sink"))

	def bus_call(bus, message, loop):
		t = message.type
		if t == gst.MESSAGE_EOS:
			print("End-of-stream")
			loop.quit()
		elif t == gst.MESSAGE_ERROR:
			err, debug = message.parse_error()
			print("Error: %s: %s" % (err, debug))
			loop.quit()
		return True

#	src = gst.element_factory_make('filesrc')
#	src.set_property('location', 'test.bin')

	receiver = Receiver('/videostream')
	src = CCNSrc('source')
	src.set_receiver(receiver)

#	demuxer = gst.element_factory_make('mpegtsdemux')
	decoder = gst.element_factory_make('ffdec_h264')
	decoder.set_property('max-threads', 3)

	sink = gst.element_factory_make('xvimagesink')

	pipeline = gst.Pipeline()
	pipeline.add(src, decoder, sink)

	caps = receiver.fetch_stream_info()

	#caps = gst.caps_from_string('video/x-h264,width=352,height=288,framerate=30000/1001')
	#caps = gst.caps_from_string('video/x-h264, width=(int)704, height=(int)576, framerate=(fraction)30000/1001, pixel-aspect-ratio=(fraction)6/5, codec_data=(buffer)014d401fffe1001c674d401feca0580937fe000c000a20000003002ee6b28001e30632c001000468ebecb2, stream-format=(string)avc, alignment=(string)au')
	#caps = gst.caps_from_string('video/x-h264, width=(int)704, height=(int)576, framerate=(fraction)30000/1001, pixel-aspect-ratio=(fraction)6/5, stream-format=(string)byte-stream, alignment=(string)au')
	src.link_filtered(decoder, caps)
#	demuxer.connect("pad-added", on_dynamic_pad)
	decoder.link(sink)

	receiver.start()

	#gst.element_link_many(src, demuxer, decoder, sink)

	loop = gobject.MainLoop()
	bus = pipeline.get_bus()
	#bus.add_signal_watch()
	#bus.connect('message::eos', on_eos)
	bus.add_watch(bus_call, loop)

	pipeline.set_state(gst.STATE_PLAYING)

	try:
		loop.run()
	except KeyboardInterrupt:
		print "Ctrl+C pressed, exitting"
		pass

	pipeline.set_state(gst.STATE_NULL)
	pipeline.get_state(gst.CLOCK_TIME_NONE)