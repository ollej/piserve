#!/usr/bin/python

import os
import time
import math
import logging
import random
import RPi.GPIO as GPIO

import settings
from flowmeter import *
from dothat import lcd, backlight

"""
Setup a FlowMeter and trigger on pours.

TODO: Calibration value to adjust flow for different pressures.
TODO: Subclass for handlers, or send in handler object?
TODO: Config for liters when starting
TODO: Keep track of how much is left in keg

DOTHAT plugin:
TODO: Class to update DOTHAT with info.
TOSO: Idle plugin to show beer info and total pours and liters poured.
TODO: Display info about pour
TODO: Keep count of pours served
TODO: Show progression when pouring with lights and stats
TODO: Read vote buttons and keep score
TODO: Take photo when pressing button and tweet
"""
class PiServe:
    last_progress = 0
    progress_interval = 500

    def __init__(self, handler = None, options = {}):
        self.handler = handler
        self.options = options
        self.setup()

    def setup(self):
        """
        Setups the GPIO, adds event listener and instantiates a FlowMeter()
        """

        GPIO.setmode(GPIO.BCM) # use real GPIO numbering
        GPIO.setup(self.options['gpio_pin'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(self.options['gpio_pin'], GPIO.RISING, callback=self.trigger_click, bouncetime=20)

        # set up the flow meter
        self.fm = FlowMeter(self.options['units'], [self.options['beverage']])
        self.last_progress = self.current_time()
        self.update_idle()

    def trigger_click(self, channel):
        """
        Triggered on every click of the flow meter. Updates FlowMeter.
        TODO: FlowMeter.update() should set time itself
        """
        if self.fm.enabled == True:
            self.fm.update(self.current_time())
        #else:
        #    print('.', end='', flush=True)

    def trigger_large_pour(self):
        """
        Method called after `large_pour_inactivity` time in seconds if thisPour is more than
        `minimum_pour_size`.
        """
        #values = [self.fm.getFormattedThisPour(), self.fm.getBeverage()]
        #message = "\nSomeone just poured {0} of {1}".format(*values)
        #print(message)
        if self.handler:
            self.handler.show_large_pour(self.fm)
        self.fm.reset_pour(True)

    def trigger_small_pour(self):
        """
        Method called after `small_pour_inactivity` time in seconds if thisPour is less than
        `minimum_pour_size`. Currently implemented to cancel pour and reset pour counter.
        """
        if self.handler:
            self.handler.show_small_pour(self.fm)
        #values = [self.fm.getFormattedThisPour(), self.fm.getBeverage()]
        #message = "\nsmall pour {0} of {1}".format(*values)
        #print(message)
        self.fm.reset_pour(False)

    def trigger_progress(self):
        """
        Triggered every `progress_interval` milliseconds while pouring.
        """
        self.last_progress = self.current_time()
        #print(':', end='', flush=True)
        if self.handler:
            self.handler.show_progress(self.fm)

    def trigger_idle(self):
        """
        Triggered every `idle_interval` seconds after pouring.
        """
        self.update_idle()
        if self.handler:
            self.handler.show_idle(self.fm)

    def update_idle(self):
        """
        Updates last idle time.
        """
        self.last_idle = self.current_time()

    def has_poured(self):
        return self.fm.thisPour > 0

    def is_large_pour(self):
        """
        Returns true if thisPour is larger than `minimum_pour_size`.
        """
        return self.fm.thisPour > self.options['minimum_pour_size']

    def is_small_pour(self):
        """
        Returns true if thisPour is smaller than `minimum_pour_size`.
        """
        return self.fm.thisPour <= self.options['minimum_pour_size']

    def current_time(self):
        """
        Returns time in milliseconds as an integer.
        """
        return int(time.time() * FlowMeter.MS_IN_A_SECOND)

    def inactive_for(self, inactivity_time):
        """
        Return true if there have been no clicks for `inactivity_time` seconds.
        TODO: Move to FlowMeter
        """
        #return self.current_time() - self.fm.lastClick > inactivity_time * FlowMeter.MS_IN_A_SECOND
        return self.time_passed_greater_than(self.fm.lastClick, inactivity_time * FlowMeter.MS_IN_A_SECOND)

    def time_passed_greater_than(self, last_time, max_delta):
        return self.current_time() - last_time > max_delta

    def run(self):
        """
        Main run loop that triggers handlers on pours.
        """
        while True:
            if self.has_poured():
                # Triggers after 10 seconds of inactivity after a large pour.
                if (self.is_large_pour() and self.inactive_for(self.options['large_pour_inactivity'])):
                    self.trigger_large_pour()

                # Triggers meter after small pour and 2 secs of inactivity
                elif (self.is_small_pour() and self.inactive_for(self.options['small_pour_inactivity'])):
                    self.trigger_small_pour()

                elif (self.time_passed_greater_than(self.last_progress, self.progress_interval)):
                    self.trigger_progress()
            elif self.inactive_for(self.last_idle, self.options['idle_interval']):
                self.trigger_idle()

      # TODO: Catch interrupts and cleanup
      #GPIO.cleanup()
      #fm.clear()

class DotHandler:
    max_chars = 16
    color_white = [255, 255, 255]
    color_beer = [255, 204, 0]
    color_red = [255, 0, 0]

    def __init__(self, opts):
        self.step = 0
        self.options = opts

    def reset_display(self):
        backlight.rgb(*self.color_white) # Set white background
        lcd.clear()

    def show_progress(self, fm):
        if self.step == 0:
            self.reset_display()
        self.step += 1
        self.write_poured_info(fm)
        self.backlight_progress(fm)
        #self.write_debug_info(fm)

    def show_small_pour(self, fm):
        self.step = 0
        self.reset_display()
        backlight.rgb(*self.color_red)
        self.write_centered(1, "No beer for you!")
        self.write_centered(0, self.poured_message(fm))

    def show_large_pour(self, fm):
        self.step = 0
        self.reset_display()
        self.write_centered(0, "Cheers!")
        self.write_centered(1, self.poured_message(fm))

    def show_idle(self, fm):
        self.reset_display()
        self.write_msg(0, 0, fm.beverage)
        self.write_msg(0, 1, self.pours_message(fm))
        self.write_msg(0, 2, self.total_message(fm))

    def write_poured_info(self, fm):
        self.write_centered(0, fm.beverage)
        self.write_centered(1, self.formatted_centiliters(fm))

    def write_debug_info(self, fm):
        self.write_right(0, fm.getFormattedFlow())
        self.write_right(1, fm.getFormattedHertz())
        self.write_right(2, fm.getFormattedClickDelta())

    def backlight_progress(self, fm):
        # Sweep if progress > target
        progress = fm.thisPour / self.options['target_pour_size']
        for index in range(6):
            if (index / 6) < progress:
                color = self.color_beer
            else:
                color = self.color_white
            backlight.single_rgb(index, *color)

    def centiliters(self, fm):
        return round(fm.thisPour * 100)

    def formatted_centiliters(self, fm):
        return "{0} cl".format(self.centiliters(fm))

    def formatted_total(self, fm):
        return "{0} L".format(str(round(fm.totalPour,1)))

    def total_message(self, fm):
        return "Totalt: {0} L".format(self.formatted_total(fm))

    def pours_message(self, fm):
        return "Antal: {0} st".format(fm.pours)

    def poured_message(self, fm):
        return "Poured {0}".format(self.formatted_centiliters(fm))

    def write_centered(self, row, msg):
        pos = int((self.max_chars - len(msg)) / 2)
        self.write_msg(pos, row, msg)

    def write_right(self, row, msg):
        pos = max(self.max_chars - len(msg) - 1, 0)
        self.write_msg(pos, row, msg)

    def write_msg(self, pos, row, msg):
        lcd.set_cursor_position(pos, row)
        lcd.write(msg)

if __name__ == '__main__':
    # TODO: Loop and find configs automatically
    opts = {
            'gpio_pin': int(os.environ.get('PISERVE_GPIO_PIN')),
            'large_pour_inactivity': int(os.environ.get('PISERVE_LARGE_POUR_INACTIVITY')),
            'small_pour_inactivity': int(os.environ.get('PISERVE_SMALL_POUR_INACTIVITY')),
            'minimum_pour_size': float(os.environ.get('PISERVE_MINIMUM_POUR_SIZE')),
            'target_pour_size': float(os.environ.get('PISERVE_TARGET_POUR_SIZE')),
            'idle_interval': float(os.environ.get('PISERVE_IDLE_INTERVAL')),
            'units': os.environ.get('PISERVE_UNITS'),
            'beverage': os.environ.get('PISERVE_BEVERAGE'),
            }
    print(opts)
    dt = DotHandler(opts)
    PiServe(dt, opts).run()
