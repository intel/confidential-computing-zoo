# Retrieval Augment Generation with Intel&#174; TDX
This repo contains code to build various chatbot services using the state-of-the-art large language models.

## Getting Started 

### 1. Prepare for Docker images
You can download the Docker images from `docker.io`:

```bash
docker pull intelcczoo/tdx-dev:dcap_mvp2023ww15-ubuntu22.04-latest
docker pull intelcczoo/rag-llm:release
docker pull intelcczoo/rag-llm:ui
```

Or you can compile Docker images locally:

```bash
# clone the repo
git clone https://github.com/intel/confidential-computing-zoo.git
cd cczoo/rag
./build-images.sh
```

### 2. Prepare for your backend models
We uses `Llama-2-7b-chat-hf` as the backend LLM and `ms-marco-MiniLM-L-12-v2` as the reranker model by default. If you want to use other models, you can also refer to the steps below.

Download the `Llama-2-7b-chat-hf` model from the Hugging Face website:

```bash
git lfs install
git clone https://huggingface.co/meta-llama/Llama-2-7b-chat-hf
```

Download the `ms-marco-MiniLM-L-12-v2` model from the Hugging Face website:

```bash
git lfs install
git clone https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-12-v2
```

### 3. Start the RAG service 

#### start the database service container
```bash
./run.sh db
```

#### start the backend service container

Modify the "Store component" IP address in the `backend/pipelines/rag.yaml`.
Open a new terminal and execute the following command:

```bash
# llm_path: Path to LLM (default: /home/data/Llama-2-7b-chat-hf/)
# reranker_path: Path to reranker (default: /home/data/ms-marco-MiniLM-L-12-v2/)
# ra: Enable remote attestation (optional)
./run.sh llm <llm_path> <reranker_path> <ra>
```

If you enable remote attestation, please modify the `dynamic_config.json` file in the frontend service and backend service containers and fill in the correct values.

You can obtain the hash values of the fields to be verified in the current container environment by executing `/usr/bin/tdx_report_parser`.

#### Add data to the dataset
You can edit data in `data.json` then execute the following command in the backend service container:

```bash
python3 generate_db.py
```

#### Start the frontend service container
In another new terminal execute the following command:

```bash
./run.sh ui
```

You should see messages similar to the following if the frontend service container is up:

```txt
  You can now view your Streamlit app in your browser.

  Network URL: http://10.165.9.166:8502
  External URL: http://134.134.139.85:8502
```

#### port forwarding
In addition, you need to do a port forwarding in the TD environment. The command is as follows:

```bash
ssh -N -R <host_ip>:<host_port>:<guest_ip>:<guest_port> <host_user>@<host_server> -o TCPKeepAlive=yes
```

#### 
In your local browser, open the Network URL `http://<host_server>:<host_port>` and ask questions.
