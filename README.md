PiServe
-------

Measure a liquid flow meter and display status on a displayotron HAT on a
Raspberry Pi.

Requires `flowmeter.py` from
https://github.com/adafruit/Kegomatic/blob/master/kegomatic.py

Tested with the Adafruit Liquid Flow Meter.

Configuration
-------------

Configuration can be done in the file `.env` or with ENV variables.

Set `PISERVE_GPIO_PIN` to the GPIO pin number the yellow data line of the flow
meter is connected to on the Raspberry Pi.

```
PISERVE_GPIO_PIN=26
PISERVE_SMALL_POUR_INACTIVITY=2
PISERVE_LARGE_POUR_INACTIVITY=10
PISERVE_MINIMUM_POUR_SIZE=0.23
PISERVE_UNITS=metric
PISERVE_BEVERAGE=beer
```
