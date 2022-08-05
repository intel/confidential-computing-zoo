===============================
TensorFlow Serving Cluster PPML 
===============================

This solution presents a framework for developing a PPML (Privacy-Preserving
Machine Learning) solution - `TensorFlow Serving <https://www.tensorflow.org/tfx/guide/serving>`__
cluster with Intel SGX and Gramine.

Introduction
------------

Simply running a TensorFlow Serving system inside Gramine is not enough for a
safe & secure end-user experience. Thus, there is a need to build a complete
secure inference flow. This paper will present TensorFlow Serving with Intel
SGX and Gramine and will provide end-to-end protection (from client to servers)
and integrate various security ingredients such as the load balancer (Nginx
Ingress) and elastic scheduler (Kubernetes). Please refer to `What is Kubernetes
<https://www.redhat.com/en/topics/containers/what-is-kubernetes>`__ for more
details.

.. image:: ./img/NGINX-Ingress-Controller.svg
   :target: ./img/NGINX-Ingress-Controller.svg
   :scale: 80 %
   :alt: Figure: Nginx Ingress controller

In this solution, we focus on:

- AI Service - TensorFlow Serving, a flexible, high-performance serving system
  for machine learning models.
- Model protection - protecting the confidentiality and integrity of the model
  when the inference takes place on an untrusted platform such as a public cloud
  virtual machine.
- Data protection - establishing a secure communication link from end-user to
  TensorFlow Serving when the user doesn’t trust the remote platform where the
  TensorFlow Serving system is executing.
- Platform Integrity - providing a way for Intel SGX platform to attest itself
  to the remote user, so that she can gain trust in the remote SGX platform.
- Elasticity - providing the Kubernetes service for automating deployment,
  scaling, and management of containerized TensorFlow Serving so that the cloud
  providers can setup the environment easily. We use Nginx for automatic load
  balancing.

The goal of this solution is to show how these applications - TensorFlow Serving
and Kubernetes - can run in an untrusted environment (like a public cloud),
automating deployment while still ensuring the confidentiality and integrity of
sensitive input data and the model. To this end, we use Intel SGX enclaves to
isolate TensorFlow Serving's execution to protect data confidentiality and
integrity, and to provide a cryptographic proof that the program is correctly
initialized and running on legitimate hardware with the latest patches. We also
use LibOS Gramine to simplify the task of porting TensorFlow Serving to SGX, without
any changes.

.. image:: ./img/Gramine_TF_Serving_Flow.svg
   :target: ./img/Gramine_TF_Serving_Flow.svg
   :alt: Figure: TensorFlow Serving Flow

In this tutorial, we use three machines: client trusted machine, it can be a non-SGX
platform or an SGX platform; SGX-enabled machine, treated as untrusted machine;
remote client machine. In this solution, you can also deploy this solution in one SGX-enabled machine
with below steps.

Here we will show the complete workflow for using Kubernetes to manage the
TensorFlow Serving running inside an SGX enclave with Gramine and its features
of Secret Provisioning and Protected Files.
We rely on the new ECDSA/DCAP remote attestation scheme developed by Intel for
untrusted cloud environments.

To run the TensorFlow Serving application on a particular SGX platform, the owner
of the SGX platform must retrieve the corresponding SGX certificate from the Intel
Provisioning Certification Service, along with Certificate Revocation Lists (CRLs)
and other SGX-identifying information **①**. Typically, this is a part of provisioning
the SGX platform in a cloud or a data center environment, and the end user can
access it as a service (in other words, the end user doesn’t need to deal with
the details of this SGX platform provisioning but instead uses a simpler interface
provided by the cloud/data center vendor).

As a second preliminary step, the user must encrypt model files with her cryptographic
(wrap) key and send these protected files to the remote storage accessible from
the SGX platform **②**.

