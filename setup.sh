#!/bin/bash

# TC API Development Setup Script

echo "Setting up TC API development environment..."

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create necessary directories
mkdir -p uploads builds logs

# Copy environment file
cp .env.example .env

echo "Setup complete!"
echo ""
echo "To run the service:"
echo "1. Activate virtual environment: source venv/bin/activate"
echo "2. Start the service: python main.py"
echo ""
echo "API will be available at: http://localhost:8000"
echo "API documentation: http://localhost:8000/docs"
