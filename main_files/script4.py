#!/usr/bin/env python3

# NOTE: this example requires PyAudio because it uses the Microphone class

import speech_recognition as sr
import timeit
from ctypes import *
from contextlib import contextmanager

#ALSA Error Message Handling
ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)

def py_error_handler(filename, line, function, err, fmt):
    pass

c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

@contextmanager
def noalsaerr():
    asound = cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(c_error_handler)
    yield
    asound.snd_lib_error_set_handler(None)

with noalsaerr():
    m = sr.Microphone()
    # c = sr.Recognizer()
    r = sr.Recognizer()
    with m as source:
        print("Setting ambient noise...")
        r.adjust_for_ambient_noise(source)
    while True:
        r.set_output_sentence("")
        try:
            with m as source:
                print("Say something!")
                r.listenMo(source)
        except sr.UnknownValueError:
            print("Google Speech Recognition could not understand audio")
        except sr.RequestError as e:
            print("Could not request results from Google Speech Recognition service; {0}".format(e))
