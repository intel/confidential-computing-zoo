python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. homo_lr.proto
python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. hetero_attestation.proto
make clean
make SGX=1 -j
