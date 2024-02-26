#!/usr/bin/env python3
import argparse
import os
import signal
import sys
import time

import adafruit_gps
import adafruit_pcf8574
import adafruit_bitbangio
import board
import digitalio
from libcamera import controls
from picamera2 import Picamera2, Preview
import piexif

from exif_utils import (
    degrees_decimal_to_degrees_minutes_seconds,
    number_to_exif_rational,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Directory path for the output images.")
    args = parser.parse_args()

    output_directory = os.path.join(os.getenv("HOME"), "Pictures")
    if args.output:
        output_directory = args.output
    if not os.path.isdir(output_directory):
        print(f"The output directory '{output_directory}' does not exist")
        print(f"Creating the output directory '{output_directory}'")
        try:
            os.mkdir(output_directory)
        except FileExistsError:
            pass

    i2c = adafruit_bitbangio.I2C(board.D11, board.D10)

    pcf = adafruit_pcf8574.PCF8574(i2c)
    button = pcf.get_pin(0)
    button.switch_to_input(pull=digitalio.Pull.UP)

    # Initialize the GPS
    gps = adafruit_gps.GPS_GtopI2C(i2c, debug=False)
    gps.send_command(b"PMTK314,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
    gps.send_command(b"PMTK220,1000")

    frame = int(time.time())
    with Picamera2() as picam2:
        picam2.options["quality"] = 95
        picam2.options["compress_level"] = 9

        lores_size = picam2.sensor_resolution
        while lores_size[0] > 800:
            lores_size = (lores_size[0] // 2 & ~1, lores_size[1] // 2 & ~1)

        # Set up QT preview window.
        capture_config = picam2.create_still_configuration(
            lores={
                # Only Pi 5 and newer can use formats besides YUV here which may be faster in the preview Window.
                # "format": "RGB888",
                "size": lores_size,
            },
            buffer_count=4,
            # Don't display anything in the preview window since the system is running headless.
            display="lores",
            encode="lores",
            # Only rotating 180 degrees is supported...
            # transform=Transform(hflip=True, vflip=True),
        )
        picam2.configure(capture_config)
        # Enable autofocus.
        if "AfMode" in picam2.camera_controls:
            picam2.set_controls({"AfMode": controls.AfModeEnum.Auto})
        picam2.start_preview(Preview.QTGL, x=0, y=0, width=800, height=480)
        picam2.start()

        def signal_handler(_sig, _frame):
            print("You pressed Ctrl+C!")
            picam2.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)

        time.sleep(2)
        print("Preview started")

        prev_state = button.value
        while True:
            cur_state = button.value
            if cur_state != prev_state:
                if not cur_state:
                    gps.update()
                    if "AfMode" in picam2.camera_controls:
                        for _ in range(5):
                            if picam2.autofocus_cycle():
                                break
                    exif_dict = {}
                    if gps.update() and gps.has_fix:
                        latitude = degrees_decimal_to_degrees_minutes_seconds(
                            gps.latitude
                        )
                        longitude = degrees_decimal_to_degrees_minutes_seconds(
                            gps.longitude
                        )

                        gps_ifd = {
                            piexif.GPSIFD.GPSAltitude: number_to_exif_rational(
                                abs(0 if gps.altitude_m is None else gps.altitude_m)
                            ),
                            piexif.GPSIFD.GPSAltitudeRef: (
                                0 if gps.altitude_m is None or gps.altitude_m > 0 else 1
                            ),
                            piexif.GPSIFD.GPSLatitude: (
                                number_to_exif_rational(abs(latitude[0])),
                                number_to_exif_rational(abs(latitude[1])),
                                number_to_exif_rational(abs(latitude[2])),
                            ),
                            piexif.GPSIFD.GPSLatitudeRef: (
                                "N" if latitude[0] > 0 else "S"
                            ),
                            piexif.GPSIFD.GPSLongitude: (
                                number_to_exif_rational(abs(longitude[0])),
                                number_to_exif_rational(abs(longitude[1])),
                                number_to_exif_rational(abs(longitude[2])),
                            ),
                            piexif.GPSIFD.GPSLongitudeRef: (
                                "E" if longitude[0] > 0 else "W"
                            ),
                            piexif.GPSIFD.GPSProcessingMethod: "GPS".encode("ASCII"),
                            piexif.GPSIFD.GPSSatellites: str(gps.satellites),
                            piexif.GPSIFD.GPSSpeed: (
                                number_to_exif_rational(0)
                                if gps.speed_knots is None
                                else number_to_exif_rational(gps.speed_knots)
                            ),
                            piexif.GPSIFD.GPSSpeedRef: "N",
                            piexif.GPSIFD.GPSVersionID: (2, 3, 0, 0),
                        }
                        if gps.fix_quality_3d > 0:
                            gps_ifd[piexif.GPSIFD.GPSMeasureMode] = str(
                                gps.fix_quality_3d
                            )
                        if gps.timestamp_utc:
                            gps_ifd[piexif.GPSIFD.GPSDateStamp] = time.strftime(
                                "%Y:%m:%d", gps.timestamp_utc
                            )
                            gps_ifd[piexif.GPSIFD.GPSTimeStamp] = (
                                number_to_exif_rational(gps.timestamp_utc.tm_hour),
                                number_to_exif_rational(gps.timestamp_utc.tm_min),
                                number_to_exif_rational(gps.timestamp_utc.tm_sec),
                            )
                        if gps.isactivedata:
                            gps_ifd[piexif.GPSIFD.GPSStatus] = gps.isactivedata
                        exif_dict = {"GPS": gps_ifd}
                        print(f"Exif GPS metadata: {gps_ifd}")
                    else:
                        print("No GPS fix")
                    filename = os.path.join(output_directory, f"{frame}.jpg")
                    picam2.capture_file(filename, exif_data=exif_dict, format="jpeg")
                    print(f"Image captured: {filename}")
                    frame += 1
                else:
                    print("BTN is up")
            prev_state = cur_state
            gps.update()
            # debounce
            time.sleep(0.01)


if __name__ == "__main__":
    main()
