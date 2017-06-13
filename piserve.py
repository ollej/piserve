#!/usr/bin/python

import os
import time
import math
import logging
import random
import RPi.GPIO as GPIO

import settings
from flowmeter import *
from dothat import lcd, backlight, touch
from dot3k.menu import Menu, MenuOption

"""
Extend FlowMeter
"""
class PiServeFlowMeter(FlowMeter):
    def __init__(self, options = {}):
        self.options = options or self.read_options()
        super().__init__(self.options['units'], [self.options['beverage']])

    def setup(self):
        """
        Setups the GPIO, adds event listener and instantiates a FlowMeter()
        """

        GPIO.setmode(GPIO.BCM) # use real GPIO numbering
        GPIO.setup(self.options['gpio_pin'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(self.options['gpio_pin'], GPIO.RISING, callback=self.on_click, bouncetime=20)

    def read_options(self):
        """
        Return dict of options read from ENV.
        """
        return {
            'gpio_pin': int(os.environ.get('PISERVE_GPIO_PIN')),
            'large_pour_inactivity': int(os.environ.get('PISERVE_LARGE_POUR_INACTIVITY')),
            'small_pour_inactivity': int(os.environ.get('PISERVE_SMALL_POUR_INACTIVITY')),
            'minimum_pour_size': float(os.environ.get('PISERVE_MINIMUM_POUR_SIZE')),
            'target_pour_size': float(os.environ.get('PISERVE_TARGET_POUR_SIZE')),
            'idle_interval': float(os.environ.get('PISERVE_IDLE_INTERVAL')),
            'units': os.environ.get('PISERVE_UNITS'),
            'beverage': os.environ.get('PISERVE_BEVERAGE'),
            }

    def on_click(self, channel):
        """
        Triggered on every click of the flow meter. Updates FlowMeter.
        """
        if self.enabled == True:
            self.update(self.current_time())

    def reset_pour(self, counts=False):
        """
        Resets thisPour and increases pours counter if counts is True.
        """
        self.thisPour = 0.0
        if counts:
            self.pours += 1

    def get_progress(self):
        """
        Return progress of thisPour until target_pour_size.
        """
        return self.thisPour / self.options['target_pour_size']

    def centiliters(self):
        return round(self.thisPour * 100)

    def has_poured(self):
        """
        Returns True if a pour has started.
        """
        return self.thisPour > 0

    def is_large_pour(self):
        """
        Returns true if thisPour is larger than `minimum_pour_size`.
        """
        return self.thisPour > self.options['minimum_pour_size']

    def is_small_pour(self):
        """
        Returns true if thisPour is smaller than `minimum_pour_size`.
        """
        return self.thisPour <= self.options['minimum_pour_size']

    def current_time(self):
        """
        Returns time in milliseconds as an integer.
        """
        return int(time.time() * FlowMeter.MS_IN_A_SECOND)


      # TODO: Catch interrupts and cleanup
      #GPIO.cleanup()
      #fm.clear()

class LedPulse:
    leds = [
            [0, 0, 0, 0, 0, 0],
            [0, 0, 1, 1, 0, 0],
            [0, 1, 1, 1, 1, 0],
            [1, 1, 1, 1, 1, 1],
            [0, 1, 1, 1, 1, 0],
            [0, 0, 1, 1, 0, 0],
            ]

    def __init__(self):
        self.iteration = 0

    def next(self):
        led_list = self.leds[self.iteration]
        self.iteration += 1
        if self.iteration >= 6:
            self.reset()
        return led_list

    def reset(self):
        self.iteration = 0

class PiServePresenter:
    def __init__(self, fm):
        self.fm = fm

    def formatted_centiliters(self):
        return "{0} cl".format(self.fm.centiliters())

    def formatted_total(self):
        return "{0} L".format(str(round(self.fm.totalPour, 1)))

    def total_message(self):
        return "{0} serverat".format(self.formatted_total())

    def pours_message(self):
        return "{0} serveringar".format(self.fm.pours)

    def poured_message(self):
        return "Serverade {0}".format(self.formatted_centiliters())

class PiServeMenu(Menu):
    def write_centered(self, row, text):
        pos = int((self.lcd.COLS - len(text)) / 2)
        self.write_row(row, ' ' * pos + text)

    def write_right(self, row, text):
        pos = max(self.lcd.COLS - len(text) - 1, 0)
        self.write_row(row, ' ' * pos + text)

class PiServeMenuOption(MenuOption):
    def __init__(self, fm):
        super().__init__()
        self.fm = fm
        self.presenter = PiServePresenter(self.fm)

class PiServeVoteMenu(PiServeMenuOption):
    def setup(self, options):
        self.options = options
        self.message = None

    def redraw(self, menu):
        if self.message is not None:
            menu.write_row(1, self.message)
        else:
            menu.lcd.clear()

    def left(self):
        self.message = "Pressed left!"
        return True

    def right(self):
        self.message = "Pressed right!"
        return False

# TODO: Never gets triggered.
class PiServeIdle(PiServeMenuOption):
    def redraw(self, menu):
        """
        Triggered every `idle_interval` seconds after pouring.
        """
        menu.write_row(0, self.fm.getBeverage())
        menu.write_row(1, self.presenter.pours_message())
        menu.write_row(2, self.presenter.total_message())

class PiServeDebug(PiServeMenuOption):
    def redraw(self, menu):
        menu.write_right(0, self.fm.getFormattedFlow())
        menu.write_right(1, self.fm.getFormattedHertz())
        menu.write_right(2, self.fm.getFormattedClickDelta())

class PiServeProgress(PiServeMenuOption):
    max_chars = 16
    progress_interval = 0.5
    last_progress = 0
    color_white = [255, 255, 255]
    color_beer = [255, 204, 0]
    color_red = [255, 0, 0]

    def __init__(self, fm):
        super().__init__(fm)
        self.is_setup = False

    def setup(self, options):
        #self.options = options or self.read_options()
        self.options = self.fm.options
        if not self.is_setup:
            self.is_setup = True
            self.ledpulse = LedPulse()
            self.cleanup()

    def redraw(self, menu):
        """
        Main run loop that triggers handlers on pours.
        """
        if self.fm.has_poured():
            # Triggers after 10 seconds of inactivity after a large pour.
            if (self.fm.is_large_pour() and self.inactive_for(self.options['large_pour_inactivity'])):
                self.show_large_pour(menu)

            # Triggers meter after small pour and 2 secs of inactivity
            elif (self.fm.is_small_pour() and self.inactive_for(self.options['small_pour_inactivity'])):
                self.show_small_pour(menu)

            elif (self.inactive_for(self.progress_interval, self.last_progress)):
                self.show_progress(menu)
        elif self.inactive_for(self.options['idle_interval'], self.last_idle):
            self.show_idle(menu)

    def cleanup(self):
        self.reset_display()
        self.is_setup = False
        self.last_progress = self.millis()
        self.last_idle = 0
        self.step = 0

    def inactive_for(self, inactivity_time, last_time=None):
        """
        Return true if there have been no clicks for `inactivity_time` seconds.
        last_time defaults to lastClick on FlowMeter.
        """
        if last_time is None:
            last_time = self.fm.lastClick
        return self.millis() - last_time > inactivity_time * FlowMeter.MS_IN_A_SECOND

    def reset_display(self, menu=None):
        backlight.rgb(*self.color_white) # Set white background
        backlight.set_graph(0)
        self.ledpulse.reset()
        if menu is not None:
            menu.lcd.clear()

    def show_progress(self, menu):
        """
        Triggered every `progress_interval` milliseconds while pouring.
        """
        self.last_progress = self.millis()
        if self.step == 0:
            self.reset_display(menu)
        self.step += 1
        self.write_poured_info(menu)
        self.backlight_progress()
        backlight.set_graph(self.fm.get_progress())

    def show_small_pour(self, menu):
        """
        Method called after `small_pour_inactivity` time in seconds if thisPour is less than
        `minimum_pour_size`. Currently implemented to cancel pour and reset pour counter.
        """
        self.step = 0
        self.reset_display(menu)
        backlight.rgb(*self.color_red)
        menu.write_centered(1, "No beer for you!")
        menu.write_centered(0, self.presenter.poured_message())
        self.fm.reset_pour(False)
        time.sleep(5)

    def show_large_pour(self, menu):
        """
        Method called after `large_pour_inactivity` time in seconds if thisPour is more than
        `minimum_pour_size`.
        """
        self.step = 0
        self.reset_display(menu)
        menu.write_centered(0, "Cheers!")
        menu.write_centered(1, self.presenter.poured_message())
        self.fm.reset_pour(True)
        self.sweep()
        time.sleep(5)

    def show_idle(self, menu):
        """
        Triggered every `idle_interval` seconds after pouring.
        """
        self.last_idle = self.millis()
        self.reset_display(menu)
        menu.write_row(0, self.fm.getBeverage())
        menu.write_row(1, self.presenter.pours_message())
        menu.write_row(2, self.presenter.total_message())

    def write_poured_info(self, menu):
        menu.write_centered(0, self.fm.getBeverage())
        menu.write_centered(1, self.presenter.formatted_centiliters())

    def backlight_progress(self):
        # Sweep if progress > target
        for index in range(6):
            if (index / 6) < self.fm.get_progress():
                color = self.color_beer
            else:
                color = self.color_white
            backlight.single_rgb(index, *color)

    def sweep(self, iterations=1000):
        for x in range(iterations):
            backlight.sweep((x % 360) / 360.0)
            if x % 10 == 0:
                self.set_bargraph(self.ledpulse.next())

    def bargraph_pulse(self, iterations=100, sleep=0.1):
        for i in range(iterations):
            self.set_bargraph(self.ledpulse.next())
            time.sleep(sleep)

    def set_bargraph(self, leds):
        for i in range(6):
            backlight.graph_set_led_state(i, leds[i])

if __name__ == '__main__':
    fm = PiServeFlowMeter()
    fm.setup()
    menu = PiServeMenu(
            structure={
                    'Servera': PiServeProgress(fm),
                    'Debug': PiServeDebug(fm),
                    'Vote': PiServeVoteMenu(fm),
                    },
            lcd=lcd,
            idle_handler=PiServeIdle(fm),
            idle_timeout=15,
            )
    touch.bind_defaults(menu)
    while True:
        menu.redraw()
        time.sleep(0.01)

