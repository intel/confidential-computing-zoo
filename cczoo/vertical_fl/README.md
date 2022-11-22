
## Prerequisites

- Ubuntu 18.04. This solution should work on other Linux distributions as well, but for simplicity we provide the steps for Ubuntu 18.04 only.

- Docker Engine. Docker Engine is an open source containerization technology for building and containerizing your applications. In this solution, Gramine, Fedlearner, gRPC will be built in a Docker image. Please follow [this guide](https://docs.docker.com/engine/install/ubuntu/#install-using-the-convenience-script) to install Docker Engine. The Docker daemon's storage location (/var/lib/docker for example) should have at least 32GB available.

- SGX capable platform. Intel SGX Driver and SDK/PSW. You need a machine that supports Intel SGX and FLC/DCAP. Please follow [this guide](https://download.01.org/intel-sgx/latest/linux-latest/docs/) to install the Intel SGX driver and SDK/PSW. One way to verify SGX enabling status in your machine is to run [QuoteGeneration](https://github.com/intel/SGXDataCenterAttestationPrimitives/blob/master/QuoteGeneration) and [QuoteVerification](https://github.com/intel/SGXDataCenterAttestationPrimitives/blob/master/QuoteVerification) successfully.

Here, we will demonstrate vertical federated learning using a leader container and a follower container.


## Executing Fedlearner in SGX

### 1. Download source code

Download the [Fedlearner source code](https://github.com/bytedance/fedlearner/tree/fix_dev_sgx) which is a git submodule of CCZoo.

```
git submodule init
git submodule update
cd cczoo/vertical_fl
./apply_overlay.sh
cd vertical_fl
```

### 2. Build Docker image                                    

`build_dev_docker_image.sh` provides the parameter `proxy_server` to specify the network proxy. `build_dev_docker_image.sh` also accepts an optional argument to specify the docker image tag.

For deployments on Microsoft Azure:
```
AZURE=1 ./sgx/build_dev_docker_image.sh
```
For other cloud deployments:
```
./sgx/build_dev_docker_image.sh
```

Example of built image:

```
REPOSITORY             TAG         IMAGE ID            CREATED           SIZE
fedlearner-sgx-dev     latest      8c3c7a05f973        45 hours ago      15.2GB
```

### 3. Start Container

Start the leader and follower containers:

```
docker run -itd --name=fedlearner_leader --restart=unless-stopped -p 50051:50051 \
    --device=/dev/sgx_enclave:/dev/sgx/enclave --device=/dev/sgx_provision:/dev/sgx/provision fedlearner-sgx-dev:latest bash
    
docker run -itd --name=fedlearner_follower --restart=unless-stopped -p 50052:50052 \
    --device=/dev/sgx_enclave:/dev/sgx/enclave --device=/dev/sgx_provision:/dev/sgx/provision fedlearner-sgx-dev:latest bash
```

Take note of the container IP addresses for later steps:

```
docker inspect --format '{{ .NetworkSettings.IPAddress }}' fedlearner_leader
docker inspect --format '{{ .NetworkSettings.IPAddress }}' fedlearner_follower
```

In terminal 1, enter the leader container shell:

```
docker exec -it fedlearner_leader bash
```

In terminal 2, enter the follower container shell:

```
docker exec -it fedlearner_follower bash
```

#### 3.1 Configure PCCS

- For deployments on Microsoft Azure, skip this section, as configuring the PCCS is not necessary on Azure.

- If you are using public cloud instance, please replace the PCCS url in `/etc/sgx_default_qcnl.conf` with the new pccs url provided by the cloud.

  ```
  Old: PCCS_URL=https://pccs.service.com:8081/sgx/certification/v3/ 
  New: PCCS_URL=https://public_cloud_pccs_url
  ```

- If you are using your own machine, please make sure, the PCCS service is running successfully in your host with command `systemctl status pccs`. And add your host IP address in `/etc/hosts` under container. For example:

  ```
  cat /etc/hosts
  XXX.XXX.XXX.XXX pccs.service.com   #XXX.XXX.XXX.XXX is the host IP
  ```

#### 3.2 Start aesm service

Start the aesm service in both the leader and follower containers:

```
/root/start_aesm_service.sh
```

#### 4. Prepare data

Generate data in both the leader and follower containers:

```
cd /gramine/CI-Examples/wide_n_deep
./test-ps-sgx.sh data
```

#### 5. Compile applications

Compile applications in both the leader and follower containers:

```
cd /gramine/CI-Examples/wide_n_deep
./test-ps-sgx.sh make
```

Take note of the `mr_enclave` and `mr_signer` values from the resulting log from the leader container.
The following is an example log:

```
+ make
+ grep 'mr_enclave\|mr_signer\|isv_prod_id\|isv_svn'
    isv_prod_id: 0
    isv_svn:     0
    mr_enclave:  bda462c6483a15f18c92bbfd0acbb61b9702344202fcc6ceed194af00a00fc02
    mr_signer:   dbf7a340bbed6c18345c6d202723364765d261fdb04e960deb4ca894d4274839
    isv_prod_id: 0
    isv_svn:     0
```

In both the leader and follower containers, in `dynamic_config.json`, confirm that `mr_enclave` and `mr_signer` are set to the values from the leader container's log. Use the actual values from the leader container's log, not the values from the example log above. 

```
dynamic_config.json:
{
......
  "sgx_mrs": [
    {
      "mr_enclave": "",
      "mr_signer": "",
      "isv_prod_id": "0",
      "isv_svn": "0"
    }
  ],
......
}

```

#### 6. Run the distributing training

Start the training process in the follower container:

```
cd /gramine/CI-Examples/wide_n_deep
peer_ip=REPLACE_WITH_LEADER_IP_ADDR
./test-ps-sgx.sh follower $peer_ip
```

Wait until the follower training process is ready, when the following log is displayed:

```
2022-10-12 02:53:47,002 [INFO]: waiting master ready... (fl_logging.py:95)
```

Start the training process in the leader container:

```
cd /gramine/CI-Examples/wide_n_deep
peer_ip=REPLACE_WITH_FOLLOWER_IP_ADDR
./test-ps-sgx.sh leader $peer_ip
```

The following logs occur on the leader when the leader and follower have established communication:

```
2022-10-12 05:22:27,056 [INFO]: [Channel] state changed from CONNECTING_UNCONNECTED to CONNECTING_CONNECTED, event: PEER_CONNECTED (fl_logging.py:95)
2022-10-12 05:22:27,067 [INFO]: [Channel] state changed from CONNECTING_CONNECTED to READY, event: CONNECTED (fl_logging.py:95)
2022-10-12 05:22:27,068 [DEBUG]: [Bridge] stream transmit started (fl_logging.py:98)
```

The following logs on the leader are an example of a training iteration:

```
2022-10-12 05:23:52,356 [DEBUG]: [Bridge] send start iter_id: 123 (fl_logging.py:98)
2022-10-12 05:23:52,483 [DEBUG]: [Bridge] receive peer commit iter_id: 122 (fl_logging.py:98)
2022-10-12 05:23:52,484 [DEBUG]: [Bridge] received peer start iter_id: 123 (fl_logging.py:98)
2022-10-12 05:23:52,736 [DEBUG]: [Bridge] received data iter_id: 123, name: act1_f (fl_logging.py:98)
2022-10-12 05:23:52,737 [DEBUG]: [Bridge] Data: received iter_id: 123, name: act1_f after 0.117231 sec (fl_logging.py:98)
2022-10-12 05:23:52,739 [DEBUG]: [Bridge] Data: send iter_id: 123, name: act1_f_grad (fl_logging.py:98)
2022-10-12 05:23:52,817 [DEBUG]: [Bridge] receive peer commit iter_id: 123 (fl_logging.py:98)
2022-10-12 05:23:52,818 [DEBUG]: [Bridge] received peer start iter_id: 124 (fl_logging.py:98)
2022-10-12 05:23:53,070 [DEBUG]: [Bridge] received data iter_id: 124, name: act1_f (fl_logging.py:98)
2022-10-12 05:23:53,168 [DEBUG]: [Bridge] send commit iter_id: 123 (fl_logging.py:98)
2022-10-12 05:23:53,170 [DEBUG]: after session run. time: 0.814208 sec (fl_logging.py:98)
```

When the training processes are done, the leader will display these logs:


```
**************export model hook**************
sess : <tensorflow.python.client.session.Session object at 0x7e8fb898>
model:  <fedlearner.trainer.estimator.FLModel object at 0x8ee60f98>
export_dir:  model/leader/saved_model/1665552233
inputs:  {'examples': <tf.Tensor 'examples:0' shape=<unknown> dtype=string>, 'act1_f': <tf.Tensor 'act1_f:0' shape=<unknown> dtype=float32>}
outpus:  {'output': <tf.Tensor 'MatMul_2:0' shape=(None, 2) dtype=float32>}
*********************************************
2022-10-12 05:24:07,675 [INFO]: export_model done (fl_logging.py:95)
2022-10-12 05:24:07,676 [INFO]: Trainer Master status transfer, from WORKER_COMPLETED to COMPLETED (fl_logging.py:95)
2022-10-12 05:24:09,017 [INFO]: master completed (fl_logging.py:95)
```

The updated model files are saved in these locations:

```
./model/leader/saved_model/<id>/saved_model.pb
```

```
./model/follower/saved_model/<id>/saved_model.pb
```
