#Written by Ryan Kim
#DIYgm code adapted from code from Lukas which was adapted from code by
#James Seekamp, Jeffery Xiao, Issa El-Amir, Regina Tuey, Max Li, Andrew Kent

#Feb 27. 2025

from code import compile_command
from http.server import BaseHTTPRequestHandler, HTTPServer
import time
import threading
import signal
import sys
from unicodedata import name
import random
import os
import datetime
import ssl
import zipfile
import zlib
import subprocess

DEBUG = True

host = "localhost"
port = 443

PWM_GPIO = 18 # reg edition make sure to use a PWM pin (check RPi datasheet)
#PWM_GPIO = 13 # this is for diygm rws lite edition
MEAS_GPIO = 21
PULLUP_GPIO = 12

mode_ionizing = True
router = ""
ADAPTER = "wlan0"

# Pins
if not DEBUG:
    import pigpio
    pi = pigpio.pi()

    # PWM Pin
    pi.hardware_PWM(PWM_GPIO, 1000, 100000) # Set the frequency and instantiate PWM control on pin

    # Measurement Pullup Pin
    pi.write(PULLUP_GPIO, 1)

global filename
filename = ""

# Preventing race conditions
lock = threading.Lock()

# This method is called every second and handles the pushing and popping for the cpm lists
# this runs on a separate thread
def reset():
    while True:
        lock.acquire()
        global last_count
        global counts
        global cpm_fast
        global cpm_slow
        global fast_min
        global slow_min 
        global count_min

        if DEBUG:
            counts = random.randint(150, 175) / 100
        if not mode_ionizing and router != "":
            result = subprocess.run(['sudo', 'iw', ADAPTER, 'scan'], stdout=subprocess.PIPE).stdout.decode('utf-8')
            for ssid in result.split("BSS"):
                if ADAPTER in ssid:
                    signals = ssid.split('\n')
                    signals = [i for i in signals if 'signal' in i or 'SSID' in i]
                    i = 0
                    while i < len(signals):
                        name = signals[i+1][6:].strip()
                        if name == router:
                            # this is in -dBm, we want in mW
                            strength = signals[i][8:-3]
                            strength = float(strength)

                            # dBm = 10*log(power mW)
                            strength = 10**(strength/10)
                            counts = strength
                        i = i + 2
        elif not mode_ionizing:
            counts = 0

        # cpm fast averages over 4 seconds, so make only four values in the array
        if len(cpm_fast) < 4:
            cpm_fast.append(counts)
        else:
            cpm_fast.pop(0)
            cpm_fast.append(counts)

        # cpm fast averages over 22 seconds, so make only 22 values in the array
        if len(cpm_slow) < 22:
            cpm_slow.append(counts)
        else:
            cpm_slow.pop(0)
            cpm_slow.append(counts)

        if len(fast_min) < 60:
            fast_min.append(int(sum(cpm_fast) * 60/len(cpm_fast)))
            slow_min.append(int(sum(cpm_slow) * 60/len(cpm_slow)))
            count_min.append(counts)
        else:
            fast_min.append(int(sum(cpm_fast) * 60/len(cpm_fast)))
            fast_min.pop(0)

            slow_min.append(int(sum(cpm_slow) * 60/len(cpm_slow)))
            slow_min.pop(0)

            count_min.append(counts)
            count_min.pop(0)

        last_count = counts
        counts = 0
        lock.release()
        time.sleep(1)

# This is called every count, don't change arguments of function
def detection_callback(gpio, level, tick):
    lock.acquire()
    global counts
    counts += 1
    #last_rand = randnum
    #dir = os.path.dirname(os.path.abspath(__file__)) + f"/logs/rand.csv"
    #with open(dir, "a+") as log:
    #    log.write(f"{last_rand}\n")
    lock.release()

