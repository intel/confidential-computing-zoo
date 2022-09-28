# Executing Confidential TF Serving with CCP

The solution uses ccp (Confidential Computing Platform) to perform confidential TF services.

## Introduction

### Prerequisites
- Ubuntu 20.04.

- Docker Engine. Docker Engine is an open source containerization technology for
  building and containerizing your applications.
  Please follow [this guide](https://docs.docker.com/engine/install/ubuntu/#install-using-the-convenience-script)
  to install Docker engine.

- TensorFlow 2.4.2.


### 1. Service Preparation

Under client machine, please download source package:

    git clone https://github.com/intelconfidential-computing-zoo.git

- 1.1 Download the Model

First, use `download_model.sh` to download the pre-trained model file. It will
generate the directory `models/resnet50-v15-fp32` in current directory:

    ```
    cd <tensorflow-serving-cluster dir>/tensorflow-serving/docker/client
    ./download_model.sh
    ```

The model file will be downloaded to `models/resnet50-v15-fp32`. 
Then use `model_graph_to_saved_model.py` to convert the pre-trained model to SavedModel:
 
    ```
    pip3 install -r requirements.txt
    
    python3 ./model_graph_to_saved_model.py \
        --import_path `pwd -P`/modelsresnet50-v15-fp32/resnet50-v15-fp32.pb \
        --export_dir `pwd -P`/modelsresnet50-v15-fp32 \ 
        --model_version 1 \
        --inputs input \
        --outputs predict
    ```

- 1.2 Create the SSL/TLS certificate

We choose gRPC SSL/TLS and create the SSL/TLS Keys and certificates by setting
TensorFlow Serving domain name to establish a communication link between client
and TensorFlow Serving.

one-way SSL/TLS authentication(client verifies server):

    ```
    service_domain_name=grpc.tf-serving.service.com
    ./generate_oneway_ssl_config.sh ${service_domain_name}
    ```

`generate_oneway_ssl_config.sh` will generate the directory 
`ssl_configure` which includes `server/*.pem` and `ssl.cfg`.
`server/cert.pem` will be used by the remote client and `ssl.cfg` 
will be used by TensorFlow Serving.

two-way SSL/TLS authentication(server and client verify each other):

    ```
    service_domain_name=grpc.tf-serving.service.com
    client_domain_name=client.tf-serving.service.com
    ./generate_twoway_ssl_config.sh ${service_domain_name} {client_domain_name}
    ```

`generate_twoway_ssl_config.sh` will generate the directory 
`ssl_configure` which includes `server/*.pem`, `client/*.pem`, 
`ca_*.pem` and `ssl.cfg`.
`client/*.pem` and `ca_cert.pem` will be used by the remote client 
and `ssl.cfg` will be used by TensorFlow Serving.

- 1.3 Create encrypted model file

Use the `gramine-sgx-pf-crypt` tool to encrypt the model file command as follow:

    ```
    mkdir -p plaintext

    mv models/resnet50-v15-fp32/1/saved_model.pb plaintext

    mkdir -p /models/resnet50-v15-fp32/1
    LD_LIBRARY_PATH=./libs ./gramine-sgx-pf-crypt encrypt -w files/wrap-key -i      plaintext/saved_model.pb -o  /models/resnet50-v15-fp32/1/saved_model.pb
    mv /models/resnet50-v15-fp32/1/saved_model.pb  models/resnet50-v15-fp32/1
    rm -rf /models/resnet50-v15-fp32/1
    ```
  
For more information about `gramine-sgx-pf-crypt`, please refer to [pf_crypt](https://github.com/gramineproject/gramine/tree/master/Pal/src/host/Linux-SGX/tools/pf_crypt)

- 1.4 Start Secret Provision Service

Build and run the secret provisioning service container.For cloud deployments:

    ```
    cd <tensorflow-serving-cluster dir>/tensorflow-serving/docker/secret_prov
    ./build_secret_prov_image.sh
    ./run_secret_prov.sh -i <secret_prov_service_image_id> -a pccs.service.com:<ip_addr>
    ```

*Note*:
   1. `ip_addr` is the host machine where your PCCS service is installed.
   2. `secret provision service` will start port `4433` and monitor request. Under public cloud instance, please make sure the port `4433` is enabled to access.


### 2. Run TensorFlow Serving w/ Gramine in SGX-enabled machine

Under SGX-enabled machine, please download source package:

- 2.1 Preparation

    Recall that we've created encrypted model and TLS certificate in client machine,
    we need to copy them to this machine.
    For example:

    ```
    cd <tensorflow-serving-cluster dir>/tensorflow-serving/docker/tf_serving_ccp
    cp ../client/models .
    cp ../client/ssl_configure .
    ```

- 2.2 Prepare the tf_serving application and package it as a confidential image using ccp

    ```
    image_tag=tf_serving:latest
    docker_file=tf_serving.dockerfile

    ./build_ccp_tf_serving_image.sh  ${image_tag} ${docker_file} <app_name> tensorflow_model_server.toml <secret-id> <secret-key> <capp-id>
    ```

*Note*:
   1. `app_name` is the application name that the user applies for on Tencent Cloud.
   2. Users can also obtain `secret-id` `secret-key` `capp-id` on Tencent Cloud.For details, please refer to [the link](https://cloud.tencent.com/document/product/1542).


- 2.3 Start the sec_tf_serving application

    ```
    ./run_ccp_tf_serving.sh  -i <sec_tf_serving_image_id> -p 8500-8501 -a attestation.service.com:<secret_prov_service_machine_ip>
     ```

Now, the TensorFlow Serving is running in SGX and waiting for remote requests.

![](https://raw.githubusercontent.com/pengyuabc/confidential-computing-zoo/0f573059ee42d813ca161bbf586679fb3e834f03/documents/readthedoc/docs/source/Solutions/tensorflow-serving-cluster/img/TF_Serving.svg)

### 3.Remote Inference Request

In this section, the files in the `ssl_configure` directory will be reused.

- 3.1 Build Client Docker Image
Build the Client container:

    ```
    cd <tensorflow-serving-cluster dir>/tensorflow-serving/docker/client
    docker build -f client.dockerfile . -t client:latest
    ```
    Run the Client container:

    ```
    docker run -it --add-host="${service_domain_name}:<tf_serving_service_ip_addr>" tf_serving_client:latest bash
    ```

- 3.2 Send remote inference request

Send the remote inference request (with a dummy image) to demonstrate a single TensorFlow serving node with remote attestation:

   one-way SSL/TLS authentication:

    ```
    cd /client
    python3 ./resnet_client_grpc.py -batch 1 -cnum 1 -loop 50 -url {service_domain_name}:8500 -crt `pwd -P`/ssl_configure/server/cert.pem
    ```

   two-way SSL/TLS authentication:

    ```
    cd /client
    python3 ./resnet_client_grpc.py -batch 1 -cnum 1 -loop 50 -url grpctf-serving.service.com:8500 -ca `pwd -P`/ssl_configure/ca_cert.pem -crt`pwd -P`/ssl_configure/client/cert.pem -key `pwd -P`/ssl_configure/clientkey.pem
    ```
The inference result is printed in the terminal window.


