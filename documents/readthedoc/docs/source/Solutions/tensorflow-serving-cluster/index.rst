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

- Ubuntu 20.04. This solution should work on other Linux distributions as well,
  but for simplicity we provide the steps for Ubuntu 20.04 only.

- Docker Engine. Docker Engine is an open source containerization technology for
  building and containerizing your applications. In this tutorial, applications,
  like Gramine, TensorFlow Serving, secret provisioning, will be built in Docker
  images. Then Kubernetes will manage these Docker images.
  Please follow `this guide <https://docs.docker.com/engine/install/ubuntu/#install-using-the-convenience-script>`__
  to install Docker engine.

- CCZoo source::

   git clone https://github.com/intel/confidential-computing-zoo.git
   
- System with processor that supports Intel® Software Guard Extensions (Intel® SGX), Datacenter Attestation Primitives (DCAP), and Flexible Launch Control (FLC).

- For deployments on Microsoft Azure, run the following script to install general dependencies, Intel SGX DCAP dependencies, and the Azure DCAP Client. To run this script::

   cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving
   sudo ./setup_azure_vm.sh

  Verify the Intel Architectural Enclave Service Manager is active (running)::
  
   sudo systemctl status aesmd

- For other deployments (other than on Microsoft Azure), use `this guide <https://download.01.org/intel-sgx/latest/linux-latest/docs/Intel_SGX_Installation_Guide_Linux_2.10_Open_Source.pdf>`__
  to install the Intel SGX driver and SDK/PSW on the machine/VM. Make sure to install the driver
  with ECDSA/DCAP attestation.
  

Solution Ingredients
--------------------
This solution leverages the following ingredients.

- TensorFlow Serving. `TensorFlow Serving <https://www.TensorFlow.org/tfx/guide/serving>`__
  is a flexible, high-performance serving system for machine learning models.
- Gramine. `Gramine <https://gramine.readthedocs.io>`__ is a lightweight library OS, designed to run a single application with minimal host requirements. Gramine runs unmodified applications inside Intel SGX.
- Kubernetes. `Kubernetes <https://kubernetes.io/docs/concepts/overview/what-is-kubernetes/>`__
  is an open-source system for automating deployment, scaling, and management of
  containerized applications. In this guide, we will first run the solution without the use of Kubernetes. Then we will run the solution using Kubernetes to provide automated deployment, scaling, and management of the containerized TensorFlow Serving application.


Executing Confidential TF Serving without Kubernetes
----------------------------------------------------
There are several options to run this solution.

Typical Setup: The Client, Secret Provisioning Server, and TensorFlow Serving containers run on separate systems/VMs.

Quick Start Setup (for demonstration purposes): Run all steps on a single system/VM (Client, Secret Provisioning Server, and TensorFlow Serving containers all run on the same system/VM).

1. Download/Build Client Container Image
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Follow the steps below to download (or alternatively build) the Client container image to the Client system/VM.

1.1 Download Client Container Image
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For Anolisos cloud deployments::

   docker pull intelcczoo/tensorflow_serving:anolis_client_latest

For other cloud deployments, including on Microsoft Azure::

   docker pull intelcczoo/tensorflow_serving:default_client_latest


1.2 Alternatively Build Client Container Image
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Alternatively, build the Client container image.

Download the CCZoo source::

    git clone https://github.com/intel/confidential-computing-zoo.git
    cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/client
    
For Anolisos::

    ./build_client_image.sh -b anolisos

For other cloud deployments, including on Microsoft Azure::

    ./build_client_image.sh -b default


2. Download/Build Secret Provisioning Server Container Image
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
In order to deploy this service easily, we build and run this service in container.
Basically, we use ``secret_prov_server_dcap`` as the remote SGX Enclave Quote
authentication service and relies on the Quote-related authentication library
provided by SGX DCAP. The certification service will obtain Quote certification
related data from Intel PCCS, such as TCB related information and CRL information.
After successful verification of SGX Enclave Quote, the key stored in ``files/wrap-key``
will be sent to the remote application.
The remote application here is Gramine in the SGX environment.
After remote Gramine gets the key, it will decrypt the encrypted model file.

Follow the steps below to download (or alternatively build) the Secret Provisioning Server container image to the Secret Provisioning Server system/VM.

2.1 Download Secret Provisioning Server Container Image
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
For deployments on Microsoft Azure::

   docker pull intelcczoo/tensorflow_serving:azure_secret_prov_server_latest
      
