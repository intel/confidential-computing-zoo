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
LLM_PATH="${2:-/home/data/Llama-2-7b-chat-hf/}"
RERANKER_PATH="${3:-/home/data/ms-marco-MiniLM-L-12-v2/}"

[ "$4" == "ra" ] && REMOTE_ATTESTATION="grpc-ratls"

function show_help {
    echo "Usage: ./script.sh SERVICE_NAME [LLM_PATH] [RERANKER_PATH] [ra]"
    echo ""
    echo "Arguments:"
    echo "  SERVICE_NAME  : Name of the service (required)"
    echo "  LLM_PATH      : Path to LLM (default: /home/data/Llama-2-7b-chat-hf/)"
    echo "  RERANKER_PATH : Path to reranker (default: /home/data/ms-marco-MiniLM-L-12-v2/)"
    echo "  ra            : Enable remote attestation (optional)"
    exit 1
}

if [ -z "$SERVICE_NAME" ]; then
    echo -e "\nPlease specify the service name."
    show_help
    exit 1
fi

if [ "$SERVICE_NAME" == 'db' ]; then
    if docker ps -a | grep -q "rag_db"; then
        docker stop rag_db
        docker rm rag_db
    fi
    echo -e "\nstart database container..."
    docker run -it --name rag_db  --network host  --shm-size=8gb -e "discovery.type=single-node" \
        -v $(pwd)/dataset:/usr/share/elasticsearch/data \
        -e ES_JAVA_OPTS="-Xmx8g -Xms8g" elasticsearch:7.9.2
elif [ "$SERVICE_NAME" == 'llm' ]; then
    if docker ps -a | grep -q "rag_llm"; then
        docker stop rag_llm
        docker rm rag_llm
    fi
    echo -e "\nstart backend container..."
    docker run -itd --privileged --network host \
       -e http_proxy=${http_proxy} \
       -e https_proxy=${https_proxy} \
       -e no_proxy=${no_proxy} \
       -e API_PROTOCOL=${API_PROTOCOL} \
       -e PIPELINE_YAML_PATH=/home/user/workspace/rag.yaml \
       -e ENABLE_OPTIMUM_INTEL=False \
       -e QUERY_PIPELINE_NAME=query \
       -e ONEDNN_MAX_CPU_ISA=AVX512_CORE_BF16 \
       -e PYTHONWARNINGS=ignore \
       -v /dev:/dev \
       -v /var/run/aesmd/aesm.socket:/var/run/aesmd/aesm.socket \
       -v ${LLM_PATH}:/home/user/Llama-2-7b-chat-hf \
       -v ${RERANKER_PATH}:/home/user/ms-marco-MiniLM-L-12-v2 \
       -v $(pwd)/backend/pipelines:/home/user/workspace \
       --shm-size=64gb --name rag_llm appliedmlwf/rag-llm:release /bin/bash
    sleep 5
    if [ "$REMOTE_ATTESTATION" == 'grpc-ratls' ]; then
        docker exec -i rag_llm /bin/bash -c "cd /home/user/workspace && python3 -u server.py"
    else
        docker exec -i rag_llm /bin/bash -c "gunicorn rest_api.application:app -b 0.0.0.0:80 -k uvicorn.workers.UvicornWorker --workers 1 --timeout 600"
    fi

elif [ "$SERVICE_NAME" == 'ui' ]; then
    if docker ps -a | grep -q "rag_ui"; then
        docker stop rag_ui
        docker rm rag_ui
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
        --shm-size=64gb --name rag_ui appliedmlwf/rag-llm:ui /bin/bash
    sleep 5
    docker exec -i rag_ui /bin/bash -c "streamlit run app.py"
else
    echo -e "\nplease specify the correct name of the service. Choose from one of the following: db, llm or ui. "
fi
