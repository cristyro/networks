import socket
import select
import sys
import queue
import time
import re
import os
from datetime import datetime
import time

def process_request(command)-> [str, bool]:
    bad_request= "HTTP/1.0 400 Bad Request"
    okay_request= "HTTP/1.0 200 OK "
    not_found= "HTTP/1.0 404 Not Found "
    response= ""
    is_persistent= False
    str_format= re.compile(r'GET\s([^\s]+)\s+HTTP/1.0') #regex to get filename in valid string format- check spaces after get
    #add keep-alive or Keep-alive. If theres nothing but keep alive
    result= re.findall(str_format, command)
    for s in result:
        if s: #if result==[] invalid request as does not meet with string format
            filename= result[0]
            filename= filename.strip() 
            filename= filename[1:] #remove the / from the filename
            check_file= os.path.isfile(filename)

            if check_file: 
                with open(filename, 'r') as f:
                    file_contents= f.read()
                    response= okay_request + "\r\n" + file_contents
                    f.close()
            else: #file not found
                response= not_found 
        else: #did not match regex
            response= bad_request
            return response, False #not persistent , exit 
        
    response+= "\n"
    persistent1= "connection:keep-alive"
    persistent2= "connection: keep-alive"
    command= command.lower()
    if persistent1 in command or persistent2 in command:
        is_persistent= True

    return response, is_persistent    

def check_persistent(command)-> bool:
    command= command.strip()
    persistent1= "Connection:Keep-alive"
    persistent2= "Connection: keep-alive"
    if persistent1 in command or persistent2 in command:
        return True
    return False

def connect(ip, port)-> socket: # Create a socket object
    server= socket.socket(socket. AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) #allow reuse of socket
    server.setblocking(0)
    server.bind( (ip, port) ) # Bind to the port
    server.listen(5) #  wait for client connection.
    return server


def complete_test(text)->bool: #check this method! 
    text= text.strip()
    if text.endswith("\\r\\n\\r\\n") or text.endswith("\\n\\n"):
        return True
    return False

# format of response_messages
#time: client_ip:client_port request; response
# Wed Sep 15 21:44:35 PDT 2021: 192.168.1.100:54321 GET /sws.py HTTP/1.0; HTTP/1.0 200 OK""
# ADD PDT to the time stamp or ask if we can put it after the year!!
def generate_response(ip, port, request, response):
    t = time.localtime()
    time_stamp = datetime.fromtimestamp(time.mktime(t))
    time_stamp = time_stamp.strftime("%a %b %d %H:%M:%S PDT %Y")
    result = f"{time_stamp}: {ip}:{port} {request}; {response}"
    return result


def shutdown_connection(conn, s, active_clients, request_messages, response_messages):
    if conn is not None:
        if s in active_clients:
            active_clients.remove(s)
        if s.fileno() in request_messages:   
            del request_messages[s.fileno()]          
        if s in response_messages:
            del response_messages[s.fileno()] 
    #s.shutdown(socket.SHUT_RDWR) 
    s.close()
    return active_clients



#check if there are multiple requests in the same message
#return if multiple or not
def check_multiple_requests(req)-> list:
    pattern= re.compile(r'((?:GET|go)\s/.*?HTTP/1\.0(?:.*?\\r\\n){2}(?:.*?\\n)?)')
    #print("PATTERN", pattern)
    result= re.findall(pattern, req)
    return result



def service_multiple_requests(s, multi_req, ip, port_no,outputs, response_messages):
    multiple= s.fileno()
    #marked= False
    for req in multi_req:
        answer, is_persistent = process_request(req)
        answer = generate_response(ip, port_no, req, answer) 
        multiple*=11 #multiply by a prime number to get a unique number
        response_messages[multiple]= answer
        outputs.append(s)
    return answer, is_persistent, response_messages, outputs


def manage_readable(readable, server, inputs, request_messages, active_clients, response_messages, outputs):
    answer = ''
    is_persistent = False
    multi_req = []
    conn = None

    for s in readable:
        if s == server:  # if we have a new connection from the client
            conn, address = server.accept()
            inputs.append(conn)
            request_messages[conn.fileno()] = ''  # message received from the client and added to the dictionary
            active_clients.append(conn)
            response_messages[conn.fileno()] = []  # use a list to store multiple responses
        else:
            message = s.recv(1024).decode()  # if we are receiving data from the client
            if not s.fileno() in request_messages:
                request_messages[s.fileno()] = message
            else:
                request_messages[s.fileno()] += message

            #print("Complete test: ", complete_test(message))
            if complete_test(message):
                multi_req = check_multiple_requests(request_messages[s.fileno()])
                print("MULTI REQ",multi_req)
                if len(multi_req) > 1:  # update values modified
                    answer, is_persistent, response_messages, outputs = service_multiple_requests(
                        s, multi_req, ip, port_no, outputs, response_messages)
                else:
                    whole_message = request_messages[s.fileno()]
                    outputs.append(s)  # add the socket to the list of sockets to write to
                    answer, is_persistent = process_request(whole_message)
                    answer = generate_response(ip, port_no, whole_message, answer)
                    response_messages[s.fileno()] = answer

    return active_clients, answer, is_persistent, response_messages, request_messages, outputs, multi_req, conn

