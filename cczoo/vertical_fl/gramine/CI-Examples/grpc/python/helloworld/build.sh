set -e

shopt -s expand_aliases
alias make_logfilter="grep -v 'measured'"
alias runtime_logfilter="grep -v 'FUTEX|measured|memory entry|cleaning up|async event|shim_exit'"

export EXP_PATH=${GRPC_PATH}/examples
export EXP_PY_PATH=${EXP_PATH}/python/helloworld

function get_env() {
    gramine-sgx-sigstruct-view --verbose --output-format=text ./python.sig | grep $1 | awk -F ":" '{print $2}' | xargs
}

# build example
${EXP_PY_PATH}/build.sh

# copy examples
cp ${EXP_PY_PATH}/greeter_client.py ./grpc-client.py
cp ${EXP_PY_PATH}/greeter_server.py ./grpc-server.py
cp ${EXP_PY_PATH}/helloworld_pb2.py .
cp ${EXP_PY_PATH}/helloworld_pb2_grpc.py .

# build and generate config json with gramine
make clean && make | make_logfilter
jq ' .sgx_mrs[0].mr_enclave = ''"'`get_env mr_enclave`'" | .sgx_mrs[0].mr_signer = ''"'`get_env mr_signer`'" ' ${EXP_PATH}/dynamic_config.json > ./dynamic_config.json
cat ./dynamic_config.json

kill -9 `pgrep -f gramine`