For Anolisos cloud deployments::

   docker pull intelcczoo/tensorflow_serving:anolis_secret_prov_server_latest

For other cloud deployments::

   docker pull intelcczoo/tensorflow_serving:default_secret_prov_server_latest


2.2 Alternatively Build Secret Provisioning Server Container Image
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Alternatively, build the Secret Provisioning Server container image.

Download the CCZoo source::

   git clone https://github.com/intel/confidential-computing-zoo.git
   cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/secret_prov

For deployments on Microsoft Azure::

   ./build_secret_prov_image.sh azure
   
For Anolisos cloud deployments::

   ./build_secret_prov_image.sh anolisos

For other cloud deployments::

   ./build_secret_prov_image.sh


3. Download/Build TensorFlow Serving Container Image
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Follow the steps below to download (or alternatively build) the TensorFlow Serving container image to the TensorFlow Serving system/VM.

3.1 Download TensorFlow Serving Container Image
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Download the TensorFlow Serving container image to the SGX-enabled machine.

For deployments on Microsoft Azure::

   docker pull intelcczoo/tensorflow_serving:azure_tensorflow_serving_latest
      
For Anolisos cloud deployments::

   docker pull intelcczoo/tensorflow_serving:anolis_tensorflow_serving_latest

For other cloud deployments::

   docker pull intelcczoo/tensorflow_serving:default_tensorflow_serving_latest


3.2 Alternatively Build TensorFlow Serving Container Image
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Alternatively, build the TensorFlow Serving container image.

Download the CCZoo source::

   git clone https://github.com/intel/confidential-computing-zoo.git
   cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/tf_serving
   
For deployments on Microsoft Azure::
   
   ./build_gramine_tf_serving_image.sh azure
      
For Anolisos cloud deployments::

   ./build_gramine_tf_serving_image.sh anolisos

For other cloud deployments::

   ./build_gramine_tf_serving_image.sh

3.2.1 TensorFlow Serving Container Build Explained
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This section describes what is included in the TensorFlow Serving container build. Note that no specific customizations are required to build the reference TensorFlow Serving container.  

The gramine_tf_serving dockerfile includes the following install items:

- Install basic dependencies for source code build.
- Install TensorFlow Serving.
- Install LibOS - Gramine.
- Copy files from host to built container.

The files copied from host to container include:

- Makefile. Used to compile TensorFlow with Gramine.
- sgx_default_qcnl.conf. If needed, replace the PCCS url provided by the public cloud service being used.
- tf_serving_entrypoint.sh. The script that is executed when container is started.
- tensorflow_model_server.manifest.template. The TensorFlow Serving configuration template used by Gramine.

Gramine supports SGX RA-TLS function, it can be enabled by configuration parameters in the Gramine template file::

   sgx.remote_attestation = true
   loader.env.LD_PRELOAD = "libsecret_prov_attest.so"
   loader.env.SECRET_PROVISION_CONSTRUCTOR = "1"
   loader.env.SECRET_PROVISION_SET_KEY = "default"
   loader.env.SECRET_PROVISION_CA_CHAIN_PATH = "ssl/ca.crt"
   loader.env.SECRET_PROVISION_SERVERS = "attestation.service.com:4433"
   sgx.trusted_files = [
     ...
     "file:libsecret_prov_attest.so",
     "file:ssl/ca.crt",
     ...
   ]

``SECRET_PROVISION_CONSTRUCTOR`` is set to true to initialize the RA-TLS session and retrieve the secret before the application starts.

``SECRET_PROVISION_SET_KEY`` is the name of the key that will be provisioned into the Gramine enclave as the secret.

``SECRET_PROVISION_CA_CHAIN_PATH`` is the path to the CA chain of certificates to verify the server.

``SECRET_PROVISION_SERVERS`` is the server names with ports to connect to for secret provisioning.

The Gramine template file contains parameters to allow for mounting files that are encrypted on disk and transparently decrypted when accessed by Gramine or by application running inside Gramine::

  fs.mounts = [
    ...
    { path = "/models/resnet50-v15-fp32/1/saved_model.pb", uri = "file:models/resnet50-v15-fp32/1/saved_model.pb", type = "encrypted" },
    { path = "/ssl.cfg", uri = "file:ssl.cfg", type = "encrypted" }
    ...
  ]

