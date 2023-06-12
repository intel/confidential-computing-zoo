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
set -ex

if [ "$ENABLE_VFS" == "on" ]; then
    cd /luks_tools
        # APP_ID=hfl-tdx-coco-app
        # RA_SERVICE_ADDRESS=ra.service.com:50051
        VFS_PATH=/luks_tools/vfs
        MOUNT_PATH=${WORKDIR}/model
        ./mount_encrypted_vfs.sh ${VFS_PATH} ${MOUNT_PATH} ${APP_ID}
    cd -
fi

TASK=$1
if [ "$TASK" == "ps0" ]; then
    ./test-tdx.sh ps0 "['localhost:60002']" "['w0.hfl-tdx-coco.service.com:30443','w1.hfl-tdx-coco.service.com:30443']"
elif [ "$TASK" == "worker0" ]; then
    ./test-tdx.sh worker0 "['ps0.hfl-tdx-coco.service.com:30443']" "['localhost:61002','w1.hfl-tdx-coco.service.com:30443']"
    sleep infinity
elif [ "$TASK" == "worker1" ]; then
    ./test-tdx.sh worker1 "['ps0.hfl-tdx-coco.service.com:30443']" "['w0.hfl-tdx-coco.service.com:30443','localhost:61003']"
    sleep infinity
fi
