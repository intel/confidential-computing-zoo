# Retrieval Augment Generation with Intel&#174; TDX
This repo contains code to build various chatbot services using the state-of-the-art large language models.

## Getting Started 

### 1. Download CCZoo Source

```bash
git clone https://github.com/intel/confidential-computing-zoo.git
cczoo_base_dir=$PWD/confidential-computing-zoo
```

### 2. Prepare Docker images

Build the container images for the backend and frontend services:

```bash
cd ${cczoo_base_dir}/cczoo/rag
./build-images.sh default
```

Optionally, download the container images from `docker.io`:

```bash
docker pull intelcczoo/tdx-rag:backend
docker pull intelcczoo/tdx-rag:frontend
```

### 3. Setup Encrypted Storage
If encrypted storage has previously been setup, mount the encrypted storage, replacing `<loop device>` with the loop device name previously associated with the encrypted storage (for example, `/dev/loop0`):
```shell
losetup <loop device> /home/vfs
./mount_encrypted_vfs.sh <loop_device>
```

Otherwise, create a LUKS encrypted volume for the model files. When prompted for confirmation, type `YES` (in all uppercase) and enter a passphrase at the prompt which will be used to decrypt the volume. Take note of the loop device name as displayed in the output from `create_encrypted_vfs.sh`.

```shell
cd ${cczoo_base_dir}/cczoo/rag/luks_tools
yum install -y cryptsetup
VFS_SIZE=30G
VIRTUAL_FS=/home/vfs
./create_encrypted_vfs.sh ${VFS_SIZE} ${VIRTUAL_FS}
```

Replace `<loop device>` with the loop device name provided by `create_encrypted_vfs.sh` (for example, `/dev/loop0`).

```shell
export LOOP_DEVICE=<loop device>
```

Format the block device as ext4. Enter the passphrase when prompted to decrypt and mount the volume.

```shell
mkdir /home/encrypted_storage
./mount_encrypted_vfs.sh ${LOOP_DEVICE} format
```

### 4. Download Backend Models

By default, the following models are used:
- `Llama-2-7b-chat-hf` is used for the backend LLM
- `ms-marco-MiniLM-L-12-v2` is used for the sorting model
- `dpr-ctx_encoder-single-nq-base` and `dpr-question_encoder-single-nq-base` are used as encoder models

The sample content in `${cczoo_base_dir}/cczoo/rag/data/data.txt` is used as document data.

Visit https://huggingface.co/meta-llama/Llama-2-7b-chat-hf and follow the instructions on the page to request access to the Llama-2-7b-chat-hf model. The instructions include requesting access from the Meta website, and then returning to the Hugging Face website to complete the `Access Llama 2 on Hugging Face` form.

Download the models from the Hugging Face mirror, replacing `<HF_ACCESS_TOKEN>` with your Hugging Face access token:

```shell
cd /home/encrypted_storage
pip install -U huggingface_hub
export HF_ENDPOINT=https://hf-mirror.com
huggingface-cli download --resume-download --local-dir-use-symlinks False meta-llama/Llama-2-7b-chat-hf --local-dir Llama-2-7b-chat-hf --token <HF_ACCESS_TOKEN>
huggingface-cli download --resume-download --local-dir-use-symlinks False cross-encoder/ms-marco-MiniLM-L-12-v2 --local-dir ms-marco-MiniLM-L-12-v2
huggingface-cli download --resume-download --local-dir-use-symlinks False facebook/dpr-ctx_encoder-single-nq-base --local-dir dpr-ctx_encoder-single-nq-base
huggingface-cli download --resume-download --local-dir-use-symlinks False facebook/dpr-question_encoder-single-nq-base --local-dir dpr-question_encoder-single-nq-base
```

### 5. Start the Database Service Container

To use MySQL, replace `DB_TYPE` with `mysql`. To use Elasticsearch, replace `DB_TYPE` with `es`.

```bash
cd ${cczoo_base_dir}/cczoo/rag
./start_db.sh <DB_TYPE>
```

Wait for the database service startup to complete, indicated by the following log message:
```bash
'rag' database created successfully, database service IP address:
X.X.X.X
```

To get the database container's IP address to be used to setup the backend service container in a later step:
```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' rag_db
```

### 6. Start the Backend Service Container

Start the backend service container.
Replace `IMAGE_ID` with the image ID of the backend service container image.
Replace `DB_TYPE` with the database type started in the previous step - `mysql` for MySQL, `es` for Elasticsearch.
Replace `RA` with `0` to disable remote attestation, `1` to enable remote attestation.

```bash
cd ${cczoo_base_dir}/cczoo/rag
./start_backend.sh <IMAGE_ID> <DB_TYPE> <RA>
```

When prompted, enter the database container's IP address, the database username (default `root`), and the database password (default `123456`).

Wait for the backend service startup to complete, indicated by the following log message:
```bash
[INFO] Application startup complete.
```

During the execution of the script, the content in `data.txt` will be divided and stored in the database.

If you enable remote attestation, please modify the `dynamic_config.json` file in the frontend service and backend service containers and fill in the correct values.

You can obtain the hash values of the fields to be verified in the current container environment by executing `/usr/bin/tdx_report_parser`.

### 7. Optionally Add Data To the Dataset
If you used MySQL, from the backend service container, edit data in `/home/rag_data/data.txt`.

If you used Elasticsearch, from the backend service container, edit data in `/home/rag_data/data.json` and then execute the following command:

```bash
python3 generate_db.py
```

### 8. Start the Frontend Service Container

Start the frontend service container.
Replace `IMAGE_ID` with the image ID of the frontend service container image.

```bash
cd ${cczoo_base_dir}/cczoo/rag
./start_frontend.sh <IMAGE_ID>
```

You should see messages similar to the following if the frontend service container is up:

```txt
  You can now view your Streamlit app in your browser.

  Network URL: http://10.165.9.166:8502
  External URL: http://<user_tdx_instance_ip>:8502
```

### 9. Network Configuration

Configure port forwarding between the host and TD guest:

```bash
ssh -N -R <host_ip>:<host_port>:<guest_ip>:<guest_port> <host_user>@<host_server> -o TCPKeepAlive=yes
```

### 10. Test RAG Chatbot Demo

From a browser, access the RAG Chatbot Demo at `http://<frontend_ip>:<frontend_port>` and ask the chatbot questions.

For more information about the RAG framework (customizations, known issues, etc.), please refer to [Haystack](https://github.com/deepset-ai/haystack/tree/main).

### 11. Cleaning Up

To clean up after this demo: Stop and remove the database, backend, and frontend containers. Remove the FAISS files. Unmount the encrpyted storage.

```bash
docker stop tdx_rag_frontend tdx_rag_backend rag_db
docker rm tdx_rag_frontend tdx_rag_backend rag_db
rm /home/encrypted_storage/faiss-index-so.faiss /home/encrypted_storage/faiss-index-so.json
cd ${cczoo_base_dir}/cczoo/rag/luks_tools
./unmount_encrypted_vfs.sh
```
