#!/bin/sh

python -m grpc_tools.protoc -I. --python_out=stock --grpc_python_out=stock proto/*.proto
python -m grpc_tools.protoc -I. --python_out=payment --grpc_python_out=payment proto/*.proto
python -m grpc_tools.protoc -I. --python_out=order --grpc_python_out=order proto/*.proto
