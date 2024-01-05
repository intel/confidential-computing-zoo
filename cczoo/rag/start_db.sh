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
    echo -e "Usage: $0 DB_TYPE"
    echo -e "  DB_TYPE        mysql: MySQL, es: Elasticsearch;"
}


if [ "$#" -lt 1 ]; then
    usage
    exit 1
fi

db_type=$1
if  [ "$1" != "mysql" ] && [ "$1" != "es" ]; then
    usage
    exit 1
fi

if [ "$db_type" == 'mysql' ]; then
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
    echo "'rag' database created successfully, database service IP address:"
    docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' rag_db
elif [ "$db_type" == 'es' ]; then
    if docker ps -a | grep -q "rag_db"; then
        docker stop rag_db
        docker rm rag_db
    fi
    echo -e "\nstart database container..."
    docker run -it --name rag_db  --network host  --shm-size=8gb -e "discovery.type=single-node" \
        -v $(pwd)/dataset:/usr/share/elasticsearch/data \
        -e ES_JAVA_OPTS="-Xmx8g -Xms8g" elasticsearch:7.9.2
    echo "'rag' database created successfully, database service IP address:"
    docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' rag_db
else
    echo -e "\nInvalid db type specified."
fi
