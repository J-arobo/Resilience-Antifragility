FROM python:3.11-slim
WORKDIR /locust
COPY locustfile.py ./
RUN pip install locust
EXPOSE 8089
CMD ["locust", "-f", "locustfile.py", "--host=http://app:5002"]
