Modified Speech Recognition Library Reference
====================================

**All of new codes and modifications is mainly added to Recognizer() class. The other classes are untouched.**
Make sure you read all library explanations and references of the original version `here <https://github.com/smeeklai/masterThesis/blob/master/reference/library-reference.rst> `__ first

``AudioSource()`` **Untouched**
----------------

``Microphone()`` **Untouched**
----------------

``WavFile()`` **Untouched**
----------------

``AudioData()`` **Untouched**
----------------

``Recognizer()`` **Modified**
----------------

``recognizer_instance.sendCaptionToClient(source, timeout = None)``
----------------------------------------------------------------------

ฺBasically, the method is a method that is modified from ``recognizer_instance.listen(source, timeout = None)`` method.
However, instead of listen to a single speech, I customized it to keep listening until the system is existed manually (press ctrl+c).
The method can automatically define an end of a speech, and then starts listen to the next one while completed audio data of the previous speech is sent to Google for performing speech recognition and get the result back

Additionally, the method also separates the speech every ``duration_t`` to send partial audio data of the separated speech using sub-threads from ``myThread()`` class to Google so that the system can acquire interim results of a speech. More details about concepts and architectures of the system can be found at `thesis document <https://github.com/smeeklai/masterThesis/blob/master/reference/thesis.pdf> `__

The ``timeout`` parameter is the maximum number of seconds that it will wait for a phrase to start before giving up and throwing an ``speech_recognition.WaitTimeoutError`` exception. If ``timeout`` is ``None``, it will wait indefinitely.

``myThread(audio_data, key = None, language = "en-US", show_all = False, parent = None)`` **Added**
----------------------------------------------------------------------

Crate a new myThread instance, which uses to handle audio data to do http requests to Google.
4 parameters are passed to create a myThread instance:
* audio_data (AudioSource instance) **required**
* key (Google Speech API key) **optional**
* language (language of the audio_data) **default is English**
* parent (an instance of a parent class who created the thread) **use "self" as a parameter**

By default, when a thread is instantiated, it'll look for run() function which is a derived function from super class.
This function needs to be overrided to tell a thread what to do. So we overrided it to call our created ``streamDataToGoogle()`` function.

Example of how to instantiate a thread:
.. code:: python
    self.myThread(audioData,None,"en-US", self)

``myThread_instance.streamDataToGoogle()``
-------------------------------------------------------------------------------

Prepare ``upstream_url`` and ``downstream_url`` to do http requests to Google. A ``pair`` of string is generated and used as a code to match downstream and upstream requests so that we won't get incorrect results

After url are ready, create two external thread to perform the upstream and downstream request.

More details about how urls are defined can be read `here <http://codeabitwiser.com/2014/09/python-google-speech-api/>`__

``myThread_instance.getPair()``
-------------------------------------------------------------------------------

Genareate a hexadecimal number from a unique 64 bits integers

``myThread_instance.gen_data()``
-------------------------------------------------------------------------------

A function that is used to stream a big file when sending a http request.

In our case, the audio data cannot just upload all of it in one time. The audio data needs to be divided into multiple chucks of 8192 bytes, and then steam each of them at a time

``myThread_instance.final()``
-------------------------------------------------------------------------------

In every responses from downstream requests. There are final results, and this method is meant to check whether the current line in responses is the final one or not

``myThread_instance.upstream()``
-------------------------------------------------------------------------------

A callback function for upstream thread. On the other hands, this is the function that is send to a thread in order to tell it what to do.

``myThread_instance.downstream()``
-------------------------------------------------------------------------------

A callback function for downstream thread. On the other hands, this is the function that is send to a thread in order to tell it what to do.
