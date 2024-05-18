Projects created related to the learning of computer networks, internet UDP and TCP/IP protocols. The main programming language for this repository is in python3. 
There are 3 projects in this repo:
1. sws.py - a simple web server that sends HTTP request over TCP sockets
2. rdp.py - a Reliable Datagram Protocol that uses 3 way handshake and acknowledgement mechanisms to send packages through UPD sockets. It is a simple version of Google QUIC protocl
3. SOR - (sor client and SOR server) which is sending HTTP request throgh UDP using 3 way handshake and acknowledgements to process and receive requests. It is an improvement from RDP as it is more efficient in terms of Round Trips to send packages, by sending multiple commands in a single trip when possible.
