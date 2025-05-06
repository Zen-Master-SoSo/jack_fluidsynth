#  jack_fluidsynth/test.py
#
#  Copyright 2024 liyang <liyang@veronica>
#
import argparse, logging, os
import numpy as np
from time import sleep
from jack_fluidsynth import Fluidsynth


if __name__ == "__main__":
	p = argparse.ArgumentParser()
	p.add_argument("--verbose", "-v", action="store_true", help="Show more detailed debug information")
	p.add_argument("--drums", "-d", action="store_true", help="Test drums")
	p.add_argument("--notes", "-n", action="store_true", help="Check playing a series of notes")
	p.add_argument("--pygame", "-p", action="store_true", help="Check playing pygame midi events")
	p.add_argument("--midi", "-m", action="store_true", help="Check playing the output of midi file")
	p.add_argument("--midicsv", "-c", action="store_true", help="Check playing the output of midicsv")
	p.add_argument("--wav-capture", "-w", action="store_true", help="Test waveform capture")
	p.add_argument("--save-files", "-s", action="store_true", help="Test waveform capture and save as files")
	options = p.parse_args()
	logging.basicConfig(
		level = logging.DEBUG if options.verbose else logging.ERROR,
		format = "[%(filename)24s:%(lineno)-4d] %(message)s"
	)

	with Fluidsynth() as fs:
		fs.auto_connect = True
		filename = os.path.join('res', 'tiny-tim.sf2')
		bank, program = (128, 0) if options.drums else (0, 0)
		fs.assign_program(0, filename, bank, program)
		fs.audio_on()

		if options.notes:
			print("Fluidsynth.play_note ...", end='')
			fs.play_note(60 , 100 , 400 )
			fs.play_note(67 , 100 , 400 )
			fs.play_note(64 , 100 , 198 )
			fs.play_note(62 , 100 , 198 )
			fs.play_note(60 , 100 , 198 )
			fs.play_note(72 , 100 , 800 )
			fs.play_note(67 , 100 , 800 )
			print("done")
			sleep(0.25)

		if options.pygame:
			print("Fluidsynth.play_pygame_midi_events ...", end='')
			fs.play_pygame_midi_events([
				[[144, 48, 109, 0], 1135],
				[[144, 48, 0, 0], 1267],
				[[144, 50, 107, 0], 1425],
				[[144, 50, 0, 0], 1540],
				[[144, 52, 89, 0], 1633],
				[[144, 52, 0, 0], 1755],
				[[144, 50, 96, 0], 1949],
				[[144, 50, 0, 0], 2099],
				[[144, 48, 112, 0], 2124],
				[[144, 48, 0, 0], 2252]
			])
			print("done")
			sleep(0.25)

		if options.midi:
			print("Fluidsynth.play_midi_file ...", end='')
			fs.play_midi_file(os.path.join('res', ('drums.mid' if options.drums else 'piano.mid')))
			print("done")
			sleep(0.25)

		if options.midicsv:
			print("Fluidsynth.play_midicsv_file ...", end='')
			fs.play_midicsv_file(os.path.join('res', ('midicsv-drums.csv' if options.drums else 'midicsv-piano.csv')))
			print("done")
			sleep(0.25)

		if options.wav_capture or options.save_files:

			fs.audio_off()
			if options.save_files:
				import soundfile as sf
			elif fs.use_jack:
				from jack_audio import JackPlayer
				jplay = JackPlayer()
			else:
				from pygame import mixer
				from pygame.mixer import Sound
				from fluidsynth import raw_audio_string
				mixer.init()

			print("Fluidsynth.get_samples_dual_float ...", end='')
			left, right = fs.get_samples_dual_float(80)
			fs.noteon(0, 48, 110)
			left, right = fs.get_samples_dual_float(fs.samplerate)
			fs.noteoff(0, 48)
			print(' %d, %d samples' % (len(left), len(right)))
			if options.save_files:
				sf.write('float_samples_left.wav', left, fs.samplerate, subtype='FLOAT')
				sf.write('float_samples_right.wav', right, fs.samplerate, subtype='FLOAT')
			elif fs.use_jack:
				print('   JackPlayer.play_native_stereo (%s) ...' % left.dtype, end='')
				jplay.play_native_stereo(left, right)
				print("done")
			else:
				dtype = np.int16
				s = Sound(raw_audio_string(left.astype(dtype)))
				s.play()
				print('   sleep %.2f seconds ...' % s.get_length(), end='')
				sleep(s.get_length())
				print("done")
				s = Sound(raw_audio_string(right.astype(dtype)))
				s.play()
				print('   sleep %.2f seconds ...' % s.get_length(), end='')
				sleep(s.get_length())
				print("done")

			print("Fluidsynth.get_samples ...", end='')
			fs.noteon(0, 48, 110)
			samples = fs.get_samples(fs.samplerate)
			fs.noteoff(0, 48)
			print(' %d samples' % len(samples))
			if options.save_files:
				sf.write('get_samples.wav', samples, int(fs.samplerate * 2), subtype='PCM_16')
			elif fs.use_jack:
				print('   JackPlayer.play_int16_interleaved (%s) ...' % samples.dtype, end='')
				jplay.play_int16_interleaved(samples)
				print("done")
			else:
				s = Sound(raw_audio_string(samples[::2]))
				s.play()
				print('   sleep %.2f seconds ...' % s.get_length(), end='')
				sleep(s.get_length())
				print("done")

			print("Fluidsynth.get_samples_dual ...", end='')
			fs.noteon(0, 48, 110)
			left, right = fs.get_samples_dual(fs.samplerate)
			fs.noteoff(0, 48)
			print(' %d, %d samples' % (len(left), len(right)))
			if options.save_files:
				sf.write('get_samples_dual_left.wav', left, fs.samplerate, subtype='PCM_16')
				sf.write('get_samples_dual_right.wav', right, fs.samplerate, subtype='PCM_16')
			elif fs.use_jack:
				print('   JackPlayer.play_int16_stereo (%s) ...' % left.dtype, end='')
				jplay.play_int16_stereo(left, right)
				print("done")
			else:
				s = Sound(raw_audio_string(left))
				s.play()
				print('   sleep %.2f seconds ...' % s.get_length(), end='')
				sleep(s.get_length())
				print("done")
				s = Sound(raw_audio_string(right))
				s.play()
				print('   sleep %.2f seconds ...' % s.get_length(), end='')
				sleep(s.get_length())
				print("done")


#  end jack_fluidsynth/test.py
