# Retrieval Augment Generation with Intel&#174; TDX
This repo contains code to build various chatbot services using the state-of-the-art large language models.

## Getting Started 

### 1. Prepare for Docker images
You can download the Docker images from `docker.io`:

```bash
docker pull intelcczoo/tdx-rag:backend
docker pull intelcczoo/tdx-rag:frontend
```

Or you can compile Docker images locally:

```bash
# clone the repo
git clone https://github.com/intel/confidential-computing-zoo.git
cd cczoo/rag
./build-images.sh
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
export HF_ENDPOINT=https://hf-mirror.com
huggingface-cli download --resume-download --local-dir-use-symlinks False meta-llama/Llama-2-7b-chat-hf --local-dir Llama-2-7b-chat-hf
huggingface-cli download --resume-download --local-dir-use-symlinks False cross-encoder/ms-marco-MiniLM-L-12-v2 --local-dir ms-marco-MiniLM-L-12-v2
huggingface-cli download --resume-download --local-dir-use-symlinks False facebook/dpr-ctx_encoder-single-nq-base --local-dir dpr-ctx_encoder-single-nq-base
huggingface-cli download --resume-download --local-dir-use-symlinks False facebook/dpr-question_encoder-single-nq-base --local-dir dpr-question_encoder-single-nq-base
```

### 4. Start the RAG service

#### start the database service container

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

#### start the backend service container

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

#### Start the frontend service container
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

