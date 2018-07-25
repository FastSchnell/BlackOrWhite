# -*- coding: utf-8 -*-

import socket
import hashlib
import base64
import logging

GEVENT = None
TCP_BUF_SIZE = 8192
WS_MAGIC_STRING = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
RESPONSE_STRING = 'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n' \
                  'Connection: Upgrade\r\nSec-WebSocket-Accept: {}\r\n\r\n'

logger = logging.getLogger('I`m_Black')


class T(object):
    type = 'gevent'  # threading or gevent

    def __init__(self):
        try:
            global GEVENT
            import gevent
            from gevent.pool import Group
            from gevent.monkey import patch_all
            patch_all()
            self.Thread = Group().spawn
            GEVENT = gevent
            logger.warning('import gevent success')
        except Exception as e:
            logger.warning('failed to import gevent' + repr(e))
            self.type = 'threading'
            from threading import Thread
            self.Thread = Thread

    def thread(self, target, args=()):
        if self.type == 'gevent':
            self.Thread(target, *args)
        else:
            self.Thread(target=target, args=args).start()


class WebSocket(object):
    def __init__(self, host=None, port=None, listen_count=None):
        self.host = host or '127.0.0.1'
        self.port = port or 1908
        self.listen_count = listen_count or 0
        self.Thread = T().thread
        self.path_mappings = dict()

    def request(self, f):
        _request = dict()
        line = f.readline().strip()
        line_l = line.split(' ')

        if len(line_l) == 3:
            _request.update({
                'method': line_l[0],
                'path': line_l[1],
                'http_protocol': line_l[2],
            })
        else:
            raise Exception('method, path, http_protocol error: %s' % line)
        while line:
            if line == '\r\n':
                break
            line = f.readline()
            line_l = line.strip().split(': ')
            if len(line_l) == 2:
                _request[line_l[0]] = line_l[1]

        if _request['method'] != 'GET':
            raise Exception('method error, %s' % _request['method'])

        if _request['path'] not in self.path_mappings.keys():
            raise Exception('path not found, %s' % _request['path'])

        if _request['http_protocol'] != 'HTTP/1.1':
            raise Exception('http_protocol error, %s' % _request['http_protocol'])

        return _request

    @staticmethod
    def ws_key(request):
        if request.get('Upgrade') == 'websocket':
            if request.get('Connection') == 'Upgrade':
                if request.get('Sec-WebSocket-Version') == '13':
                    return request.get('Sec-WebSocket-Key')

    @staticmethod
    def make_ws_accept(ws_key):
        key = ws_key + WS_MAGIC_STRING
        sha1 = hashlib.sha1()
        sha1.update(key)
        key = sha1.digest()
        ws_accept = base64.b64encode(key)
        return ws_accept

    @staticmethod
    def parse_data(msg):
        code_length = ord(msg[1]) & 127

        if code_length == 126:
            masks = msg[4:8]
            data = msg[8:]
        elif code_length == 127:
            masks = msg[10:14]
            data = msg[14:]
        else:
            masks = msg[2:6]
            data = msg[6:]

        i = 0
        raw_str = ''

        for d in data:
            raw_str += chr(ord(d) ^ ord(masks[i % 4]))
            i += 1
        return raw_str

    @staticmethod
    def send_data(raw_str):
        back_str = list()
        back_str.append('\x81')
        data_length = len(raw_str)

        if data_length < 125:
            back_str.append(chr(data_length))
        else:
            back_str.append(chr(126))
            back_str.append(chr(data_length >> 8))
            back_str.append(chr(data_length & 0xFF))

        back_str = ''.join(back_str) + raw_str
        return back_str

    def register(self, path, recv_func=None, send_func=None):
        self.path_mappings[path] = {
            'recv_func': recv_func,
            'send_func': send_func,
            'client_pools': [],
        }

    def fake_tunnel(self, client, path):
        if path in self.path_mappings.keys():
            self.path_mappings[path]['client_pools'].append(client)
        path_mapping = self.path_mappings.get(path, {})
        recv_func = path_mapping.get('recv_func')
        send_func = path_mapping.get('send_func')
        self.Thread(target=self.recv, args=(recv_func, client, path))
        self.Thread(target=send_func, args=(self,))

    def close(self, client, path):
        try:
            self.path_mappings[path]['client_pools'].remove(client)
        except ValueError:
            pass

        try:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except:
                pass
            client.close()
        except Exception as e:
            logger.warning('client close error, e=%s' % repr(e))

    def recv(self, recv_func, client, path):
        data = ''
        d = client.recv(TCP_BUF_SIZE)
        while d:
            data += d
            if len(d) < TCP_BUF_SIZE:
                recv_func(self.parse_data(data))
                data = ''
            d = client.recv(TCP_BUF_SIZE)

        self.close(client, path)

    def send(self, data, path):
        clients = self.path_mappings.get(path, {}).get('client_pools', [])
        for client in clients:
            try:
                client.sendall(self.send_data(data))
            except Exception as e:
                logger.warning('client sendall error, e=%s' % repr(e))
                self.close(client, path)

    def serve_forever(self):
        soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        soc.bind((self.host, self.port))
        soc.listen(self.listen_count)

        while True:
            try:
                client, _ = soc.accept()
                try:
                    f = client.makefile()
                    request = self.request(f)
                    ws_key = self.ws_key(request)
                    if ws_key:
                        ws_accept = self.make_ws_accept(ws_key)
                        data = RESPONSE_STRING.format(ws_accept)
                        client.sendall(data)
                        self.fake_tunnel(client, request.get('path'))

                    else:
                        raise Exception('Sec-Websocket-Key error')

                except:
                    logging.error('closing client', exc_info=1)
                    client.close()

            except Exception as e:
                logging.error(repr(e))


__all__ = ['WebSocket']
