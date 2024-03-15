#!/bin/bash

python3 process_txt.py 

echo -n "Enter database ip addr: "
read ip_addr

echo -n "Enter database username: "
read username

echo -n "Enter database password: "
read -s password

python3 generate_faiss.py "$ip_addr" "$username" "$password"

unset ip_addr
unset password

