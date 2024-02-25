import socket
import select
import sys
import queue
import time
import re
import os
from datetime import datetime
import time

DAT_PACK_SIZE = 1024
SLIDING_WINDOW = 1024*5
PACK_HEADER_MIN = 3

all_acks= []
to_send= []
data_packs = []
filename = None
outfile = None
echo_server = ("localhost", 8888)  # for local testing

class udp_socket:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = int(float(port))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(0) # Set non-blocking mode
        self.sock.bind((ip, self.port))
        self.sock.setblocking(0)
        self.inputs = [self.sock]
        self.outputs = []
        self.timeout = 10

    def recv(self):
        data, addr = self.sock.recvfrom(5000)
        return data, addr

    def close(self):
        self.sock.close()

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
        string = f"{self.sequence};{SLIDING_WINDOW-self.length}"
        return string
    
    def __reduce__(self):
        return (self.__class__, (self.command, self.sequence, self.length, self.payload))
        
    def __str__(self) -> str:
        return f"{self.command};{self.sequence};{self.length}; {self.payload}"


class rdp_sender:
    def __init__(self, udp_sock):
        global snd_buff
        self.state = ""
        self.timeout = 10  # Set your desired timeout value here
        self.udp_sock = udp_sock

    def get_state(self):
        return self.state

    def open(self):
        self.state = "SYN"
        syn_message = "SYN\nSequence:0\nLength:0\n\n"
        self.udp_sock.sendto(syn_message.encode(), echo_server)
        print(f"{datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')}: Send; SYN; Sequence: 0; Length: 0")

    

               
    def prepare_data_packs(self):
        global to_send
        self.state = "DAT"
        seq_number = 0
        for i in range (0, len(data_packs)):
            if i == 0:
                seq_number = 1
            else:   
                seq_number += len(data_packs[i])
            data = f"DAT:{seq_number}:{len(data_packs[i])}:{data_packs[i]}"
            to_send.append(data)


      
    def close(self):
        self.state = "FIN"
        # Implement sending FIN packet
        # Start timeout timer

    def send_packet(self, data):
        p= packetize(data)
        string = str(p)
        self.udp_sock.sendto(string.encode(), echo_server)

    def log_ack(self, ack_number, window_sz):
        timestamp = datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')
        log_message = f"{timestamp}: Receive; ACK; Acknowledgment: {ack_number}; Window: {window_sz}"
        print(log_message)

    def log_sent_data(self, command, sequence, length):
        timestamp = datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')
        log_message = f"{timestamp}: Sent; {command}; Sequence: {sequence}; Length: {length}"
        print(log_message)

    def update_window(self, length_freed):
        global SLIDING_WINDOW
        SLIDING_WINDOW += length_freed


    def process_ack(self, data):
        info  = data.split(":")
        print("ACK received:", info)
        syn_received= [p for p in info if "SYN" in p]
        dat_received= [p for p in info if "DAT" in p]
        fin_received= [p for p in info if "FIN" in p]
        
        if syn_received and self.state!= "SYN":
            self.state = "SYN"
        if dat_received:
            self.state = "DAT"
            print("ACK for DAT", info)
            self.update_window(int(info[2]))
            self.log_ack(int(info[1]), int(info[2]))


    def check_timeout(self):
        if self.state != "closed":
            # Check if timeout occurred
            pass




class rdp_receiver:
    def __init__(self, udp_sock):
        self.state = ""
        self.expected_seq = 0
        self.prev_seq=0
        self.udp_sock = udp_sock
        self.window_available= SLIDING_WINDOW #2048
        self.first= True

    def rcv_data(self, udp_sock, data):
        self.state= ""
    
    def set_seq(self, seq):
        self.seq= seq

    def stablish_connection(self, received):
        print(f"{datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')}: Receive; SYN; Sequence: 0; Length: 0")
        self.expected_seq = 0
        ack_sequence = 0
        ack_packet = f"ACK:{ack_sequence}:{self.window_available}:SYN:0:0"
        print(f"{datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')}: Send; ACK; Acknowledgment: {ack_sequence}; Window: {self.window_available}")
        self.udp_sock.sendto(ack_packet.encode(), echo_server)

    def log_received_data(self, command, sequence, length):
        timestamp = datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')
        log_message = f"{timestamp}: Receive; {command}; Sequence: {sequence}; Length: {length}"
        print(log_message)

    def log_send_ack(self, ack_sequence, window_size):
        timestamp = datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')
        log_message = f"{timestamp}: Send; ACK; Acknowledgment: {ack_sequence}; Window: {window_size}"
        print(log_message)

    #PRODUCES ACKS FOR RECEIVED PACKETS
    def rcv_data(self, udp_sock, data):
            global all_acks
            received = data
            if "SYN" in received and self.state!= "SYN":
                received = received.split("\n")
                self.stablish_connection(received)
            elif "FIN" in received:
                print("implement FIN connection")
            if "DAT" in received:
                #print("IN DAT....")
                instructions = received.split(":")
                if len(instructions) >= PACK_HEADER_MIN:
                    # Extract command, sequence, and payload length
                    command = instructions[0].strip()
                    seq_str = instructions[1]  #instructions[1].strip().split(":")[1]
                    sequence = int(seq_str)
                    payload_length_str = instructions[2]  #instructions[2].strip().split(":")[1]
                    payload_length = int(payload_length_str)
                    payload = instructions[3]
                    print("Command:", command, "Sequence:", sequence)
                    if self.window_available - payload_length >= 0: #sliding window is available
                        self.log_received_data(command, sequence, payload_length)
                        if self.first: # If the first packet is received, send the first ACK
                            rdp_sender.send_next = 1
                            ack_sequence = 1
                            sequence= 1
                            self.prev_seq=1
                            self.expected_seq = 1
                            self.first= False
                        else:
                            self.expected_seq = self.prev_seq + payload_length
                            ack_sequence = self.prev_seq + payload_length
                            
                            # Print DAT header
                        print("DAT Header - Sequence:", ack_sequence)

                        #if ack_sequence == self.expected_seq:
                        print("Received in-order packet.")
                        write_to_file(payload)
                        self.window_available -= payload_length
                        ack_packet = f"ACK:{ack_sequence}:{self.window_available}:{command}:{sequence}:{payload_length}"
                        all_acks.append(ack_packet)
                        self.prev_seq = ack_sequence
                        print("END......")
                                
                        #else:
                            #print("Out-of-order packet. Waiting for packet with sequence:", self.expected_seq)
                            #print("terminating program")
                            #exit(1)
            
            # exit(1)

