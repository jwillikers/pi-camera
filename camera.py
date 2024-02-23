#!/usr/bin/env python3
import time

import io
import date
import board
from libcamera import controls
import adafruit_pcf8574
from picamera2 import Picamera2, Preview
import adafruit_bitbangio
import digitalio

from exif import Image
from exif import GpsAltitudeRef

import adafruit_gps


i2c = adafruit_bitbangio.I2C(board.D11, board.D10)

pcf = adafruit_pcf8574.PCF8574(i2c)
button = pcf.get_pin(0)
button.switch_to_input(pull=digitalio.Pull.UP)

# Initialize the GPS
gps = adafruit_gps.GPS_GtopI2C(i2c, debug=False)
gps.send_command(b"PMTK314,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
gps.send_command(b"PMTK220,1000")

with Picamera2() as picam2:
    frame = int(time.time())

    # Set up QT preview window.
    preview_config = picam2.create_preview_configuration()
    # Only rotating 180 degrees is supported...
    # preview_config["transform"] = Transform(hflip=True, vflip=True)
    capture_config = picam2.create_still_configuration()
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
                data = io.BytesIO()
                picam2.switch_mode_and_capture_file(capture_config, data)
                image = Image(data)
                if gps.has_fix:
                    # https://exiftool.org/TagNames/GPS.html
                    # https://exif.readthedocs.io/en/latest/api_reference.html#image
                    # todo Needed?
                    # image.gps_version_id = (2, 3, 0, 0)
                    image.gps_latitude = gps.latitude
                    image.gps_latitude_ref = "N" if gps.latitude > 0 else "S"
                    image.gps_longitude = gps.longitude
                    image.gps_longitude_ref = "E" if gps.longitude > 0 else "W"
                    image.gps_altitude = gps.altitude_m
                    image.gps_altitude_ref = (
                        GpsAltitudeRef.ABOVE_SEA_LEVEL
                        if gps.altitude_m > 0
                        else GpsAltitudeRef.BELOW_SEA_LEVEL
                    )
                    image.gps_datestamp = date.fromtimestamp(gps.timestamp_utc)
                    image.gps_timestamp = gps.timestamp_utc
                    image.gps_satellites = gps.satellites
                    image.gps_status = gps.isactivedata
                    image.gps_measure_mode = gps.fix_quality_3d
                    image.gps_speed_ref = "N"  # knots
                    image.gps_speed = gps.speed_knots
                    image.gps_processing_method = "GPS"
                    image.gps_track = gps.track_angle_deg
                    # todo image.gps_track_ref = "M" or "T"?
                with open(filename, "wb") as new_image_file:
                    new_image_file.write(image.get_file())
                print(f"Image captured: {filename}")
                frame += 1
            else:
                print("BTN is up")
        prev_state = cur_state
        time.sleep(0.01)  # debounce
