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
last_sequence_number = 0
data_index=0
expected_seq= 0
previous_seq= 0
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
        string = f"{self.sequence}<<<<{SLIDING_WINDOW-self.length}"
        return string
    
    def __reduce__(self):
        return (self.__class__, (self.command, self.sequence, self.length, self.payload))
        
    def __str__(self) -> str:
        return f"{self.command}<<<<{self.sequence}<<<<{self.length}<<<<{self.payload}"


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
        syn_message = "SYN<<<<Sequence:0<<<<Length:0"
        self.log_sent_data("SYN", 0, 0)
        self.udp_sock.sendto(syn_message.encode(), echo_server)
 
    def prepare_data_packs(self):
        global to_send
        global last_sequence_number
        self.state = "DAT"
        seq_number = 0
        self.total_packets= 0
        self.sent_packets= 0

        for i in range (0, len(data_packs)):
            if i == 0:
                seq_number = 1
            else:   
                seq_number += len(data_packs[i])

            data = f"DAT<<<<{seq_number}<<<<{len(data_packs[i])}<<<<{data_packs[i]}"
            to_send.append(data)
            if last_sequence_number < seq_number:
                last_sequence_number = seq_number

      
    def close(self):
        self.state = "FIN" #for now, modify 
        fin_message = f"FIN<<<<Sequence:{last_sequence_number}<<<<Length:0"
        self.udp_sock.sendto(fin_message.encode(), echo_server)
        # Implement sending FIN packet
        # Start timeout timer

    def log_ack(self, ack_number, window_sz):
        timestamp = datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')
        log_message = f"{timestamp}: Receive; ACK; Acknowledgment: {ack_number}; Window: {window_sz}"
        print(log_message)

    def log_sent_data(self, command, sequence, length):
        timestamp = datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')
        log_message = f"{timestamp}: Send; {command}; Sequence: {sequence}; Length: {length}"
        print(log_message)

    def update_window(self, length_freed):
        global SLIDING_WINDOW
        SLIDING_WINDOW += length_freed


    def process_ack(self, data):
        info  = data.split("<<<<")
        syn_received= [p for p in info if "SYN" in p]
        dat_received= [p for p in info if "DAT" in p]
        fin_received= [p for p in info if "FIN" in p]
        
        if syn_received and self.state!= "SYN":
            self.state = "SYN"
            self.log_ack(0, SLIDING_WINDOW)
        if dat_received:
            self.state = "DAT"
            self.update_window(int(info[2]))
            self.log_ack(int(info[1], SLIDING_WINDOW))

        if fin_received:
            self.state = "FIN"
            self.log_ack(int(info[1]), SLIDING_WINDOW)


    def check_timeout(self):
        if self.state != "closed":
            # Check if timeout occurred
            pass




class rdp_receiver:
    def __init__(self, udp_sock ):
        self.state = ""
        self.udp_sock = udp_sock
        self.first= True
 
    def rcv_data(self, udp_sock, data):
        self.state= ""
    
    def set_seq(self, seq):
        self.seq= seq

    def stablish_connection(self, received):
        print(f"{datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')}: Receive; SYN; Sequence: 0; Length: 0")
        self.expected_seq = 0
        ack_sequence = 0
        ack_packet = f"ACK:{ack_sequence}:{SLIDING_WINDOW}:SYN:0:0"
        print(f"{datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')}: Send; ACK; Acknowledgment: {ack_sequence}; Window: {SLIDING_WINDOW}")
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
            global expected_seq, previous_seq
            global SLIDING_WINDOW
            ack_no = 0
            received = data
            if "SYN" in received and self.state!= "SYN":
                self.stablish_connection(received)
            elif "FIN" in received:
                print("implement FIN connection")
            if "DAT" in received:
                instructions = received.split("<<<<")
                #print("Instructions:\n", instructions)
                if len(instructions) >= PACK_HEADER_MIN:
                    command = instructions[0].strip()
                    seq_str = instructions[1]  #instructions[1].strip().split(":")[1]
                    sequence = int(seq_str)
                    payload_length_str = instructions[2]  #instructions[2].strip().split(":")[1]
                    payload_length = int(payload_length_str)
                    payload = instructions[3]
                    if SLIDING_WINDOW - payload_length >= 0: #sliding window is available
                        self.log_received_data(command, sequence, payload_length)
                        if self.first: # If the first packet is received, send the first ACK
                            previous_seq= 1
                            expected_seq= 1
                            self.first= False
                        else:
                            expected_seq = previous_seq + payload_length

                        if expected_seq == sequence:
                            write_to_file(payload)
                            ack_packet = f"ACK<<<<{sequence}<<<<{SLIDING_WINDOW}<<<<{command}<<<<{sequence}<<<<{payload_length}"
                            all_acks.append(ack_packet)
                            previous_seq = sequence # Update previous sequence
                        else:
                            #print("Packet out of order", "Expected sequence:", expected_seq, "Received sequence:", sequence)
                            SLIDING_WINDOW-= payload_length
                            ack_packet = f"ACK<<<<{sequence}<<<<{SLIDING_WINDOW}<<<<{command}<<<<{sequence}<<<<{payload_length}"
                            all_acks.append(ack_packet)
                        if sequence == last_sequence_number:
                            print("Last packet received")
                            exit(1)

# Write payload to file
def write_to_file(payload):
    with open(outfile, "a") as file:
        file.write(payload)

        

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


def driver(udp_sock):
    global to_send
    global SLIDING_WINDOW
    global data_index
    sender = rdp_sender(udp_sock)
    receiver = rdp_receiver(udp_sock)
    timeout = 10
    syn_sent = False
    packs_sent = []

    while sender.get_state() != "closed" or receiver.get_state() != "closed":
        readable, writable, exceptional = select.select([udp_sock], [udp_sock], [udp_sock], timeout)
        for sock in readable:
            if sock is udp_sock:
                data, conn = udp_sock.recvfrom(6000)
                data = data.decode()
                if "ACK" in data:
                    sender.process_ack(data)
                elif "SYN" in data or "DAT" in data or "FIN" in data:
                    receiver.rcv_data(udp_sock, data)

        if udp_sock in writable:
            if not syn_sent:
                #syn_message = "SYN\nSequence:0\nLength:0\n\n"
                #udp_sock.sendto(syn_message.encode(), echo_server)
                sender.open()
                syn_sent = True
            else: 
                sender.prepare_data_packs()    
                while data_index <len(data_packs):
                    pack= to_send[data_index] 
                    pack= pack.split("<<<<")
                    length= int(pack[2])    
                    if SLIDING_WINDOW - length >= 0:
                        udp_sock.sendto(to_send[data_index].encode(), echo_server)
                        data_index += 1
                    else: 
                        print("Window full, waiting for acks")
                        break;
                
                for a in all_acks:
                    udp_sock.sendto(a.encode(), echo_server)
                    ack_seq= int(a.split("<<<<")[1])
                    ack_window= int(a.split("<<<<")[2])
                    receiver.log_send_ack(ack_seq, ack_window)
                
                
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
