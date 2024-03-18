import socket
import select
import sys
import queue
import time
import re
import os
import argparse
from datetime import datetime
import time

# Global variables 
snd_buff = {} #queue to send messages
rcv_buff = {} #queue of received messages 
sock= None #socket object
window_size= 0
paylad_len= 0 


def udp_sock_start(ip, port):
    global sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((ip , port))
    sock.setblocking(0)


if __name__== "__main__":
    ip, port , window_size, payload_len = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
    print("ip: ", ip, " port: ", port, " window_size: ", window_size, " payload_len: ", payload_len)
    udp_sock_start(ip, port)

