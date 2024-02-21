import socket
import select
import sys
import queue
import threading
import time
import pickle
import re
import os
from datetime import datetime
import time

WINDOW_SIZE = 2048
#for tuple access
ACK= 0
WINDOW= 1
PACK_HEADER_MIN= 4
snd_buff = []
rcv_buff = []
#echo_server=  ("10.10.1.100", 8888) for picolab
echo_server= ("localhost", 8888) # for local testing
sender_lock = threading.Lock()
receiver_lock = threading.Lock()

class udp_socket:
    def __init__(self, ip, port):
        global snd_buff, rcv_buff
        self.ip =  ip
        self.port =  int(float (port))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((ip , self.port))
        self.sock.setblocking(0)
        self.inputs = [self.sock]
        self.outputs = []
        self.timeout = 10
       
    def recv(self):
        data, addr = self.sock.recvfrom(1024)
        return data, addr

    def close(self):
        self.sock.close()

class rdp_sender:
    def __init__(self):
        global snd_buff
        self.state = ""
        self.timeout = 10  # Set your desired timeout value here

    def get_state(self):
        return self.state

    def open(self):
        self.state = "SYN"
        # Implement sending SYN packet
        # Start timeout timer

    def check_timeout(self):
        if self.state != "closed":
            # Check if timeout occurred
            pass


class packet:
    def __init__(self, command, sequence, length, payload):
        self.command = command
        self.sequence = int(sequence)
        self.length = int(length)
        if payload is None:
            self.payload = 0
        else:
            self.payload = payload

    #Returns acknoledgment number and window size
    def generate_ack(self):
        string = f"{self.sequence};{WINDOW_SIZE-self.length}"
        return string
    
    def __reduce__(self):
        return (self.__class__, (self.command, self.sequence, self.length, self.payload))
        

    def __str__(self) -> str:
        return f"{self.command}; {self.sequence}; {self.length}; {self.payload}"
   


class rdp_receiver:
    def __init__(self):
        global rcv_buff
        self.state = ""

    def rcv_data(self, udp_sock, data):
        print(".......\n")
        try:
            with receiver_lock:
                received, addr = udp_sock.recvfrom(1024)
                received= received.decode()
                received= received.strip()

                if received.isnumeric(): #received ACK
                    rcv_buff.append(received)
                    print("ACK RECEIVED", received)
                    ack, window= received.split(";")      

                else: #received DAT or SYN pack 
                    print("OTHER INFO in RDP RECEIVER \n", received)
                    rcv_buff.append(received)
                    #received DAT pack
                    pack_and_send(udp_sock, received)
               
        except BlockingIOError:
                print("No data received yet")
                pass
        # Handle received data
   
def is_complete(data):
    lines= data.split("\n")
    
    if lines[0].strip() not in ["SYN", "DAT", "FIN"]: #command not correct
        #print("Command not correct")
        return False
    
    if not lines[1].strip().startswith("Sequence:"): #sequence number not correct
        #print("Sequence number not correct")
        return False
    
    return True
    
        

def get_number(string):
    result= ""
    for char in string:
        if char.isdigit():    
            result+= char

    int_result= int(result)
    return int_result

#TODO: handle special DAT case
#Return a packet object if the data is a valid packet

def packetize(data):
    packet_regex = r'\n'
    command_found = re.split(packet_regex, data)
    #print("Command found", command_found)
    correct_format= command_found[0].strip() in ["SYN", "DAT", "FIN"] and command_found is not None
    #print("Correct format", correct_format)
    if correct_format : #and command is not DAT
        if "DAT" not in command_found:
            instructions= data.split("\n")
            #print("INSTRUCTIONS:", instructions)
            command= instructions[0]
            sequence= instructions[1]
            seq_no= get_number(sequence)
            l= instructions[2]
            length= get_number(l)
            p = packet(command, seq_no, length, 0)  #payload is not needed for SYN, FIN, ACK, RST
            return p

        if "DAT" in command_found : #special case
            instructions= data.split("\n")
            #print("INSTRUCTIONS:", instructions , len(instructions))
            if len(instructions) >= PACK_HEADER_MIN:
                command, sequence, l, payload= instructions[0], instructions[1], instructions[2], instructions[3]
                seq_no= get_number(sequence)
                length= get_number(l)
                p = packet(command, seq_no, length, payload)
                return p 

  
