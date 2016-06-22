#!/usr/bin/env python3

"""Modifed version"""

__author__ = "Boss"
__version__ = "0.1"
__license__ = "BSD"

import io, os, subprocess, wave, base64
import math, audioop, collections, threading
import platform, stat
import json
import timeit
import random
from struct import *
import requests
import threading
from threading import Thread
import time

try: # try to use python2 module
    from urllib2 import Request, urlopen, URLError, HTTPError
except ImportError: # otherwise, use python3 module
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError

# define exceptions
class WaitTimeoutError(Exception): pass
class RequestError(Exception): pass
class UnknownValueError(Exception): pass

class AudioSource(object):
    def __init__(self):
        raise NotImplementedError("this is an abstract class")

    def __enter__(self):
        raise NotImplementedError("this is an abstract class")

    def __exit__(self, exc_type, exc_value, traceback):
        raise NotImplementedError("this is an abstract class")

try:
    import pyaudio

    class Microphone(AudioSource):
        """
        This is available if PyAudio is available, and is undefined otherwise.

        Creates a new ``Microphone`` instance, which represents a physical microphone on the computer. Subclass of ``AudioSource``.

        If ``device_index`` is unspecified or ``None``, the default microphone is used as the audio source. Otherwise, ``device_index`` should be the index of the device to use for audio input.

        A device index is an integer between 0 and ``pyaudio.get_device_count() - 1`` (assume we have used ``import pyaudio`` beforehand) inclusive. It represents an audio device such as a microphone or speaker. See the `PyAudio documentation <http://people.csail.mit.edu/hubert/pyaudio/docs/>`__ for more details.

        The microphone audio is recorded in chunks of ``chunk_size`` samples, at a rate of ``sample_rate`` samples per second (Hertz).

        Higher ``sample_rate`` values result in better audio quality, but also more bandwidth (and therefore, slower recognition). Additionally, some machines, such as some Raspberry Pi models, can't keep up if this value is too high.

        Higher ``chunk_size`` values help avoid triggering on rapidly changing ambient noise, but also makes detection less sensitive. This value, generally, should be left at its default.
        """
        def __init__(self, device_index = None, sample_rate = 16000, chunk_size = 1024):
            assert device_index is None or isinstance(device_index, int), "Device index must be None or an integer"
            if device_index is not None: # ensure device index is in range
                audio = pyaudio.PyAudio(); count = audio.get_device_count(); audio.terminate() # obtain device count
                assert 0 <= device_index < count, "Device index out of range"
            assert isinstance(sample_rate, int) and sample_rate > 0, "Sample rate must be a positive integer"
            assert isinstance(chunk_size, int) and chunk_size > 0, "Chunk size must be a positive integer"
            self.device_index = device_index
            self.format = pyaudio.paInt16 # 16-bit int sampling
            self.SAMPLE_WIDTH = pyaudio.get_sample_size(self.format) # size of each sample
            self.SAMPLE_RATE = sample_rate # sampling rate in Hertz
            self.CHUNK = chunk_size # number of frames stored in each buffer

            self.audio = None
            self.stream = None

        def __enter__(self):
            assert self.stream is None, "This audio source is already inside a context manager"
            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                input_device_index = self.device_index, channels = 1,
                format = self.format, rate = self.SAMPLE_RATE, frames_per_buffer = self.CHUNK,
                input = True, # stream is an input stream
            )
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            if not self.stream.is_stopped():
                self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            self.audio.terminate()
except ImportError:
    pass

class WavFile(AudioSource):
    """
    Creates a new ``WavFile`` instance given a WAV audio file `filename_or_fileobject`. Subclass of ``AudioSource``.

    If ``filename_or_fileobject`` is a string, then it is interpreted as a path to a WAV audio file (mono or stereo) on the filesystem. Otherwise, ``filename_or_fileobject`` should be a file-like object such as ``io.BytesIO`` or similar.

    Note that the WAV file must be in PCM/LPCM format; WAVE_FORMAT_EXTENSIBLE and compressed WAV are not supported and may result in undefined behaviour.
    """

    def __init__(self, filename_or_fileobject):
        if isinstance(filename_or_fileobject, str):
            self.filename = filename_or_fileobject
        else:
            assert filename_or_fileobject.read, "Given WAV file must be a filename string or a file-like object"
            self.filename = None
            self.wav_file = filename_or_fileobject
        self.stream = None
        self.DURATION = None

    def __enter__(self):
        assert self.stream is None, "This audio source is already inside a context manager"
        if self.filename is not None: self.wav_file = open(self.filename, "rb")
        self.wav_reader = wave.open(self.wav_file, "rb")
        assert 1 <= self.wav_reader.getnchannels() <= 2, "Audio must be mono or stereo"
        self.SAMPLE_WIDTH = self.wav_reader.getsampwidth()
        self.SAMPLE_RATE = self.wav_reader.getframerate()
        self.CHUNK = 4096
        self.FRAME_COUNT = self.wav_reader.getnframes()
        self.DURATION = self.FRAME_COUNT / float(self.SAMPLE_RATE)
        self.stream = WavFile.WavStream(self.wav_reader)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.filename: self.wav_file.close()
        self.stream = None
        self.DURATION = None

    class WavStream(object):
        def __init__(self, wav_reader):
            self.wav_reader = wav_reader

        def read(self, size = -1):
            buffer = self.wav_reader.readframes(self.wav_reader.getnframes() if size == -1 else size)
            if isinstance(buffer, str) and str is not bytes: buffer = b"" # workaround for https://bugs.python.org/issue24608, unfortunately only fixes the issue for little-endian systems
            if self.wav_reader.getnchannels() != 1: # stereo audio
                buffer = audioop.tomono(buffer, self.wav_reader.getsampwidth(), 1, 1) # convert stereo audio data to mono
            return buffer

