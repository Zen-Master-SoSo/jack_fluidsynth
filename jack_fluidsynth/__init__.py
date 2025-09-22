#  jack_fluidsynth/__init__.py
#
#  Copyright 2025 Leon Dionne <ldionne@dridesign.sh.cn>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
"""
A wrapper for fluidsynth.Synth with extra methods for playing midi files,
listing SoundFont presets, and capturing samples.
"""
import re, logging
from time import sleep
from os.path import abspath
from pprint import pprint
from ctypes import	c_void_p, c_short, c_float, c_int, c_char_p, sizeof, \
					create_string_buffer, byref, pointer, POINTER
from mido import MidiFile
import fluidsynth, jack
import numpy as np

__version__ = "1.0.3"


fluid_sequencer_remove_events = fluidsynth.cfunc('fluid_sequencer_remove_events', None,
							('seq', c_void_p, 1),
							('source', c_short, 1),
							('dest', c_short, 1),
							('type', c_int, 1))

fluid_synth_write_float = fluidsynth.cfunc('fluid_synth_write_float', c_int,
							('synth', c_void_p, 1),
							('len', c_int, 1),
							('lbuf', c_void_p, 1),
							('loff', c_int, 1),
							('lincr', c_int, 1),
							('rbuf', c_void_p, 1),
							('roff', c_int, 1),
							('rincr', c_int, 1))

fluid_synth_process = fluidsynth.cfunc('fluid_synth_process', c_int,
							('synth', c_void_p, 1),
							('len', c_int, 1),
							('nfx', c_int, 1),
							('fx', c_void_p, 1),
							('nout', c_int, 1),
							('out', c_void_p, 1))



class PresetEnum:
	"""
	Drop-in replacement for sf2utils.preset.Sf2Preset, used for
	iterating over available presets using fluidsynth.
	This class is just a data structure, and does nothing.
	"""

	def __init__(self, filename, bank, preset, name):
		self.filename = filename
		self.bank = bank
		self.preset = preset
		self.name = name

	def __unicode__(self):
		return f'PresetEnum[{self.bank:03}:{self.preset:03} {self.name}]'

	def __repr__(self):
		return self.__unicode__()



