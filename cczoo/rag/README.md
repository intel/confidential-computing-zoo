# Retrieval Augment Generation with Intel&#174; TDX
This repo contains code to build various chatbot services using the state-of-the-art large language models.

## Getting Started 

### 1. Prepare for Docker images
You can download the Docker images from `docker.io`(Use dcap 1.18 by default):

```bash
docker pull intelcczoo/tdx-rag:backend
docker pull intelcczoo/tdx-rag:frontend
```

Or you can compile Docker images locally, providing the same dcap version as the host when building the images:

```bash
# clone the repo
git clone https://github.com/intel/confidential-computing-zoo.git
cd confidential-computing-zoo/cczoo/rag
# Note: If you use the PCCS service in the public cloud, modify the `backend/configs/etc/sgx_default_qcnl.conf` file and the `frontend/chatbot-rag/ra_configs/etc/sgx_default_qcnl.conf` file before building the Docker image, and fill in the correct PCCS service configuration.
./build-images.sh --dcap-version 1.18
```

### 2. Create encrypted partition
Create an encrypted directory to store model files and document data to ensure data and privacy security.

Create a LUKS block file and bind it to the idle loop device:

```shell
cd <workdir>/confidential-computing-zoo/cczoo/rag/luks_tools
yum install -y cryptsetup
VFS_SIZE=30G
VIRTUAL_FS=/home/vfS
./create_encrypted_vfs.sh ${VFS_SIZE} ${VIRTUAL_FS}
```

According to the loop device number output by the above command (such as `/dev/loop0`), create the `LOOP_DEVICE` environment variable to bind the loop device:

```shell
export LOOP_DEVICE=<the binded loop device>
```

On first execution, the block loop device needs to be formatted as ext4:

```shell
mkdir /home/encrypted_storage
./mount_encrypted_vfs.sh ${LOOP_DEVICE} format
```

### 3. Prepare for your data and backend models

By default we use:

- The sample content in `<workdir>/confidential-computing-zoo/cczoo/rag/data/data.txt` is used as document data;

- `Llama-2-7b-chat-hf` as backend LLM;
- `ms-marco-MiniLM-L-12-v2` as a sorting model;
- `dpr-ctx_encoder-single-nq-base` and `dpr-question_encoder-single-nq-base` as encoder models.

The steps to download the required model from the Hugging Face mirror website are as follows. If you want to use other models, you can also refer to the following steps:

```shell
cd /home/encrypted_storage
pip install -U huggingface_hub
# If your server is in China, you can set this environment variable: export HF_ENDPOINT=https://hf-mirror.com
huggingface-cli download --resume-download --local-dir-use-symlinks False meta-llama/Llama-2-7b-chat-hf --local-dir Llama-2-7b-chat-hf --token <your huggingface token>
huggingface-cli download --resume-download --local-dir-use-symlinks False cross-encoder/ms-marco-MiniLM-L-12-v2 --local-dir ms-marco-MiniLM-L-12-v2
huggingface-cli download --resume-download --local-dir-use-symlinks False facebook/dpr-ctx_encoder-single-nq-base --local-dir dpr-ctx_encoder-single-nq-base
huggingface-cli download --resume-download --local-dir-use-symlinks False facebook/dpr-question_encoder-single-nq-base --local-dir dpr-question_encoder-single-nq-base
```

### 4. Run the RAG service

#### run the database service container

If you want to use MySQL as the storage:

```bash
cd <workdir>/confidential-computing-zoo/cczoo/rag
./run.sh db
```

If you want to use ElasticSearch as the storage:

```bash
cd <workdir>/confidential-computing-zoo/cczoo/rag
./run.sh es
```

#### run the backend service container

If you use MySQL as the storage:

```bash
cd <workdir>/confidential-computing-zoo/cczoo/rag
./run.sh backend
```

If you use ElasticSearch as the storage:

```bash
cd <workdir>/confidential-computing-zoo/cczoo/rag
./run.sh backend_es
```

During the execution of the script, the content in `data.txt` will be divided and stored in the database, and you need to enter the database IP address, database account, and database password according to the prompts.

Open a new terminal and execute the following command:

If you enable remote attestation, please modify the `dynamic_config.json` file in the frontend service and backend service containers and fill in the correct values.

You can obtain the hash values of the fields to be verified in the current container environment by executing `/usr/bin/tdx_report_parser`.

#### Add data to the dataset
If you use ElasticSearch as the storage, you can edit data in `data/data.json` then execute the following command in the backend service container:

```bash
python3 generate_db.py
```

If you use MySQL as the storage, you can edit data in `data/data.txt` directly.

#### Run the frontend service container
In another new terminal execute the following command:

```bash
./run.sh frontend
```

You should see messages similar to the following if the frontend service container is up:

```txt
  You can now view your Streamlit app in your browser.

  Network URL: http://10.165.9.166:8502
  External URL: http://<user_tdx_intance_ip>:8502
```

#### port forwarding
In addition, you need to do a port forwarding in the TD environment. The command is as follows:

```bash
ssh -N -R <host_ip>:<host_port>:<guest_ip>:<guest_port> <host_user>@<host_server> -o TCPKeepAlive=yes
```

In your local browser, open the Network URL `http://<host_server>:<host_port>` and ask questions.

For customized modifications and issues with the RAG framework, please refer to [Haystack](https://github.com/deepset-ai/haystack/tree/main).

#### Run RAG service with RA-TLS

If you want to run the RAG service with remote attestation, you need to modify the following steps:

**Get the verification hash value and configure**

We can get the attestation message by running for both backend and frontend containers:

```shell
docker exec -it tdx_rag_backend bash -c "cd /usr/bin && ./tdx_report_parser"
docker exec -it tdx_rag_frontend bash -c "cd /usr/bin && ./tdx_report_parser"
```

In the `frontend/chatbot-rag/dynamic_config.json` and `backend/pipelines/dynamic_config.json` files:
- Fill in the "ON" or "OFF" to config verification strategy.
- Fill in the hash value obtained through the above command into the `dynamic_config.json` file of the corresponding directory. For example, the hash value obtained from the backend should be filled in the frontend configuration file.

**Add RA configuration when running backend service container**

```shell
./run.sh backend ra <ip addr>
```
The "ra" means "remote attestation" and the subsequent IP address is the attestation server address. If the PCCS service has been configured in `backend/configs/etc/sgx_default_qcnl.conf` and `frontend/chatbot-rag/ra_configs/etc/sgx_default_qcnl.conf` files, this configuration can be ignored.

Then, enter the following message:

```shell
Enter database ip addr: <database ip addr>

Enter database username: root

Enter database password: 123456
```

It will finally print the attestation message. It means the backend server runs successfully.

**Add RA configuration when running frontend service container**

```shell
./run.sh frontend ra <ip addr>
```

The "ra" means "remote attestation" and the subsequent IP address is the attestation server address.

**Visit the Web UI and ask questions**

You can click the link generated by the frontend service to access the RAG service.

If everything goes well, you should be able to see the green security connection box at the web page, and the detailed information about remote attestation below.
