#Written by Ryan Kim
#DIYgm code adapted from code from Lukas which was adapted from code by
#James Seekamp, Jeffery Xiao, Issa El-Amir, Regina Tuey, Max Li, Andrew Kent

#Aug 12. 2022

#If you're reading this, I'm sorry I was given 24 hours to turn this around

from code import compile_command
from http.server import BaseHTTPRequestHandler, HTTPServer
import time
import threading
import signal
import sys
import pigpio
import os
import datetime
import ssl

host = "192.168.4.1"
port = 8080

# Pins
pi = pigpio.pi()

PWM_GPIO = 18 # make sure to use a PWM pin (check RPi datasheet)
MEAS_GPIO = 21
PULLUP_GPIO = 12

# Disables error message
#GPIO.setwarnings(False)

# PWM Pin
pi.hardware_PWM(PWM_GPIO, 1000, 100000) # Set the frequency and instantiate PWM control on pin

# Measurement Receiver Pin

# Measurement Pullup Pin
pi.write(PULLUP_GPIO, 1)

lock = threading.Lock()

def reset():
    while True:
        lock.acquire()
        global last_count
        global counts
        global cpm_fast
        global cpm_slow
        if len(cpm_fast) < 4:
            cpm_fast.append(counts)
        else:
            cpm_fast.pop(0)
            cpm_fast.append(counts)

        if len(cpm_slow) < 22:
            cpm_slow.append(counts)
        else:
            cpm_slow.pop(0)
            cpm_slow.append(counts)

        last_count = counts
        counts = 0
        lock.release()
        time.sleep(1)

def detection_callback(gpio, level, tick):
    lock.acquire()
    global counts
    counts += 1
    lock.release()

class Server(BaseHTTPRequestHandler):
    def do_GET(self):
        global log
        if self.path == "/data":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()

            lock.acquire()
            self.wfile.write(bytes(f"{{\"counts\": {last_count}, \"cpm_fast\": {int(sum(cpm_fast) * 60/len(cpm_fast))}, \"cpm_slow\": {int(sum(cpm_slow) * 60/len(cpm_slow))}}}", "utf-8"))
            lock.release()
        elif self.path == "/plotly-2.14.0.min.js":
            self.send_response(200)
            self.send_header("Content-type", "text/javascript")
            self.end_headers()

            res = open("plotly-2.14.0.min.js", "rb")

            self.wfile.write(res.read())
        elif self.path == "/start":
            lock.acquire()
            if not log:
                name = str(datetime.datetime.now()).replace(" ", "_")
                dir = os.path.dirname(os.path.abspath(__file__)) + f"/logs/{name}.csv"
                log = dir
                with open(log, "w") as file:
                    file.write("Time,Latitude,Longitude,Counts,CPM Fast,CPM Slow\n")
            lock.release()
            self.send_response(200) 
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(bytes("{}", "utf-8"))
        elif self.path == "/end":
            lock.acquire()
            log = None
            lock.release()
            self.send_response(200) 
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(bytes("{}", "utf-8"))            
        elif self.path == "/download":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            res = open("download.html", "rb")

            self.wfile.write(res.read())
        elif self.path == "/update":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            res = open("update.html", "rb")

            self.wfile.write(res.read())
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            res = open("diygmserveredition.html", "rb")

            self.wfile.write(res.read())

    def do_POST(self):
        global log
        if len(self.path) > 12 and self.path[0:12] == "/logs/delete":
            filename = self.path[12:]
            path = os.path.dirname(os.path.abspath(__file__)) + f"/logs/{filename}"
            lock.acquire()
            if os.path.exists(path):
                os.remove(path)
            lock.release()
            self.send_response(200) 
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(bytes("{}", "utf-8"))
        elif len(self.path) > 5 and self.path[0:5] == "/logs":
            self.send_response(200) 
            self.send_header("Content-type", "text/csv")
            self.end_headers()

            filename = self.path[5:]

            lock.acquire()
            path = os.path.dirname(os.path.abspath(__file__)) + f"/logs/{filename}"
            if len(filename) >= 4 and filename[len(filename)-4:] == ".csv" and os.path.exists(path):
                ret = open(path, "rb")
                self.wfile.write(ret.read())
            lock.release()
        elif self.path == "/logs":
            self.send_response(200)
            
            self.send_header("Content-type", "application/json")
            self.end_headers()

            lognames = os.listdir(os.path.dirname(os.path.abspath(__file__)) + "/logs")

            lognames.sort()

            res = "{\"logs\": ["

            #this is a workaround for single vs double quotes
            for name in lognames:
                res += "\"" + name + "\","

            res = res[0:len(res)-1]
            res += "]}"

            self.wfile.write(bytes(res, "utf-8"))
        elif self.path[0:7] == "/update":
            with open(self.path[8:], "w") as file:
                lock.acquire()
                self.data_string = self.rfile.read(int(self.headers['Content-Length']))
                self.data_string = self.data_string.decode("utf-8")

                file.write(self.data_string)
                lock.release()
            
            if self.path[8:] == os.path.basename(__file__):
                os.system("sudo reboot")
            self.send_response(200) 
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(bytes("{}", "utf-8"))
        elif self.path == "/restart":
            os.system("sudo reboot")
        elif self.path == "/shutdown":
            os.system("sudo shutdown -h now")
        elif self.path == "/host":
            with open("/etc/hostapd/hostapd.conf", "w") as file:
                lock.acquire()
                self.data_string = self.rfile.read(int(self.headers['Content-Length']))
                self.data_string = self.data_string.decode("utf-8")

                file.write(f"country_code=US\ninterface=wlan0\nssid={self.data_string}\nhw_mode=g\nchannel=7\nmacaddr_acl=0\nauth_algs=1\nignore_broadcast_ssid=0")
                lock.release()
                os.system("sudo reboot")
        else: 
            self.data_string = self.rfile.read(int(self.headers['Content-Length']))
            self.data_string = self.data_string.decode("utf-8")

            print(self.data_string)

            lock.acquire()
            if log:
                with open(log, "a") as file:
                    file.write(f"{datetime.datetime.now()}{self.data_string},{last_count},{int(sum(cpm_fast) * 60/len(cpm_fast))},{int(sum(cpm_slow) * 60/len(cpm_slow))}\n")
            lock.release()

            self.send_response(200) 
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(bytes("{}", "utf-8"))

        

if __name__=="__main__":
    # Globals
    global counts
    global last_count
    global cpm_fast
    global cpm_slow

    log = None
    last_count = 0
    counts = 0
    cpm_fast = [0]
    cpm_slow = [0]
    global QUIT
    QUIT = False

    dir = os.path.dirname(os.path.abspath(__file__)) + "/logs"
    if os.path.exists(dir):
        pass
    else:
        os.mkdir(dir)
    pi.callback(MEAS_GPIO, pigpio.FALLING_EDGE, detection_callback)


    t = threading.Thread(target=reset, daemon=True)
    t.start()

    webServer = HTTPServer((host, port), Server)

    webServer.socket = ssl.wrap_socket(webServer.socket,
                                        keyfile="forgedkey.pem",
                                        certfile="forgedcert.pem", server_side=True)

    webServer.serve_forever()

    t.stop()
    Server.server_close()