Next, the untrusted remote platform uses Kubernetes to start TensorFlow Serving
inside the SGX enclave **③**. Meanwhile, the user starts the secret provisioning
application on her own machine. The three machines establish a TLS connection using
RA-TLS **④**, the user verifies that the untrusted remote platform has a genuine
up-to-date SGX processor and that the application runs in a genuine SGX enclave
**⑤**, and finally provisions the cryptographic wrap key to this untrusted remote
platform **⑥**. Note that during build time, Gramine informs the user of the
expected measurements of the SGX application.

After the cryptographic wrap key is provisioned, the untrusted remote platform may
start executing the application. Gramine uses Protected FS to transparently
decrypt the model files using the provisioned key when the TensorFlow Serving
application starts **⑦**. TensorFlow Serving then proceeds with execution on
plaintext files **⑧**. The client and the TensorFlow Serving will establish a
TLS connection using gRPC TLS with the key and certificate generated by the
client **⑨**. The Nginx load balancer will monitor the requests from the client
**⑩**, and will forward external requests to TensorFlow Serving **⑪**.
When TensorFlow Serving completes the inference, it will send back the result to
the client through gRPC TLS **⑫**.

Prerequisites
-------------

- Ubuntu 18.04. This solution should work on other Linux distributions as well,
  but for simplicity we provide the steps for Ubuntu 18.04 only.

- Docker Engine. Docker Engine is an open source containerization technology for
  building and containerizing your applications. In this tutorial, applications,
  like Gramine, TensorFlow Serving, secret provisioning, will be built in Docker
  images. Then Kubernetes will manage these Docker images.
  Please follow `this guide <https://docs.docker.com/engine/install/ubuntu/#install-using-the-convenience-script>`__
  to install Docker engine.

- TensorFlow Serving. `TensorFlow Serving <https://www.TensorFlow.org/tfx/guide/serving>`__
  is a flexible, high-performance serving system for machine learning models,

- Kubernetes. `Kubernetes <https://kubernetes.io/docs/concepts/overview/what-is-kubernetes/>`__
  is an open-source system for automating deployment, scaling, and management of
  containerized applications. In this tutorial, we will provide a script (``install_kubernetes.sh``)
  to install Kubernetes in your machine.

- Intel SGX Driver and SDK/PSW. You need a machine that supports Intel SGX and
  FLC/DCAP. Please follow `this guide <https://download.01.org/intel-sgx/latest/linux-latest/docs/Intel_SGX_Installation_Guide_Linux_2.10_Open_Source.pdf>`__
  to install the Intel SGX driver and SDK/PSW on the machine/VM. Make sure to install the driver
  with ECDSA/DCAP attestation.
  For deployments on Microsoft Azure, a script is provided to install general dependencies, Intel SGX DCAP dependencies, and the Azure DCAP Client. To run this script::

   cd <tensorflow-serving-cluster dir>/tensorflow-serving
   sudo ./setup_azure_vm.sh

  After Intel SGX DCAP is setup, verify the Intel Architectural Enclave Service Manager is active (running)::
  
   sudo systemctl status aesmd
      
- Gramine. Follow `Quick Start <https://gramine.readthedocs.io/en/latest/quickstart.html>`__
  to learn more about it.

- TensorFlow Serving cluster scripts package. You can download the source package
  ``tensorflow-serving-cluster``::

   git clone https://github.com/intel/confidential-computing-zoo.git

We will start with the TensorFlow Serving service running in a container without the use of Kubernetes.
The TensorFlow Serving service provides confidentiality of the model file using encryption (handled by Gramine) and remote attestation from a secret provisioning server (run from a separate container).

Then we will use Kubernetes to provide automated deployment, scaling
and management of the containerized TensorFlow Serving application.

Executing Confidential TF Serving without Kubernetes
----------------------------------------------------

1. Client Preparation
~~~~~~~~~~~~~~~~~~~~~
Under client machine, please download source package::

   git clone https://github.com/intel/confidential-computing-zoo.git