def multi_clients(active_clients):
    print("ACTIVE CLIENTS", len(active_clients))
    if len(active_clients) > 1:
        return True
    return False

def handle_writable(multi_req, writable, inputs, outputs, response_messages, request_messages, is_persistent, sockets_to_close, active_clients):
    sent_requests = []
    has_multi_clients= multi_clients(active_clients)
    print("CLIENTS", active_clients)
    print("HAS MULTI CLIENTS", has_multi_clients)

    for s in writable:  # sockets ready to send data to the client  
        if len(response_messages) == 1 or has_multi_clients:  
            print("HEYYYYYY in writable")
            next_message = response_messages[s.fileno()]  # Get the next message to send
            is_persistent = check_persistent(request_messages[s.fileno()])
            if s.fileno()> 0:
                next_message= str(next_message)
                next_message= next_message.encode()
                s.send(next_message)
                print("IS PERSISTENT?", is_persistent)
                if is_persistent:
                    request_messages[s.fileno()] = ''  # reset the request message for the persistent connection
                    inputs.remove(s)
                    outputs.remove(s) #
                else:
                    if not s in sockets_to_close:
                        print("not persistent, closing socket")
                        sockets_to_close.append(s)
        elif len(response_messages) >= 2 and not has_multi_clients:
            #print("HERE ")
            for key in response_messages:
                next_message = response_messages[key]
                if next_message not in sent_requests:
                    sent_requests.append(next_message)
                    next_message = str(next_message)
                    next_message = next_message.encode()
                    s.send(next_message)
                    if s in outputs:
                        outputs.remove(s)
            if not s in sockets_to_close:
                sockets_to_close.append(s)

    print("SOCKETS TO CLOSE HEY : ", sockets_to_close)
    return sockets_to_close, outputs, inputs

#function that checks every 30 seconds if there are persistent connections longer than 30 sec (timeout)
def process_timeout(active_clients, last_times): 
    now= time.time()
    for clients in active_clients:
        last_activity_time= last_times.get(clients, 0)
        if now - last_activity_time > 30:
            print(f"Timeout for socket {clients.fileno()}, closing connection")
            active_clients.remove(clients)
            clients.close() #close the socket that timed out 
            del last_times[clients] #delete the socket from the dictionary of last times
    return active_clients, last_times


#Todo: figure if timeout on current client :D 
def check_loop(server, ip, port_no):
    timeout = 100
    inputs = [server]
    outputs = []
    active_clients = []  # List to store persistent connections
    response_messages = {}
    request_messages = {}
    sockets_to_close = []
    last_times= {} #dictionary to store the last time a socket was active
    
    while True: #this is for real implementation
        try: 
            readable, writable, exceptional = select.select(inputs, outputs, inputs, timeout )
            active_clients, answer, is_persistent, response_messages,request_messages,  outputs , multi_req, conn= manage_readable(readable, server, inputs, request_messages, active_clients, response_messages, outputs)
            sockets_to_close, outputs, inputs= handle_writable(multi_req, writable, inputs, outputs, response_messages, request_messages, is_persistent, sockets_to_close, active_clients)
            #print("SOCKETS TO CLOSE IN LOOP ", sockets_to_close)
            if not (readable or writable or exceptional):
                print("Timeout HERE")

            for s in sockets_to_close:
                #print(" WHAT IS IN SOCKETS ?? \n ",sockets_to_close)
                #print(f"Closing socket,  {s.fileno()}")
                active_clients= shutdown_connection(conn, s, active_clients, request_messages, response_messages)
                if s in outputs:
                   outputs.remove(s)
               #print("s in inputs?",s,  s in inputs)
                if s in inputs:
                    inputs.remove(s)
                if s in active_clients:
                    active_clients.remove(s)
                #print("Active clients after closing", active_clients)

            #print(inputs)
            # Update the list of active persistent connections
            inputs = [server] + active_clients
            #print("Active clients ...", active_clients)
            #print("readable", readable)
            #print("writable", writable)
            #print("exceptional", exceptional)
            #print("lists")
            #print("inputs 3: ", inputs)
            #print("outputs", outputs)
            print("--- End of iteration ---")
        except ValueError:

            #print("Value error")
            print("Mhhh... something went wrong")
            #pass
            break; 

                        
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Can't start server, no port or ip address provided")
        exit(1)
    else: # maybe do error handling for the int conversion "forced"
        ip, port_no= sys.argv[1], sys.argv[2]
       
    port_no = int( float ( port_no ))
    server= connect(ip, port_no) #connect to server
    check_loop(server, ip , port_no)
