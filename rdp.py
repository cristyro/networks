import socket
import select
import sys
import queue
import time
import re
import os
from datetime import datetime
import time
#ADD 

DAT_PACK_SIZE = 1024
SLIDING_WINDOW = 1024*5
PACK_HEADER_MIN = 3
TIMEOUT= 20 #change to 30

all_acks= []
to_send= []
all_packets={}
data_packs = []
#for retransmission
sent_packs= {}
ack_count={}
#for sliding window
win={}

syn_sent = False
last_sequence_number = 0
data_index=0
expected_seq= 0
previous_seq= 0
filename = None
outfile = None
terminate_connection = False
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

    def process_ack(self, data):
        global ack_count, sent_packs
        info  = data.split("<<<<")
        syn_received= [p for p in info if "SYN" in p]
        dat_received= [p for p in info if "DAT" in p] 
        fin_received= [p for p in info if "FIN" in p]
        
        if syn_received and self.state!= "SYN":
            self.state = "SYN"
            self.log_ack(0, SLIDING_WINDOW)
        if dat_received:
            self.state = "DAT"
            seq_no= info[1]
            sent_packs[seq_no]= time.time() #update time upon receiving ACK
            if int(seq_no) in ack_count and ack_count[int(seq_no)] >= 3:
                print("Reach here... needs to be checked ")
                packet_retransmit= all_packets[int(seq_no)]
                if packet_retransmit:
                    to_send.insert(0, packet_retransmit) #re-transmit by sending it in front 
                    return;     
    
            #otherwise we are good to send
            self.update_window(int(info[2]))
            self.log_ack(info[1], SLIDING_WINDOW)

        if fin_received:
            self.state = "FIN"
            self.log_ack(int(info[1]), SLIDING_WINDOW)

  
    def close(self):
        global to_send
        self.state = "FIN" 
        fin_message = f"FIN<<<<Sequence:{last_sequence_number}<<<<Length:0"
        self.log_sent_data("FIN", last_sequence_number, 0)
        to_send.insert(0, fin_message) #send it in front to see it and terminate 

    
    def check_timeout(self):
        global sent_packs, to_send
        for seq_no in sent_packs:
            pack_time= sent_packs[seq_no]
            #print("CUR TIME", time.time(), "LAST ACTIVITY TIME", pack_time, "OLD ENOUGH?", time.time() - pack_time > TIMEOUT)
            if time.time() - pack_time > TIMEOUT: #if elapsed time > 30-> retransmit that 
                print("Retransmiting.... timeout happenened .....")
                packet_retransmit= all_packets[seq_no]
                if packet_retransmit:
                    to_send.insert(0, packet_retransmit)


    def log_ack(self, ack_number, window_sz):
        timestamp = datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')
        log_message = f"{timestamp}: Receive; ACK; Acknowledgment: {ack_number}; Window: {window_sz}"
        #print(log_message)

    def log_sent_data(self, command, sequence, length):
        timestamp = datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')
        log_message = f"{timestamp}: Send; {command}; Sequence: {sequence}; Length: {length}"
        #print(log_message)

    def update_window(self, length_freed):
        global SLIDING_WINDOW
        while SLIDING_WINDOW <= (1024*5):
            SLIDING_WINDOW += length_freed

 

