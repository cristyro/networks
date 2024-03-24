import socket
import select
import sys
import queue
import time
import re
import os
from datetime import datetime
import time

# Global variables 
snd_buff = {} #queue to send messages
rcv_buff = {} #queue of received messages 
retransmit_buff= {} #buff associated with packets 
sock= None #socket object
window_size= 0
paylad_len= 0 
dat_string= ""
clients= {} #keep instances of the rdp class

#maybe get rid of this ones
sucess_message= {} #queue of successful messages
sucess_req= {} #queue of successful requests

#have a lisst with active clients 

#server process the http request and sends the response from the client !!!!!
class packet:
    def __init__(self, command,seq_num, ack_num, payload):
        self.command= command
        self.seq_num= seq_num
        self.ack_num= ack_num
        self.payload= payload
        self.length= len(payload)
    
    def add_command(self, new_command):
        self.commmand+= new_command

    def update_seq(self, new_seq):
        self.seq_num= new_seq
    def update_ack(self, new_ack):
        self.ack_num= new_ack

    def update_payload(self, new_payload):
        self.payload= new_payload
        self.length= len(new_payload)
   
    def __str__(self) :
        return f"Command: {self.command}, Seq: {self.seq_num}, Ack: {self.ack_num}, Length: {self.length}, Payload: {self.payload}"

#----------Helpers to service requests ----------------

