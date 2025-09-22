#  jack_fluidsynth/test.py
#
#  Copyright 2024 Leon Dionne <ldionne@dridesign.sh.cn>
#
import argparse, logging, os
import numpy as np
from time import sleep
from jack_fluidsynth import JackFluidsynth


if __name__ == "__main__":
	p = argparse.ArgumentParser()
	p.add_argument("--verbose", "-v", action = "store_true", help = "Show more detailed debug information")
	p.add_argument("--drums", "-d", action = "store_true", help = "Test drums")
	p.add_argument("--notes", "-n", action = "store_true", help = "Check playing a series of notes")
	p.add_argument("--pygame", "-p", action = "store_true", help = "Check playing pygame midi events")
	p.add_argument("--midi", "-m", action = "store_true", help = "Check playing the output of midi file")
	p.add_argument("--midicsv", "-c", action = "store_true", help = "Check playing the output of midicsv")
	p.add_argument("--wav-capture", "-w", action = "store_true", help = "Test waveform capture")
	p.add_argument("--save-files", "-s", action = "store_true", help = "Test waveform capture and save as files")
	options = p.parse_args()
	logging.basicConfig(
		level = logging.DEBUG if options.verbose else logging.ERROR,
		format = "[%(filename)24s:%(lineno)-4d] %(message)s"
	)

	with JackFluidsynth() as fs:
		fs.auto_connect = True
		filename = os.path.join('res', 'tiny-tim.sf2')
		bank, program = (128, 0) if options.drums else (0, 0)
		fs.assign_program(0, filename, bank, program)
		fs.audio_on()

		if options.notes:
			print("JackFluidsynth.play_note ...", end = '')
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
			print("JackFluidsynth.play_pygame_midi_events ...", end = '')
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
			print("JackFluidsynth.play_midi_file ...", end = '')
			fs.play_midi_file(os.path.join('res', ('drums.mid' if options.drums else 'piano.mid')))
			print("done")
			sleep(0.25)

		if options.midicsv:
			print("JackFluidsynth.play_midicsv_file ...", end = '')
			fs.play_midicsv_file(os.path.join('res', ('midicsv-drums.csv' if options.drums else 'midicsv-piano.csv')))
			print("done")
			sleep(0.25)

		if options.wav_capture or options.save_files:

			fs.audio_off()
			if options.save_files:
				import soundfile as sf
			else:
				from jack_audio_player import JackAudioPlayer
				jplay = JackAudioPlayer(auto_connect = True)

			note_length = fs.samplerate
			tail_length = int(fs.samplerate * 0.25)

			print("JackFluidsynth.get_samples ...", end = '')
			samples = fs.get_samples(80)
			fs.noteon(0, 48, 110)
			samples = fs.get_samples(note_length)
			fs.noteoff(0, 48)
			tail = fs.get_samples(tail_length)
			total_samples = np.concatenate((samples, tail))
			print(' %d samples' % len(total_samples))
			if options.save_files:
				sf.write('get_samples.wav', total_samples, int(fs.samplerate * 2), subtype = 'PCM_16')
			else:
				print('   JackAudioPlayer.play_int16_interleaved (%s) ...' % samples.dtype, end = '')
				jplay.play_int16_interleaved(total_samples)
				print("done")

			print("JackFluidsynth.get_samples_dual ...", end = '')
			left, right = fs.get_samples_dual(80)
			fs.noteon(0, 48, 110)
			left, right = fs.get_samples_dual(note_length)
			fs.noteoff(0, 48)
			tail_left, tail_right = fs.get_samples_dual(tail_length)
			total_left = np.concatenate((left, tail_left))
			total_right = np.concatenate((right, tail_right))
			print(' %d, %d samples' % (len(total_left), len(total_right)))
			if options.save_files:
				sf.write('get_samples_dual_left.wav', total_left, fs.samplerate, subtype = 'PCM_16')
				sf.write('get_samples_dual_right.wav', total_right, fs.samplerate, subtype = 'PCM_16')
			else:
				print('   JackAudioPlayer.play_int16_stereo (%s) ...' % left.dtype, end = '')
				jplay.play_int16_stereo(total_left, total_right)
				print("done")

			print("JackFluidsynth.get_samples_dual_float ...", end = '')
			left, right = fs.get_samples_dual_float(80)
			fs.noteon(0, 48, 110)
			left, right = fs.get_samples_dual_float(note_length)
			fs.noteoff(0, 48)
			tail_left, tail_right = fs.get_samples_dual_float(tail_length)
			total_left = np.concatenate((left, tail_left))
			total_right = np.concatenate((right, tail_right))

			print(' %d, %d samples' % (len(total_left), len(total_right)))
			if options.save_files:
				sf.write('float_samples_left.wav', total_left, fs.samplerate, subtype = 'FLOAT')
				sf.write('float_samples_right.wav', total_right, fs.samplerate, subtype = 'FLOAT')
			else:
				print('   JackAudioPlayer.play_native_stereo (%s) ...' % total_left.dtype, end = '')
				jplay.play_native_stereo(total_left, total_right)
				print("done")

#  end jack_fluidsynth/test.py