class rdp_receiver:
    def __init__(self, udp_sock ):
        self.state = ""
        self.udp_sock = udp_sock
        self.first= True
 
    def rcv_data(self, udp_sock, data):
        self.state= ""
    
    def get_state(self):
        return self.state

    def stablish_connection(self, received):
        print(f"{datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')}: Receive; SYN; Sequence: 0; Length: 0")
        self.expected_seq = 0
        ack_sequence = 0
        ack_packet = f"ACK:{ack_sequence}:{SLIDING_WINDOW}:SYN:0:0"
        print(f"{datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')}: Send; ACK; Acknowledgment: {ack_sequence}; Window: {SLIDING_WINDOW}")
        self.udp_sock.sendto(ack_packet.encode(), echo_server)

    def terminate_connection(self):
        self.state = "FIN"
        self.log_received_data("FIN", last_sequence_number, 0)
        self.log_send_ack(last_sequence_number, SLIDING_WINDOW)

    def log_received_data(self, command, sequence, length):
        timestamp = datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')
        log_message = f"{timestamp}: Receive; {command}; Sequence: {sequence}; Length: {length}"
        #print(log_message)

    def log_send_ack(self, ack_sequence, window_size):
        timestamp = datetime.now().strftime('%a %b %d %H:%M:%S %Z %Y')
        log_message = f"{timestamp}: Send; ACK; Acknowledgment: {ack_sequence}; Window: {window_size}"
        #print(log_message)

    #PRODUCES ACKS FOR RECEIVED PACKETS
    def rcv_data(self, udp_sock, data):
            global all_acks, ack_count
            global expected_seq, previous_seq
            global SLIDING_WINDOW
            global terminate_connection
            ack_no = 0
            pattern = r"(?=(SYN|DAT|FIN))"
            packets = re.split(pattern, data)
            packets = [packet for packet in packets if packet.strip()] #remove empty strings
            for received in packets:


                if "SYN" in received and self.state!= "SYN":
                    self.stablish_connection(received)
                elif "FIN" in received:
                    print("RECEIVE FIN PACKET")
                    self.terminate_connection(received)
                if "DAT" in received:
                    instructions = received.split("<<<<")
                    if len(instructions) >= PACK_HEADER_MIN:
                        command = instructions[0].strip()
                        seq_str = instructions[1]  #instructions[1].strip().split(":")[1]
                        sequence = int(seq_str)
                        payload_length_str = instructions[2]  #instructions[2].strip().split(":")[1]
                        payload_length = int(payload_length_str)
                        payload = instructions[3]
                        #print("INSTRUCTIONS", instructions)
                        #print("\n\n")
                        if SLIDING_WINDOW - payload_length >= 0: #sliding window is available
                            self.log_received_data(command, sequence, payload_length)
                            if self.first: # If the first packet is received, send the first ACK
                                previous_seq= 1
                                expected_seq= 1
                                self.first= False
                            else:
                                expected_seq = previous_seq + payload_length
                            print("EXPECTED", expected_seq, "RECEIVED", sequence)
                            if expected_seq == sequence:
                                write_to_file(payload)
                                #send next packet wanted?
                                ack_packet = f"ACK<<<<{sequence}<<<<{SLIDING_WINDOW}<<<<{command}<<<<{sequence}<<<<{payload_length}"
                                all_acks.append(ack_packet)
                                previous_seq = sequence # Update previous sequence
                                #update ack_count for received seq_no
                                ack_count[sequence]+=1
                                print("ACK COUNT", ack_count)
                            else:
                                print("Packet out of order", "Expected sequence:", expected_seq, "Received sequence:", sequence)
                                ack_count[sequence]+=1 #look for retransmission
                                SLIDING_WINDOW-= payload_length
                                ack_packet = f"ACK<<<<{sequence}<<<<{SLIDING_WINDOW}<<<<{command}<<<<{sequence}<<<<{payload_length}"
                                all_acks.append(ack_packet)

                            if sequence == last_sequence_number:
                                print("Last packet received")
                                terminate_connection = True


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

def prepare_data_packs():
        global to_send
        global ack_count, all_packets
        global last_sequence_number
        seq_number = 0

        for i in range (0, len(data_packs)):
            if i == 0:
                seq_number = 1
            elif i==1:
                seq_number = len(data_packs[i])+1 #from previous sequence number
            else:   
                seq_number += len(data_packs[i])

            data = f"DAT<<<<{seq_number}<<<<{len(data_packs[i])}<<<<{data_packs[i]}"
            to_send.append(data)
            all_packets[seq_number]= data

            if last_sequence_number < seq_number:
                last_sequence_number = seq_number

            ack_count[seq_number]= 0 # initialize to 0
    

def get_number(string):
    result= ""
    for char in string:
        if char.isdigit():    
            result+= char

    int_result= int(result)
    return int_result


def driver(udp_sock):
    global to_send, data_index, ack_count, sent_packs, all_acks
    global SLIDING_WINDOW
    sender = rdp_sender(udp_sock)
    receiver = rdp_receiver(udp_sock)
    timeout = 10
    syn_sent = False
    packs_sent = []

    while sender.get_state() != "FIN" or receiver.get_state() != "FIN":
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
                sender.open()
                syn_sent = True
            else:   
                for p in to_send:
                    pack= p.split("<<<<")
                    #print("PACK", pack)
                    length= int(pack[2])   
                    if SLIDING_WINDOW - length >= 0: #only if packet is being succesfuly sent
                        udp_sock.sendto(p.encode(), echo_server)
                        seq_no= pack[1]
                        sent_packs[seq_no]= time.time()
                    else: 
                        print("Window full, waiting for acks")
                        break;
                
                for a in all_acks:
                    udp_sock.sendto(a.encode(), echo_server)
                    ack_seq= int(a.split("<<<<")[1])
                    ack_window= int(a.split("<<<<")[2])
                    receiver.log_send_ack(ack_seq, ack_window)

                if terminate_connection:
                    print("Terminating connection...")
                    sender.close()
                    receiver.terminate_connection()

                    
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
        prepare_data_packs()
        socket = udp_socket(ip_address, port_no)
        driver(socket.sock)
