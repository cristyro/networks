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
files_and_len= {}
sock= None #socket object
args= None #command line arguments 
rdp= None
get_requests= [] #list of get requests
all_req=[]
window_size = 0 #change to given by client
files_to_write =[]
payload_acc= "" #only modify when we need to accumulate payload 
usual_length = 0


def udp_sock_start(ip, port):
    global sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


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
    
# ------- Write HTTP request to the server -------
#format of the request: GET/filename HTTP/1.0\r\nConnection:Keep-alive\r\n\r\n
#Populates the global list files_to_write which contains the name of the files where we will write
#Initializes the global dict payload_received_per_file which has filename as key and an initial amount of 0 for the 
#total amount received 
def write_http_request():
    global get_requests
    global all_req
    global files_to_write
    file_pairs = [(args.file_pairs[i], args.file_pairs[i+1]) for i in range(0, len(args.file_pairs), 2)]

    #get rid of the Connection:keep-alive from the request xwxw
    if len(file_pairs)>1:
        for read_file, write_file in file_pairs:
            files_to_write.append(write_file)
            request= "GET /"+read_file+" HTTP/1.0\r\nConnection:Keep-alive\r\n\r\n"
            get_requests.append(request)
            files_and_len[read_file]= 0
            all_req.append(write_file)
            
    else:
        files_and_len[file_pairs[0][1]]= 0
        files_to_write.append(file_pairs[0][1])
        request= "GET /"+file_pairs[0][0]+" HTTP/1.0\r\n\r\n"
        get_requests.append(request)
        all_req.append(file_pairs[0][1])


class PayloadHandler:
    def __init__(self, rdp_instance):
        # Initialize with empty values and structures as needed
        self.rdp_instance= rdp_instance
        self.payload_acc = ""  # Accumulator for the payload
        self.expected_content_length = None  # Expected length of the current content
        self.current_file = ""  # The file we are currently writing to
        self.files_and_data = {}  # Store files and their corresponding lengths
        self.have_sent_first= False

    def set_file(self, newfile):
        self.current_file= newfile

    def acknowledge(self):
        global snd_buff
        new_packet= packet("ACK", self.rdp_instance.current_seq, self.rdp_instance.current_ack, "")
        snd_buff.append(new_packet)

    #writes data to specific file and resets necessary variables
    def write_to_file(self, data):
        print("writing to", self.current_file)
        with open(self.current_file, 'w') as file:
            file.write(data)

        #Re-use for other function calls 
        self.files_and_data[self.current_file]= data
        self.payload_acc=""
        self.expected_content_length= None

    def select_payload(self, string_with_command, initial_payload):
        pay_wanted=""
        if initial_payload:
            pattern =  r"^(.*?)(?=,\s*Window:)"
            match_payload = re.search(pattern, string_with_command, re.DOTALL)
        else:
            pattern = r"Payload:\*+(.*?)(?=\*, Window:)"
            match_payload = re.search(pattern, string_with_command, re.DOTALL)
        if match_payload:
            wanted= match_payload.group(1)
            payload_contents = wanted.split("***")
            for chunck in payload_contents:
                if not chunck.isspace():
                    chunck = chunck.replace("*", "")
                    pay_wanted+= str (chunck)
        
           
            return pay_wanted

    def check_and_write(self):
        print("in check and write", self.expected_content_length, len(self.payload_acc), "Are equal?", len(self.payload_acc) == int(self.expected_content_length))
        print( type(len(self.payload_acc)), type(self.expected_content_length)  )
        if len(self.payload_acc) == int(self.expected_content_length): 
            self.write_to_file(self.payload_acc) #In case we received extra data 
            self.expected_content_length= None #reset for next file 


    #Processes the given data, extracts content length if present, accumulates payload, and writes to file as necessary.
    def gather_payload(self,data):
        global all_req
        global usual_length
        # Regular expression to find content length and initial part of the payload
        pattern = r"Content Length: (\d+)\r?\n\r?\n([\s\S]*)"
        matches = re.search(pattern, data)

        if matches:
            file_in_order= all_req.pop(0)
            self.set_file(file_in_order)
            # Extract content length and initial payload from the data
            content_len_str, initial_payload = matches.groups()
            initial_payload = self.select_payload(initial_payload, True)
            if len(initial_payload)== int(content_len_str):
                self.check_and_write()
            content_len = int(content_len_str)
            self.expected_content_length = content_len  # Set the expected content length
            self.payload_acc+= initial_payload #Add initial payload to accumulator

            if not self.have_sent_first: #acknowledge first request
                self.acknowledge()
                self.have_sent_first= True #change to True once sent first ACK
        else: 
            pay_wanted= self.select_payload(data,False)         
            self.payload_acc+= pay_wanted
            usual_length= len(data)
            #Check if we have reached content length 

        self.check_and_write() #Check at the end of the iteration if we can write to file



