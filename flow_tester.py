#!/usr/bin/python

import os
import time
import math
import logging
import RPi.GPIO as GPIO

from flowmeter import *

flowmeter_gpio_pin = 26
pour_inactivity_time = 2
message_inactivity_time = 10
minimum_pour_size = 0.23

GPIO.setmode(GPIO.BCM) # use real GPIO numbering
GPIO.setup(flowmeter_gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# set up the flow meters
fm = FlowMeter('metric', ["beer"])

# Beer, on Pin 23.
def doAClick(channel):
  currentTime = int(time.time() * FlowMeter.MS_IN_A_SECOND)
  print('.', end='', flush=True)
  if fm.enabled == True:
    fm.update(currentTime)

# Beer, on Pin 26
GPIO.add_event_detect(flowmeter_gpio_pin, GPIO.RISING, callback=doAClick, bouncetime=20)

      #GPIO.cleanup()
      #fm.clear()
# main loop
while True:
  currentTime = int(time.time() * FlowMeter.MS_IN_A_SECOND)

  # Print message after 10 seconds of inactivity
  if (fm.thisPour > minimum_pour_size and currentTime - fm.lastClick > message_inactivity_time * FlowMeter.MS_IN_A_SECOND):
    message = "Someone just poured {0} of {1}".format(fm.getFormattedThisPour(), fm.getBeverage())
    print(message)
    fm.thisPour = 0.0

  # reset flow meter after each pour (2 secs of inactivity)
  if (fm.thisPour <= minimum_pour_size and currentTime - fm.lastClick > pour_inactivity_time * FlowMeter.MS_IN_A_SECOND):
    fm.thisPour = 0.0

