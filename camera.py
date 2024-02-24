#!/usr/bin/env python3
import argparse
from fractions import Fraction
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

        # Set up QT preview window.
        preview_config = picam2.create_preview_configuration()
        # Only rotating 180 degrees is supported...
        # preview_config["transform"] = Transform(hflip=True, vflip=True)
        capture_config = picam2.create_still_configuration()
        picam2.configure(preview_config)
        picam2.start_preview(Preview.QTGL, x=0, y=0, width=800, height=480)
        picam2.start()

        def signal_handler(_sig, _frame):
            print("You pressed Ctrl+C!")
            picam2.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)

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
                    exif_dict = {}
                    if gps.update() and gps.has_fix:

                        def decimal_minutes_to_minutes_seconds(
                            minutes_decimal: float,
                        ) -> tuple[int, Fraction]:
                            minutes = int(minutes_decimal)
                            seconds = Fraction(
                                (minutes_decimal - minutes) * 60
                            ).limit_denominator(100)
                            return (minutes, seconds)

                        latitude_minutes, latitude_seconds = (
                            decimal_minutes_to_minutes_seconds(gps.latitude_minutes)
                        )
                        longitude_minutes, longitude_seconds = (
                            decimal_minutes_to_minutes_seconds(gps.longitude_minutes)
                        )

                        def format_fraction(fraction: Fraction) -> tuple[int, int]:
                            return (
                                int(fraction.limit_denominator(100).numerator),
                                int(fraction.limit_denominator(100).denominator),
                            )

                        gps_ifd = {
                            piexif.GPSIFD.GPSVersionID: (2, 3, 0, 0),
                            piexif.GPSIFD.GPSAltitude: format_fraction(
                                Fraction(
                                    abs(0 if gps.altitude_m is None else gps.altitude_m)
                                ).limit_denominator(100)
                            ),
                            piexif.GPSIFD.GPSAltitudeRef: (
                                0 if gps.altitude_m is None or gps.altitude_m > 0 else 1
                            ),
                            piexif.GPSIFD.GPSLatitude: (
                                (abs(gps.latitude_degrees), 1),
                                (latitude_minutes, 1),
                                format_fraction(latitude_seconds),
                            ),
                            piexif.GPSIFD.GPSLatitudeRef: (
                                "N" if gps.latitude > 0 else "S"
                            ),
                            piexif.GPSIFD.GPSLongitude: (
                                (abs(gps.longitude_degrees), 1),
                                (longitude_minutes, 1),
                                format_fraction(longitude_seconds),
                            ),
                            piexif.GPSIFD.GPSLongitudeRef: (
                                "E" if gps.longitude > 0 else "W"
                            ),
                            piexif.GPSIFD.GPSProcessingMethod: "GPS".encode("ASCII"),
                            piexif.GPSIFD.GPSSatellites: str(gps.satellites),
                            piexif.GPSIFD.GPSSpeed: (
                                (0, 1)
                                if gps.speed_knots is None
                                else format_fraction(Fraction(gps.speed_knots))
                            ),
                            piexif.GPSIFD.GPSSpeedRef: "N",
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
                                (gps.timestamp_utc.tm_hour, 1),
                                (gps.timestamp_utc.tm_min, 1),
                                (gps.timestamp_utc.tm_sec, 1),
                            )
                        if gps.isactivedata:
                            gps_ifd[piexif.GPSIFD.GPSStatus] = gps.isactivedata
                        exif_dict = {"GPS": gps_ifd}
                        print(f"Exif GPS metadata: {gps_ifd}")
                    else:
                        print("No GPS fix")
                    filename = os.path.join(output_directory, f"{frame}.jpg")
                    capture_config = picam2.create_still_configuration()
                    picam2.switch_mode_and_capture_file(
                        capture_config,
                        filename,
                        delay=10,
                        exif_data=exif_dict,
                        format="jpeg",
                    )
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