def pack_and_send(udp_sock, data):
    #with sender_lock:
        #print("IS COMPLETE", is_complete(data))
        if data is not None : #and is_complete(data):
            #print("Data to be packetized", repr (data))
            p = packetize(data)
            string_p= str(p)
            #print("Packetized data", p)
            #string_p= string_p.replace("\n", ";")
            #print("Sending packet....", string_p)

            snd_buff.append(string_p)
            udp_sock.sendto(string_p.encode(), echo_server)
            return True


def unpack_and_ack(instructions, dp_sock):
    command, seq, length, payload= instructions[0], instructions[1], instructions[2], instructions[3]
    p= packet(command, seq, length, payload)
    print("Creating acknowledgment...... ")
    ack_info = p.generate_ack()
    print("ACK INFO", ack_info)
    #with sender_lock:
    dp_sock.sendto(ack_info.encode(), echo_server)


def driver(udp_sock):
    global snd_buff, rcv_buff
    sender = rdp_sender()
    receiver = rdp_receiver()
    timeout= 10

    while sender.get_state() != "closed" or receiver.get_state() != "closed":
        readable, writable, exceptional = select.select([udp_sock], [udp_sock], [udp_sock], timeout)
        if udp_sock in readable:
            #print("socket is readable")
                data, conn = udp_sock.recvfrom(1024)
                data= data.decode()
                #print("Data received.....", data)
                receiver.rcv_data(udp_sock, data)

            #send SYN
                pack_and_send(udp_sock, data)
                
            #receive ACK and handshake
        try:
                with receiver_lock:
                    received, addr = udp_sock.recvfrom(1024)
                    received= received.decode()
                    received= received.strip()
                    if received.isnumeric(): #received ACK
                        rcv_buff.append(received)
                        #print("ACK RECEIVED", received)
                        ack, window= received.split(";")
                        
                    else:
                        #received DAT pack
                        #print("OTHER INFO", received)
                        pack_and_send(udp_sock, received)
               
        except BlockingIOError:
                #print("No data received yet")
                pass
                
                
        if udp_sock in writable:
            message= "SYN\nSequence:0\nLength:0\n\n"
            next_message= "DAT\nSequence:1\nLength:22\nThis is the payload\n\n"

            udp_sock.sendto(message.encode(), echo_server) #to start the handshake

            #RECEIVE SYN, send ACK this is receive data 
            try:
                #with receiver_lock:
                    packet_received = udp_sock.recvfrom(1024)
                    packet_received= packet_received[0]
                    packet_received= packet_received.decode().strip()
                    instructions= packet_received.split(";")
                    #print(instructions, len(instructions))
                    if packet_received is not None : #to meet the minimum length of a packet header 
                        if not packet_received.isnumeric(): #received ACK
                            if len(instructions) >= PACK_HEADER_MIN: #for SYN and FIN
                                unpack_and_ack(instructions, udp_sock)

                    else: #for DAT
                        #print("Instructions......", instructions)
                        instructions= packet_received.split("\n")
                        unpack_and_ack(instructions, udp_sock)

           
            except BlockingIOError:
                print("No data received yet")
                pass
            #GET SYN and send ACK

            
            #send DAT
            try:
                udp_sock.sendto(next_message.encode(), echo_server)

            except BlockingIOError:
                print("No data received yet")
                pass
                       

        sender.check_timeout()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python script.py <ip_address> <port>")
        exit(1)
    else:
        ip_address, port_no = sys.argv[1], int(sys.argv[2])
        socket= udp_socket(ip_address, port_no)
        driver(socket.sock)
