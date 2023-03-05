# Create Dockerfile for python with cashed dnf and pip installed packages
FROM python:3.10-alpine

# Install git and pip packages
RUN apk add git
COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt

# Copy source code
COPY . /app
WORKDIR /app

# Run application
ENTRYPOINT [ "python", "app.py"]