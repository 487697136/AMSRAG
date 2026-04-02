#!/bin/bash

echo "========================================"
echo "AMSRAG-Web Frontend Starting..."
echo "========================================"
echo ""

echo "Checking Node.js..."
if ! command -v node &> /dev/null; then
    echo "Error: Node.js not found!"
    echo "Please install Node.js from https://nodejs.org/"
    exit 1
fi
node --version

echo ""
echo "Checking dependencies..."
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install dependencies!"
        exit 1
    fi
fi

echo ""
echo "Starting development server..."
echo "Frontend will be available at: http://localhost:5173"
echo ""
npm run dev