For more syntax used in the manifest template, please refer to `Gramine Manifest syntax <https://github.com/gramineproject/gramine/blob/master/Documentation/manifest-syntax.rst>`__.


4. Obtain the TensorFlow Serving Container SGX Measurements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The TensorFlow Serving container SGX measurements are used by the Secret Provisioning Server container to verify the TensorFlow Serving enclave identity (mr_enclave) and signing identity (mr_signer).

On the system with an already built TensorFlow Serving container image, get the image ID, then use the script as described below to retrieve the mr_enclave and mr_signer values::

   $ cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/tf_serving
   $ docker images
   $ ./get_image_enclave_mr.sh <gramine_tf_serving_image_id>
    mr_enclave:  39b02dbf3cd6d6c68eb227a5da019c3721162085116a614ab4be0d1f81199d8f
    mr_signer:   ae483edd52e38b2ef67f3962b75ad47f987db8d3a42d0cd1ca7b6ee4c7035a6e
    isv_prod_id: 0
    isv_svn:     0

These are the same SGX measurements displayed during the TensorFlow Serving container build.
Example mr_enclave and mr_signer values from a TensorFlow Serving container build::

   Step 38/45 : RUN make SGX=${SGX} RA_TYPE=${RA_TYPE} -j `nproc` | grep "mr_enclave\|mr_signer\|isv_prod_id\|isv_svn" | tee -a enclave.mr
    ---> Running in 1c1468764466
       isv_prod_id: 0
       isv_svn:     0
       mr_enclave:  39b02dbf3cd6d6c68eb227a5da019c3721162085116a614ab4be0d1f81199d8f
       mr_signer:   ae483edd52e38b2ef67f3962b75ad47f987db8d3a42d0cd1ca7b6ee4c7035a6e
       isv_prod_id: 0
       isv_svn:     0


5. Update Expected TF Serving Container SGX Measurements for the Secret Provisioning Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
On the Secret Provisioning Server system/VM, modify ``<cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/secret_prov/patches/secret_prov_pf/ra_config.json`` with the TensorFlow Serving container measurements from the previous section. Do not copy and paste the following example values. Use the actual mr_enclave values from your TensorFlow Serving container(s). To support multiple TensorFlow Serving containers, the measurements for each container must be added as separate items in the "mrs" array::

   {
       "verify_mr_enclave" : "on",
       "verify_mr_signer" : "on",
       "verify_isv_prod_id" : "on",
       "verify_isv_svn" : "on",
       "mrs": [
           {
               "mr_enclave" : "39b02dbf3cd6d6c68eb227a5da019c3721162085116a614ab4be0d1f81199d8f",
               "mr_signer" : "ae483edd52e38b2ef67f3962b75ad47f987db8d3a42d0cd1ca7b6ee4c7035a6e",
               "isv_prod_id" : "0",
               "isv_svn" : "0"
           }
       ]
   }


6. Run Secret Provisioning Server Container
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run the Secret Provisioning Server container.

Change directories::

   cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/secret_prov

For deployments on Microsoft Azure::
  
   ./run_secret_prov.sh -i tensorflow_serving:<azure_secret_prov_server_tag> -r <absolute path to patches/secret_prov_pf/ra_config.json> -b https://sharedcus.cus.attest.azure.net
   
For Anolisos cloud deployments::

   ./run_secret_prov.sh -i tensorflow_serving:<anolis_secret_prov_server_tag> -r <absolute path to patches/secret_prov_pf/ra_config.json> -a pccs.service.com:ip_addr

For other cloud deployments::

   ./run_secret_prov.sh -i tensorflow_serving:<default_secret_prov_server_tag> -r <absolute path to patches/secret_prov_pf/ra_config.json> -a pccs.service.com:ip_addr

*Note*:
   1. ``ip_addr`` is the host machine where your PCCS service is installed.
   2. ``secret provisioning server`` will start port ``4433`` and monitor request. Under public cloud instance, please make sure the port ``4433`` is enabled to access.
   3. Under cloud SGX environment (except for Microsoft Azure), if CSP provides their own PCCS server, please replace the PCCS URL in ``sgx_default_qcnl.conf`` with the one provided by CSP. You can start the secret provisioning server::
      
      ./run_secret_prov.sh -i tensorflow_serving:<secret_prov_server_tag> -r <absolute path to patches/secret_prov_pf/ra_config.json> 

