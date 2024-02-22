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
DAT_PACK_SIZE= 1024
#for tuple access
ACK= 0
WINDOW= 1
PACK_HEADER_MIN= 3
snd_buff = []
rcv_buff = []
data_packs= []
filename= None
#echo_server=  ("10.10.1.100", 8888) for picolab
echo_server= ("localhost", 8888) # for local testing

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

    #implement with the ugly code i have
    def open(self):
        self.state = "SYN"
        # Implement sending SYN packet
        # Start timeout timer
    
    def send(self, data):
        # Implement sending data packet
        pass

    def close(self):
        self.state = "FIN"
        # Implement sending FIN packet
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

class rdp_receiver:
    def __init__(self):
        global rcv_buff
        self.state = ""

    def rcv_data(self, udp_sock, data):
        global rcv_buff
        print(".......\n")
        data= data.decode() 
        print("Received data in rcv data 1:", data)
        print("\n")
        pack_and_send(udp_sock, data)
        #receive ACK and handshake
        try:
            received, addr = udp_sock.recvfrom(1024)
            print("Received data in rcv data 2:")
            received= received.decode()
            received= received.strip()
            if not received.isnumeric(): 
                pack_and_send(udp_sock, received)
            else: #acknowledgment
                print("Received acknowledgment:", received) 

                # Generate and send acknowledgment for the received data packet
                ack_packet = packet("ACK", int(received), 0, None)
                ack_info = ack_packet.generate_ack()
                print("Sending acknowledgment:", ack_info)
                udp_sock.sendto(ack_info.encode(), addr)

        except BlockingIOError:
            #print("No data received yet")
            pass

        
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




#generae data packs from the file, all with 1024 bytes
def generate_data_packs(filename):
    global data_packs
    with open(filename, "r") as file:
        data= file.read()
        data= data.strip()
        #print("Data length", len(data))
        for i in range(0, len(data), DAT_PACK_SIZE): #split the data into 1024 byte packs
            pack= data[i:i+DAT_PACK_SIZE] #get the next 1024 bytes
            data_packs.append(pack)
            pack_size_bytes = len(pack.encode())  # Calculate the size in bytes
    #return data_packs
            
#Return a packet object if the data is a valid packet
def packetize(data):
    packet_regex = r'\n'
    command_found = re.split(packet_regex, data)
    correct_format= command_found[0].strip() in ["SYN", "DAT", "FIN"] and command_found is not None
    print("Correct format", correct_format)
    print("\n")
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
            print("INSTRUCTIONS IN PACKETIZE:", instructions , len(instructions))
            print("\n")
            if len(instructions) >= PACK_HEADER_MIN:
                command, sequence, l, payload= instructions[0], instructions[1], instructions[2], instructions[3]
                seq_no= get_number(sequence)
                length= get_number(l)
                p = packet(command, seq_no, length, payload)
                return p 
            
  
def pack_and_send(udp_sock, data):
    global snd_buff
    if data is not None:  # and is_complete(data):
        p = packetize(data)
        print("PACKETIZED DATA:", p)
        if p is not None:  # Check if packetization was successful
            string_p = str(p)
            if packetize(data) is not None:
                ack_info = p.generate_ack()
                print("ACK INFO", ack_info)

                #print("Sending packet....", string_p)
                #snd_buff.append(string_p)
                #if p.sequence not in seq_dict:
                    #seq_dict[p.sequence]= p
                udp_sock.sendto(string_p.encode(), echo_server)




def unpack_and_ack(instructions, dp_sock):
    if len (instructions) == 3:
        command, seq, length= instructions[0], instructions[1], instructions[2]
        payload= 0
    elif len(instructions) > PACK_HEADER_MIN:
        command, seq, length, payload= instructions[0], instructions[1], instructions[2], instructions[3]
    seq_no= get_number(seq)
    length= get_number(length)
    p= packet(command, seq_no, length, payload)
    ack_info = p.generate_ack()
    #print("ACK INFO", ack_info)
    return ack_info

    #dp_sock.sendto(ack_info.encode(), echo_server)

def driver(udp_sock):
    global snd_buff, rcv_buff
    sender = rdp_sender()
    receiver = rdp_receiver()
    timeout = 10
    syn_sent = False
    data_sent = False

    while sender.get_state() != "closed" or receiver.get_state() != "closed":
        readable, writable, exceptional = select.select([udp_sock], [udp_sock], [udp_sock], timeout)

        if udp_sock in readable:
            data, conn = udp_sock.recvfrom(1024)
            receiver.rcv_data(udp_sock, data)

        if udp_sock in writable:
            if not syn_sent:
                # Send SYN packet
                syn_message = "SYN\nSequence:0\nLength:0\n\n"
                udp_sock.sendto(syn_message.encode(), echo_server)
                print("Sent SYN packet")
                syn_sent = True
            elif not data_sent:
                # Send data packets
                print("Sending data packets")
                for data_pack in data_packs:
                    udp_sock.sendto(data_pack.encode(), echo_server)
                    print("Sent data packet:", data_pack)

                data_sent = True  # Mark that data has been sent
                
            else:
                # Wait for acknowledgment for data packets
                try:
                    print("Waiting for acknowledgment for data packets")
                    ack_packet, addr = udp_sock.recvfrom(1024)
                    ack_packet = ack_packet.decode().strip()
                    print("Received acknowledgment for data packet:", ack_packet)
                    # Process acknowledgment packet if needed
                except BlockingIOError:
                    print("No acknowledgment received yet for data packets")
                    pass

                # End of data transmission, send FIN packet
                fin_message = "FIN\nSequence:0\nLength:0\n\n"
                udp_sock.sendto(fin_message.encode(), echo_server)
                print("Sent FIN packet")

                # Wait for acknowledgment for FIN packet
                try:
                    ack_packet, addr = udp_sock.recvfrom(1024)
                    ack_packet = ack_packet.decode().strip()
                    print("Received acknowledgment for FIN packet:", ack_packet)
                    exit(0)
                    # Process acknowledgment packet if needed
                except BlockingIOError:
                    print("No acknowledgment received for FIN packet yet")
                    pass

        sender.check_timeout()



if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python script.py <ip_address> <port>")
        exit(1)
    else:
        ip_address, port_no = sys.argv[1], int(sys.argv[2])
        filename= sys.argv[3]
        generate_data_packs(filename) #return a list of data packs
        socket= udp_socket(ip_address, port_no)
        driver(socket.sock)