class JackFluidsynth(fluidsynth.Synth):

	auto_connect		= False	# Set to True to connect to system outputs

	__synth				= None
	__sfid				= None
	__sequencer			= None
	__synthid			= None
	__sfids				= {}	# Dict of ints, indexed on filename
	__presets			= {}	# Dict of lists, indexed on filename
	__channels			= {}	# { soundfont : { "bbb:bbb" : channel } } where:
								# 	soundfont is string(path)
								# 	"bbb" is zero-padded bank,
								# 	"ppp" is zero-padded preset,
								#	channel is int
	__audio_out_enabled	= False


	def __init__(self, client_name = None, gain = 1.0, channels = 128, **kwargs):
		self.__jack_client = jack.Client(
			self.__class__.__name__ if client_name is None else client_name,
			no_start_server = True
		)
		self.settings = fluidsynth.new_fluid_settings()
		self.setting('audio.driver', 'jack')
		self.setting('synth.gain', gain)
		self.setting('synth.midi-channels', channels)
		self.setting('synth.sample-rate', float(self.samplerate))
		for opt,val in kwargs.items():
			self.setting(opt, val)
		self.synth = fluidsynth.new_fluid_synth(self.settings)
		self.__previous_gain = 0.0
		self.audio_driver = None
		self.midi_driver = None
		self.router = None

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		self.close()

	def close(self):
		self.stop_playback()
		self.system_reset()
		self.__jack_client.deactivate()
		self.__jack_client.close()
		self.delete()

	@property
	def samplerate(self):
		return self.__jack_client.samplerate

	def audio_on(self):
		if not self.__audio_out_enabled:
			self.start()
			if self.auto_connect:
				self.connect_jack_system_ports()
			self.__audio_out_enabled = True

	def audio_off(self):
		if self.__audio_out_enabled:
			self.setting('audio.driver', None)
			self.__audio_out_enabled = False

	def start_sequencer(self):
		if self.__sequencer is None:
			logging.debug('Starting sequencer')
			self.__sequencer = fluidsynth.Sequencer(use_system_timer = False)
			self.__synthid = self.__sequencer.register_fluidsynth(self)

	def stop_playback(self):
		if self.__sequencer is not None:
			self.__sequencer.delete()
			self.__sequencer = None

	def out_ports(self):
		return list(self.__jack_client.get_ports(name_pattern = 'fluidsynth.*'))

	def connect_jack_system_ports(self):
		sources = self.out_ports()
		targets = list(self.__jack_client.get_ports(is_input = True, is_physical = True))
		for source, target in zip(sources, targets):
			logging.debug('Connecting %s to %s', source.name, target.name)
			self.__jack_client.connect(source, target)

	def gain(self):
		return self.get_setting('synth.gain')

	def set_gain(self, gain):
		self.setting('synth.gain', gain)

	def mute(self):
		self.__previous_gain = self.gain()
		self.set_gain(0.0)

	def unmute(self):
		if self.__previous_gain is not None:
			self.set_gain(self.__previous_gain)

	def load_soundfont(self, soundfont):
		return self.sfid(soundfont)

	def unload_soundfont(self, soundfont):
		soundfont = abspath(soundfont)
		if soundfont in self.__sfids:
			sfid = self.__sfids[soundfont]
			self.sfunload(sfid)
			del self.__sfids[soundfont]
			del self.__presets[soundfont]
			del self.__channels[soundfont]
			logging.debug('Unloaded soundfont "%s" with sfid %d; %d sfids remaining',
				soundfont, sfid, len(self.__sfids))
		else:
			logging.debug('Request to unload a soundfont which is not loaded: "%s"', soundfont)

	def sfid(self, soundfont):
		"""
		Returns fluidsynth's sfid associated with the given soundfont.
		If the soundfont is not loaded, loads the soundfont.
		"""
		soundfont = abspath(soundfont)
		if soundfont not in self.__sfids:
			logging.debug('Loading soundfont "%s" having %d sfids loaded', soundfont, len(self.__sfids))
			self.__sfids[soundfont] = self.sfload(soundfont)
		return self.__sfids[soundfont]

	def preset(self, soundfont, moniker):
		"""
		Returns PresetEnum
		moniker may be preset name, or bank:program i.e. "000:000"
		Throws up if not found
		"""
		grp = re.compile('([0-9]+):([0-9]+)').match(moniker)
		if grp:
			for p in self.presets(soundfont):
				if p.bank == int(grp.group(1)) and p.preset == int(grp.group(2)):
					return p
		else:
			for p in self.presets(soundfont):
				if p.name == moniker:
					return p
		raise IndexError(f'Preset "{moniker}" not found')

	def presets(self, soundfont):
		"""
		Returns a list of PresetEnum
		"""
		soundfont = abspath(soundfont)
		if soundfont not in self.__presets:
			self.__presets[soundfont] = list(self.__iter_presets(soundfont))
		return self.__presets[soundfont]

	def __iter_presets(self, soundfont):
		"""
		Generator function which iterates over all possible presets in the
		given soundfont and yields "PresetEnum"
		"""
		sfid = self.sfid(soundfont)
		for bank in range(129):
			for prenum in range(128):
				name = self.sfpreset_name(sfid, bank, prenum)
				if name is not None:
					yield PresetEnum(soundfont, bank, prenum, name)

	def assign_program(self, channel, soundfont, bank, program):
		if 0 <= channel <= 127 and 0 <= bank <= 128 and 0 <= program <= 127:
			if fluidsynth.fluid_synth_bank_select(self.synth, channel, bank):
				raise RuntimeError("fluid_synth_bank_select error")
			sfid = self.sfid(soundfont)
			if fluidsynth.fluid_synth_program_select(self.synth, channel, sfid, bank, program):
				raise RuntimeError("fluid_synth_program_select error")
			sfkey = abspath(soundfont)
			if sfkey not in self.__channels:
				self.__channels[sfkey] = {}
			self.__channels[sfkey][f"{bank:03d}:{program:03d}"] = channel
		else:
			raise ValueError()

	def channel(self, soundfont, bank, program):
		soundfont = abspath(soundfont)
		if soundfont not in self.__channels:
			return None
		key = f"{bank:03d}:{program:03d}"
		if key in self.__channels[soundfont]:
			return self.__channels[soundfont][key]
		return None

	def play_note(self, pitch, velocity, duration, channel = 0, block = True):
		self.start_sequencer()
		self.__sequencer.note_on(time = 0, absolute = False, channel = channel, key = pitch,
			velocity = velocity, dest = self.__synthid)
		self.__sequencer.note_on(time = duration, absolute = False, channel = channel, key = pitch,
			velocity = 0, dest = self.__synthid)
		if block:
			sleep(duration / 1000)

	def play_midicsv_file(self, filename, channel = 0, block = True):
		"""
		Returns the duration in milliseconds of the midi events played.
		"""
		with open(filename) as f:
			csv = f.readlines()
		return self.play_midicsv(csv, channel, block)

	def play_midicsv(self, csv, channel = 0, block = True):
		"""
		Returns the duration in milliseconds of the midi events played.
		"""
		self.start_sequencer()
		first_on_time = None
		last_off_time = None
		for line in csv:
			tup = line.split(',')
			if tup[2].strip(' ').find('Note_on_c') == 0:
				t = int(tup[1])
				if first_on_time is None:
					first_on_time = t
				else:
					last_off_time = t
				if int(tup[5].strip(' \r\n')) == 0:
					self.__sequencer.note_off(time = t, channel = channel, key = int(tup[4]),
						absolute = False, dest = self.__synthid)
				else:
					self.__sequencer.note_on(time = t, channel = channel, key = int(tup[4]),
						velocity = int(tup[5]), absolute = False, dest = self.__synthid)
		duration = last_off_time - first_on_time
		if block:
			sleep(duration / 1000 + 0.1)
		return duration

	def play_midi_file(self, filename, channel = None, block = True):
		"""
		Returns the duration in milliseconds of the midi events played.

		Differs from fluidsynth.play_midi_file in that all notes may
		be played on the given channel, and blocking is optional.
		"""
		if not block and channel is None:
			return super().play_midi_file(filename)

		self.start_sequencer()
		mid = MidiFile(filename)
		tick = 0
		if channel is None:
			for msg in mid.merged_track:
				if msg.type == 'note_on':
					tick += msg.time
					if msg.velocity == 0:
						self.__sequencer.note_off(time = tick, channel = msg.channel,
							key = msg.note, absolute = False, dest = self.__synthid)
					else:
						self.__sequencer.note_on(time = tick, channel = msg.channel,
							key = msg.note, velocity = msg.velocity, absolute = False,
							dest = self.__synthid)
		else:
			for msg in mid.merged_track:
				if msg.type == 'note_on':
					tick += msg.time
					if msg.velocity == 0:
						self.__sequencer.note_off(time = tick, channel = channel,
							key = msg.note, absolute = False, dest = self.__synthid)
					else:
						self.__sequencer.note_on(time = tick, channel = channel,
						key = msg.note, velocity = msg.velocity, absolute = False,
						dest = self.__synthid)
		duration = tick
		if block:
			sleep(duration / 1000 + 0.1)
		return duration

	def sample_int(self, key, channel = 0, velocity = 88, on_duration = 2.0, off_duration = 2.0):
		"""
		Returns tuple of nparray(int16), left and right channels
		"""
		self.all_sounds_off(channel)
		self.noteon(channel, key, velocity)
		samples = self.get_samples(int(self.__jack_client.samplerate * on_duration))
		self.noteoff(channel, key)
		np.append(samples, self.get_samples(int(self.__jack_client.samplerate * off_duration)))
		return (samples[::2], samples[1::2])

	def echo_pygame_event(self, event):
		n, _ = event
		_, pitch, velo, channel = n
		self.noteon(channel, pitch, velo)

	def play_pygame_midi_events(self, events, block = True):
		self.start_sequencer()
		if events[0][0][2] == 0:
			events.pop(0)
		if len(events) == 0:
			return
		first_on_time = events[0][1]
		last_off_time = events[len(events)-1][1]
		for event in events:
			n, t = event
			_, pitch, velo, channel = n
			self.__sequencer.note_on(time = t - first_on_time, absolute = False, channel = channel,
				key = pitch, velocity = velo, dest = self.__synthid)
		if block:
			elapsed_ticks = last_off_time - first_on_time
			sleep(elapsed_ticks / 1000 + 0.05)

	def get_samples_dual(self, length):
		"""
		Returns tuple of nparray(int16), left and right channels
		"""
		left = create_string_buffer(length * 2)
		right = create_string_buffer(length * 2)
		if fluidsynth.fluid_synth_write_s16(self.synth, length,
			byref(left), 0, 1, byref(right), 0, 1):
			raise RuntimeError("fluid_synth_write_s16 failed")
		return (
			np.frombuffer(left[:], dtype = np.int16),
			np.frombuffer(right[:], dtype = np.int16)
		)

	def get_samples_dual_float(self, length):
		"""
		Returns tuple of nparray(float), left and right channels
		"""
		buflen = length * 4
		left = create_string_buffer(buflen)
		right = create_string_buffer(buflen)
		bufptype = POINTER(type(left)) * 2
		buffers = bufptype(pointer(left), pointer(right))
		if fluid_synth_process(self.synth, length, 0, None, 2, buffers) != 0:
			raise RuntimeError("fluid_synth_process failed")
		return (
			np.frombuffer(left[:], dtype = np.float32),
			np.frombuffer(right[:], dtype = np.float32)
		)



# end jack_fluidsynth/__init__.py