To check the Secret Provisioning Server logs::

   docker ps -a
   docker logs <secret_prov_server_container_id>

Get the Secret Provisioning Server container's IP address, which will be used when starting the TensorFlow Serving service in a later step::

   docker ps -a
   docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <secret_prov_server_container_id>
   

7. Prepare ML Model and SSL/TLS Certificates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The steps in this section can be performed on any system. The encrypted model is copied to the TensorFlow Serving system/VM.

7.1 Prepare Model
^^^^^^^^^^^^^^^^^^
We use ResNet50 model with FP32 precision for TensorFlow Serving to the inference.
First, use ``download_model.sh`` to download the pre-trained model file. It will
generate the directory ``models/resnet50-v15-fp32`` in current directory::

   cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/client
   ./download_model.sh

The model file will be downloaded to ``models/resnet50-v15-fp32``. 
Then use ``model_graph_to_saved_model.py`` to convert the pre-trained model to SavedModel::

   pip3 install -r requirements.txt
   python3 ./model_graph_to_saved_model.py --import_path `pwd -P`/models/resnet50-v15-fp32/resnet50-v15-fp32.pb --export_dir  `pwd -P`/models/resnet50-v15-fp32 --model_version 1 --inputs input --outputs  predict

Confirm that the converted model file appears under::

   models/resnet50-v15-fp32/1/saved_model.pb

7.2 Create SSL/TLS Certificate
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
We choose gRPC SSL/TLS and create the SSL/TLS Keys and certificates by setting
TensorFlow Serving domain name to establish a communication link between client
and TensorFlow Serving.

For ensuring security of the data being transferred between a client and server, SSL/TLS can be implemented with either one-way TLS authentication or two-way TLS authentication (mutual TLS authentication).

To use two-way SSL/TLS authentication (server and client verify each other)::

      service_domain_name=grpc.tf-serving.service.com
      client_domain_name=client.tf-serving.service.com
      ./generate_twoway_ssl_config.sh ${service_domain_name} ${client_domain_name}
      

