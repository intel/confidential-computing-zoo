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
#!/bin/bash

SERVICE_NAME="${1:-}"

[ "$2" == "ra" ] && REMOTE_ATTESTATION="grpc-ratls"

function show_help {
    echo "Usage: ./script.sh SERVICE_NAME [ra]"
    echo ""
    echo "Arguments:"
    echo "  SERVICE_NAME  : Name of the service (db: Mysql, es: ElasticSearch, backend, backend_es, frontend)"
    echo "  ra            : Enable remote attestation (optional)"
    exit 1
}

if [ -z "$SERVICE_NAME" ]; then
    echo -e "\nPlease specify the service name."
    show_help
    exit 1
fi

if [ "$SERVICE_NAME" == 'db' ]; then
    while [ "`docker ps -a |grep rag_db`" != "" ]
        do
            echo "Try to delete rag_db..."
            docker rm -f rag_db || true
            sleep 5s
    done
    echo -e "\nstart database container..."
    docker run -d --name rag_db -p 3306:3306 -e MYSQL_ROOT_PASSWORD=123456 mysql:latest
    while [ "`docker logs rag_db 2>&1 |grep 'port: 3306  MySQL'`" = "" ]
        do
            echo "Waiting for MySQL to start..."
            sleep 5s
    done
    docker exec -it rag_db mysql -uroot -p123456 -h 127.0.0.1 -e "CREATE DATABASE rag CHARACTER SET UTF8mb3 COLLATE utf8_general_ci;"
    echo "The MySQL container and the 'rag' database created successfully."
elif [ "$SERVICE_NAME" == 'es' ]; then
    if docker ps -a | grep -q "rag_db"; then
        docker stop rag_db
        docker rm rag_db
    fi
    echo -e "\nstart database container..."
    docker run -it --name rag_db  --network host  --shm-size=8gb -e "discovery.type=single-node" \
        -v $(pwd)/dataset:/usr/share/elasticsearch/data \
        -e ES_JAVA_OPTS="-Xmx8g -Xms8g" elasticsearch:7.9.2
elif [ "$SERVICE_NAME" == 'backend' ]; then
    if docker ps -a | grep -q "tdx_rag_backend"; then
        docker stop tdx_rag_backend
        docker rm tdx_rag_backend
    fi
    rm -rf backend/pipelines/faiss-index-so.*
    echo -e "\nstart backend container..."
    mv -n data/data.txt /home/encrypted_storage
    docker run -itd --privileged --network host \
       -e http_proxy=${http_proxy} \
       -e https_proxy=${https_proxy} \
       -e no_proxy=${no_proxy} \
       -e API_PROTOCOL=${API_PROTOCOL} \
       -e PIPELINE_YAML_PATH=/home/user/workspace/rag_db.yaml \
       -e ENABLE_OPTIMUM_INTEL=False \
       -e QUERY_PIPELINE_NAME=query \
       -e ONEDNN_MAX_CPU_ISA=AVX512_CORE_BF16 \
       -e PYTHONWARNINGS=ignore \
       -v /dev:/dev \
       -v /var/run/aesmd/aesm.socket:/var/run/aesmd/aesm.socket \
       -v /home/encrypted_storage:/home/rag_data/ \
       -v $(pwd)/backend/pipelines:/home/user/workspace \
       --shm-size=64gb --name tdx_rag_backend intelcczoo/tdx-rag:backend /bin/bash
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
elif [ "$SERVICE_NAME" == 'backend_es' ]; then
    if docker ps -a | grep -q "tdx_rag_backend"; then
        docker stop tdx_rag_backend
        docker rm tdx_rag_backend
    fi
    rm -rf backend/pipelines/faiss-index-so.*
    echo -e "\nstart backend container..."
    mv -n data/data.txt /home/encrypted_storage
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
       --shm-size=64gb --name tdx_rag_backend intelcczoo/tdx-rag:backend /bin/bash
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
elif [ "$SERVICE_NAME" == 'frontend' ]; then
    if docker ps -a | grep -q "tdx_rag_frontend"; then
        docker stop tdx_rag_frontend
        docker rm tdx_rag_frontend
    fi
    echo -e "\nstart frontend container..."
    docker run -itd --privileged --network host \
        -e http_proxy=${http_proxy} \
        -e https_proxy=${https_proxy} \
        -e no_proxy=${no_proxy} \
        -e API_PROTOCOL=${API_PROTOCOL} \
        -e STREAMLIT_SERVER_PORT=8502 \
        -e PYTHONWARNINGS=ignore \
        -w /home/user/workspace \
        -v /dev:/dev \
        -v /var/run/aesmd/aesm.socket:/var/run/aesmd/aesm.socket \
        -v $(pwd)/frontend/chatbot-rag:/home/user/workspace \
        --shm-size=64gb --name tdx_rag_frontend intelcczoo/tdx-rag:frontend /bin/bash
    sleep 5
    docker exec -i tdx_rag_frontend /bin/bash -c "streamlit run app.py"
else
    echo -e "\nplease specify the correct name of the service. Choose from one of the following: db, es, backend, backend_es or frontend. "
fi
