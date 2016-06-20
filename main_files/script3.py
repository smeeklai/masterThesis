#!/usr/bin/env python3

# NOTE: this example requires PyAudio because it uses the Microphone class

import speech_recognition as sr
import timeit

# this is called from the background thread
def callback(recognizer, audio, start):
    # received audio data, now we'll recognize it using Google Speech Recognition
    try:
        # for testing purposes, we're just using the default API key
        # to use another API key, use `r.recognize_google(audio, key="GOOGLE_SPEECH_RECOGNITION_API_KEY")`
        # instead of `r.recognize_google(audio)`
        result = r.recognize_google(audio)
        stop = timeit.default_timer()
        print(result)
        print "Google Response Time: %f" % (stop - start)
        # print recognizer.recognize_google(audio, None, "en-US", True)
    except sr.UnknownValueError:
        print("Google Speech Recognition could not understand audio")
    except sr.RequestError as e:
        print("Could not request results from Google Speech Recognition service; {0}".format(e))


r = sr.Recognizer()
# r.pause_threshold = 0.5
r.dynamic_energy_ratio = 8
m = sr.Microphone()
with m as source:
    print("Say something!")
    r.adjust_for_ambient_noise(source) # we only need to calibrate once, before we start listening

# start listening in the background (note that we don't have to do this inside a `with` statement)
stop_listening = r.listen_in_background(m, callback)
# `stop_listening` is now a function that, when called, stops background listening

# # do some other computation for 5 seconds, then stop listening and keep doing other computations
import time
# for _ in range(50): time.sleep(30) # we're still listening even though the main thread is doing other things
# stop_listening() # calling this function requests that the background listener stop listening
while True: time.sleep(0.1)
stop_listening()
