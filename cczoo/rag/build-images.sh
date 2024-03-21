#!/bin/bash
set -ex

echo -e "\nbuild backend image..."
cd backend
./build-image.sh

sleep 1s

echo -e "\nbuild frontend image..."
cd ../frontend/chatbot-rag
./build-image.sh
