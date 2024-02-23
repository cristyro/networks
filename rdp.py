import socket
import select
import sys
import queue
import time
import pickle
import re
import os
from datetime import datetime
import time

WINDOW_SIZE = 3  # Adjust window size as needed
SLIDING_WINDOW = 2048
DAT_PACK_SIZE = 1024
PACK_HEADER_MIN= 3

snd_buff = []
rcv_buff = []
data_packs = []
filename = None
outfile = None
echo_server = ("localhost", 8888)  # for local testing

class udp_socket:
    def __init__(self, ip, port):
        global snd_buff, rcv_buff
        self.ip = ip
        self.port = int(float(port))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((ip, self.port))
        self.sock.setblocking(0)
        self.inputs = [self.sock]
        self.outputs = []
        self.timeout = 10

    def recv(self):
        data, addr = self.sock.recvfrom(1024)
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
        string = f"{self.sequence};{WINDOW_SIZE-self.length}"
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

    
    def send_data(self, udp_sock):
        self.state = "DAT"
        for i in range(len(data_packs)):
            seq_number = i
            length = len(data_packs[i])
            data=  f"DAT;Sequence:{seq_number};Length:{len(data_packs[i])};{data_packs[i]}"
            self.send_packet(data)
            self.log("DAT", seq_number, length)
            self.receive_ack()
            

    def close(self):
        self.state = "FIN"
        # Implement sending FIN packet
        # Start timeout timer

    def send_packet(self, data):
        p= packetize(data)
        string = str(p)
        self.udp_sock.sendto(string.encode(), echo_server)

    def log(self, command, sequence, length):
        timestamp = datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')
        log_message = f"{timestamp}: Receive; {command}; Sequence: {sequence}; Length: {length}"
        print(log_message)


    def receive_ack(self):
        ack_received = False
        while not ack_received:
            readable, _, _ = select.select([self.udp_sock], [], [], self.timeout)
            for sock in readable:
                if sock == self.udp_sock:
                    data, addr = self.udp_sock.recvfrom(1024)
                    self.process_ack(data)
                    ack_received = True

    def process_ack(self, data):
        ack = data.decode().split(";")
        if "ACK" in ack:
            ack_number = int(ack[1].split(":")[1])
            window_size = int(ack[2].split(":")[1])
            self.log("ACK", ack_number, window_size)


    def check_timeout(self):
        if self.state != "closed":
            # Check if timeout occurred
            pass




class rdp_receiver:
    def __init__(self, udp_sock):
        global rcv_buff
        self.state = ""
        self.expected_seq = 0
        self.prev_seq=0
        self.udp_sock = udp_sock
        self.window_available= SLIDING_WINDOW #2048
        self.first= True

    def rcv_data(self, udp_sock, data):
        global rcv_buff
        self.state= ""
    
    def set_seq(self, seq):
        self.seq= seq
        print("SEQUENCE NUMBER", self.seq)

    def stablish_connection(self, received):
        print(".......")
        print(f"{datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')}: Receive; SYN; Sequence: 0; Length: 0")
        self.expected_seq = 0
        ack_sequence = 0
        ack_packet = f"{ack_sequence}:{self.window_available}"
        print(f"{datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')}: Send; ACK; Acknowledgment: {ack_sequence}; Window: {self.window_available}")
        self.udp_sock.sendto(ack_packet.encode(), echo_server)


    #PRODUCES ACKS FOR RECEIVED PACKETS
    #TODO : ADD send ack log message
    def rcv_data(self, udp_sock, data):
            global rcv_buff
            # Decode received data
            received = data.decode()
            if "SYN" in received:
                received = received.split("\n")
                self.stablish_connection(received)
                #print("Remove exit to continue")
                #exit(1)
            elif "FIN" in received:
                print("implement FIN connection")
                #finish
            if "DAT" in received:
                print(received)
                instructions = received.split(";")
                if len(instructions) >= PACK_HEADER_MIN:
                    # Extract command, sequence, and payload length
                    command = instructions[0].strip()
                    seq_str = instructions[1]  #instructions[1].strip().split(":")[1]
                    sequence = int(seq_str)
                    payload_length_str = instructions[2]  #instructions[2].strip().split(":")[1]
                    payload_length = int(payload_length_str)
                
                    payload = instructions[3]
                    if self.window_available - payload_length >= 0: #sliding window is available
                        print(f"{datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')}: Receive; DAT; Sequence: {sequence}; Length: {payload_length}")

                        if self.first: # If the first packet is received, send the first ACK
                            rdp_sender.send_next = 1
                            ack_sequence = 1
                            sequence= 1
                            self.prev_seq=1
                            self.expected_seq = 1
                            print("IN FIRST ACK")
                            print("Expected sequence number:", self.expected_seq, "Current sequence number:", sequence)
                            print("Sending ACK: in FIRST SEND")
                            self.first= False
                        else:
                            print("AFTER first packet")
                            self.expected_seq = self.prev_seq + payload_length
                            ack_sequence = self.prev_seq + payload_length
                            
                            # Print DAT header
                        print("DAT Header - Sequence:", ack_sequence)

                        if ack_sequence == self.expected_seq:
                            print("Received in-order packet. ")
                            write_to_file(payload)
                            ack_packet = f"{ack_sequence}:{self.window_available}"
                            print("Sending ACK:", ack_packet)
                            udp_sock.sendto(ack_packet.encode(), echo_server)
                            self.window_available += payload_length #Restore after sending ack
                            self.prev_seq = ack_sequence
                            print("END......")
                                
                        else:
                            print("Out-of-order packet. Waiting for packet with sequence:", self.expected_seq)
            
            # exit(1)

# Write payload to file
def write_to_file(payload):
    with open(outfile, "a") as file:
        file.write(payload)
        #print('Payload:', payload)
        print("Writing to file.....")

        

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
    global snd_buff, rcv_buff
    sender = rdp_sender(udp_sock)
    receiver = rdp_receiver(udp_sock)
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
                syn_message = "SYN\nSequence:0\nLength:0\n\n"
                udp_sock.sendto(syn_message.encode(), echo_server)
                sender.open()
                receiver.set_seq(1)
                print("Sent SYN packet")
                syn_sent = True

            elif not data_sent:
                print("HERE")
                sender.send_data(udp_sock)
                data_sent = True
                print("Sent data packets.......")

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
