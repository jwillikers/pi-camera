from picamera2 import Picamera2, Preview
import time

picam2 = Picamera2()
camera_config = picam2.create_preview_configuration()
picam2.configure(camera_config)
picam2.start_preview(Preview.QTGL)
picam2.start()
time.sleep(1)
picam2.set_controls({"AfMode": 0, "LensPosition": 425})
time.sleep(2)
picam2.capture_file("test.jpg")
