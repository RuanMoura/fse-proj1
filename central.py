import socket
import json
import sys
import os
import threading
import time
import curses
from curses import wrapper
from typing import List
from datetime import datetime

with open(sys.argv[1]) as FILE_CFG:
    CFG = json.load(FILE_CFG)
HOST = CFG["ip_servidor_central"]
PORT = CFG["porta_servidor_central"]
CONNS = dict()
DATA = dict()
WIN = dict()
PEOPLE_WIN = None
ALARM = set()
FIRE = set()
STDSCR = None
LOG_FILE = None
ON = "⚡️"
OFF = "⭕"

def accept_connection(skt: socket.socket):
    global CONNS, CONNS
    while True:
        conn, _ = skt.accept()
        name = conn.recv(1024).decode()
        DATA[name] = json.loads(conn.recv(1024).decode()[6:])
        CONNS[name] = conn
        add_window(name)
        threading.Thread(target=listen_connection, args=(conn, name)).start()

def listen_connection(conn: socket.socket, room: str):
    global DATA
    while True:
        msg = conn.recv(1024).decode()
        if msg.startswith('report'):
            DATA[room] = json.loads(msg[6:])
            if room in ALARM:
                verify_alarm(room)
            if room in FIRE:
                verify_fire(room)
            refresh_win(room)
            refresh_people_win()

def send_cmd(cmd: str, room: str):
    CONNS[room].send(cmd.encode())

def execute_cmd(cmd: List) -> str:
    def get_rooms(room: str) -> List:
        if room == "Todas":
            return list(CONNS.keys())
        return [room]
    FP.write(f"{datetime.now().strftime('%H:%M:%S')},{','.join(cmd)}\n")
    action, device, room = cmd
    msg = action + " " + device
    message_error_alarm = "Nao foi possivel ligar o sistema de alarme para"
    message_error_alarm += " a {}.\n Verifique os estados dos sensores."
    if msg == "ligar Alarme":
        for r in get_rooms(room):
            if not alarm_is_posssible(r):
                return message_error_alarm.format(r)
        for r in get_rooms(room):
            ALARM.add(r)
            CONNS[r].send("ligar sistema de alarme".encode())
        return "Sistema de alarme ativado com sucesso"
    if msg == "desligar Alarme":
        for r in get_rooms(room):
            if r in ALARM:
                ALARM.remove(r)
                CONNS[r].send("desligar sistema de alarme".encode())
        deactivate_general_alarm()
        return "Sistema de alarme desligado com sucesso"
    if msg == "ligar Alarme Incêndio":
        for r in get_rooms(room):
            FIRE.add(r)
        return "Alarme de incendio ativado com sucesso"
    if msg == "desligar Alarme Incêndio":
        for r in get_rooms(room):
            if r in FIRE:
                FIRE.remove(r)
        deactivate_general_alarm()
        return "Alarme de incêndio desligado com sucesso"
    for r in get_rooms(room):
        send_cmd(msg , r)
    return ""

def alarm_is_posssible(room: str) -> bool:
    return not (DATA[room]["Sensor de Presença"] or
                DATA[room]["Sensor de Janela"] or
                DATA[room]["Sensor de Porta"])

def verify_alarm(room):
    if not alarm_is_posssible(room):
        activate_general_alarm()

def verify_fire(room):
    if DATA[room]["Sensor de Fumaça"]:
        activate_general_alarm()

def activate_general_alarm():
    for conn in CONNS.values():
        conn.send("ligar alarme".encode())

def deactivate_general_alarm():
    for conn in CONNS.values():
        conn.send("desligar alarme".encode())

def waiting_conn():
    count = 0
    while not CONNS:
        STDSCR.clear()
        STDSCR.addstr(1, 1, "Aguardando conexões" + (count+1)*".")
        STDSCR.refresh()
        count = (count + 1) % 5
        time.sleep(1)

def add_window(name):
    global WIN
    WIN[name] = curses.newwin(16, 32, 0, len(WIN)*32)
    refresh_win(name)

