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

# obtain audio from the microphone
with noalsaerr():
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print("Say something!")
            r.listenMo(source)
    except sr.UnknownValueError:
        print("Google Speech Recognition could not understand audio")
    except sr.RequestError as e:
        print("Could not request results from Google Speech Recognition service; {0}".format(e))

# with sr.Microphone() as source:
#     print("Say something!")
#     audio= r.listen(source)
# # recognize speech using Google Speech Recognition
# try:
#     # for testing purposes, we're just using the default API key
#     # to use another API key, use `r.recognize_google(audio, key="GOOGLE_SPEECH_RECOGNITION_API_KEY")`
#     # instead of `r.recognize_google(audio)`
#     # start = timeit.default_timer()
#     # result = r.recognize_google(audio, key = "AIzaSyC1GY4NPun44trK7g7V-TNmp642aIugTCQ", language = "en-US", show_all = True)
#     # stop = timeit.default_timer()
#     # print(result)
#     # print "Response Time: %f" % (stop - start)
#     start = timeit.default_timer()
#     result = r.continuously_recognize_google(audio, key = "AIzaSyC1GY4NPun44trK7g7V-TNmp642aIugTCQ", language = "en-US", show_all = False)
#     stop = timeit.default_timer()
#     print result
#     print "Response Time: %f" % (stop - start)
# except sr.UnknownValueError:
#     print("Google Speech Recognition could not understand audio")
# except sr.RequestError as e:
#     print("Could not request results from Google Speech Recognition service; {0}".format(e))

# # recognize speech using Wit.ai
# WIT_AI_KEY = "4LBWXGE6RPHHHLF3NGPREZBEGXAR5BAF" # Wit.ai keys are 32-character uppercase alphanumeric strings
# try:
#     start2 = timeit.default_timer()
#     result = r.recognize_wit(audio, key=WIT_AI_KEY)
#     stop2 = timeit.default_timer()
#     print("Wit.ai thinks you said: " + result)
#     print "Response Time: %f" % (stop2 - start2)
# except sr.UnknownValueError:
#     print("Wit.ai could not understand audio")
# except sr.RequestError as e:
#     print("Could not request results from Wit.ai service; {0}".format(e))
#
# # recognize speech using IBM Speech to Text
# IBM_USERNAME = "3c1ca6d4-99a2-4af2-a5cd-55ef2e59947e" # IBM Speech to Text usernames are strings of the form XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
# IBM_PASSWORD = "wk0LrikJ0iAC" # IBM Speech to Text passwords are mixed-case alphanumeric strings
# try:
#     start3 = timeit.default_timer()
#     result = r.recognize_ibm(audio, username=IBM_USERNAME, password=IBM_PASSWORD)
#     stop3 = timeit.default_timer()
#     print("IBM Speech to Text thinks you said: " + result)
#     print "Response Time: %f" % (stop3 - start3)
# except sr.UnknownValueError:
#     print("IBM Speech to Text could not understand audio")
# except sr.RequestError as e:
#     print("Could not request results from IBM Speech to Text service; {0}".format(e))

# # recognize speech using AT&T Speech to Text
# ATT_APP_KEY = "bnt1iyki9hpc6tm3tgcqfpgdx0lcda5i" # AT&T Speech to Text app keys are 32-character lowercase alphanumeric strings
# ATT_APP_SECRET = "1ewnznhg0dyc33o8od5zrrfwvim9jpir" # AT&T Speech to Text app secrets are 32-character lowercase alphanumeric strings
# try:
#     start = timeit.default_timer()
#     result = r.recognize_att(audio, app_key=ATT_APP_KEY, app_secret=ATT_APP_SECRET)
#     stop = timeit.default_timer()
#     print("AT&T Speech to Text thinks you said " + result)
#     print "Response Time: %f" % (stop - start)
# except sr.UnknownValueError:
#     print("AT&T Speech to Text could not understand audio")
# except sr.RequestError as e:
#     print("Could not request results from AT&T Speech to Text service; {0}".format(e))