class AudioData(object):
    def __init__(self, frame_data, sample_rate, sample_width):
        assert sample_rate > 0, "Sample rate must be a positive integer"
        assert sample_width % 1 == 0 and sample_width > 0, "Sample width must be a positive integer"
        self.frame_data = frame_data
        self.sample_rate = sample_rate
        self.sample_width = int(sample_width)

    def get_wav_data(self):
        """
        Returns a byte string representing the contents of a WAV file containing the audio represented by the ``AudioData`` instance.

        Writing these bytes directly to a file results in a valid WAV file.
        """
        with io.BytesIO() as wav_file:
            wav_writer = wave.open(wav_file, "wb")
            try: # note that we can't use context manager due to Python 2 not supporting it
                wav_writer.setframerate(self.sample_rate)
                wav_writer.setsampwidth(self.sample_width)
                wav_writer.setnchannels(1)
                wav_writer.writeframes(self.frame_data)
            finally:  # make sure resources are cleaned up
                wav_writer.close()
            wav_data = wav_file.getvalue()
        return wav_data

    def get_flac_data(self):
        """
        Returns a byte string representing the contents of a FLAC file containing the audio represented by the ``AudioData`` instance.

        Writing these bytes directly to a file results in a valid FLAC file.
        """
        wav_data = self.get_wav_data()

        # determine which converter executable to use
        system = platform.system()
        path = os.path.dirname(os.path.abspath(__file__)) # directory of the current module file, where all the FLAC bundled binaries are stored
        flac_converter = shutil_which("flac") # check for installed version first
        if flac_converter is None: # flac utility is not installed
            if system == "Windows" and platform.machine() in ["i386", "x86", "x86_64", "AMD64"]: # Windows NT, use the bundled FLAC conversion utility
                flac_converter = os.path.join(path, "flac-win32.exe")
            elif system == "Linux" and platform.machine() in ["i386", "x86", "x86_64", "AMD64"]:
                flac_converter = os.path.join(path, "flac-linux-i386")
            elif system == "Darwin" and platform.machine() in ["i386", "x86", "x86_64", "AMD64"]:
                flac_converter = os.path.join(path, "flac-mac")
            else:
                raise OSError("FLAC conversion utility not available - consider installing the FLAC command line application using `brew install flac` or your operating system's equivalent")

        # mark FLAC converter as executable
        try:
            stat_info = os.stat(flac_converter)
            os.chmod(flac_converter, stat_info.st_mode | stat.S_IEXEC)
        except OSError: pass

        # run the FLAC converter with the WAV data to get the FLAC data
        process = subprocess.Popen("\"{0}\" --stdout --totally-silent --best -".format(flac_converter), stdin=subprocess.PIPE, stdout=subprocess.PIPE, shell=True)
        flac_data, stderr = process.communicate(wav_data)
        return flac_data