``generate_twoway_ssl_config.sh`` will generate the directory 
``ssl_configure`` which includes ``server/*.pem``, ``client/*.pem``, 
``ca_*.pem`` and ``ssl.cfg``.
``client/*.pem`` and ``ca_cert.pem`` will be used by the remote client 
and ``ssl.cfg`` will be used by TensorFlow Serving.

Alternatively, to use one-way SSL/TLS authentication (client verifies server)::

      service_domain_name=grpc.tf-serving.service.com
      ./generate_oneway_ssl_config.sh ${service_domain_name}

``generate_oneway_ssl_config.sh`` will generate the directory 
``ssl_configure`` which includes ``server/*.pem`` and ``ssl.cfg``.
``server/cert.pem`` will be used by the remote client and ``ssl.cfg`` 
will be used by TensorFlow Serving.



7.3 Encrypt Model and SSL/TLS Certificate
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
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

Encrypt the model file::

   mkdir -p plaintext/
   mv models/resnet50-v15-fp32/1/saved_model.pb plaintext/
   LD_LIBRARY_PATH=./libs ./gramine-sgx-pf-crypt encrypt -w files/wrap-key -i  plaintext/saved_model.pb -o  models/resnet50-v15-fp32/1/saved_model.pb
   tar -cvf models.tar models

Encrypt ssl.cfg::

      mkdir -p plaintext/
      mv ssl_configure/ssl.cfg plaintext/
      LD_LIBRARY_PATH=./libs ./gramine-sgx-pf-crypt encrypt -w files/wrap-key -i plaintext/ssl.cfg -o ssl.cfg
      mv ssl.cfg ssl_configure/
      tar -cvf ssl_configure.tar ssl_configure
      
For more information about ``gramine-sgx-pf-crypt``, please refer to `pf_crypt <https://github.com/gramineproject/gramine/tree/master/Pal/src/host/Linux-SGX/tools/pf_crypt>`__.


8. Run TensorFlow Serving w/ Gramine on SGX-enabled System
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

8.1 Preparation
^^^^^^^^^^^^^^^
Copy the encrypted model and encrypted SSL/TLS certificate to the TensorFlow Serving SGX-enabled system/VM.

For example (if using the Quick Start Setup where all steps are run on a single system/VM)::

   cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/tf_serving
   cp ../client/models.tar .
   cp ../client/ssl_configure.tar .
   tar -xvf models.tar
   tar -xvf ssl_configure.tar
   
8.2 Execute TensorFlow Serving w/ Gramine in SGX
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Change directories and copy ssl.cfg::

   cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/tf_serving
   cp ssl_configure/ssl.cfg .

Run the TensorFlow Serving container, specifying the TensorFlow Serving container ID and the Secret Provisioning Server container IP address.

For deployments on Microsoft Azure::

    ./run_gramine_tf_serving.sh -i tensorflow_serving:<azure_tensorflow_serving_tag> -p 8500-8501 -m resnet50-v15-fp32 -s ssl.cfg -a attestation.service.com:<secret_prov_server_container_ip_addr> -b https://sharedcus.cus.attest.azure.net

For Anolisos cloud deployments::

    ./run_gramine_tf_serving.sh -i tensorflow_serving:<anolis_tensorflow_serving_tag> -p 8500-8501 -m resnet50-v15-fp32 -s ssl.cfg -a attestation.service.com:<secret_prov_server_container_ip_addr>

For other cloud deployments::

    ./run_gramine_tf_serving.sh -i tensorflow_serving:<default_tensorflow_serving_tag> -p 8500-8501 -m resnet50-v15-fp32 -s ssl.cfg -a attestation.service.com:<secret_prov_server_container_ip_addr>

*Note*:
   1. ``8500-8501`` are the ports created on (bound to) the host, you can change them if you need.
   2. ``secret_prov_server_container_ip_addr`` is the ip address of the container running the Secret Provisioning Server.

Check the TensorFlow Serving container logs::

   docker ps -a
   docker logs <tf_serving_container_id>

The TensorFlow Serving application is ready to service inference requests when the following log is output::

   [evhttp_server.cc : 245] NET_LOG: Entering the event loop ...


.. image:: ./img/TF_Serving.svg
   :target: ./img/TF_Serving.svg
   :scale: 50 %
   :alt: Figure: TensorFlow Serving

Get the container's IP address, which will be used when starting the Client container in the next step::

   docker ps -a
   docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <tf_serving_container_id>


9. Run Client Container and Send Inference Request
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

9.1 Preparation
^^^^^^^^^^^^^^^
If the SSL/TLS certificates were prepared on a system other than the Client system/VM, copy the certificates to the following directory on Client system/VM::

   <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/client

Extract the certificates on the Client system/VM::
   
   cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/client
   tar -xvf ssl_configure.tar
   
9.2 Run Client Container
^^^^^^^^^^^^^^^^^^^^^^^^
On the Client system/VM, change directories and run the Client container::

    cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/client
    ./run_client.sh -s <SSLDIR> -t <IPADDR> -i <IMAGEID>
      -s SSLDIR      SSLDIR is the absolute path to the ssl_configure directory
      -t IPADDR      IPADDR is the TF serving service IP address
      -i IMAGEID     IMAGEID is the client docker image ID

For Anolisos, IMAGEID is <anolisos_client:tag>.
For other cloud deployments, including on Microsoft Azure, IMAGEID is <default_client:tag>.


9.3 Send Remote Inference Request
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
From the Client container, send the remote inference request (with a dummy image)::

   If using two-way SSL/TLS authentication::

      cd /client
      ./run_inference.sh twoway_ssl

   If using one-way SSL/TLS authentication::

      cd /client
      ./run_inference.sh oneway_ssl


      
Observe the inference response output that begins with the following string::

      {'outputs': {'predict': {'dtype': 'DT_FLOAT', 'tensorShape':



Executing Confidential TF Serving with Kubernetes
--------------------------------------------------
There are several options to run this solution.

Typical Setup: The Client container, Secret Provisioning Server container, and Kubernetes run on separate systems/VMs.

Quick Start Setup (for demonstration purposes): Run all steps on a single system/VM - Client container, Secret Provisioning Server container, and Kubernetes all run on the same system/VM.

In this section, we will setup Kubernetes on the SGX-enabled machine.
Then we will use Kubernetes to start multiple TensorFlow Serving containers.
The following sections will reuse the machine/VM Intel SGX DCAP setup and containers built from the previous sections.

1. Preparation
~~~~~~~~~~~~~~
Stop and remove the client and tf-serving containers. Start the Secret Provisioning Server container if it isn't running::

    docker ps -a
    docker stop <client_container_id> <tf_serving_container_id>
    docker rm <client_container_id> <tf_serving_container_id>
    docker start <secret_prov_server_container_id>

Take note of the Secret Provisioning Server container's IP address, which will be used in a later step::

   docker ps -a
   docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <secret_prov_server_container_id>
   

2. Setup Kubernetes
~~~~~~~~~~~~~~~~~~~
This section sets up Kubernetes on the SGX-enabled system/VM that will run the TensorFlow Serving container(s).

2.1 Install Kubernetes
^^^^^^^^^^^^^^^^^^^^^^

First, please make sure the system date/time on your machine is updated to the current date/time.

Refer to ``https://kubernetes.io/docs/setup/production-environment/`` or
use ``install_kubernetes.sh`` to install Kubernetes::

   cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/kubernetes
   sudo ./install_kubernetes.sh

Create the control plane / master node::

   unset http_proxy && unset https_proxy
   swapoff -a && free -m
   sudo rm /etc/containerd/config.toml
   containerd config default | sudo tee /etc/containerd/config.toml
   sudo systemctl restart containerd
   sudo kubeadm init --v=5 --node-name=master-node --pod-network-cidr=10.244.0.0/16 --kubernetes-version=v1.27.1

   mkdir -p $HOME/.kube
   sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
   sudo chown $(id -u):$(id -g) $HOME/.kube/config


2.2 Setup Flannel in Kubernetes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Setup Flannel in Kubernetes.

Flannel is focused on networking and responsible for providing a layer 3 IPv4
network between multiple nodes in a cluster. Flannel does not control how
containers are networked to the host, only how the traffic is transported between
hosts.

Deploy the Flannel service::

   kubectl apply -f flannel/deploy.yaml

2.3 Setup Ingress-Nginx in Kubernetes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Setup Ingress-Nginx in Kubernetes.
Please refer to the Introduction part for more information about Nginx.

Deploy the Nginx service::

   kubectl apply -f ingress-nginx/deploy-nodeport.yaml

2.4 Allow Scheduling On Node
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Allow pods to be scheduled on the node::

   kubectl taint nodes --all node-role.kubernetes.io/control-plane:NoSchedule-
   
2.5 Verify Node Status
^^^^^^^^^^^^^^^^^^^^^^

Get node info to verify that the node status is Ready::

   kubectl get node
   
2.6 Config Kubernetes cluster DNS
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Configure the cluster DNS in Kubernetes so that all the TensorFlow
Serving pods can communicate with the Secret Provisioning Server::

   kubectl edit configmap -n kube-system coredns

The config file will open in an editor. Add the following "hosts" section above the "prometheus" line as shown below, replacing x.x.x.x with the Secret Provisioning Server container IP address::

    # new added
    hosts {
           x.x.x.x attestation.service.com
           fallthrough
       }
    # end

    prometheus :9153
    forward . /etc/resolv.conf {
              max_concurrent 1000
    }



2.7 Setup Docker Registry
^^^^^^^^^^^^^^^^^^^^^^^^^
Setup a local Docker registry to serve the TensorFlow Serving container image to the Kubernetes cluster::

    docker run -d -p 5000:5000 --restart=always --name registry registry:2
    docker tag tensorflow_serving:<tag> localhost:5000/tensorflow_serving:<tag>
    docker push localhost:5000/tensorflow_serving:<tag>

   
2.8 Start TensorFlow Serving Deployment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Let's take a look at the configuration for the elastic deployment of
TensorFlow Serving under the directory::

   <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/kubernetes

There are two Yaml files: ``deploy.yaml`` and ``ingress.yaml``.

Please refer to this `guide <https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.20/#deploymentspec-v1-apps>`__
for more information about the yaml parameters.

Customize ``deploy.yaml``, replacing "<tensorflow_serving_tag>" with the tag of your TensorFlow Serving container::

    containers:
    - name: gramine-tf-serving-container
      image: localhost:5000/tensorflow_serving:<tensorflow_serving_tag>
      imagePullPolicy: IfNotPresent

Customize ``deploy.yaml`` with the host absolute path to the models directory and the host absolute path to ssl.cfg::     

     - name: model-path
       hostPath:
         path: <absolute_path_cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/tf_serving/models
          
     - name: ssl-path
       hostPath:
         path: <absolute_path_cczoo_base_dir/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/tf_serving/ssl_configure/ssl.cfg


``ingress.yaml`` mainly configures the networking options.
Use the default domain name, or use a custom domain name::

    rules:
      - host: grpc.tf-serving.service.com

Apply the two yaml files::

    cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/kubernetes
    kubectl apply -f deploy.yaml
    kubectl apply -f ingress.yaml

2.9 Verify TensorFlow Serving Deployment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Verify one pod of the TensorFlow Serving container is running and that the service is ready::

    $ kubectl get pods -n gramine-tf-serving
    NAME                                             READY   STATUS    RESTARTS   AGE                         
    gramine-tf-serving-deployment-548f95f46d-rx4w2   1/1     Running   0          5m1s
    $ kubectl logs -n gramine-tf-serving gramine-tf-serving-deployment-548f95f46d-rx4w2

The TensorFlow Serving application is ready to service inference requests when the following log is output::

   [evhttp_server.cc : 245] NET_LOG: Entering the event loop ...


.. image:: ./img/TF_Serving.svg
   :target: ./img/TF_Serving.svg
   :scale: 50 %
   :alt: Figure: TensorFlow Serving


Check pod info if the pod is not running::

    kubectl describe pod -n gramine-tf-serving gramine-tf-serving-deployment-548f95f46d-rx4w2
    
Check the coredns setup if the TensorFlow Serving service is not ready. This can be caused when the TensorFlow Serving service is unable to obtain the wrap-key (used to decrypt the model file) from the Secret Provisioning Server container.


2.10 Scale the TensorFlow Serving Service
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Scale the TensorFlow Serving service to two replicas::

   kubectl scale -n gramine-tf-serving deployment.apps/gramine-tf-serving-deployment --replicas 2

This starts two TensorFlow Serving containers, each with its own TensorFlow Serving service running on its own SGX enclave.

Verify that two pods are now running. Also verify that the second pod of the TensorFlow Serving container is running and that the service is ready (look for log "Entering the event loop")::

    $ kubectl get pods -n gramine-tf-serving
    NAME                                             READY   STATUS    RESTARTS   AGE
    gramine-tf-serving-deployment-548f95f46d-q4bcg   1/1     Running   0          2m28s
    gramine-tf-serving-deployment-548f95f46d-rx4w2   1/1     Running   0          4m10s
    $ kubectl logs -n gramine-tf-serving gramine-tf-serving-deployment-548f95f46d-q4bcg


3. Run Client Container and Send Inference Request
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

3.1 Get IP Address of TensorFlow Serving Service
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Get the CLUSTER-IP of the load balanced TensorFlow Serving service::

    $ kubectl get service -n gramine-tf-serving                             
    NAME                         TYPE       CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
    gramine-tf-serving-service   NodePort   10.108.27.161   <none>        8500:30500/TCP   13m


3.2 Run Client Container
^^^^^^^^^^^^^^^^^^^^^^^^
On the Client system/VM, change directories and run the Client container, where IPADDR is the CLUSTER-IP value::

    cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/docker/client
    
    ./run_client.sh -s <SSLDIR> -t <IPADDR> -i <IMAGEID>
      -s SSLDIR      SSLDIR is the absolute path to the ssl_configure directory
      -t IPADDR      IPADDR is the TF serving service IP address
      -i IMAGEID     IMAGEID is the client docker image ID

For Anolisos, IMAGEID is <anolisos_client:tag>.
For other cloud deployments, including on Microsoft Azure, IMAGEID is <default_client:tag>.


3.3 Send Remote Inference Request
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
From the Client container, send the remote inference request (with a dummy image)::

   If using two-way SSL/TLS authentication::

      cd /client
      ./run_inference.sh twoway_ssl

   If using one-way SSL/TLS authentication::

      cd /client
      ./run_inference.sh oneway_ssl


Observe the inference response output that begins with the following string::

      {'outputs': {'predict': {'dtype': 'DT_FLOAT', 'tensorShape':



4. Cleaning Up
~~~~~~~~~~~~~~

To stop the TensorFlow Serving deployment::

   cd <cczoo_base_dir>/cczoo/tensorflow-serving-cluster/tensorflow-serving/kubernetes
   kubectl delete -f deploy.yaml


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
- Instance Kernel: 5.15.0-1037-azure
- Instance OS    : Ubuntu Server 20.04 LTS - Gen2
- Instance Encrypted Memory: 64G
- Instance vCPU  : 16
