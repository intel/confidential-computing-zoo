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
    echo -e "Usage: $0 IMAGE_ID"
    echo -e "  IMAGE_ID       frontend docker image ID;"
}


if [ "$#" -lt 1 ]; then
    usage
    exit 1
fi

image_id=$1

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
    --shm-size=64gb --name tdx_rag_frontend ${image_id} /bin/bash
sleep 5
docker exec -i tdx_rag_frontend /bin/bash -c "streamlit run app.py"
