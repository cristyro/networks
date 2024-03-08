import socket
import select
import sys
import queue
import time
import re
import os
from datetime import datetime
#ADD

DAT_PACK_SIZE = 1024
SLIDING_WINDOW = 1024*4
PACK_HEADER_MIN = 3
TIMEOUT= 0.4 #change to 30

#to keep track
all_acks= []
to_send= []
previous_acks=[]
all_packets={}
data_packs = []
written=[]
all_seqno=[]
acks_sent=[]
#for retransmission
sent_packs= {}
ack_count={}
packets_sent=[]
#for sliding window
win={}

expected=1
first_received= False
#global variables
syn_sent = False #controls whether or not syn has been sent
#both are to keep track of the last package which may differ in length to (be shorter)
last_packet_len=0
last_sequence_number = 0
old_ack= 1  #keeps track of last ack sent
expected_seq= 0
previous_seq= 0
filename = None
outfile = None
terminate_connection = False
echo_server = ("h2", 8888)

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


    def open(self) -> str:
        global to_send
        self.state = "SYN"
        syn_message = "SYN<<<<0<<<<0"
        self.udp_sock.sendto(syn_message.encode(), echo_server)
        self.log_sent_data("SYN", 0, 0)
        to_send.append(syn_message)


    def process_ack(self, data):
        global ack_count, sent_packs
        global expected  
        info = data.split("<<<<")
        #print("info", info)
       
        if "SYN" in info and self.state!= "SYN":
            self.state = "SYN"
            self.log_ack(0, SLIDING_WINDOW)
        if "ACK" in info:
            self.state = "DAT"
            seq_no= info[1]
            sent_packs[seq_no]= time.time() #update time upon receiving ACK
            self.log_ack(info[1], SLIDING_WINDOW)          
            if int(seq_no)== last_sequence_number+1:
                self.close()
           
            if int(seq_no) in ack_count and ack_count[int(seq_no)] >= 3:
                packet_retransmit= all_packets[int(seq_no)]
                if packet_retransmit:
                    #alternatively add to the to_send at the front of the queue
                    udp_sock.sendto(packet_retransmit.encode(), echo_server)
                    self.log_ack(info[1], SLIDING_WINDOW)
   
            #otherwise we are good to send
            if not "SYN" in data:
                self.log_ack(info[1], SLIDING_WINDOW)

        if "FIN" in info:
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
            if time.time() - pack_time > TIMEOUT: #if elapsed time > 30-> retransmit that
                #print("Retransmiting.... timeout happenened .....")
                packet_retransmit= all_packets[int(seq_no)]
                if packet_retransmit:
                    to_send.insert(0, packet_retransmit)


    def log_ack(self, ack_number, window_sz):
        timestamp = time.strftime('%a %b %d %X %Z %Y')
        log_message = f"{timestamp}: Receive; ACK; Acknowledgment: {ack_number}; Window: {window_sz}"
        print(log_message)

    def log_sent_data(self, command, sequence, length):
        timestamp = time.strftime('%a %b %d %X %Z %Y')
        log_message = f"{timestamp}: Send; {command}; Sequence: {sequence}; Length: {length}"
        print(log_message)


