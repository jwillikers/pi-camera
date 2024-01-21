#!/usr/bin/env python3
import time

import board
from libcamera import controls, Transform
import adafruit_pcf8574
from picamera2 import Picamera2, Preview
import adafruit_bitbangio
import digitalio

i2c = adafruit_bitbangio.I2C(board.D11, board.D10)

pcf = adafruit_pcf8574.PCF8574(i2c)
button = pcf.get_pin(0)
button.switch_to_input(pull=digitalio.Pull.UP)

with Picamera2() as picam2:
    frame = int(time.time())

    # Set up QT preview window.
    preview_config = picam2.create_preview_configuration()
    # Only rotating 180 degrees is supported...
    # preview_config["transform"] = Transform(hflip=True, vflip=True)
    capture_config = picam2.create_still_configuration()
    capture_config["transform"] = Transform(rotation=270)
    picam2.configure(preview_config)
    picam2.start_preview(Preview.QTGL, x=0, y=0, width=800, height=480)
    picam2.start()
    time.sleep(2)

    # Turn on full-time autofocus.
    picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})

    time.sleep(1)
    print("Preview started")

    prev_state = button.value
    while True:
        cur_state = button.value
        if cur_state != prev_state:
            if not cur_state:
                filename = f"/home/jordan/Pictures/{frame}.jpg"
                picam2.switch_mode_and_capture_file(capture_config, filename)
                print(f"Image captured: {filename}")
                frame += 1
            else:
                print("BTN is up")
        prev_state = cur_state
        time.sleep(0.01)  # debounce
