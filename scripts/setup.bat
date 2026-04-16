@echo off
REM TC API Development Setup Script for Windows

echo Setting up TC API development environment...

REM Create virtual environment
python -m venv venv
call venv\Scripts\activate.bat

REM Install package and dependencies
pip install -e .

REM Create necessary directories
mkdir uploads 2>NUL
mkdir builds 2>NUL
mkdir logs 2>NUL

REM Copy environment file
copy .env.example .env

echo Setup complete!
echo.
echo To run the service:
echo 1. Activate virtual environment: venv\Scripts\activate.bat
echo 2. Start the service: python -m tc_api.main
echo.
echo API will be available at: http://localhost:8000
echo API documentation: http://localhost:8000/docs

pause
