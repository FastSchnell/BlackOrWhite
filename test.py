# -*- coding: utf-8 -*-
import logging
import time

from black import WebSocket


def resv_data(data):
    print data


def send_data(ws):
    while 1:
        time.sleep(1)
        ws.send('ok a ~', path='/')


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    ws = WebSocket(host='0.0.0.0', port=1907)
    ws.register(path='/', recv_func=resv_data, send_func=send_data)
    ws.serve_forever()
