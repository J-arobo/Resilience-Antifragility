FROM python:3.11-slim

#install system dependencies including tc (from iproute2)
#RUN apt-get update && apt-get install -y iproute2 && rm -rf /var/lib/apt/lists/*
# Install system dependencies including tc (from iproute2) and build tools for matplotlib/scikit-learn 
RUN apt-get update && apt-get install -y \
iproute2 \
gcc \ 
g++ \ 
python3-dev \ 
libfreetype6-dev \ 
libpng-dev \ 
pkg-config \ 
build-essential \ 
&& rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app


# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .
#COPY resilient_api /app/resilient_api/

EXPOSE 5002

# Run the API
CMD ["python", "app.py"]