# Write payload to file
def write_to_file(payload):
    with open(outfile, "a") as file:
        file.write(payload)
        #print('Payload:', payload)

        

def generate_data_packs(filename):
    global data_packs
    with open(filename, "r") as file:
        data = file.read()
        data = data.strip()
        for i in range(0, len(data), DAT_PACK_SIZE):
            pack = data[i:i + DAT_PACK_SIZE]
            data_packs.append(pack)
    

def get_number(string):
    result= ""
    for char in string:
        if char.isdigit():    
            result+= char

    int_result= int(result)
    return int_result

#PACKET type 1 is for DAT
def packetize(data):
    packet_regex = r";"
    command_found = re.split(packet_regex, data)
    correct_format = command_found and len(command_found) > 0 and command_found[0].strip() in ["SYN", "DAT", "FIN"]
    if correct_format:
        if "DAT" not in command_found:
            instructions = data.split("\n")
            if len(instructions) >= PACK_HEADER_MIN:
                command, sequence, l = instructions[0], instructions[1], instructions[2]
                seq_no = get_number(sequence)
                length = get_number(l)
                p = packet(command, seq_no, length, 0)
                return p

        if "DAT" in command_found:
            instructions = data.split(";")
            if len(instructions) >= PACK_HEADER_MIN:
                command, sequence, l, payload = instructions[0], instructions[1], instructions[2], instructions[3]
                seq_no = get_number(sequence)
                length = get_number(l)
                p = packet(command, seq_no, length, payload)
                return p


def driver(udp_sock):
    global to_send
    global SLIDING_WINDOW
    sender = rdp_sender(udp_sock)
    receiver = rdp_receiver(udp_sock)
    timeout = 10
    syn_sent = False

    while sender.get_state() != "closed" or receiver.get_state() != "closed":
        readable, writable, exceptional = select.select([udp_sock], [udp_sock], [udp_sock], timeout)
        for sock in readable:
            if sock is udp_sock:
                data, conn = udp_sock.recvfrom(6000)
                data = data.decode()
                if "ACK" in data:
                    sender.process_ack(data)
                elif "SYN" in data or "DAT" in data or "FIN" in data:
                    print("Received data:", data)
                    receiver.rcv_data(udp_sock, data)

        if udp_sock in writable:
            if not syn_sent:
                syn_message = "SYN\nSequence:0\nLength:0\n\n"
                udp_sock.sendto(syn_message.encode(), echo_server)
                sender.open()
                syn_sent = True
            else:   
                sender.prepare_data_packs()          
                index_to_send = 0

                while index_to_send < len(to_send):
                    pack= to_send[index_to_send] 
                    pack= pack.split(":")
                    length= int(pack[2])
                    if SLIDING_WINDOW - length >= 0:
                        SLIDING_WINDOW -= length
                        udp_sock.sendto(to_send[index_to_send].encode(), echo_server)
                        sender.log_sent_data("DAT", int(pack[1]), int(pack[2])) 
                        index_to_send += 1# Increment index only if the packet is successfully sent
            
                    else: 
                        break;  # Break out of the loop if the window is full
                        #print("Window full, waiting for acks")
                
                for a in all_acks:
                    udp_sock.sendto(a.encode(), echo_server)
                    ack_seq= int(a.split(":")[1])
                    ack_window= int(a.split(":")[2])
                    receiver.log_send_ack(ack_seq, ack_window)

                
                
                #sender.close()
                #print("Sent FIN packet.......")
    

        # Check timeout and other tasks
        sender.check_timeout()




if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python script.py <ip_address> <port>")
        exit(1)
    else:
        ip_address, port_no = sys.argv[1], int(sys.argv[2])
        filename = sys.argv[3]
        outfile = sys.argv[4]
        generate_data_packs(filename)
        socket = udp_socket(ip_address, port_no)
        driver(socket.sock)
