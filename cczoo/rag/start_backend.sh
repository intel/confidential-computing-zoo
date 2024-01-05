#!/bin/bash
#
# Copyright (c) 2023 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e

function usage() {
    echo -e "Usage: $0 IMAGE_ID DB_TYPE RA"
    echo -e "  IMAGE_ID       backend docker image ID;"
    echo -e "  DB_TYPE        mysql: MySQL, es: Elasticsearch;"
    echo -e "  RA             remote attestation. 0: disabled, 1: enabled"
}


if [ "$#" -lt 3 ]; then
    usage
    exit 1
fi

image_id=$1

db_type=$2
if  [ "$2" != "mysql" ] && [ "$2" != "es" ]; then
    usage
    exit 1
fi

ra=$3
if  [ "$3" != "0" ] && [ "$3" != "1" ]; then
    usage
    exit 1
fi


[ "$ra" == "1" ] && REMOTE_ATTESTATION="grpc-ratls"

if [ "$db_type" == 'mysql' ]; then
    if docker ps -a | grep -q "tdx_rag_backend"; then
        docker stop tdx_rag_backend
        docker rm tdx_rag_backend
    fi
    rm -rf backend/pipelines/faiss-index-so.*
    echo -e "\nstart backend container..."
    cp -n data/data.txt /home/encrypted_storage
    docker run -itd --privileged --network host \
       -e http_proxy=${http_proxy} \
       -e https_proxy=${https_proxy} \
       -e no_proxy=${no_proxy} \
       -e API_PROTOCOL=${API_PROTOCOL} \
       -e PIPELINE_YAML_PATH=/home/user/workspace/rag_mysql.yaml \
       -e ENABLE_OPTIMUM_INTEL=False \
       -e QUERY_PIPELINE_NAME=query \
       -e ONEDNN_MAX_CPU_ISA=AVX512_CORE_BF16 \
       -e PYTHONWARNINGS=ignore \
       -v /dev:/dev \
       -v /var/run/aesmd/aesm.socket:/var/run/aesmd/aesm.socket \
       -v /home/encrypted_storage:/home/rag_data/ \
       -v $(pwd)/backend/pipelines:/home/user/workspace \
       --shm-size=64gb --name tdx_rag_backend ${image_id} /bin/bash
    sleep 5

    # Add workaround for mysql 5.x
    file_path="/usr/local/lib/python3.10/dist-packages/haystack/document_stores/sql.py"
    insert_line="        self.use_windowed_query=False"
    docker exec -i tdx_rag_backend /bin/bash -c "sed -i '314i\\$insert_line' '$file_path' && cd /home/user/workspace/ && ./handle_docs.sh"
    if [ "$REMOTE_ATTESTATION" == 'grpc-ratls' ]; then
        docker exec -i tdx_rag_backend /bin/bash -c "cd /home/user/workspace && python3 -u server.py"
    else
        docker exec -i tdx_rag_backend /bin/bash -c "gunicorn rest_api.application:app -b 0.0.0.0:80 -k uvicorn.workers.UvicornWorker --workers 1 --timeout 600"
    fi
elif [ "$db_type" == 'es' ]; then
    if docker ps -a | grep -q "tdx_rag_backend"; then
        docker stop tdx_rag_backend
        docker rm tdx_rag_backend
    fi
    rm -rf backend/pipelines/faiss-index-so.*
    echo -e "\nstart backend container..."
    cp -n data/data.txt /home/encrypted_storage
    docker run -itd --privileged --network host \
       -e http_proxy=${http_proxy} \
       -e https_proxy=${https_proxy} \
       -e no_proxy=${no_proxy} \
       -e API_PROTOCOL=${API_PROTOCOL} \
       -e PIPELINE_YAML_PATH=/home/user/workspace/rag_es.yaml \
       -e ENABLE_OPTIMUM_INTEL=False \
       -e QUERY_PIPELINE_NAME=query \
       -e ONEDNN_MAX_CPU_ISA=AVX512_CORE_BF16 \
       -e PYTHONWARNINGS=ignore \
       -v /dev:/dev \
       -v /var/run/aesmd/aesm.socket:/var/run/aesmd/aesm.socket \
       -v /home/encrypted_storage:/home/rag_data/ \
       -v $(pwd)/backend/pipelines:/home/user/workspace \
       --shm-size=64gb --name tdx_rag_backend ${image_id} /bin/bash
    sleep 5

    # Add workaround for mysql 5.x
    file_path="/usr/local/lib/python3.10/dist-packages/haystack/document_stores/sql.py"
    insert_line="        self.use_windowed_query=False"
    docker exec -i tdx_rag_backend /bin/bash -c "sed -i '314i\\$insert_line' '$file_path' && cd /home/user/workspace/ && ./handle_docs.sh"
    if [ "$REMOTE_ATTESTATION" == 'grpc-ratls' ]; then
        docker exec -i tdx_rag_backend /bin/bash -c "cd /home/user/workspace && python3 -u server.py"
    else
        docker exec -i tdx_rag_backend /bin/bash -c "gunicorn rest_api.application:app -b 0.0.0.0:80 -k uvicorn.workers.UvicornWorker --workers 1 --timeout 600"
    fi
else
    echo -e "\nInvalid db_type specified."
fi
