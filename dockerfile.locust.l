FROM python:3.11-slim
WORKDIR /locust
RUN pip install locust
EXPOSE 8089