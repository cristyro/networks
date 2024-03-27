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
send_data= True #to stop or keep sending messages in snd_buff for a certain socket
#Initialization of sockets
readable= []
writable=[]
exceptional=[]
send_more_data=False
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
        self.finish= False

    def set_state(self, new_state):
        print("Transition from ", self.state, "to ", new_state)
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
        command= ["SYN","ACK"]
        syn_init= packet(command, 0, 0, "") #update the seq and ack numbers
        snd_buff[self.connection_id]= [syn_init]  
        self.set_state("connect")#since we are sending ACK|SYN evolve to connect

    #------------ All the helpers to service HTTP requests-----------
            
    #If we go in here send FIN and close the connectin INMEDIATELY 
    def bad_request():
        return "HTTP/1.0 400 Bad Request\r\nConnection: close\r\n\r\n"
        exit(1) #replace for sending FIN

    def is_persitent(self, request):
        request= request.replace("\r\n", " ")
        if "Connection:Keep-alive" not in request:
            self.finish= "True"
                    
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
                answ= "HTTP/1.0 200 OK"+ "\r\n"+"Content Length: "+str(len(data))+"\r\n\r\n"+data
            
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
            self.is_persitent(request)
        return answ
    
    # Helper to split and packet all the data according to specified payload length
    def pack_data(self, data):
        global snd_buff
        dat_string= ""
        remaining_space = payload_len - len(dat_string)
        chars_to_add = min(remaining_space, len(data))  # Determine how many characters to add
        dat_string += data[:chars_to_add]  # Add characters to the buffer
        remaining_data = data[chars_to_add:]  # Save remaining data for next iteration

        if len(dat_string) == payload_len:
            # If the buffer reaches the payload length, create DAT packet and put it
            dat_packet = packet("DAT", 0, 0, dat_string)
            self.put_dat(dat_packet)
            dat_string= "" #reset after putting it in the buffer

        else: #We were able to fit all the payload in a "small packet"
            dat_packet= packet("DAT", 0, 0, dat_string)
            self.put_dat(dat_packet)
            dat_string= "" 

        if remaining_data:
            self.pack_data(remaining_data) #pack recursively 
        

    #Function were we extract each GET request provided and service it by calling helpers
    def gather_req(self, command):
        #print("NEED TO SERVICE", command)
        patt= r'GET(?:.|\n)*?(?=GET|$)'
        matches= re.findall(patt, command) 
        for match in matches:
            match = match.split("\r\n\r\n") #anything matched after the \r\n\r\n we dont care
            match= match[0]
            answ= self.service_request(match)
            self.pack_data(answ)

    #determines if the sequence number is right! if it is, then receive package
    #Otherwise, drop it
    def check_in_accordance(self, command) -> bool:
        command = command.decode()
        seq, ack, client_paylen = self.find_numbers(command)
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
        

    def terminate_conn(self):
        global rcv_buff
        global snd_buff
        global clients
        rcv_buff[self.connection_id]= []
        snd_buff[self.connection_id]=[]
        clients[self.connection_id]= []



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
            self.current_seq+=my_paylen
            self.first_packet= False
        else:
            self.current_seq+= my_paylen #my paylength 

        #print("CLIENTS PAYLEN", client_paylen, "MINE", self.current_ack)
        self.current_ack+= int(client_paylen) #acknowledge client's received packet
        #print("AFTER UPDATE", self.current_ack)


    #Only here if we have an ACK
    #might have to add more states and transitions     
    #Returns false if ACK is in command and we want to stop parsing and skip to sending data to the client
    def process_ack(self, command)-> bool :
        global send_data
        if self.get_state()== "fin-sent" and "FIN in command": 
            print("CUT OFF CLIENT")
            self.set_state("conn-fin-rcv")
            return True
        else: #If it is just an ack for now?
            send_data= True
            self.set_state("connect")
            return False
        

        #Parse commands and branch out to handle the commands         
    def parse_command(self, command):
        continue_parsing= True
        command= command.decode()
        pattern= r'\b([A-Z]+)\b'
        matches= re.findall(pattern, command) #finds all the commands in the string. 
        relevant_matches= [match for match in matches if match in ['SYN', 'DAT', 'ACK', 'FIN']]
        for match in relevant_matches:
            if match== "ACK":
                continue_parsing= self.process_ack(command)
            if match == "SYN":
                #Stablish bidirectional connection with the client 
                #If continue_parsing then we will skip to sending the data to client 
                self.receive_connection() 
            elif match == "DAT":
                #Gather information from the client's request and process it 
                self.gather_req(command) 
            elif match == "FIN":
                #print("FIN is received, need to implement this?")
                self.terminate_conn()

        return continue_parsing

                

    # ---- Helper that puts everything together to send a said packet to client--------
    #Constructs and populates the snd_buff with taylored server responses
    #Whenever possible send joint commands, and upon detecting last ack put DAT|FIN
    def generate_response(self):
        global snd_buff
        global payload_len
        commands= []
        string_commands= ""
        first_dat = True

        queue_msg= snd_buff[self.connection_id]
        snd_buff[self.connection_id]=[]

        while queue_msg:
            p= queue_msg.pop(0)
            client_seq, client_ack, client_paylen=  self.find_numbers(rcv_buff[self.connection_id].decode())

            if p.command!= "DAT":
                commands.append(p.command)

            if p.command =="DAT" and not first_dat:
                commands= ["DAT"]

            if p.command == "DAT" and first_dat:
                first_dat = False
                commands.append("DAT")
            
            elif self.get_state()== "fin-rcv" and not queue_msg:
                commands.append("FIN")

            if (self.get_state()== "fin-rcv") and "DAT" in commands:
                print("WHY AM I HERE?")
                self.generate_nums(p.length, client_paylen)
                new_pack= packet(self.to_string(commands), self.current_seq, self.current_ack, p.payload)
                self.set_state("fin-sent")
                self.put_dat(new_pack)

            if "DAT" in commands:
                self.generate_nums(p.length, client_paylen)
                new_pack= packet(self.to_string(commands), self.current_seq, self.current_ack, p.payload)
                self.put_dat(new_pack)


        #------------------- Helpers for writable and sending data to client ---------------------

    def send_data_to_client(self, addr):
        global snd_buff
        global retransmit_buff
        global send_more_data
        info_to_send= snd_buff[self.connection_id]
        retransmit_buff[self.connection_id]= {} #how to do it nested?
        sending_data= True
        while info_to_send and sending_data: #remember to clear snd buff after all is done
            msg= info_to_send.pop(0)
            seq_no = msg.seq_num
            retransmit_buff[self.connection_id][seq_no]= msg
            sock.sendto(str(msg).encode(), addr)
            print("MESSAGE", str(msg), "IS syn in msg?", "SYN" in msg.command) 
            if ("SYN" in msg.command or "ACK" in msg.command):
                print("only send this")
                sending_data= False
                send_more_data = True if len(info_to_send)>1 else False 
                return False
        return True
            
        
              

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
    global send_data
    rdp_obj= None


    while True:
         # Select readable and writable sockets
        readable, writable, exceptional = select.select([sock], [sock], [])
        for s in readable:
            data, addr = s.recvfrom(5000)
            port_no= addr[1] # Extract port number from address
            print( "Received ", data.decode())

            # If the client is new, initialize RDP object
            if not port_no in clients:
                rdp_obj= rdp(port_no)
                clients[port_no]= rdp_obj
                rcv_buff[port_no]= data

             # Check if received packet has correct sequence number as expected by the protocol
            if rdp_obj.check_in_accordance(data):
                continue_parse= rdp_obj.parse_command(data) #Parse command from the packet
                print("continue parse? or skip to sending", continue_parse)
                if continue_parse:
                    rdp_obj.generate_response() #Generate an appropiate response
       
            # Process writable sockets and send data to clients
            
            for client_id in clients:
                print("HERE in start loop", send_data)
                if send_data and clients[client_id] !=[]:
                    rdp_obj= clients[client_id]
                    send_data= rdp_obj.send_data_to_client(addr) # Send data to the client 


if __name__== "__main__":
    ip, port , window_size, payload_len = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    udp_sock_start(ip, port)
    main_loop()