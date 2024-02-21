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

    def open(self):
        self.state = "SYN"
        syn_packet = packet("SYN", 0, 0, 0)  # Create SYN packet
        ack_info = syn_packet.generate_ack()  # Generate acknowledgment for SYN
        print("SYN Packet with Acknowledgment:", syn_packet)
        print("Acknowledgment for SYN:", ack_info)
    
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
        if self.command == "SYN":
                return f"{self.sequence};{self.sequence + 1}"  # Acknowledgment number for SYN
        else:
            return f"{self.sequence};{WINDOW_SIZE - self.length}"
    
    def __reduce__(self):
        return (self.__class__, (self.command, self.sequence, self.length, self.payload))
        

    def __str__(self) -> str:
        return f"{self.command}; {self.sequence}; {self.length}; {self.payload}"
   


class rdp_receiver:
    def __init__(self):
        global rcv_buff
        self.state = ""

    def rcv_data(self, udp_sock, data):
        global rcv_buff
        print(".......\n")
        data= data.decode() 
        pack_and_send(udp_sock, data)
        #receive ACK and handshake
        try:
            received, addr = udp_sock.recvfrom(1024)
            received= received.decode()
            received= received.strip()
            if received.isnumeric(): #received ACK
                rcv_buff.append(received)
                ack, window= received.split(";")
                print("ACK RECEIVED", ack, window)
                #ack_dict[ack]= window              
            else:
                #received DAT pack
                print("OTHER INFO", received)
                pack_and_send(udp_sock, received)
               
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


#Return a packet object if the data is a valid packet
def packetize(data):
    packet_regex = r'\n'
    command_found = re.split(packet_regex, data)
    print("Command found", command_found)
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
            #print("INSTRUCTIONS IN PACKETIZE:", instructions , len(instructions))
            if len(instructions) >= PACK_HEADER_MIN:
                command, sequence, l, payload= instructions[0], instructions[1], instructions[2], instructions[3]
                seq_no= get_number(sequence)
                length= get_number(l)
                p = packet(command, seq_no, length, payload)
                return p 
            

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
            #print("PACK ",pack)
            pack_size_bytes = len(pack.encode())  # Calculate the size in bytes
            #print(f"Packet {i // DAT_PACK_SIZE} size: {pack_size_bytes} bytes")
    #return data_packs

  
def pack_and_send(udp_sock, data):
    global snd_buff
    if data is not None:  # and is_complete(data):
        p = packetize(data)
        if p is not None:  # Check if packetization was successful
            string_p = str(p)
            # print("Sending packet....", string_p)
            if packetize(data) is not None:
                print("Sending packet....", string_p)
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
    timeout= 10
    syn_sent= False

    while sender.get_state() != "closed" or receiver.get_state() != "closed":
        readable, writable, exceptional = select.select([udp_sock], [udp_sock], [udp_sock], timeout)

        if udp_sock in readable:
            data, conn = udp_sock.recvfrom(1024)
            receiver.rcv_data(udp_sock, data)
               
                
        if udp_sock in writable:
            message= "SYN\nSequence:0\nLength:0\n\n"
            next_message= "DAT\nSequence:1\nLength:22\nStart to send data\n\n"
            
            if not syn_sent:  # Send SYN packet only if not already sent
                udp_sock.sendto(message.encode(), echo_server)  # Send SYN packet
                syn_sent = True  # Update the flag indicating that SYN packet has been sent
                
            #RECEIVE SYN, send ACK this is receive data 
            try:
                    packet_received = udp_sock.recvfrom(1024)
                    packet_received= packet_received[0]
                    packet_received= packet_received.decode().strip()
                    instructions= packet_received.split(";")
                    if len(instructions)==1:
                        instructions= packet_received.split("\n")
                    
                    if packet_received is not None : #SYN and FIN received here 
                            if len(instructions) >= PACK_HEADER_MIN: 
                               ack_info= unpack_and_ack(instructions, udp_sock)
                               print("ACK INFO", ack_info)

                    else: #for DAT
                        instructions= packet_received.split("\n")
                        unpack_and_ack(instructions, udp_sock)
                        print("ACK INFO FOR DAT", ack_info)
           
            except BlockingIOError:
                print("No data received yet")
                pass
            #GET SYN and send ACK

            if syn_sent:  # Send DAT packet only if SYN has been sent
                try:
                    udp_sock.sendto(next_message.encode(), echo_server)  # Send DAT packet

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
        filename= sys.argv[3]
        generate_data_packs(filename) #return a list of data packs
        socket= udp_socket(ip_address, port_no)
        driver(socket.sock)
