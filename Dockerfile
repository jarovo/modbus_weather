# syntax=docker/dockerfile:1

# Create Dockerfile for python with cashed dnf and pip installed packages
FROM python:3.10-alpine AS runner

# Preinstall git and pip packages
RUN apk add git
RUN mkdir /app
COPY pyproject.toml /app
RUN python -m pip install /app

# Copy source code
COPY . /app
WORKDIR /app

RUN python -m pip install /app

# Run application
ENTRYPOINT [ "modbus_weather" ]

FROM runner AS builder

RUN apk add gcc bash
#RUN apt-get update && apt-get install -y gcc bash

# https://github.com/ocaml/opam-repository/issues/13718
RUN apk add musl-dev
-
# Copy the build requirements
RUN python -m pip install '/app[dev]'

COPY .pre-commit-config.yaml .
RUN git init . && pre-commit install

ENTRYPOINT [ "pre-commit" ]