def log():
    global last_lon
    global last_lat
    global stopLog
    global filename
    global log_start
    while True:
        lock.acquire()
        if (stopLog):
            lock.release()
            break
        dir = os.path.dirname(os.path.abspath(__file__)) + f"/logs/{filename}.csv"
        with open(dir, "a+") as log:
            log.write(f"{datetime.datetime.now()-log_start},{last_lat},{last_lon},{last_count},{fast_min[len(fast_min)-1]},{slow_min[len(slow_min)-1]}\n")
        lock.release()
        time.sleep(1)

# This is a class built on top of http handler that serves as the wireless access point for the diygm
# interface 
class Server(BaseHTTPRequestHandler):
    def do_GET(self):
        global log
        global stopLog
        global loggingThread
        if self.path == "/data":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()

            lock.acquire()
            self.wfile.write(bytes(f"{{\"counts\": {count_min}, \"cpm_fast\": {fast_min}, \"cpm_slow\": {slow_min}}}", "utf-8"))
            lock.release()
        elif self.path == "/plotly-2.14.0.min.js":
            self.send_response(200)
            self.send_header("Content-type", "text/javascript")
            self.end_headers()

            res = open("plotly-2.14.0.min.js", "rb")

            self.wfile.write(res.read())
        elif self.path == "/end":
            self.send_response(200) 
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(bytes("{}", "utf-8"))      

            # stop the thread and null out the file handle to the log
            lock.acquire()
            if (loggingThread.is_alive()):
                stopLog = True
            lock.release()
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
        elif self.path == "/getStatus":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()

            bool = 'false'
            # i know this is terrible, but json doesn't play nice with True instead of true
            if not loggingThread.is_alive():
                bool = 'true'

            lock.acquire()
            self.wfile.write(bytes(f"{{\"log\": {bool}}}", "utf-8"))
            lock.release()
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            res = open("diygmserveredition.html", "rb")

            self.wfile.write(res.read())

    def do_POST(self):
        global log
        global loggingThread
        global filename
        global stopLog
        global log_start
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
        elif self.path == "/downloadall":
            self.send_response(200) 
            self.send_header("Content-type", "text/plain")
            self.end_headers()

            filename = self.path[5:]

            lock.acquire()
            with zipfile.ZipFile(os.path.dirname(os.path.abspath(__file__)) + "/logs/all-logs.zip", "w", zipfile.ZIP_DEFLATED) as zip:
                lognames = os.listdir(os.path.dirname(os.path.abspath(__file__)) + "/logs")
                for name in lognames:
                    if name[-3:] != "zip":
                        zip.write(os.path.dirname(os.path.abspath(__file__)) + "/logs/" + name, arcname=name)
            with open(os.path.dirname(os.path.abspath(__file__)) + "/logs/all-logs.zip", "rb") as ret:
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
            if lognames:
                for name in lognames:
                    if name[-4:] == '.csv':
                        res += "\"" + name + "\","

                res = res[0:len(res)-1]
            res += "]}"

            self.wfile.write(bytes(res, "utf-8"))
        elif self.path == "/start":
            if int(self.headers['Content-Length']):
                self.data_string = self.rfile.read(int(self.headers['Content-Length']))
                self.data_string = self.data_string.decode("utf-8")
                filename = self.data_string
                if filename[-4:] == '.csv':
                    filename = filename[:-4]
            else:
                filename = str(datetime.datetime.now()).replace(" ", "_")
            # create log pointer
            lock.acquire()
            if not loggingThread.is_alive():
                dir = os.path.dirname(os.path.abspath(__file__)) + f"/logs/{filename}.csv"
                with open(dir, "w") as log_file:
                    log_file.write("Time,Latitude,Longitude,Counts,CPM Fast,CPM Slow\n")
            lock.release()

            # start logging thread, should come after the log pointer
            if not loggingThread.is_alive():
                stopLog = False
                log_start = datetime.datetime.now()
                loggingThread = threading.Thread(target=log, daemon=True)
                loggingThread.start()
            self.send_response(200) 
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(bytes(f"{{\"name\": \"{filename}.csv\"}}", "utf-8"))
        elif self.path[0:7] == "/update": # this is the system updater
            with open(self.path[8:], "w") as file:
                lock.acquire()
                self.data_string = self.rfile.read(int(self.headers['Content-Length']))
                self.data_string = self.data_string.decode("utf-8")

                file.write(self.data_string)
                lock.release()
            
            # restart the system if the python file was updated
            if self.path[8:] == os.path.basename(__file__):
                os.system("sudo reboot")
            self.send_response(200) 
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(bytes("{}", "utf-8"))
        elif self.path == "/restart": #restart the pi
            os.system("sudo reboot")
        elif self.path == "/shutdown": #shutdown the raspberry pi
            os.system("sudo shutdown -h now")
        elif self.path == "/host": #handles changing the hostname
            with open("/etc/hostapd/hostapd.conf", "w") as file:
                lock.acquire()
                self.data_string = self.rfile.read(int(self.headers['Content-Length']))
                self.data_string = self.data_string.decode("utf-8")

                #this might not work outside of the united states
                file.write(f"country_code=US\ninterface=wlan0\nssid={self.data_string}\nhw_mode=g\nchannel=7\nmacaddr_acl=0\nauth_algs=1\nignore_broadcast_ssid=0")
                lock.release()
                os.system("sudo reboot")
        elif self.path == "/pwm": #change the pwm stuff
            self.data_string = self.rfile.read(int(self.headers['Content-Length']))
            self.data_string = self.data_string.decode("utf-8")

            self.data_string = self.data_string.split(',')

            duty_cycle = int(self.data_string[0])
            frequency = int(self.data_string[1])

            pi.hardware_PWM(PWM_GPIO, frequency, duty_cycle * 10000) # Set the frequency and instantiate PWM control on pin
        elif self.path == "/ionizing":
            mode_ionizing = True

            self.send_response(200) 
            self.send_header("Content-type", "application/json")
            self.end_headers()
        elif self.path == "/wifi":
            mode_ionizing = False

            self.send_response(200) 
            self.send_header("Content-type", "application/json")
            self.end_headers()
        else: 
            global last_lat
            global last_lon

            self.data_string = self.rfile.read(int(self.headers['Content-Length']))
            self.data_string = self.data_string.decode("utf-8")

            self.data_string = self.data_string.split(',')

            lock.acquire()
            last_lat = self.data_string[0]
            last_lon = self.data_string[1]
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

    global fast_min
    global slow_min 
    global count_min

    global stopLog

    global last_lon
    global last_lat
    global loggingThread
    global log_start

    log_start = None

    last_lon = 0
    last_lat = 0

    stopLog = False
    loggingThread = threading.Thread(target=log, daemon=True)

    last_count = 0
    counts = 0
    cpm_fast = [0]
    cpm_slow = [0]

    fast_min = [0]
    slow_min = [0]
    count_min = [0]

    global QUIT
    QUIT = False

    # creates log directory if it doesn't already exist
    dir = os.path.dirname(os.path.abspath(__file__)) + "/logs"
    if os.path.exists(dir):
        pass
    else:
        os.mkdir(dir)

    # sets interrupt for measurement pin
    if not DEBUG:
        pi.callback(MEAS_GPIO, pigpio.FALLING_EDGE, detection_callback)

    # create thread to handle cpm lists
    t = threading.Thread(target=reset, daemon=True)
    t.start()

    # initialize the web server
    webServer = HTTPServer((host, port), Server)

    # this needs to be exist to handle communication over https so location can be access
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile='forgedcert.pem', keyfile='forgedkey.pem') 
    webServer.socket = context.wrap_socket(webServer.socket, server_side=True)

    '''
    webServer.socket = ssl.wrap_socket(webServer.socket,
                                        keyfile="forgedkey.pem",
                                        certfile="forgedcert.pem", server_side=True)
    '''
    webServer.serve_forever()

    t.stop()
    Server.server_close()