class Recognizer(AudioSource):
    def __init__(self):
        """
        Creates a new ``Recognizer`` instance, which represents a collection of speech recognition functionality.
        """
        self.energy_threshold = 300 # minimum audio energy to consider for recording
        self.dynamic_energy_threshold = True
        self.dynamic_energy_adjustment_damping = 0.15
        self.dynamic_energy_ratio = 1.5
        self.pause_threshold = 0.8 # seconds of non-speaking audio before a phrase is considered complete
        self.phrase_threshold = 0.3 # minimum seconds of speaking audio before we consider the speaking audio a phrase - values below this are ignored (for filtering out clicks and pops)
        self.non_speaking_duration = 0.5 # seconds of non-speaking audio to keep on both sides of the recording
        self.output_sentence = ""
        self.time_of_last_response = 0
        self.finalThreadStarted = 0

    def record(self, source, duration = None, offset = None):
        """
        Records up to ``duration`` seconds of audio from ``source`` (an ``AudioSource`` instance) starting at ``offset`` (or at the beginning if not specified) into an ``AudioData`` instance, which it returns.

        If ``duration`` is not specified, then it will record until there is no more audio input.
        """
        assert isinstance(source, AudioSource), "Source must be an audio source"

        frames = io.BytesIO()
        seconds_per_buffer = (source.CHUNK + 0.0) / source.SAMPLE_RATE
        elapsed_time = 0
        offset_time = 0
        offset_reached = False
        while True: # loop for the total number of chunks needed
            if offset and not offset_reached:
                offset_time += seconds_per_buffer
                if offset_time > offset:
                    offset_reached = True

            buffer = source.stream.read(source.CHUNK)
            if len(buffer) == 0: break

            if offset_reached or not offset:
                elapsed_time += seconds_per_buffer
                if duration and elapsed_time > duration: break

                frames.write(buffer)

        frame_data = frames.getvalue()
        frames.close()
        return AudioData(frame_data, source.SAMPLE_RATE, source.SAMPLE_WIDTH)


    def adjust_for_ambient_noise(self, source, duration = 1):
        """
        Adjusts the energy threshold dynamically using audio from ``source`` (an ``AudioSource`` instance) to account for ambient noise.

        Intended to calibrate the energy threshold with the ambient energy level. Should be used on periods of audio without speech - will stop early if any speech is detected.

        The ``duration`` parameter is the maximum number of seconds that it will dynamically adjust the threshold for before returning. This value should be at least 0.5 in order to get a representative sample of the ambient noise.
        """
        assert isinstance(source, AudioSource), "Source must be an audio source"
        assert self.pause_threshold >= self.non_speaking_duration >= 0

        seconds_per_buffer = (source.CHUNK + 0.0) / source.SAMPLE_RATE
        elapsed_time = 0

        # adjust energy threshold until a phrase starts
        while True:
            elapsed_time += seconds_per_buffer
            if elapsed_time > duration: break
            buffer = source.stream.read(source.CHUNK)
            energy = audioop.rms(buffer, source.SAMPLE_WIDTH) # energy of the audio signal

            # dynamically adjust the energy threshold using assymmetric weighted average
            damping = self.dynamic_energy_adjustment_damping ** seconds_per_buffer # account for different chunk sizes and rates
            target_energy = energy * self.dynamic_energy_ratio
            self.energy_threshold = self.energy_threshold * damping + target_energy * (1 - damping)

    def replace_output_sentence(self, sentence):
        self.output_sentence = sentence
        print self.output_sentence

    def handle_google_result(self, thread_name, responses_lines_from_google, time_of_responses):
        output_sentence_length = len(self.output_sentence)
        for response in responses_lines_from_google:
            if thread_name == "finalThread":
                self.replace_output_sentence(response)
                self.time_of_last_response = time_of_responses
            elif len(response) > output_sentence_length:
                if response != self.output_sentence:
                    self.replace_output_sentence(response)
                    self.time_of_last_response = time_of_responses
            elif len(response) == output_sentence_length and time_of_responses > self.time_of_last_response:
                if response != self.output_sentence:
                    self.replace_output_sentence(response)
                    self.time_of_last_response = time_of_responses

    def get_output_sentence(self):
        return self.output_sentence

    def set_output_sentence(self, new_output_sentence):
        self.output_sentence = new_output_sentence

    def listenMo(self, source, timeout = None):
        """
        Records a single phrase from ``source`` (an ``AudioSource`` instance) into an ``AudioData`` instance, which it returns.

        This is done by waiting until the audio has an energy above ``recognizer_instance.energy_threshold`` (the user has started speaking), and then recording until it encounters ``recognizer_instance.pause_threshold`` seconds of non-speaking or there is no more audio input. The ending silence is not included.

        The ``timeout`` parameter is the maximum number of seconds that it will wait for a phrase to start before giving up and throwing an ``speech_recognition.WaitTimeoutError`` exception. If ``timeout`` is ``None``, it will wait indefinitely.
        """
        assert isinstance(source, AudioSource), "Source must be an audio source"
        assert self.pause_threshold >= self.non_speaking_duration >= 0

        seconds_per_buffer = (source.CHUNK + 0.0) / source.SAMPLE_RATE
        pause_buffer_count = int(math.ceil(self.pause_threshold / seconds_per_buffer)) # number of buffers of non-speaking audio before the phrase is complete
        phrase_buffer_count = int(math.ceil(self.phrase_threshold / seconds_per_buffer)) # minimum number of buffers of speaking audio before we consider the speaking audio a phrase
        non_speaking_buffer_count = int(math.ceil(self.non_speaking_duration / seconds_per_buffer)) # maximum number of buffers of non-speaking audio to retain before and after
        threads = []
        duration_t = 2
        start_time = 0
        # read audio input for phrases until there is a phrase that is long enough
        elapsed_time = 0 # number of seconds of audio read
        while True:
            frames = collections.deque()
            frames2 = collections.deque()
            # store audio input until the phrase starts
            while True:
                elapsed_time += seconds_per_buffer
                if timeout and elapsed_time > timeout: # handle timeout if specified
                    raise WaitTimeoutError("listening timed out")

                buffer = source.stream.read(source.CHUNK)
                if len(buffer) == 0: break # reached end of the stream
                frames.append(buffer)
                if len(frames) > non_speaking_buffer_count: # ensure we only keep the needed amount of non-speaking buffers
                    frames.popleft()

                # detect whether speaking has started on audio input
                energy = audioop.rms(buffer, source.SAMPLE_WIDTH) # energy of the audio signal
                # print "Energy: %s energy_threshold: %s" % (str(energy), str(self.energy_threshold))
                if energy > self.energy_threshold: break

                # dynamically adjust the energy threshold using assymmetric weighted average
                if self.dynamic_energy_threshold:
                    damping = self.dynamic_energy_adjustment_damping ** seconds_per_buffer # account for different chunk sizes and rates
                    target_energy = energy * self.dynamic_energy_ratio
                    self.energy_threshold = self.energy_threshold * damping + target_energy * (1 - damping)

            # read audio input until the phrase ends
            pause_count, phrase_count = 0, 0
            while True:
                elapsed_time += seconds_per_buffer
                if (start_time == 0): start_time = elapsed_time
                buffer = source.stream.read(source.CHUNK)
                if len(buffer) == 0: break # reached end of the stream
                #Main frame uses to store complated voice data
                frames.append(buffer)
                #Sub frame uses to store partial voice data (every 1 sec)
                frames2.append(buffer)

                phrase_count += 1

                # check if speaking has stopped for longer than the pause threshold on the audio input
                energy = audioop.rms(buffer, source.SAMPLE_WIDTH) # energy of the audio signal
                if energy > self.energy_threshold:
                    diff = elapsed_time - start_time
                    if diff >= duration_t:
                        start_time = 0
                        diff = 0
                        frame_data = b"".join(list(frames2))
                        partial_audioData = AudioData(frame_data, source.SAMPLE_RATE, source.SAMPLE_WIDTH)
                        #Create a request to google
                        # testThread = self.myThread(partial_audioData,"AIzaSyC1GY4NPun44trK7g7V-TNmp642aIugTCQ","en-US",False, self)
                        testThread = self.myThread(partial_audioData,None,"en-US",False, self)
                        testThread.start()
                        threads.append(testThread)
                        # frames2 = collections.deque()
                    pause_count = 0
                else:
                    pause_count += 1
                if pause_count > pause_buffer_count: # end of the phrase
                    break
            # check how long the detected phrase is, and retry listening if the phrase is too short
            phrase_count -= pause_count
            if phrase_count >= phrase_buffer_count: break # phrase is long enough, stop listening

        #Sending a request with complated voice data
        for i in range(pause_count - non_speaking_buffer_count): frames.pop() # remove extra non-speaking frames at the end
        frame_data = b"".join(list(frames))
        full_data = AudioData(frame_data, source.SAMPLE_RATE, source.SAMPLE_WIDTH)
        # finalThread = self.myThread(full_data,"AIzaSyC1GY4NPun44trK7g7V-TNmp642aIugTCQ","en-US",False, self)
        finalThread = self.myThread(full_data,None,"en-US",False, self)
        finalThread.setName("finalThread")
        finalThread.start()

        self.finalThreadStarted = 1

        # Waiting for all sub threads to be finished
        for t in threads:
            t.join()

        # # obtain frame data
        # start = timeit.default_timer()
        # for i in range(pause_count - non_speaking_buffer_count): frames.pop() # remove extra non-speaking frames at the end
        # frame_data = b"".join(list(frames))
        # return AudioData(frame_data, source.SAMPLE_RATE, source.SAMPLE_WIDTH), start

    def listen(self, source, timeout = None):
        assert isinstance(source, AudioSource), "Source must be an audio source"
        assert source.stream is not None, "Audio source must be entered before listening, see documentation for `AudioSource`; are you using `source` outside of a `with` statement?"
        assert self.pause_threshold >= self.non_speaking_duration >= 0

        seconds_per_buffer = (source.CHUNK + 0.0) / source.SAMPLE_RATE
        pause_buffer_count = int(math.ceil(self.pause_threshold / seconds_per_buffer)) # number of buffers of non-speaking audio before the phrase is complete
        phrase_buffer_count = int(math.ceil(self.phrase_threshold / seconds_per_buffer)) # minimum number of buffers of speaking audio before we consider the speaking audio a phrase
        non_speaking_buffer_count = int(math.ceil(self.non_speaking_duration / seconds_per_buffer)) # maximum number of buffers of non-speaking audio to retain before and after

        # read audio input for phrases until there is a phrase that is long enough
        elapsed_time = 0 # number of seconds of audio read
        while True:
            frames = collections.deque()

            # store audio input until the phrase starts
            while True:
                elapsed_time += seconds_per_buffer
                if timeout and elapsed_time > timeout: # handle timeout if specified
                    raise WaitTimeoutError("listening timed out")

                buffer = source.stream.read(source.CHUNK)
                if len(buffer) == 0: break # reached end of the stream
                frames.append(buffer)
                if len(frames) > non_speaking_buffer_count: # ensure we only keep the needed amount of non-speaking buffers
                    frames.popleft()

                # detect whether speaking has started on audio input
                energy = audioop.rms(buffer, source.SAMPLE_WIDTH) # energy of the audio signal
                if energy > self.energy_threshold: break

                # dynamically adjust the energy threshold using assymmetric weighted average
                if self.dynamic_energy_threshold:
                    damping = self.dynamic_energy_adjustment_damping ** seconds_per_buffer # account for different chunk sizes and rates
                    target_energy = energy * self.dynamic_energy_ratio
                    self.energy_threshold = self.energy_threshold * damping + target_energy * (1 - damping)

            # read audio input until the phrase ends
            pause_count, phrase_count = 0, 0
            while True:
                elapsed_time += seconds_per_buffer

                buffer = source.stream.read(source.CHUNK)
                if len(buffer) == 0: break # reached end of the stream
                frames.append(buffer)
                phrase_count += 1

                # check if speaking has stopped for longer than the pause threshold on the audio input
                energy = audioop.rms(buffer, source.SAMPLE_WIDTH) # energy of the audio signal
                if energy > self.energy_threshold:
                    pause_count = 0
                else:
                    pause_count += 1
                if pause_count > pause_buffer_count: # end of the phrase
                    break

            # check how long the detected phrase is, and retry listening if the phrase is too short
            phrase_count -= pause_count
            if phrase_count >= phrase_buffer_count: break # phrase is long enough, stop listening

        # obtain frame data
        for i in range(pause_count - non_speaking_buffer_count): frames.pop() # remove extra non-speaking frames at the end
        frame_data = b"".join(list(frames))

        return AudioData(frame_data, source.SAMPLE_RATE, source.SAMPLE_WIDTH)

    def listen_in_background(self, source, callback):
        """
        Spawns a thread to repeatedly record phrases from ``source`` (an ``AudioSource`` instance) into an ``AudioData`` instance and call ``callback`` with that ``AudioData`` instance as soon as each phrase are detected.

        Returns a function object that, when called, requests that the background listener thread stop, and waits until it does before returning. The background thread is a daemon and will not stop the program from exiting if there are no other non-daemon threads.

        Phrase recognition uses the exact same mechanism as ``recognizer_instance.listen(source)``.

        The ``callback`` parameter is a function that should accept two parameters - the ``recognizer_instance``, and an ``AudioData`` instance representing the captured audio. Note that ``callback`` function will be called from a non-main thread.
        """
        assert isinstance(source, AudioSource), "Source must be an audio source"
        running = [True]
        def threaded_listen():
            with source as s:
                while running[0]:
                    try: # listen for 1 second, then check again if the stop function has been called
                        audio = self.listen(s, 1)
                    except WaitTimeoutError: # listening timed out, just try again
                        pass
                    else:
                        if running[0]:
                            start = timeit.default_timer()
                            callback(self, audio, start)
        def stopper():
            running[0] = False
            listener_thread.join() # block until the background thread is done
        listener_thread = threading.Thread(target=threaded_listen)
        listener_thread.daemon = True
        listener_thread.start()
        return stopper

    def recognize_sphinx(self, audio_data, language = "en-US", show_all = False):
        """
        ;wip
        """
        assert isinstance(audio_data, AudioData), "`audio_data` must be audio data"
        assert isinstance(language, str), "`language` must be a string"

        flac_data, sample_rate = audio_data.get_flac_data(), audio_data.sample_rate

        # no transcriptions available
        raise UnknownValueError()

    class myThread (threading.Thread):
        def __init__(self, audio_data, key = None, language = "en-US", show_all = False, parent = None):
            assert isinstance(audio_data, AudioData), "`audio_data` must be audio data"
            assert key is None or isinstance(key, str), "`key` must be `None` or a string"
            assert isinstance(language, str), "`language` must be a string"
            threading.Thread.__init__(self)
            self.parent = parent
            self.result = []
            self.response_lines = []
            self.upstream_url = "https://www.google.com/speech-api/full-duplex/v1/up?key=%(key)s&pair=%(pair)s&lang=en-US&client=chromium&continuous=true&interim=true&pFilter=0"
            self.downstream_url = "https://www.google.com/speech-api/full-duplex/v1/down?pair=%(pair)s"
            if key is None:
                self.api_key = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
            else:
                self.api_key = key
            self.timeSinceResponse = 0
            self.response = ""
            self.connectionSuccessful = False
            self.no_result = False
            self.audio_data = audio_data
            self.flac_data = self.audio_data.get_flac_data()
            self.sample_rate = self.audio_data.sample_rate
            self.language = language
            self.show_all = show_all
            self.upstream_headers = {"Content-Type": "audio/x-flac; rate={0}".format(self.sample_rate)}

        def run(self):
            # print "Starting " + self.name
            self.start2()
            # print "Exiting " + self.name
            # self.parent.handle_google_result(self.name, self.result, timeit.default_timer())
            # if self.name == "finalThread":
            #     print "Final result: " + str(self.result)

        def getPair(self):
            return hex(random.getrandbits(64))[2:-1]

        def gen_data(self):
            counter = 0;
            while True:
                item = self.flac_data
                info = [item[i:i+8192] for i in range(0, len(item), 8192)]
                # if item:
                #     print("%d bytes sent" % len(info[0]))
                #     #Sending the whole FLAC data
                #     yield item
                # return
                if counter < len(info):
                    # print("%d bytes sent" % len(info[counter]))
                    yield info[counter]
                else:
                    if self.no_result or self.timeSinceResponse > 2:
                        # self.result.append(self.response)
                        # print "finished"
                        return #Google is Done Responding, close UpStream
                    # print "test"
                    time.sleep(.5)
                    self.timeSinceResponse += .5
                    yield "00000000"
                counter += 1

        def final(self):
            try:
              response = json.loads(self.response)
              if response['result']:
                  if 'final' in response['result'][0]:
                      return response['result'][0]['final']
            except Exception, e:
              # assuming invalid JSON
              return False
            return False

        def upstream(self, url):
            result = self.upsession.post(url, headers=self.upstream_headers, data=self.gen_data())
            upstream_request_status = result.status_code
            upstream_request_content = result.content
            if result.status_code != 200:
                print ("failed request, status code %d, info: %s" % (upstream_request_status,result.content))
                # self.start2()
                raise RuntimeException("upstream request exception")
            # print ("request upstream content submission response is: %i" % len(upstream_request_content))
            # print ("request upstream content submission response is: %s" % str(upstream_request_content))

        def downstream(self, url):
            r = self.downsession.get(url, stream=True)
            self.status_code = r.status_code
            if r.status_code == 200:
                for line in r.iter_lines():
                    if not self.parent.finalThreadStarted or self.name == "finalThread":
                        self.timeSinceResponse = 0
                        self.response = line
                        if line == '{"result":[]}':
                            # print "Connection successful"
                            # Google sends back an empty result signifying a successful connection
                            if not self.connectionSuccessful:
                                self.connectionSuccessful = True
                            else: # another empty response means Google couldn't find anything in the audio ...
                                # Make the result pretty / match normal results
                                print ("No Recongnizable Dialogue, closing stream")
                                self.result.append('{"result":[{"alternative":[{"transcript":"","confidence":0.99999}],"final":true}],"result_index":0}')
                                self.no_result = True
                        if self.final():
                            # self.result.append(line)
                            if self.name == "finalThread":
                                t = json.loads(line)
                                transcript = t['result'][0]['alternative'][0]['transcript']
                                # self.result.append(transcript)
                                # while not self.parent.exitFlag:
                                #     pass
                                self.parent.set_output_sentence(transcript)
                                print "Final result: " + self.parent.get_output_sentence()
                                # print "final result: " + t['result'][0]['alternative'][0]['transcript']
                            self.response = ""
                        else:
                            # print self.name + ": " + line
                            # if self.name != "finalThread":
                                response = json.loads(line)
                                transcript = ""
                                try:
                                    if len(response['result']) != 0 :
                                        transcript = response['result'][0]['alternative'][0]['transcript']
                                except:
                                    transcript = response['result']
                                finally:
                                    # self.result.append(transcript)
                                    if len(transcript) > len(self.parent.get_output_sentence()):
                                        self.parent.set_output_sentence(transcript)
                                        print self.name + ": " + self.parent.get_output_sentence()
                                # print "Interim result of thread %s: %s" % (self.name, transcript)
                            # print a['result']
                            # print self.response
                    else:
                        break;
                    # print ("request downstream content response is: %s" % self.response_lines)
            else:
                print ("Failed to connect downstream. Response is: %s \n %s" %(r.status_code, r.content))
                # print ("Failed to connect downstream")
                if self.name == "finalThread":
                    print ("Restarting Attempt")
                    self.start2()

        def stop(self):
            self.downstream_thread.join()
            self.upstream_thread.join()

        def start2(self):
                pair = self.getPair()
                upstream_url = self.upstream_url % {"pair": pair, "key": self.api_key}
                downstream_url = self.downstream_url % {"pair": pair, "key": self.api_key}
                # print "%s pair: %s" % (self.name, pair)
                self.upsession = requests.Session()
                self.downsession = requests.Session()
                self.upstream_thread = Thread(target=self.upstream, args=(upstream_url,))
                self.downstream_thread = Thread(target=self.downstream, args=(downstream_url,))
                self.downstream_thread.start()
                self.upstream_thread.start()
                self.stop()

    def recognize_google(self, audio_data, key = None, language = "en-US", show_all = False):
        """
        Performs speech recognition on ``audio_data`` (an ``AudioData`` instance), using the Google Speech Recognition API.

        The Google Speech Recognition API key is specified by ``key``. If not specified, it uses a generic key that works out of the box. This should generally be used for personal or testing purposes only, as it **may be revoked by Google at any time**.

        To obtain your own API key, simply following the steps on the `API Keys <http://www.chromium.org/developers/how-tos/api-keys>`__ page at the Chromium Developers site. In the Google Developers Console, Google Speech Recognition is listed as "Speech API".

        The recognition language is determined by ``language``, an IETF language tag like `"en-US"` or ``"en-GB"``, defaulting to US English. A list of supported language codes can be found `here <http://stackoverflow.com/questions/14257598/>`__. Basically, language codes can be just the language (``en``), or a language with a dialect (``en-US``).

        Returns the most likely transcription if ``show_all`` is false (the default). Otherwise, returns the raw API response as a JSON dictionary.

        Raises a ``speech_recognition.UnknownValueError`` exception if the speech is unintelligible. Raises a ``speech_recognition.RequestError`` exception if the key isn't valid, the quota for the key is maxed out, or there is no internet connection.
        """
        assert isinstance(audio_data, AudioData), "`audio_data` must be audio data"
        assert key is None or isinstance(key, str), "`key` must be `None` or a string"
        assert isinstance(language, str), "`language` must be a string"

        flac_data, sample_rate = audio_data.get_flac_data(), audio_data.sample_rate
        if key is None: key = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
        url = "http://www.google.com/speech-api/v2/recognize?client=chromium&lang={0}&key={1}".format(language, key)
        request = Request(url, data = flac_data, headers = {"Content-Type": "audio/x-flac; rate={0}".format(sample_rate)})

        # obtain audio transcription results
        try:
            response = urlopen(request)
        except HTTPError as e:
            raise RequestError("recognition request failed: {0}".format(getattr(e, "reason", "status {0}".format(e.code)))) # use getattr to be compatible with Python 2.6
        except URLError as e:
            raise RequestError("recognition connection failed: {0}".format(getattr(e, "reason", "status {0}".format(e.code)))) # use getattr to be compatible with Python 2.6
        response_text = response.read().decode("utf-8")

        # ignore any blank blocks
        actual_result = []
        for line in response_text.split("\n"):
            if not line: continue
            result = json.loads(line)["result"]
            if len(result) != 0:
                actual_result = result[0]
                break

        if show_all: return actual_result

        # return the best guess
        if "alternative" not in actual_result: raise UnknownValueError()
        for entry in actual_result["alternative"]:
            if "transcript" in entry:
                return entry["transcript"]

        # no transcriptions available
        raise UnknownValueError()

    def recognize_wit(self, audio_data, key, show_all = False):
        """
        Performs speech recognition on ``audio_data`` (an ``AudioData`` instance), using the Wit.ai API.

        The Wit.ai API key is specified by ``key``. Unfortunately, these are not available without `signing up for an account <https://wit.ai/getting-started>`__ and creating an app. You will need to add at least one intent (recognizable sentence) before the API key can be accessed, though the actual intent values don't matter.

        To get the API key for a Wit.ai app, go to the app settings, go to the section titled "API Details", and look for "Server Access Token" or "Client Access Token". If the desired field is blank, click on the "Reset token" button on the right of the field. Wit.ai API keys are 32-character uppercase alphanumeric strings.

        Though Wit.ai is designed to be used with a fixed set of phrases, it still provides services for general-purpose speech recognition.

        The recognition language is configured in the Wit.ai app settings.

        Returns the most likely transcription if ``show_all`` is false (the default). Otherwise, returns the `raw API response <https://wit.ai/docs/http/20141022#get-intent-via-text-link>`__ as a JSON dictionary.

        Raises a ``speech_recognition.UnknownValueError`` exception if the speech is unintelligible. Raises a ``speech_recognition.RequestError`` exception if the key isn't valid, the quota for the key is maxed out, or there is no internet connection.
        """
        assert isinstance(audio_data, AudioData), "Data must be audio data"
        assert isinstance(key, str), "`key` must be a string"

        wav_data = audio_data.get_wav_data()
        url = "https://api.wit.ai/speech?v=20141022"
        request = Request(url, data = wav_data, headers = {"Authorization": "Bearer {0}".format(key), "Content-Type": "audio/wav"})
        try:
            response = urlopen(request)
        except HTTPError as e:
            raise RequestError("recognition request failed: {0}".format(getattr(e, "reason", "status {0}".format(e.code)))) # use getattr to be compatible with Python 2.6
        except URLError as e:
            raise RequestError("recognition connection failed: {0}".format(getattr(e, "reason", "status {0}".format(e.code)))) # use getattr to be compatible with Python 2.6
        response_text = response.read().decode("utf-8")
        result = json.loads(response_text)

        if show_all: return result

        if "_text" not in result or result["_text"] is None: raise UnknownValueError()
        return result["_text"]

    def recognize_ibm(self, audio_data, username, password, language = "en-US", show_all = False):
        """
        Performs speech recognition on ``audio_data`` (an ``AudioData`` instance), using the IBM Speech to Text API.

        The IBM Speech to Text username and password are specified by ``username`` and ``password``, respectively. Unfortunately, these are not available without an account. IBM has published instructions for obtaining these credentials in the `IBM Watson Developer Cloud documentation <https://www.ibm.com/smarterplanet/us/en/ibmwatson/developercloud/doc/getting_started/gs-credentials.shtml>`__.

        The recognition language is determined by ``language``, an IETF language tag with a dialect like ``"en-US"`` or ``"es-ES"``, defaulting to US English. At the moment, this supports the tags ``"en-US"``, ``"es-ES"``, and ``"ja-JP"``.

        Returns the most likely transcription if ``show_all`` is false (the default). Otherwise, returns the `raw API response <http://www.ibm.com/smarterplanet/us/en/ibmwatson/developercloud/speech-to-text/api/v1/#recognize>`__ as a JSON dictionary.

        Raises a ``speech_recognition.UnknownValueError`` exception if the speech is unintelligible. Raises a ``speech_recognition.RequestError`` exception if the key isn't valid, or there is no internet connection.
        """
        assert isinstance(audio_data, AudioData), "Data must be audio data"
        assert isinstance(username, str), "`username` must be a string"
        assert isinstance(password, str), "`password` must be a string"
        assert language in ["en-US", "es-ES", "ja-JP"], "`language` must be a valid language."

        flac_data = audio_data.get_flac_data()
        model = "{0}_BroadbandModel".format(language)
        url = "https://stream.watsonplatform.net/speech-to-text/api/v1/recognize?continuous=true&model={0}".format(model)
        request = Request(url, data = flac_data, headers = {"Content-Type": "audio/x-flac"})
        if hasattr("", "encode"):
            authorization_value = base64.standard_b64encode("{0}:{1}".format(username, password).encode("utf-8")).decode("utf-8")
        else:
            authorization_value = base64.standard_b64encode("{0}:{1}".format(username, password))
        request.add_header("Authorization", "Basic {0}".format(authorization_value))
        try:
            response = urlopen(request)
        except HTTPError as e:
            raise RequestError("recognition request failed: {0}".format(getattr(e, "reason", "status {0}".format(e.code)))) # use getattr to be compatible with Python 2.6
        except URLError as e:
            raise RequestError("recognition connection failed: {0}".format(getattr(e, "reason", "status {0}".format(e.code)))) # use getattr to be compatible with Python 2.6
        response_text = response.read().decode("utf-8")
        result = json.loads(response_text)

        if show_all: return result

        if "results" not in result or len(result["results"]) < 1 or "alternatives" not in result["results"][0]:
            raise UnknownValueError()
        for entry in result["results"][0]["alternatives"]:
            if "transcript" in entry: return entry["transcript"]

        # no transcriptions available
        raise UnknownValueError()

    def recognize_att(self, audio_data, app_key, app_secret, language = "en-US", show_all = False):
        """
        Performs speech recognition on ``audio_data`` (an ``AudioData`` instance), using the AT&T Speech to Text API.

        The AT&T Speech to Text app key and app secret are specified by ``app_key`` and ``app_secret``, respectively. Unfortunately, these are not available without `signing up for an account <http://developer.att.com/apis/speech>`__ and creating an app.

        To get the app key and app secret for an AT&T app, go to the `My Apps page <https://matrix.bf.sl.attcompute.com/apps>`__ and look for "APP KEY" and "APP SECRET". AT&T app keys and app secrets are 32-character lowercase alphanumeric strings.

        The recognition language is determined by ``language``, an IETF language tag with a dialect like ``"en-US"`` or ``"es-ES"``, defaulting to US English. At the moment, this supports the tags ``"en-US"``, ``"es-ES"``, and ``"ja-JP"``.

        Returns the most likely transcription if ``show_all`` is false (the default). Otherwise, returns the `raw API response <https://developer.att.com/apis/speech/docs#resources-speech-to-text>`__ as a JSON dictionary.

        Raises a ``speech_recognition.UnknownValueError`` exception if the speech is unintelligible. Raises a ``speech_recognition.RequestError`` exception if the key isn't valid, or there is no internet connection.
        """
        assert isinstance(audio_data, AudioData), "Data must be audio data"
        assert isinstance(app_key, str), "`app_key` must be a string"
        assert isinstance(app_secret, str), "`app_secret` must be a string"
        assert language in ["en-US", "es-US"], "`language` must be a valid language."

        # ensure we have an authentication token
        authorization_url = "https://api.att.com/oauth/v4/token"
        authorization_body = "client_id={0}&client_secret={1}&grant_type=client_credentials&scope=SPEECH".format(app_key, app_secret)
        try:
            authorization_response = urlopen(authorization_url, data = authorization_body.encode("utf-8"))
        except HTTPError as e:
            raise RequestError("credential request failed: {0}".format(getattr(e, "reason", "status {0}".format(e.code)))) # use getattr to be compatible with Python 2.6
        except URLError as e:
            raise RequestError("credential connection failed: {0}".format(getattr(e, "reason", "status {0}".format(e.code)))) # use getattr to be compatible with Python 2.6
        authorization_text = authorization_response.read().decode("utf-8")
        authorization_bearer = json.loads(authorization_text).get("access_token")
        if authorization_bearer is None: raise RequestError("missing OAuth access token in requested credentials")

        wav_data = audio_data.get_wav_data()
        url = "https://api.att.com/speech/v3/speechToText"
        request = Request(url, data = wav_data, headers = {"Authorization": "Bearer {0}".format(authorization_bearer), "Content-Language": language, "Content-Type": "audio/wav"})
        try:
            response = urlopen(request)
        except HTTPError as e:
            raise RequestError("recognition request failed: {0}".format(getattr(e, "reason", "status {0}".format(e.code)))) # use getattr to be compatible with Python 2.6
        except URLError as e:
            raise RequestError("recognition connection failed: {0}".format(getattr(e, "reason", "status {0}".format(e.code)))) # use getattr to be compatible with Python 2.6
        response_text = response.read().decode("utf-8")
        result = json.loads(response_text)

        if show_all: return result

        if "Recognition" not in result or "NBest" not in result["Recognition"]:
            raise UnknownValueError()
        for entry in result["Recognition"]["NBest"]:
            if entry.get("Grade") == "accept" and "ResultText" in entry:
                return entry["ResultText"]

        # no transcriptions available
        raise UnknownValueError()

def shutil_which(pgm):
    """
    python2 backport of python3's shutil.which()
    """
    path = os.getenv('PATH')
    for p in path.split(os.path.pathsep):
        p = os.path.join(p, pgm)
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
