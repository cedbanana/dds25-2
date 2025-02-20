#!/bin/sh

python -m grpc_tools.protoc -I. --python_out=common --grpc_python_out=common proto/*.proto
