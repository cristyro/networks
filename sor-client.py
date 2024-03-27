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
rdp= None
get_requests= [] #list of get requests
all_req=[]
window_size = 0 #change to given by client
files_to_write =[]
payload_acc= "" #only modify when we need to accumulate payload 


def udp_sock_start(ip, port):
    global sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    #print("STATE IS NOW:", rdp.get_state())


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

    if len(file_pairs)>1:
        for read_file, write_file in file_pairs:
            files_to_write.append(write_file)
            request= "GET /"+read_file+" HTTP/1.0\r\nConnection:Keep-alive\r\n\r\n"
            get_requests.append(request)
            all_req.append(request)

    else:
        files_to_write.append(file_pairs[0][1])
        request= "GET /"+file_pairs[0][0]+" HTTP/1.0\r\n\r\n"
        get_requests.append(request)
        all_req.append(request)

    print("ALL REQUESTS", all_req)

#---- Packet class to packetize stuff ------
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
        self.payload_received="" 

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

    #checks if the seq no is the one we expect!
    def in_accordance(self, command) -> bool:
        seq, ack, client_paylen = self.gather_info(command)
        print("SEQ, ACK, LEN", seq, ack, client_paylen) 
        # Update expected sequence number
        if self.expected_seq <= int(seq):
            self.expected_seq = int(seq) + int(client_paylen)
            print("Expected sequence number updated to:", self.expected_seq)
            # Update current sequence number 
            self.current_seq = int(seq)
               
            print("Packet received in accordance with protocol.")
            return True
        else:
            print("Packet not in accordance with protocol. Expected sequence:", self.expected_seq)
            return False

    def pack_and_send(self, msg):
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
            print("SENT special case", self.sent_data)
            print('\n\n\n\n', "...........................")
        else:
            print("manage numbers ")
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
            self.pack_and_send(dat)

        
    #sample command to parse b"SYN|DAT|ACK"
    #based on this parse commands go to the state machine
    #append to commands
    def parse_command(self, command): #upon receiving a command from the server, remember it is going to be a binary string 
        pattern= rb'([A-Z]{3})(?:\|([A-Z]{3}))(?:\|([A-Z]{3}))(?:\|([A-Z]{3}))?'
        matches= re.findall(pattern, command)
        flattened= [command.decode() for command_tuple in matches for command in command_tuple ]
        return flattened
         
    #Gathers and parses Sequence numbers,ack numbers and payload length 
    def gather_info(self, data):
        pattern = rb"Seq:\s*(-?\d+).*?Ack:\s*(-?\d+).*?Length:\s*(\d+)"
        matches = re.findall(pattern, data)
        flattened= [command.decode() for command_tuple in matches for command in command_tuple]
        return flattened 
    

    def manage_acks(self, found_ack, paylen):
        expected_ack = self.current_ack+ self.sent_data
        self.current_seq= found_ack
        if expected_ack==int(found_ack):
            if self.get_state()=="syn-rcv":
                self.set_state("connect")
            self.current_ack= int(paylen)+1 #update our current if we get ack we want 


    
    def gather_payload(self, data):
        global payload_acc
        global snd_buff
        global all_req
        payload_from_file= ""
        pattern= r"Content Length: (\d+)\r?\n\r?\n([\s\S]*)"
        matches= re.search(pattern, data)
        if matches:
            # Extract content length and payload from the matched pattern
            content_len_str, payload = matches.groups()
            content_len = int(content_len_str)
            print("Content length:", content_len, "Payload", len(payload ),  )

            # Check if the payload length matches the expected content length
            if len(payload)== int(content_len):  
                payload_from_file= payload

                # Determine if there are more requests pending
                more_requests = len(self.all_requests) > 1

                # Create a packet to acknowledge the request, possibly including a FIN flag if there are no more request to service
                packet_command = "ACK" if more_requests else "ACK|FIN"
                new_packet= packet(packet_command, self.current_seq, self.current_ack, "")
                
            else:
            # If payload length doesn't match, accumulate payload and acknowledge the request
                new_packet= packet("ACK", self.current_seq, self.current_ack, "")
                snd_buff.append(new_packet)
                payload_acc+= payload
                payload_from_file=1
            return payload_from_file

    #be careful with calling this function ad it will remove the 
    #filename from the global list
    def write_to_file(self, payload):
        global files_to_write
        global all_req
        file_name= files_to_write.pop(0)# request in order
        all_req.pop(0)
        with open(file_name, "w") as file:
            file.write(payload)
            print("wrote to.... " , file_name)


    #TODO: in DAT manage wtf to do when payload is finally complete with the DAT commands sent
    def process_data(self, data):
        commands_found= self.parse_command(data)        
        nums_found = self.gather_info(data)
        print("FOUND", nums_found)
        found_seq= nums_found[0]
        found_ack = nums_found[1]
        found_paylen= nums_found[2]
        for command in commands_found:
            if command== "SYN":
                self.set_state("syn-rcv")
            elif command == "ACK":
                self.manage_acks(found_ack, found_paylen)
            elif command=="DAT":
                payload= self.gather_payload(data.decode())
                if not isinstance(payload, int):
                    self.write_to_file(payload)
            elif command=="FIN":
                self.set_state("fin-rcv")   
                
            
def main_loop():
    global snd_buff, rcv_buff, rdp
    rdp_obj.open()

    #print("Sender state: ", rdp.get_state())
    while rdp_obj.get_state!= "closed":
        #print("In main loop")
        readable, writable, exceptional = select.select([sock], [sock], [])
        for s in readable:
            data, addr = sock.recvfrom(5000)
            print("Received ", data.decode())
            rcv_buff.append(data)
            if rdp_obj.in_accordance(data): #checks the seq no
                rdp_obj.process_data(data)
        
        while snd_buff:
            msg=  str (snd_buff.pop(0)) 
            print("SENDING.....", msg)
            sock.sendto(msg.encode(), (args.server_ip, args.server_udp_port))



if __name__== "__main__":
    parse_args()
    rdp_obj= rdp()
    write_http_request()
    udp_sock_start(args.server_ip, args.server_udp_port)
    print("Client started")
    main_loop()