#   ---Class to handle the RDP state machine ---
class rdp:
    def __init__(self, connect_id):
        self.state= "idle"
        self.connection_id= connect_id
        self.win_available= window_size
        self.current_seq= 0
        self.current_ack = 0
        self.expected_seq= 0
        self.first_packet= True 

    def set_state(self, new_state):
        self.state= new_state

    def get_state(self):
        return self.state
    
    def put_dat(self, dat):
        global snd_buff
        snd_buff_data = snd_buff.get(self.connection_id)
        if snd_buff_data is None:
            snd_buff[self.connection_id]= [dat]
        else:
            snd_buff_data.append(dat)
            snd_buff[self.connection_id]= snd_buff_data

    def receive_connection(self):
        global snd_buff
        self.set_state("syn-received")
        #ACK|SYN in packet to client 
        command= ["ACK", "SYN"]
        syn_init= packet(command, 0, 0, "") #update the seq and ack numbers
        snd_buff[self.connection_id]= [syn_init]  
        self.set_state("connect")#since we are sending ACK|SYN evolve to connect

    #------------ All the helpers to service HTTP requests-----------
            
    #If we go in here send FIN and close the connectin INMEDIATELY 
    def bad_request():
        return "HTTP/1.0 400 Bad Request\r\nConnection: close\r\n\r\n"
        exit(1) #replace for sending FIN

    def is_persitent(self, request):
        if "Connection: Keep-alive" in request:
            return True
        else:
            return False
    
    #todo:check format 
    def request_answ(self, result, request):
        global sucess_message
        global sucess_req
        filename= result[0].strip()
        filename= filename[1:]
        #Add checks to see if persistent or not. if not send FIN

        if os.path.isfile(filename): #if the file exists
            with open(filename, "r") as file:
                data= file.read()
                sucess_message.setdefault(self.connection_id, {})[request]= data
                sucess_req[self.connection_id]= request
                answ= "HTTP/1.0 200 OK"+ "\r\n"+data
            
        else:
            answ = "HTTP/1.0 404 Not Found"+ filename
        return answ


    #Categorize request by the type of request
    #Possible requests answers:
            #1. 200 OK -> will automatically populate dictionary with its content associated with req
            #2. 400 -> BAD request. Will send fin (TODO: add FIN)
            #3. 404 -> File not found. Will append it on the payload for client to handle
    def service_request(self, request):
        str_format = re.compile(r'GET\s([^\s]+)\s+HTTP/1.0')  # regex to get filename 
        result = re.findall(str_format, request)
        if not result:
            answ= self.bad_request()

        else:            
            answ= self.request_answ(result, request)
        return answ
    
    # Helper to split and packet all the data according to specified payload length
    def pack_data(self, data):
        global snd_buff
        dat_string= ""
        remaining_space = payload_len - len(dat_string)
        chars_to_add = min(remaining_space, len(data))  # Determine how many characters to add
        dat_string += data[:chars_to_add]  # Add characters to the buffer
        remaining_data = data[chars_to_add:]  # Save remaining data for next iteration
        print("DAT STRING", dat_string, len(dat_string), "PAYLEN", payload_len)

        
        if len(dat_string) == payload_len:
            # If the buffer reaches the payload length, create DAT packet and put it
            dat_packet = packet("DAT", 0, 0, dat_string)
            print("DATA PACK 1 .....", dat_packet.command)
            self.put_dat(dat_packet)
            dat_string= "" #reset after putting it in the buffer

        else: #could fit it !
            #print("Little file")
            dat_packet= packet("DAT", 0, 0, dat_string)
            print("DATA PACK 2, little ", dat_packet)
            self.put_dat(dat_packet)
            dat_string= "" 


        if remaining_data:
            self.pack_data(remaining_data) #pack recursively 
        

    #Function were we extract each GET request provided and service it by calling helpers
    def gather_req(self, command):
        #print("NEED TO SERVICE", command)
        patt= rb'GET(?:.|\n)*?(?=GET|$)'
        matches= re.findall(patt, command) 
        for match in matches:
            match= match.decode()
            match = match.split("\r\n\r\n") #anything matched after the \r\n\r\n we dont care
            match= match[0]
            answ= self.service_request(match)
            self.pack_data(answ)

    #determines if the sequence number is right! if it is, then receive package
    #Otherwise, drop it
    def check_in_accordance(self, command)-> bool:
        command= command.decode()
        seq, ack, client_paylen= self.find_numbers(command)
        #print("SEQ, ACK, LEN", seq, ack, client_paylen) 
        if self.expected_seq== int(seq):
            self.current_seq= int(seq)
            #print("Welcome sir we were expecting u")
            return True
        
        print("sir you are not expected")
        return False

          
    def parse_command(self, command): #upon receiving a command from the server, remember it is going to be a binary string 
        pattern= rb'([A-Z]{3})(?:\|([A-Z]{3}))(?:\|([A-Z]{3}))?'
        matches= re.findall(pattern, command) #finds all the commands in the string. 
        matches_flat= [item for sublist in matches for item in sublist] 
        for match in matches_flat:
            if match== b"ACK":
                #process ACK 
                #check if we can do something with it -> release size in window
                #see if we can send more packets (if remaining )
                print("HELLO TAKE PRIORITY")
            if match == b"SYN":
                self.receive_connection() #ack the syn and send a syn-ack
            elif match == b"DAT":
                self.gather_req(command) 
            elif match == b"FIN":
                print("FIN is received, need to implement this?")


    def to_string(self, nested_commads):
        combined_commands = "|".join([item if isinstance(item, str) else '|'.join(item) for item in nested_commads])
        #print("COMBINED COMMANDS", combined_commands)
        return combined_commands
    
    #finds the SEQ, ACK and LENGTH of the packet received, isolates them and returns them
    #to determine the info we will send back to the client
    def find_numbers(self, string):
        pattern = r"Seq:\s*(-?\d+).*?Ack:\s*(-?\d+).*?Length:\s*(\d+)"
        matches = re.findall(pattern, string)
        if matches:
            matches= matches[0] 
            return matches
    
    #determines next seq and ack numbers to send back to the client based on current number
    #updates current_ack and current_seq accordingly
    def generate_nums(self, my_paylen, client_paylen):
        if self.first_packet:
            self.current_seq= 0
            self.first_packet= False
        else:
            self.current_seq+= my_paylen #my paylength 

        self.current_ack= int(client_paylen)+1 #acknowledge client's received packet

    


    #Constructs and populates the snd_buff with taylored server responses
    #Whenever possible send joint commands, and upon detecting last ack put DAT|FIN
    def generate_response(self):
        global snd_buff
        global payload_len
        commands= []
        string_commands= ""
        first_dat = True

        queue_msg= snd_buff[self.connection_id]
        snd_buff[self.connection_id]= []

        while (len(queue_msg))> 0:
            p= queue_msg.pop(0)
            client_seq, client_ack, client_paylen=self.find_numbers(rcv_buff[self.connection_id].decode())
            self.generate_nums(p.length, client_paylen)

            if p.command!= "DAT":
                commands.append(p.command)
            
            if p.command == "DAT" and first_dat:
                first_dat= False
                commands.append("DAT")
                string_commands= self.to_string(commands)
                new_pack= packet(string_commands, self.current_seq, self.current_ack, p.payload)
                
            
            else:
                if len(queue_msg)==0:  #if its the last send DAT|FIN
                     new_pack= packet("DAT|FIN", self.current_seq, self.current_ack, p.payload)
                     self.set_state("fin-sent")
                else:
                    new_pack= packet("DAT", self.current_seq, self.current_ack, p.payload)

            self.put_dat(new_pack)

        #------------------- Helpers for writable and sending data to client ---------------------

    def send_data_to_client(self, addr):
        global snd_buff
        global retransmit_buff
        info_to_send= snd_buff[self.connection_id]
        retransmit_buff[self.connection_id]= {} #how to do it nested?
            
        #send only howver much fits on the window!!!!!
        while len(info_to_send)>0: #remember to clear snd buff after all is done
            msg= info_to_send.pop(0)
            seq_no = msg.seq_num
            retransmit_buff[self.connection_id][seq_no]= msg
            msg= str(msg)
            sock.sendto(msg.encode(), addr)
            #self.expected_seq+= msg.

        #remove everything from snd_buff
        
              

def udp_sock_start(ip, port):
    global sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((ip , port))
    sock.setblocking(0)


def main_loop():
    global snd_buff, rcv_buff
    global payload_len
    global clients

    while True:
        readable, writable, exceptional = select.select([sock], [sock], [sock])
        for s in readable:
            data, addr = s.recvfrom(5000)
            port_no= addr[1] #Port no found ar index 1
            #print( "Received ", data.decode() )
            #print("From", port_no)
            rdp_obj= rdp(port_no)
            clients[port_no]= rdp_obj
            rcv_buff[port_no]= data

            if rdp_obj.check_in_accordance(data):
                rdp_obj.parse_command(data)
                rdp_obj.generate_response()
       

        for s in writable:
            for client_id in clients:
                rdp_obj= clients[client_id]
                rdp_obj.send_data_to_client(addr)
            
            #send the data
            #if it is the last data, send a FIN
            pass


if __name__== "__main__":
    ip, port , window_size, payload_len = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    udp_sock_start(ip, port)
    main_loop()
