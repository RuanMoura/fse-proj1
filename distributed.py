import socket
import time
import os
import RPi.GPIO as GPIO
import json
import sys
import threading
import adafruit_dht
from typing import Tuple, Any, List, Dict

with open(sys.argv[1]) as FILE_CFG:
    CFG = json.load(FILE_CFG)
HOST = CFG["ip_servidor_distribuido"]
PORT = CFG["porta_servidor_distribuido"]
HOST_CENRAL = CFG["ip_servidor_central"]
PORT_CENRAL = CFG["porta_servidor_central"]
DHT = None
MODES = {"ligar": GPIO.HIGH, "desligar": GPIO.LOW}
ALARM_SYSTEM = False
TEMPERATURE = None
HUMIDITY = None
PESSOAS = 0

def config_gpio():
    global DHT
    GPIO.setup([output["gpio"] for output in CFG["outputs"]], GPIO.OUT)
    GPIO.setup([input["gpio"] for input in CFG["inputs"]], GPIO.IN)
    for device in CFG["outputs"] + CFG["inputs"]:
        device["state"] = GPIO.input(device["gpio"])
    DHT = adafruit_dht.DHT22(CFG["sensor_temperatura"][0]["gpio"])

def connect_central(skt: socket.socket):
    count = 0
    while True:
        os.system("clear")
        try:
            skt.connect((HOST_CENRAL, PORT_CENRAL))
            print(f"Conexao estabelecida com {HOST_CENRAL}:{PORT_CENRAL}")
            skt.send(CFG["nome"].encode())
            send_report(skt)
            break
        except ConnectionRefusedError:
            print("Servidor central indisponivel" + (count+1)*".")
            time.sleep(1)
        count = (count + 1) % 5

def report_formated() -> Dict[str, Any]:
    global CFG, TEMPERATURE, HUMIDITY
    update_dht()
    response = dict()
    ignore = ["contagem"]
    for device in CFG["outputs"] + CFG["inputs"]:
        if device["type"] not in ignore:
            response[device["tag"]] = device["state"]
    response["Temperatura"] = TEMPERATURE
    response["Umidade"] = HUMIDITY
    response["Contagem de pessoas"] = PESSOAS
    return response

def execute(cmd: str):
    global ALARM_SYSTEM
    if cmd == "ligar sistema de alarme":
        ALARM_SYSTEM = True
    elif cmd == "desligar sistema de alarme":
        ALARM_SYSTEM = False
    action, _, device = cmd.partition(" ")
    next_mode = MODES.get(action)

    gpio = []
    for output in CFG["outputs"]:
        if device == "todos" and output["type"] != "alarme":
            gpio.append(output["gpio"])
        elif device == output["tag"]:
            gpio.append(output["gpio"])
            break
        elif device == output["type"]:
            gpio.append(output["gpio"])
    if gpio and next_mode != None:
        GPIO.output(gpio, next_mode)

def recv(skt: socket.socket):
    cmd = skt.recv(1024).decode()
    while cmd != "exit" and cmd:
        if cmd:
            execute(cmd)
        cmd = skt.recv(1024).decode()

def update_dht():
    global TEMPERATURE, HUMIDITY
    try:
        TEMPERATURE = DHT.temperature
        HUMIDITY = DHT.humidity
    except RuntimeError as error:
        print("DHT error:", error.args[0])
    except OverflowError as error:
        print("DHT error:", error.args[0])
    return

def need_update() -> bool:
    global PESSOAS
    report = False 
    for device in CFG["outputs"] + CFG["inputs"]:
        state = GPIO.input(device["gpio"])
        if device["state"] != state:
            report = True
        if device["tag"] == "Sensor de Contagem de Pessoas Entrada":
            if not device["state"] and state:
                PESSOAS += 1
        if device["tag"] == "Sensor de Contagem de Pessoas Saída":
            if not device["state"] and state:
                PESSOAS -= 1
        device["state"] = state
    return report

def send_report(skt: socket.socket):
    report = "report" + json.dumps(report_formated())
    skt.send(report.encode())

def watch_inputs(skt: socket.socket):
    count = 0
    while True:
        update = need_update()
        if count == 40:
            count = 0
            update = True
        if update:
            send_report(skt)
        count += 1
        time.sleep(0.05)

def light_when_presence():
    presence_cfg = dict()
    lights_gpio = []
    for device in CFG["inputs"]:
        if device["type"] == "presenca":
            presence_cfg = device
            break
    for device in CFG["outputs"]:
        if device["type"] == "lampada":
            lights_gpio.append(device["gpio"])
    count = 30
    while True:
        if GPIO.input(presence_cfg["gpio"]) and not ALARM_SYSTEM:
            GPIO.output(lights_gpio, MODES["ligar"])
            count = 30
        else:
            count = max(-1, count-1)
        if count == 0:
            GPIO.output(lights_gpio, MODES["desligar"])
        time.sleep(0.5)

def main():
    skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    skt.bind((HOST, PORT))
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    config_gpio()
    threading.Thread(target=light_when_presence, args=()).start()
    connect_central(skt)
    threading.Thread(target=watch_inputs, args=(skt,)).start()

    recv(skt)

    skt.close()
    os._exit(0)

if __name__ == "__main__":
    main()
