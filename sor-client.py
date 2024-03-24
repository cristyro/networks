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
get_requests= [] #list of get requests
window_size = 0 #change to given by client

# ------- Write HTTP request to the server -------
#format of the request: GET/filename HTTP/1.0\r\nConnection:Keep-alive\r\n\r\n
def write_http_request():
    global get_requests
    file_pairs = [(args.file_pairs[i], args.file_pairs[i+1]) for i in range(0, len(args.file_pairs), 2)]

    if len (file_pairs)>1:
        for read_file, write_file in file_pairs:
            request= "GET /"+read_file+" HTTP/1.0\r\nConnection:Keep-alive\r\n\r\n"
            get_requests.append(request)

    else:
        request= "GET /"+file_pairs[0][0]+" HTTP/1.0\r\n\r\n"
        get_requests.append(request)



#   ---Class to handle the RDP state machine ---
class rdp:
    def __init__(self):
        self.state= "closed"

    def set_state(self, new_state):
        self.state= new_state

    def get_state(self):
        return self.state
    
    def put_dat(self, dat):
        global snd_buff
        snd_buff.append(dat)

    def clean_up(self):
        global snd_buff
        global command
        snd_buff= []

    def pack_and_send(self, msg):
        global snd_buff
        global window_size
        #Packetize still
        commands= [msg.command for msg in snd_buff]
        length=0
        payload= ""
           
        while len(snd_buff) > 0: #check window size as well 
            msg= snd_buff.pop(0)    
            payload+= msg.payload
            #print("msg", msg)
            length+= len(msg.payload)
            window_size-= len(msg.payload) #decrement window size when sending a packet


        commands_str = "|".join(commands)
        final_pack=packet(commands_str, 0, -1, payload)
        sock.sendto(str(final_pack).encode(), (args.server_ip, args.server_udp_port))
        #print("sent!", final_pack)
        snd_buff=[] #clear the buffer after sending the packets
        commands=[]
        #sock.sendto(msg, (args.server_ip, args.server_udp_port))
                  
    
    def open(self):
        global snd_buff
        if self.state == "closed":
            self.state= "syn_sent"
            syn = packet("SYN",0, -1, "")
            snd_buff.append(syn)
      
            info=""
            while len(get_requests) > 0:
                dat_send= get_requests.pop(0)
                info+=dat_send
            dat= packet("DAT", 0, -1, info)
            self.put_dat(dat)
            self.pack_and_send(dat)

        
    #sample command to parse b"SYN|DAT|ACK"
    #based on this parse commands go to the state machine
    #append to commands
    def parse_command(self, command): #upon receiving a command from the server, remember it is going to be a binary string 
        pattern= rb'([A-Z]{3})(?:\|([A-Z]{3}))(?:\|([A-Z]{3}))?'
        matches= re.findall(pattern, command)
        print(matches.decode() for match in matches)
        return matches



    def state_machine(self):
        if self.state != "closed":
            print("NEED TO IMPLEMENT STATE MACHINE....")
            #parse command and decide what to do!

    
    def __str__(self) :
        return str(self.seq_num).encode()+ str(self.ack_num).encode() +  self.payload.encode()

        
    
class packet:
    def __init__(self, command,seq_num, ack_num, payload):
        self.command= command
        self.seq_num= seq_num
        self.ack_num= ack_num
        self.payload= payload
        self.length= len(payload)

    
    def __str__(self) :
        return f"Command: {self.command}, Seq: {self.seq_num}, Ack: {self.ack_num}, Length: {self.length}, Payload: {self.payload}, Window: {window_size}"



rdp= rdp()

def udp_sock_start(ip, port):
    global sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rdp.open()
    print("STATE IS NOW:", rdp.get_state())



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
    #print("Window size", window_size)
    

def main_loop():
    global snd_buff, rcv_buff, rdp
    rdp.open()
    print("Sender state: ", rdp.get_state())

    while rdp.get_state!= "closed":
        print("In main loop")
        readable, writable, exceptional = select.select([sock], [], [], 10)
        for s in readable:
            data, addr = sock.recvfrom(5000)
            print("Received ", data.decode())
            #rcv_buff.append(data)
            #receiver.rcv_data(data)
        for s in writable:
            if len(snd_buff) > 0:
                msg= snd_buff.pop(0)
                sock.sendto(msg, (args.server_ip, args.server_udp_port))



if __name__== "__main__":
    parse_args()
    write_http_request()
    udp_sock_start(args.server_ip, args.server_udp_port)
    print("Client started")
    main_loop()