#------------- Packet class to packetize stuff ------------
class packet:
    def __init__(self, command,seq_num, ack_num, payload):
        self.command= command
        self.seq_num= seq_num
        self.ack_num= ack_num
        self.payload= payload
        self.length= len(payload)

    
    def __str__(self) :
        return f"Command: {self.command}, Seq: {self.seq_num}, Ack: {self.ack_num}, Length: {self.length}, Payload: {self.payload}, Window: {window_size}"


#  -------- Class to handle the RDP state machine -----------
class rdp:
    def __init__(self):
        self.state= "closed"
        self.current_seq= 0
        self.current_ack=0
        self.expected_seq= 0 
        self.sent_data= 0
        self.last_received= ""
        self.window =[] #keeps track of sent but unacked packets
        self.payload_manager= PayloadHandler(self) #Pass our instance for inheritance 

    def change_current_seq(self, new_val):
        self.current_seq= new_val

    def set_state(self, new_state):
        self.state= new_state
        print(self.state)

    def get_state(self):
        return self.state
    
    def put_dat(self, dat):
        global snd_buff
        snd_buff.append(dat)

    def clean_up(self):
        global snd_buff
        global command
        snd_buff= []


    def to_reset(self, seq) -> bool:
        seq_num = int(seq)
        # Check if the sequence number is within a reasonable range of expected_seq
        # This includes both a bit ahead of expected_seq and a bit behind, to accommodate reordering or retransmission
        if self.expected_seq - window_size <= seq_num <= self.expected_seq + window_size:
            # If within range, then no need to send RST
            return False
        else:
            # If outside this range, it may indicate an error or unexpected behavior, thus RST is considered
            print("sending reset, you are fucked ")
            exit(1)
            return True

    
    def send_rst(self):
        global snd_buff
        snd_buff=[]
        rst_packet= packet("RST", self.current_seq, self.current_ack, " ")
        self.put_dat(rst_packet)
        self.set_state("rst_mode")

    def in_accordance(self, command) -> bool:
        check_expected= 0
        seq, ack, client_paylen, window = self.gather_info(command)
        if self.to_reset(seq):
            self.send_rst()
            return False
        else:
            if "SYN" in command:
                self.current_seq =0
            if self.current_seq == int(seq):
                self.expected_seq = int(seq) + int(client_paylen)
                # Update current sequence number 
                self.current_seq+=int(client_paylen)
                self.last_received= seq
                return True
            else:
                print("Packet not in accordance with protocol. Expected sequence:", self.expected_seq)
                return False
           
        
    def send_first(self, msg):
        global snd_buff
        global window_size
        commands= [msg.command for msg in snd_buff]
        length=0
        payload= ""
           
        while len(snd_buff) > 0: #check window size as well 
            msg= snd_buff.pop(0)    
            payload+= msg.payload
            length+= len(msg.payload)
            window_size-= len(msg.payload) #decrement window size when sending a packet

        commands_str = "|".join(commands)
        if "SYN" in commands_str:
            final_pack=packet(commands_str, 0, -1, payload)
            self.sent_data= len(payload)

        sock.sendto(str(final_pack).encode(), (args.server_ip, args.server_udp_port))
        snd_buff=[] #clear the buffer after sending the packets
        commands=[]
                  
    
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
            self.send_first(dat)

        
    #sample command to parse b"SYN|DAT|ACK"
    #based on this parse commands go to the state machine
    #append to commands
    def parse_command(self, command):
        continue_parsing= True
        pattern= r'\b([A-Z]+)\b'
        matches= re.findall(pattern, command) #finds all the commands in the string. 
        relevant_matches= [match for match in matches if match in ['SYN', 'DAT', 'ACK', 'FIN']]
        return relevant_matches
         
    #Gathers and parses Sequence numbers,ack numbers and payload length 
    def gather_info(self, data):
        pattern = r"Seq:\s*(-?\d+).*?Ack:\s*(-?\d+).*?Length:\s*(\d+).*?"
        matches = re.findall(pattern, data)
        window_pattern = re.compile(r"Window:\s*(\d+)")
        window_match= window_pattern.search(data)
        flattened= [command for command_tuple in matches for command in command_tuple]
        flattened.append(window_match.group(1))
        return flattened 
    
    def can_send_pack(self,pack_len):
        global window_size
        measurement= window_size - pack_len
        return measurement >= 0
    
    #Here we release. Put everything but the first SYN to start connection
    def release_packets(self):
        while self.window !=[] and self.can_send_pack(self.window[0].length):
            next_packet= self.window.pop(0) #Gets the next inmediate packet to send
            updated_packet = packet(next_packet.command, self.current_seq, self.current_ack, next_packet.payload)
            if self.window:
                peek= self.window[0]
                self.current_seq += peek.length  #peek next
                print("added to snd_buff....", updated_packet)
                snd_buff.append(updated_packet)

    def manage_acks(self, found_ack, paylen):
        #updates initial state of syn received to connect state upon receiving initial client handshake
        expected_ack = self.current_ack+ self.sent_data
        if expected_ack==int(found_ack):
            if self.get_state()=="syn-rcv":
                self.set_state("connect")
            self.current_ack= int(paylen)+1 #update our current if we get ack we want 

        else:
            self.release_packets()
            #removes all the packets from the sliding window once they have been acked
            self.window = [p for p in self.window if p.seq_num > int(found_ack)]
            print("after acks , we have", len(self.window))
            self.current_ack = max (found_ack, self.current_seq) # this is what we found has been last acknowledge on the other side 


    #update you server of my current ack 
    def sender_win(self, window_on_server):
        print("in sender win", int (window_on_server) )
        if int (window_on_server) == 0 or int  (window_on_server) <= usual_length: 
            #send an ACK 
            self.current_ack = self.last_received
            print("sending ack to slide window -------ccccccc-------\n\n")
            ack_to_sender= packet("ACK", self.current_seq, self.current_ack, "")

            snd_buff.append(ack_to_sender)
    
    def process_data(self, data):
        global snd_buff
        commands_found= self.parse_command(data)        
        nums_found = self.gather_info(data)
        found_seq= int (nums_found[0])
        found_ack =int (nums_found[1])
        found_paylen= int (nums_found[2])
        window_server_side = int (nums_found[3])
        for command in commands_found:
            #print("COMMAND?", command, "\n\n")
            if command== "SYN":
                self.set_state("syn-rcv")
                #here 
            elif command == "ACK":
                self.manage_acks(found_ack, found_paylen)
            elif command=="DAT":
                #call instance of PayloadManager
                self.payload_manager.gather_payload(data)
                self.sender_win(window_server_side)
            elif command=="FIN":
                self.set_state("fin-rcv")
                #send ACK for the Fin 
                self.current_ack=found_seq #acknowledge all packets up untill this seq no
                ack_for_fin= packet("ACK|FIN", self.current_seq, self.current_ack, "")
                print("acknowledgment for last packet has:", str (ack_for_fin) )
                snd_buff.append(ack_for_fin)
                self.set_state("fin-sent") 
                 
            
def main_loop():
    global snd_buff, rcv_buff, rdp
    rdp_obj.open()

    while True:
        #print("In main loop")
        readable, writable, exceptional = select.select([sock], [sock], [])
        for s in readable:
            data, addr = sock.recvfrom(5000)
            data = data.decode()
            #print("Received ", data , "\n\n\n....................\n")
            rcv_buff.append(data)
            if rdp_obj.in_accordance(data): #checks the seq no
                #print("into processing data.....")
                rdp_obj.process_data(data)

        while snd_buff:
            msg= str (snd_buff.pop(0)) 
           # print("SENDING.....", msg)
            sock.sendto(msg.encode(), (args.server_ip, args.server_udp_port))

        if rdp_obj.get_state()=="fin-sent" or rdp_obj.get_state == "rst_mode":
            print("closing connection....")
            sock.close()
            break;



if __name__== "__main__":
    parse_args()
    rdp_obj= rdp()
    write_http_request()
    udp_sock_start(args.server_ip, args.server_udp_port)
    print("Client started")
    main_loop()
