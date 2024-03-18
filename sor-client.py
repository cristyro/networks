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
snd_buff = [] #queue to send messages
rcv_buff = [] #queue of received messages 
sock= None #socket object
args= None #command line arguments 
window_size = 0


#   ---Class to handle the RDP state machine ---
class rdp:
    def __init__(self):
        self.state= "closed"

    def set_state(self, new_state):
        self.state= new_state

    def get_state(self):
        return self.state
    
    def open(self):
        self.state= "syn_sent"
        syn = packet(0, -1, "", window_size)
        snd_buff.append(syn)


    def state_machine(self):
        if self.state != "closed":
            print("NEED TO IMPLEMENT STATE MACHINE....")
        
    

class packet:
    def __init__(self, seq_num, ack_num, payload, window_size):
        self.seq_num= seq_num
        self.ack_num= ack_num
        self.payload= payload
        self.length= len(payload)
        self.win= window_size

    def __str__(self):
        return "Seq: " + str(self.seq_num) + " Ack: " + str(self.ack_num) + " Length: " + str(self.length) + " Payload: " + str(self.payload) + " Window: " + str(self.win)



def udp_sock_start(ip, port):
    global sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((ip , port))
    sock.setblocking(0)



#   ---Helpers to parse the command line arguments---  
def parse_args():
    global args
    parser = argparse.ArgumentParser(description="Process command line arguments")
    parser.add_argument("server_ip", help="Server IP address")
    parser.add_argument("server_udp_port", type=int, help="Server UDP port number")
    parser.add_argument("client_buffer_size", type=int, help="Client buffer size")
    parser.add_argument("client_payload_length", type=int, help="Client payload length")
    parser.add_argument("file_pairs", nargs="+", metavar=("read_file", "write_file"), 
                        help="Pairs of read and write file names")
    
    args = parser.parse_args()
    global window_size
    window_size= args.client_buffer_size

# 
def run_sor_client():
    global args
    parse_args()
    #Group optional pairs in read, write tuple
    file_pairs = [(args.file_pairs[i], args.file_pairs[i+1]) for i in range(0, len(args.file_pairs), 2)]
    #print("Server IP:", args.server_ip)
    #print("Server UDP Port:", args.server_udp_port)
    #print("Client Buffer Size:", args.client_buffer_size)
    #print("Client Payload Length:", args.client_payload_length)
    #print("File Pairs:")
    #for read_file, write_file in file_pairs:
        #print("  Request:", read_file, "Write:", write_file)
    

def main_loop():
    global snd_buff, rcv_buff
    sender= rdp()
    receiver= rdp()

    sender.open()

    while sender.get_state!= "closed" and receiver!= "closed":
        readable, writable, exceptional = select.select([sock], [], [], 10)
        for s in readable:
            data, addr = sock.recvfrom(1024)
            rcv_buff.append(data)
            #receiver.rcv_data(data)
        for s in writable:
            if len(snd_buff) > 0:
                msg= snd_buff.pop(0)
                sock.sendto(msg, (args.server_ip, args.server_udp_port))
                #sender.send(msg)


    

if __name__== "__main__":
    run_sor_client()
    udp_sock_start(args.server_ip, args.server_udp_port)
    print("Client started")
    main_loop()




