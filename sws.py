import socket 
import select 
import sys
import queue
import time
import re 

def bad_request():
    print(" HTTP/1.0 400 Bad Request \r\nConnection :close \r\n\r\n")
    exit(1)
    #close connection of the socket?? 


def handle_command(command):
    fomat= re.compile(r'GET\s([^\s]+)\s+HTTP/1.0') #regex to get filename in valid string format
    result= re.findall(fomat, command)
    if result!=[]: #if result==[] invalid request as does not meet with string format
        print(result)
        print("valid request")
    else:
        bad_request()

def connect(ip, port): # Create a socket object
    server= socket.socket(socket. AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) #allow reuse of socket
    server.setblocking(0) 
    port= int(port)
    server.bind( (ip, port )) # Bind to the port
    server.listen(5) #  wait for client connection.
           


        
    
    



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Can't start server, no port or ip address provided")
        exit(1)
    else: # maybe do error handling for the int conversion "forced"
        ip, port_no= sys.argv[1], sys.argv[2]


    #connect(ip, port_no) #connect to server
        
    command= input("Enter command: ")
    handle_command(command)

        
    