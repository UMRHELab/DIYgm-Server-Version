import os
import pigpio

# Pins
pi = pigpio.pi()

PWM_GPIO = 18 # make sure to use a PWM pin (check RPi datasheet)
MEAS_GPIO = 21
PULLUP_GPIO = 12

last_rand = 0
randnum = 0

def detection_callback(gpio, level, tick):
    last_rand = randnum
    dir = os.path.dirname(os.path.abspath(__file__)) + f"/logs/rand.csv"
    with open(dir, "a+") as log:
        log.write(f"{last_rand}\n")

# sets interrupt for measurement pin
pi.callback(MEAS_GPIO, pigpio.FALLING_EDGE, detection_callback)

while True:
    if randnum == 10:
        randnum = 0
    else:
        randnum += 1