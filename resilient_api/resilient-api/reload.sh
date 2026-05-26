#!/bin/bash
echo "Restarting Flask app..."
pkill -f app.py
python app.py &

echo "Restarting Locust..."
pkill -f locust
locust -f locustfile.py --host=http://localhost:5002 &
