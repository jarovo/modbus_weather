# syntax=docker/dockerfile:1

# Create Dockerfile for python with cashed dnf and pip installed packages
FROM python:3.10-alpine AS runner

# Install git and pip packages
RUN apk add git
COPY requirements.txt /tmp/

RUN pip install -r /tmp/requirements.txt

# Run application
ENTRYPOINT [ "python", "app.py" ]

# Copy source code
#VOLUME /app
COPY . /app
WORKDIR /app

FROM runner AS builder
# Copy the build requirements
COPY requirements.build.txt /tmp/
RUN pip install -r /tmp/requirements.build.txt

RUN pip install pre-commit
COPY .pre-commit-config.yaml .
RUN git init . && pre-commit install-hooks