class rdp_receiver:
    def __init__(self, udp_sock ):
        self.state = ""
        self.udp_sock = udp_sock
 
    def rcv_data(self, udp_sock, data):
        self.state= ""
   
    def get_state(self):
        return self.state

    def stablish_connection(self, received):
        print(f"{time.strftime('%a %b %d %X %Z %Y')}: Receive; SYN; Sequence: 0; Length: 0")
        ack_sequence = 1 #want next one
        ack_packet = f"ACK<<<<{ack_sequence}<<<<{SLIDING_WINDOW}"
        self.udp_sock.sendto(ack_packet.encode(), echo_server)
        all_acks.append(ack_packet)

    def terminate_connection(self):
        self.state = "FIN"
        self.log_received_data("FIN", last_sequence_number, 0)
        self.log_send_ack(last_sequence_number, SLIDING_WINDOW)

    def log_received_data(self, command, sequence, length):
        timestamp = time.strftime('%a %b %d %X %Z %Y')
        log_message = f"{timestamp}: Receive; {command}; Sequence: {sequence}; Length: {length}"
        print(log_message)
       
    def log_send_ack(self, ack_sequence, window_size):
        timestamp = time.strftime('%a %b %d %X %Z %Y')
        log_message = f"{timestamp}: Send; ACK; Acknowledgment: {ack_sequence}; Window: {window_size}"
        print(log_message)


    def next_number(self, sequence):
        increase_valid= (sequence+ DAT_PACK_SIZE) <= last_sequence_number or sequence+last_packet_len == last_sequence_number
        number_exists= int(sequence+ DAT_PACK_SIZE) in all_seqno or  int(sequence+last_packet_len) in all_seqno
        if (increase_valid and number_exists):
            if sequence+last_packet_len == last_sequence_number:
                next_packet= last_sequence_number+1
            else:
                next_packet= sequence+ DAT_PACK_SIZE
           
            return next_packet
   
    #return True and terminate connection
    def is_last_packet(self, sequence)->bool:
        global terminate_connection
        if sequence == last_sequence_number:
            terminate_connection = True
           

    #SENDS acknowledgment numbers for the next wanted package
    def rcv_data(self, udp_sock, data):
            global all_acks
            global ack_count
            global to_send
            global old_ack
            global win
            global written
            global first_received
            global expected_seq, previous_seq
            global SLIDING_WINDOW
            global terminate_connection
            ack_no = 0
            pattern = r"(?=(SYN|DAT|FIN|ACK))" #for fifo
            packets = re.split(pattern, data)
            packets = [packet for packet in packets if packet.strip()] #remove empty strings

            for received in packets:
                if "SYN" in received:
                    self.state="SYN"
                    self.stablish_connection(received)
                    break;
                elif "FIN" in received:
                    self.terminate_connection(received)
                if "DAT" in received:
                    instructions = received.split("<<<<")
                    if len(instructions) >= PACK_HEADER_MIN:
                        command = instructions[0].strip()
                        seq_str = instructions[1]  
                        sequence = int(seq_str)
                        payload_length_str = instructions[2]
                        payload_length = get_number(payload_length_str)
                        payload = instructions[3]

                        if SLIDING_WINDOW - payload_length >= 0: #sliding window is available
                            self.log_received_data(command, sequence, payload_length)
                           
                            if sequence ==1 and not first_received:
                                previous_seq=1
                                expected_seq=1
                                first_received= True

                            else:
                                 if (expected_seq+ payload_length) <= last_sequence_number and int(expected_seq+ payload_length) in all_seqno:
                                    expected_seq = previous_seq + payload_length
                                   
                                 if not first_received:
                                    expected_seq=1
                                   
                            #print("EXPECTED", expected_seq, "RECEIVED", sequence)
                            if expected_seq == sequence:
                                    if sequence not in written:
                                        write_to_file(payload) #check were i write to file
                                        written.append(sequence)
                                    if received in to_send:
                                        to_send.remove(received) #remove the one received from to send
                                    next_wanted= self.next_number(sequence)
                                    if sequence==last_sequence_number:
                                        next_wanted= last_sequence_number+1
                                                               
                                    #check_window_gaps function
                                    #renoved from win keeps track of all the seqno to del from win to keep it clean
                                    #yeet all of this into a helper
                                    remove_from_win=[]
                                    if len(win)>0:
                                        for seqno in win:
                                            if next_wanted == seqno:
                                                payload= win[seqno]
                                                if seqno not in written:
                                                    write_to_file(payload)
                                                    written.append(seqno)
                                                remove_from_win.append(seqno)
                                                next_wanted= self.next_number(next_wanted)
                                               
                               
                                    for item in remove_from_win:
                                        SLIDING_WINDOW+= len(win[item])
                                        del win[item]
                                                               
                                   
                                    ack_packet = f"ACK<<<<{next_wanted}<<<<{SLIDING_WINDOW}"
                                    all_acks.append(ack_packet)
                                    acks_sent.append(ack_packet)
                                    previous_seq = sequence # Update previous sequence
                                    old_ack= next_wanted #last sucesfully acked in order
                                    self.is_last_packet(sequence) #check for now to avoid overflow

                        elif int(sequence) > int (expected_sequence):
                                        if old_ack in ack_count:
                                            ack_count[old_ack]+=1
                                       
                                        #now if we have space add to window
                                        if SLIDING_WINDOW - payload_length >=0:
                                            SLIDING_WINDOW= SLIDING_WINDOW- payload_length
                                            win[sequence]= payload
                                           
                                           
                                        #every time i add an entry, sort the dict by order
                                        k = list (win.keys() )
                                        k.sort()
                                        sorted_win = {i: win[i] for i in k}
                                        win.clear()
                                        win = sorted_win
                                   
 
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
        global last_sequence_number, last_packet_len
        global all_seqno
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
            all_seqno.append(seq_number)

            if last_sequence_number < seq_number:
                last_sequence_number = seq_number
                last_packet_len= len(data_packs[i])
               

            ack_count[seq_number]= 0 # initialize to 0
   

def get_number(string):
    result= ""
    for char in string:
        if char.isdigit():    
            result+= char

    int_result= int(result)
    return int_result


def resend(udp_sock, seqno, window):
    #resend seqno and all other packages after the one i dropped\
    #resend all packets after and including seqno
    keys_resend= []
    for key in all_packets.keys():
        if int(key) >= int(seqno):
            keys_resend.append(key)
   
    #now keys_resend has all keys i want to resend
    for resend in keys_resend:
        if resend in all_packets:
            resending_data= all_packets[resend]
            to_send.insert(0, resending_data)
            udp_sock.sendto(resending_data.encode(), echo_server)
   

def driver(udp_sock):
    global to_send,  ack_count, sent_packs
    global all_acks
    global SLIDING_WINDOW
    sender = rdp_sender(udp_sock)
    receiver = rdp_receiver(udp_sock)
    timeout = 10
    lastest_ack=""
    global syn_sent
    packs_sent = []

    while sender.get_state() != "FIN" or receiver.get_state() != "FIN":
        readable, writable, exceptional = select.select([udp_sock], [udp_sock], [udp_sock], timeout)
        for sock in readable:
            if udp_sock in readable:
                data, conn = udp_sock.recvfrom(8000000)
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
                    length= get_number(pack[2])  
                    if SLIDING_WINDOW - length >= 0: #only if packet is being succesfuly sent
                        udp_sock.sendto(p.encode(), echo_server)
                        seq_no= pack[1]
                        sent_packs[seq_no]= time.time()
                       
                       
                last_ack = None
                last_seq=0
                for a in all_acks:
                    if not a.isspace():
                        a_list = a.split("<<<<")
                        ack_seq = int(a_list[1])
                        ack_window = int(a_list[2])
                        last_seq= ack_seq
                        udp_sock.sendto(a.encode(), echo_server)
                        receiver.log_send_ack(ack_seq, ack_window)
                        sender.process_ack(a)
                       

                # Check for repeated acknowledgments
                if last_ack and not terminate_connection:
                    repeated = [i for i in acks_sent if i == last_ack]
                    if len(repeated) >= 3:
                        resend(udp_sock, ack_seq, ack_window)


                if terminate_connection is True:
                    sender.close()
                    receiver.terminate_connection()
                else:
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
