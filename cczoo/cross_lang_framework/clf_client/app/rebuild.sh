clear
make clean
GRAMINEDIR=/home/ubuntu/gramine SGX_SIGNER_KEY=/home/ubuntu/.config/gramine/enclave-key.pem make SGX=1 DEBUG=1
#gramine-sgx java -Xmx2G clf_test
#gramine-sgx test
gramine-sgx java -Xmx2G clf_test