1.1 Download the Model
^^^^^^^^^^^^^^^^^^^^^^
We use ResNet50 model with FP32 precision for TensorFlow Serving to the inference.
First, use ``download_model.sh`` to download the pre-trained model file. It will
generate the directory ``models/resnet50-v15-fp32`` in current directory::

   cd <tensorflow-serving-cluster dir>/tensorflow-serving/docker/client
   ./download_model.sh

The model file will be downloaded to ``models/resnet50-v15-fp32``. 
Then use ``model_graph_to_saved_model.py`` to convert the pre-trained model to SavedModel::

   pip3 install -r requirements.txt
   python3 ./model_graph_to_saved_model.py --import_path `pwd -P`/models/resnet50-v15-fp32/resnet50-v15-fp32.pb --export_dir  `pwd -P`/models/resnet50-v15-fp32 --model_version 1 --inputs input --outputs  predict

``Note:`` ``model_graph_to_saved_model.py`` has dependencies on tensorflow, please
install tensorflow.

The converted model file will be under::

   models/resnet50-v15-fp32/1/saved_model.pb

1.2 Create the SSL/TLS certificate
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
We choose gRPC SSL/TLS and create the SSL/TLS Keys and certificates by setting
TensorFlow Serving domain name to establish a communication link between client
and TensorFlow Serving.

For ensuring security of the data being transferred between a client and server, SSL/TLS can be implemented either one-way TLS authentication or two-way TLS authentication (mutual TLS authentication).

one-way SSL/TLS authentication(client verifies server)::

      service_domain_name=grpc.tf-serving.service.com
      ./generate_oneway_ssl_config.sh ${service_domain_name}
      tar -cvf ssl_configure.tar ssl_configure

