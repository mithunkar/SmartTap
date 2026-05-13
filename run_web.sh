#!/bin/bash

set -e

cd web
npm install

echo "Starting SmartTap React UI at http://localhost:5173"
npm run dev -- --host 127.0.0.1 --port 5173