def refresh_win(name):
    global WIN, DATA
    win = WIN[name]
    win.clear()

    special_devices = ["Temperatura", "Umidade", "Contagem de pessoas"]
    row = 1
    for device, state in DATA[name].items():
        if device not in special_devices:
            state = ON if state else OFF
            win.addstr(row, 1, f"{device}: {state}\n")
        elif device == "Temperatura":
            win.addstr(row, 1, f"{device}: {state} C")
        elif device == "Umidade":
            win.addstr(row, 1, f"{device}: {state}%")
        else:
            win.addstr(row, 1, f"{device}: {state}")
        row += 1
    state = ON if name in ALARM else OFF
    win.addstr(row, 1, f"Sistema de alarme: {state}")
    state = ON if name in FIRE else OFF
    win.addstr(row+1, 1, f"Sistema de incêndio: {state}")

    win.border()
    win.addstr(0, (32-len(name))//2, name)
    win.refresh()

def refresh_people_win():
    PEOPLE_WIN.clear()
    PEOPLE_WIN.addstr(1, 1, str(sum([ DATA[room]["Contagem de pessoas"] for room in DATA ])))
    PEOPLE_WIN.border()
    PEOPLE_WIN.addstr(0, 2, "Pessoas no prédio")
    PEOPLE_WIN.refresh()

def menu():
    def add_cmd(cmd, opts, opt_row, opt_column, lower=False):
        part = opts[opt_row][opt_column]
        part = part.lower() if lower else part
        cmd.append(part)

    win = curses.newwin(3, 75, 19, 0)
    log = curses.newwin(4, 75, 22, 0)

    action = ['Ligar', 'Desligar', 'Sair']
    options = ['Dispositivos', 'Alarme', 'Alarme Incêndio']
    by = ['type', 'tag', 'todos']
    types =  [t["type"] for t in CFG["outputs"] if t["type"] != "alarme"]
    tags = [t["tag"] for t in CFG["outputs"] if t["tag"] != "Sirene do Alarme"]
    rooms = list(CONNS.keys()) + ["Todas"]
    confirm = ['Confirmar', 'Refazer']
    opts = [action, options, by, types, tags, rooms, confirm]
    menu_names = ["Menu", "Opções", "Selecionar dispositivos por", "Tipos",\
                  "Tags", "Salas", "Confirmar"]
    res = ""
    opt_column = 0
    opt_row = 0
    cmd = []
    while True:
        win.clear()
        log.clear()
        pad = 1
        for i, choice in enumerate(opts[opt_row]):
            formated = f" {choice} "
            win.addstr(1, pad, formated, curses.A_REVERSE if i == opt_column else curses.A_NORMAL)
            pad += len(formated)
        win.border()
        win.addstr(0, 2, menu_names[opt_row])
        win.refresh()

        log.addstr(1, 1, " ".join(cmd) or res)
        log.border()
        log.addstr(0, 2, "Log")
        log.refresh()
        opts[5] = list(CONNS.keys()) + ["Todas"]

        key = STDSCR.getkey()
        if key == 'KEY_LEFT':
            opt_column = max(0, opt_column - 1)
        elif key == 'KEY_RIGHT':
            opt_column = min(len(opts[opt_row]) - 1, opt_column + 1)
        elif key == '\n':
            if opt_row == 0:
                if opt_column == 2:
                    return
                else:
                    add_cmd(cmd, opts, opt_row, opt_column, lower=True)
                res = ""
            elif opt_row == 1:
                if opt_column:
                    add_cmd(cmd, opts, opt_row, opt_column)
                    opt_row = len(opts) - 3
            elif opt_row == 2:
                if opt_column == 1:
                    opt_row += 1
                if opt_column == 2:
                    add_cmd(cmd, opts, opt_row, opt_column)
                    opt_row += 2
            elif opt_row == 3:
                add_cmd(cmd, opts, opt_row, opt_column)
                opt_row += 1
            elif opt_row == 4 or opt_row == 5:
                add_cmd(cmd, opts, opt_row, opt_column)
            elif opt_row == 6 and opt_column==0:
                res = execute_cmd(cmd)
            opt_row = (opt_row + 1) % len(opts)
            if opt_row == 0:
                cmd = []
            opt_column = 0

def main(stdscr):
    global STDSCR, FP, PEOPLE_WIN
    STDSCR = stdscr

    curses.curs_set(0)
    skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    skt.bind((HOST, PORT))
    skt.listen()

    threading.Thread(target=accept_connection, args=(skt,)).start()
    waiting_conn()

    FP = open('log.csv', 'w')
    FP.write("Horário,Ação,Dispositivo,Sala\n")
    PEOPLE_WIN = curses.newwin(3, 21, 16, 0)
    menu()

    for room in CONNS:
        send_cmd("exit", room)

    FP.close()
    skt.close()


if __name__ == "__main__":
    wrapper(main)
    os._exit(1)