``generate_oneway_ssl_config.sh`` will generate the directory 
``ssl_configure`` which includes ``server/*.pem`` and ``ssl.cfg``.
``server/cert.pem`` will be used by the remote client and ``ssl.cfg`` 
will be used by TensorFlow Serving.


two-way SSL/TLS authentication(server and client verify each other)::

      service_domain_name=grpc.tf-serving.service.com
      client_domain_name=client.tf-serving.service.com
      ./generate_twoway_ssl_config.sh ${service_domain_name} ${client_domain_name}
      tar -cvf ssl_configure.tar ssl_configure

``generate_twoway_ssl_config.sh`` will generate the directory 
``ssl_configure`` which includes ``server/*.pem``, ``client/*.pem``, 
``ca_*.pem`` and ``ssl.cfg``.
``client/*.pem`` and ``ca_cert.pem`` will be used by the remote client 
and ``ssl.cfg`` will be used by TensorFlow Serving.


1.3 Create encrypted model file
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Starting from Intel SGX SDK v1.9, SGX SDK provides the function of secure file
I/O operations. This function is provided by a component of the SGX SDK called
Protect File System Library, which enables safely I/O operations in the Enclave.

It guarantees below items.

- Integrity of user data. All user data are read from disk and then decrypted with
  MAC (Message Authentication Code) verified to detect any data tampering.

- Matching of file name. When opening an existing file, the metadata of the to-be-opened
  file will be checked to ensure that the name of the file when created is the
  same as the name given to the open operation.

- Confidentiality of user data. All user data is encrypted and then written to
  disk to prevent any data leakage.

For more details, please refer to `Understanding SGX Protected File System <https://www.tatetian.io/2017/01/15/understanding-sgx-protected-file-system/?spm=a2c4g.11186623.0.0.31165b783zw77C>`__.

In our solution, we use a tool named ``gramine-sgx-pf-crypt`` provided by the LibOS
Gramine for secure file I/O operations based on the SGX SDK, which can be used to
encrypt and decrypt files. In the template configuration file provided by Gramine,
the configuration option "sgx.protected_files.file_mode=file_name" is given, which
specifies the files to be protected by encryption.

When TensorFlow Serving loads the model, the path to load the model is ``models/resnet50-v15-fp32/1/saved_model.pb``,
and the encryption key is located in files/wrap-key. You can also customize the
128-bit password. According to the file path matching principle, the file path must
be consistent with the one used during encryption.

Use the ``gramine-sgx-pf-crypt`` tool to encrypt the model file command as follow::

   mkdir plaintext/
   mv models/resnet50-v15-fp32/1/saved_model.pb plaintext/
   LD_LIBRARY_PATH=./libs ./gramine-sgx-pf-crypt encrypt -w files/wrap-key -i  plaintext/saved_model.pb -o  models/resnet50-v15-fp32/1/saved_model.pb
   tar -cvf models.tar models

For more information about ``gramine-sgx-pf-crypt``, please refer to `pf_crypt <https://github.com/gramineproject/gramine/tree/master/Pal/src/host/Linux-SGX/tools/pf_crypt>`__.

1.4 Start Secret Provision Service
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
In order to deploy this service easily, we build and run this service in container.
Basically, we use ``secret_prov_server_dcap`` as the remote SGX Enclave Quote
authentication service and relies on the Quote-related authentication library
provided by SGX DCAP. The certification service will obtain Quote certification
related data from Intel PCCS, such as TCB related information and CRL information.
After successful verification of SGX Enclave Quote, the key stored in ``files/wrap-key``
will be sent to the remote application.
The remote application here is Gramine in the SGX environment.
After remote Gramine gets the key, it will decrypt the encrypted model file.

Build and run the secret provisioning service container. For deployments on Microsoft Azure::

   cd <tensorflow-serving-cluster dir>/tensorflow-serving/docker/secret_prov
   sudo AZURE=1 ./build_secret_prov_image.sh
   sudo ./run_secret_prov.sh -i secret_prov_server:latest
   
For other cloud deployments::

   cd <tensorflow-serving-cluster dir>/tensorflow-serving/docker/secret_prov
   ./build_secret_prov_image.sh
   ./run_secret_prov.sh -i secret_prov_server:latest -a pccs.service.com:ip_addr

*Note*:
   1. ``ip_addr`` is the host machine where your PCCS service is installed.
   2. ``secret provision service`` will start port ``4433`` and monitor request. Under public cloud instance, please make sure the port ``4433`` is enabled to access.
   3. Under cloud SGX environment (except for Microsoft Azure), if CSP provides their own PCCS server, please replace the PCCS URL in ``sgx_default_qcnl.conf`` with the one provided by CSP. You can start the secret provision service::
      
      ./run_secret_prov.sh -i <secret_prov_service_image_id> 

To check the secret provision service logs::

   docker ps -a
   docker logs <secret_prov_service_container_id>

Get the container's IP address, which will be used when starting the TensorFlow Serving Service in the next step::

   docker ps -a
   docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <secret_prov_service_container_id>
   

2. Run TensorFlow Serving w/ Gramine in SGX-enabled machine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Under SGX-enabled machine, please download source package::

   git clone https://github.com/intel/confidential-computing-zoo.git

2.1 Preparation
^^^^^^^^^^^^^^^
Recall that we've created encrypted model and TLS certificate in client machine,
we need to copy them to this machine.
For example::

   cd <tensorflow_serving dir>/docker/tf_serving
   scp -r client@client_ip:<tensorflow_serving dir>/docker/client/models.tar .
   scp -r client@client_ip:<tensorflow_serving dir>/docker/client/ssl_configure.tar .
   tar -xvf models.tar
   tar -xvf ssl_configure.tar

2.2 Build TensorFlow Serving Docker image
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Build the TensorFlow Serving container. For deployments on Microsoft Azure::

   cd <tensorflow-serving-cluster dir>/tensorflow-serving/docker/tf_serving
   sudo AZURE=1 ./build_gramine_tf_serving_image.sh
      
For other cloud deployments::

   cd <tensorflow-serving-cluster dir>/tensorflow-serving/docker/tf_serving
   ./build_gramine_tf_serving_image.sh

The dockerfile used is ``gramine_tf_serving.dockerfile``, which includes the following install items:

- Install basic dependencies for source code build.
- Install TensorFlow Serving.
- Install LibOS - Gramine.
- Copy files from host to built container.

The files copied from host to container include:

- Makefile. It is used to compile TensorFlow with Gramine.
- sgx_default_qcnl.conf. Please replace the PCCS url provided by CSP when under public cloud instance.
- tf_serving_entrypoint.sh. The execution script when container is launched.
- tensorflow_model_server.manifest.template. The TensorFlow Serving configuration
  template used by Gramine.

Gramine supports SGX RA-TLS function, it can be enabled by configurations in the
template.Key parameters used in current template as below::

   sgx.remote_attestation = 1
   loader.env.LD_PRELOAD = "libsecret_prov_attest.so"
   loader.env.SECRET_PROVISION_CONSTRUCTOR = "1"
   loader.env.SECRET_PROVISION_SET_PF_KEY = "1"
   loader.env.SECRET_PROVISION_CA_CHAIN_PATH ="certs/test-ca-sha256.crt"
   loader.env.SECRET_PROVISION_SERVERS ="attestation.service.com:4433" 
   sgx.trusted_files.libsecretprovattest ="file:libsecret_prov_attest.so"
   sgx.trusted_files.cachain= "file:certs/test-ca-sha256.crt"
   sgx.protected_files.model= "file:models/resnet50-v15-fp32/1/saved_model.pb"

``SECRET_PROVISION_SERVERS`` is the remote secret provision server address in client.
``attestation.service.com`` is the Domain name, ``4433`` is the port used by secret
provision server.

``SECRET_PROVISION_SET_PF_KEY`` presents if application need secret provision server sends
secret key back to it when attestation verification pass in secret provision server.

``sgx.protected_files`` shows self-defined encrypted files. Files is encrypted with key
stored in secret provision server.
For more syntax used in the manifest template, please refer to `Gramine Manifest syntax <https://github.com/gramineproject/gramine/blob/master/Documentation/manifest-syntax.rst>`__.


2.3 Execute TensorFlow Serving w/ Gramine in SGX
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Run the TensorFlow Serving container::

    cd <tensorflow_serving dir>/docker/tf_serving
    cp ssl_configure/ssl.cfg .
    ./run_gramine_tf_serving.sh -i gramine_tf_serving:latest -p 8500-8501 -m resnet50-v15-fp32 -s ssl.cfg -a attestation.service.com:<secret_prov_service_container_ip_addr>
   
*Note*:
   1. ``8500-8501`` are the ports created on (bound to) the host, you can change them if you need.
   2. ``secret_prov_service_container_ip_addr`` is the ip address of the container running the secret provisioning service.

Check the TensorFlow Serving container logs::

   docker ps -a
   docker logs <tf_serving_container_id>

Now, the TensorFlow Serving is running in SGX and waiting for remote requests.

.. image:: ./img/TF_Serving.svg
   :target: ./img/TF_Serving.svg
   :scale: 50 %
   :alt: Figure: TensorFlow Serving

Get the container's IP address, which will be used when starting the Client container in the next step::

   docker ps -a
   docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <tf_serving_container_id>



3. Remote Inference Request
~~~~~~~~~~~~~~~~~
In this section, the files in the `ssl_configure` directory will be reused.

3.1 Build Client Docker Image 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Build the Client container::

    cd <tensorflow_serving dir>/docker/client
    docker build -f client.dockerfile . -t client:latest

Run the Client container::

    sudo docker run -it --add-host="grpc.tf-serving.service.com:<tf_serving_service_ip_addr>" client:latest bash


3.2 Send remote inference request
^^^^^^^^^^^^^^^^^^^^^^^
Send the remote inference request (with a dummy image) to demonstrate a single TensorFlow serving node with remote attestation::

   one-way SSL/TLS authentication::

      cd /client
      python3 ./resnet_client_grpc.py -batch 1 -cnum 1 -loop 50 -url grpc.tf-serving.service.com:8500 -crt `pwd -P`/ssl_configure/server/cert.pem

   two-way SSL/TLS authentication::

      cd /client
      python3 ./resnet_client_grpc.py -batch 1 -cnum 1 -loop 50 -url grpc.tf-serving.service.com:8500 -ca `pwd -P`/ssl_configure/ca_cert.pem -crt `pwd -P`/ssl_configure/client/cert.pem -key `pwd -P`/ssl_configure/client/key.pem

The inference result is printed in the terminal window.


Executing Confidential TF Serving with Kubernetes
--------------------------------------------------
In this section, we will setup Kubernetes on the SGX-enabled machine.
Then we will use Kubernetes to start multiple TensorFlow Serving containers.
The following sections will reuse the machine/VM Intel SGX DCAP setup and containers built from the previous sections.
Stop and remove the client and tf-serving containers. Start the secret provisioning container if it isn't running::

    sudo docker ps -a
    sudo docker stop <client_container_id> <tf_serving_container_id>
    sudo docker rm <client_container_id> <tf_serving_container_id>
    sudo docker start <secret_prov_service_container_id>

1. Setup Kubernetes
~~~~~~~~~~~~~~~~~~~
First, please make sure the system time on your machine is updated.

1.1 Install Kubernetes
^^^^^^^^^^^^^^^^^^^^^^

Refer to ``https://kubernetes.io/docs/setup/production-environment/`` or
use ``install_kubernetes.sh`` to install Kubernetes::

   cd <tensorflow-serving-cluster dir>/kubernetes
   ./install_kubernetes.sh

Create the control plane / master node and allow pods to be scheduled onto this node::

   unset http_proxy && unset https_proxy
   swapoff -a && free -m
   sudo rm /etc/containerd/config.toml
   sudo systemctl restart containerd
   kubeadm init --v=5 --node-name=master-node --pod-network-cidr=10.244.0.0/16

   mkdir -p $HOME/.kube
   sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
   sudo chown $(id -u):$(id -g) $HOME/.kube/config

   kubectl taint nodes --all node-role.kubernetes.io/control-plane-
   kubectl taint nodes --all node-role.kubernetes.io/master-

1.2 Setup Flannel in Kubernetes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Setup Flannel in Kubernetes.

Flannel is focused on networking and responsible for providing a layer 3 IPv4
network between multiple nodes in a cluster. Flannel does not control how
containers are networked to the host, only how the traffic is transported between
hosts.

Deploy the Flannel service::

   kubectl apply -f flannel/deploy.yaml

1.3 Setup Ingress-Nginx in Kubernetes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Setup Ingress-Nginx in Kubernetes.
Please refer to the Introduction part for more information about Nginx.

Deploy the Nginx service::

   kubectl apply ingress-nginx/deploy.yaml


1.4 Config Kubernetes cluster DNS
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

We need to configure the cluster DNS in Kubernetes so that all the TensorFlow
Serving pods can communicate with secret provisioning server::

   kubectl edit configmap -n kube-system coredns

A config file will pop up, and we need to add the below configuration into it::

    # new added
    hosts {
           ${secret_prov_service_container_ip_addr} attestation.service.com
           fallthrough
       }
    # end
    prometheus :9153
    forward . /etc/resolv.conf {
              max_concurrent 1000
    }

``${secret_prov_service_container_ip_addr}`` is the IP address of the Secret Provisioning Service container.

1.5 Setup Docker Registry
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Setup a local Docker registry to serve the TensorFlow Serving container image to the Kubernetes cluster::

    sudo docker run -d -p 5000:5000 --restart=always --name registry registry:2
    sudo docker tag gramine_tf_serving:latest localhost:5000/gramine_tf_serving
    sudo docker push localhost:5000/gramine_tf_serving

   
1.6 Start TensorFlow Serving Deployment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Let's take a look at the configuration for the elastic deployment of
TensorFlow Serving under the directory::

   <tensorflow-serving-cluster dir>/tensorflow-serving/kubernetes

There are two Yaml files: ``deploy.yaml`` and ``ingress.yaml``.

You can look at `this <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#deploymentspec-v1-apps>`__
for more information about Yaml.

Customize the ``deploy.yaml`` TensorFlow Serving container information, if needed::

    containers:
    - name: gramine-tf-serving-container
      image: localhost:5000/gramine_tf_serving
      imagePullPolicy: IfNotPresent

Customize the ``deploy.yaml`` model and ssl host paths::

      - name: model-path
        hostPath:
          path: <Your confidential-computing-zoo path>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/tf_serving/models
      - name: ssl-path
        hostPath:
          path: <Your confidential-computing-zoo path>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/tf_serving/ssl_configure/ssl.cfg


``ingress.yaml`` mainly configures the networking options.
Use the default domain name, or use a custom domain name::

    rules:
      - host: grpc.tf-serving.service.com

Apply the two yaml files::

    kubectl apply -f gramine-tf-serving/deploy.yaml
    kubectl apply -f gramine-tf-serving/ingress.yaml

1.7 Verify TensorFlow Serving Deployment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Verify one pod of the TensorFlow Serving container is running and that the service is ready (look for log "Entering the event loop")::

    $ kubectl get pods -n gramine-tf-serving
    NAME                                             READY   STATUS    RESTARTS   AGE                         
    gramine-tf-serving-deployment-548f95f46d-rx4w2   1/1     Running   0          5m1s
    $ kubectl log -n gramine-tf-serving gramine-tf-serving-deployment-548f95f46d-rx4w2

Check pod info if the pod is not running::

    $ kubectl describe pod -n gramine-tf-serving gramine-tf-serving-deployment-548f95f46d-rx4w2
    
Check the coredns setup if the TensorFlow Serving service is not ready. This can be caused when the TensorFlow Serving service is unable to obtain the wrap-key (used to decrypt the model file) from the secret provisioning container.


1.8 Scale the TensorFlow Serving Service
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Scale the TensorFlow Serving service to two replicas::

   $ kubectl scale -n gramine-tf-serving deployment.apps/gramine-tf-serving-deployment --replicas 2

This starts two TensorFlow Serving containers, each with its own TensorFlow Serving service running on its own SGX enclave.

Verify that two pods are now running. Also verify that the second pod of the TensorFlow Serving container is running and that the service is ready (look for log "Entering the event loop")::

    $ kubectl get pods -n gramine-tf-serving
    NAME                                             READY   STATUS    RESTARTS   AGE
    gramine-tf-serving-deployment-548f95f46d-q4bcg   1/1     Running   0          2m28s
    gramine-tf-serving-deployment-548f95f46d-rx4w2   1/1     Running   0          4m10s
    $ kubectl log -n gramine-tf-serving gramine-tf-serving-deployment-548f95f46d-q4bcg

These TensorFlow Serving containers perform remote attestation with the Secret Provisioning service to get the secret key. With the secret key, 
the TensorFlow Serving containers can decrypted the model file.

3.2 Send remote inference request
^^^^^^^^^^^^^^^^^^^^^^^
Send the remote inference request (with a dummy image) to demonstrate an elastic TensorFlow Serving deployment through Kubernetes.

First, get the CLUSTER-IP of the load balanced TensorFlow Serving service::

    $ kubectl get service -n gramine-tf-serving                             
    NAME                         TYPE       CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
    gramine-tf-serving-service   NodePort   10.108.27.161   <none>        8500:30500/TCP   13m

Run the Client container using the load balanced TensorFlow Serving IP address::

    $ sudo docker run -it --add-host="grpc.tf-serving.service.com:<tf_serving_CLUSTER-IP>" client:latest bash
    
For one-way SSL/TLS authentication::

    $ cd /client
    $ python3 ./resnet_client_grpc.py -batch 1 -cnum 1 -loop 50 -url grpc.tf-serving.service.com:8500 -crt `pwd -P`/ssl_configure/server/cert.pem

For wo-way SSL/TLS authentication::

    $ cd /client
    $ python3 ./resnet_client_grpc.py -batch 1 -cnum 1 -loop 50 -url grpc.tf-serving.service.com:8500 -ca `pwd -P`/ssl_configure/ca_cert.pem -crt `pwd -P`/ssl_configure/client/cert.pem -key `pwd -P`/ssl_configure/client/key.pem

The inference result is printed in the terminal window.


2. Cleaning Up
~~~~~~~~~~~~~~

To stop the TensorFlow Serving deployment::

   $ cd <tensorflow-serving-cluster dir>/<tensorflow-serving>/docker/tf_serving/kubernetes
   $ kubectl delete -f deploy.yaml


Cloud Deployment
----------------

``Notice:``
   1. Except for Microsoft Azure, please replace server link in `sgx_default_qcnl.conf` included in the dockerfile with public cloud PCCS server address.
   2. If you choose to run this solution in separated public cloud instance, please make sure the ports ``4433`` and ``8500-8501`` are enabled to access.


1. Alibaba Cloud
~~~~~~~~~~~~~~~~

`Aliyun ECS <https://help.aliyun.com/product/25365.html>`__ (Elastic Compute Service) is
an IaaS (Infrastructure as a Service) level cloud computing service provided by Alibaba
Cloud. It builds security-enhanced instance families ( `g7t, c7t, r7t <https://help.aliyun.com/document_detail/207734.html>`__ ) based on Intel® SGX
technology to provide a trusted and confidential environment with a higher security level.

The configuration of the ECS instance as blow:

- Instance Type  : `g7t <https://help.aliyun.com/document_detail/108490.htm#section-bew-6jv-c0k>`__.
- Instance Kernel: 4.19.91-24
- Instance OS    : Alibaba Cloud Linux 2.1903
- Instance Encrypted Memory: 32G
- Instance vCPU  : 16
- Instance SGX PCCS Server: `sgx-dcap-server.cn-hangzhou.aliyuncs.com <https://help.aliyun.com/document_detail/208095.html>`__

This solution is also published in Ali Cloud as the best practice - `Deploy TensorFlow Serving in Aliyun ECS security-enhanced instance <https://help.aliyun.com/document_detail/342755.html>`__.


2. Tencent Cloud
~~~~~~~~~~~~~~~~

Tencent Cloud Virtual Machine (CVM) provides one instance named `M6ce <https://cloud.tencent.com/document/product/213/11518#M6ce>`__,
which supports Intel® SGX encrypted computing technology.

The configuration of the M6ce instance as blow:

- Instance Type  : `M6ce.4XLARGE128 <https://cloud.tencent.com/document/product/213/11518#M6ce>`__.
- Instance Kernel: 5.4.119-19-0009.1
- Instance OS    : TencentOS Server 3.1
- Instance Encrypted Memory: 64G
- Instance vCPU  : 16
- Instance SGX PCCS Server: `sgx-dcap-server-tc.sh.tencent.cn <https://cloud.tencent.com/document/product/213/63353>`__


3. ByteDance Cloud
~~~~~~~~~~~~~~~~~~

ByteDance Cloud (Volcengine SGX Instances) provides the instance named `ebmg2t`,
which supports Intel® SGX encrypted computing technology.

The configuration of the ebmg2t instance as blow:

- Instance Type  : `ecs.ebmg2t.32xlarge`.
- Instance Kernel: kernel-5.15
- Instance OS    : ubuntu-20.04
- Instance Encrypted Memory: 256G
- Instance vCPU  : 16
- Instance SGX PCCS Server: `sgx-dcap-server.bytedance.com`.


4. Microsoft Azure
~~~~~~~~~~~~~~~~~~

Microsoft Azure `DCsv3-series <https://docs.microsoft.com/en-us/azure/virtual-machines/dcv3-series>`__ instances support Intel® SGX encrypted computing technology.

The following is the configuration of the DCsv3-series instance used:

- Instance Type  : Standard_DC16s_v3
- Instance Kernel: 5.13.0-1031-azure
- Instance OS    : Ubuntu Server 20.04 LTS - Gen2
- Instance Encrypted Memory: 64G
- Instance vCPU  : 16
