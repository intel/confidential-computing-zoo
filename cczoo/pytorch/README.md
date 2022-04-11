# PyTorch with SGX



PyTorch with SGX provides a deep learning model protection method based on [PyTorch](https://github.com/pytorch/pytorch) and [Intel SGX](https://github.com/intel/linux-sgx) (Software Guard eXtensions)  technology.

- [Background](#background)
- [Framework](#framework)
- [Installation](#installation)
- [Usage Documentation](#usage-documentation)


## Background

Deep learning models are generated based on a large amount of training data and computing power, which have very high commercial value. The trained models can be deployed on virtual nodes provided in public cloud by cloud service providers (CSPs).

How to protect these models deployed on public clouds from being stolen, and how to ensure these models can be used but invisible to adversaries at the same time? These concerns are faced by both model owners and cloud service providers. PyTorch with SGX is introduced to solve these concerns by keeping the models' confidentiality with hardware solutions. 

## Framework

PyTorch with SGX can protect model parameters when processing model inference. The model parameters are stored in ciphertext at the deployment stage, the related operations are performed in SGX enclave. Model parameters are only decrypted in the SGX enclave, and the decryption key is transmitted through a secure channel established by SGX remote attestation.

![image](https://user-images.githubusercontent.com/59001339/131809297-3444c7be-3ee4-4d7c-97e6-c730652e6fdd.png)

The model owner first uses the tools provided by PyTorch with SGX to encrypt the model parameters locally. Then the encrypted model is transmitted and deployed in public cloud. The key server manages all model keys and model IDs, which run in enclave and provide to model's enclave when necessary.

![image](https://user-images.githubusercontent.com/59001339/135217757-a6513a6d-4fdd-42d6-ac8d-7063ef126179.png)

When the model is used to do inference in public cloud, the enclave will automatically request the model key from the local key distribution service. The key will be encrypted and sent to the enclave via the SGX secure channel. The enclave started by PyTorch with SGX uses the key to decrypt the model parameters and perform calculations. Model parameters under SGX-based hardware protection throughout the entire process, the model can ensure available and invisible at the same time.

## Installation
### 1. Preinstall
Please follow [Intel SGX](https://github.com/intel/linux-sgx) to install Intel SGX (Please Make sure your local device and cloud device can support Intel SGX and FLC by hardware), and setup the [DCAP server](https://github.com/intel/SGXDataCenterAttestationPrimitives/).

Then install following packages, and download the code.
```bash
sudo apt install -y git gcc-c++ python3 python3-pip 
pip3 install astunparse numpy ninja pyyaml mkl mkl-include setuptools cmake cffi typing_extensions future six requests dataclasses setuptools_rust pycryptodome torchvision
git clone https://github.com/intel/pytorch -b sgx
git submodule sync && git submodule update --init --recursive
```

### 2. Compile and start the key service on the key server side (local deployment by the model owner):
```bash
$ cd enclave_ops/deployment
$ make
$ cd bin/dkeyserver
$ sudo ./dkeyserver
```
The key server starts and waits for the key request from the dkeycache deployed on the SGX node.
This service has two built-in model keys as test keys, and users can update and maintain them according to actual applications.

### 3. Compile and start the local key distribution service on public cloud side (cloud server deployment):
```bash
$ cd enclave_ops/deployment
$ make
$ cd bin/dkeycache
$ sudo ./dkeycache
```
After key cache service is started, this service will obtain all model keys. This service get key through SGX Remote Attestation, and sends the key to PyTorch with SGX's enclave through SGX Local Attestation.

### 4. Compile PyTorch with SGX on public cloud side (cloud server deployment)

#### 4.1 Compile oneDNN used by enclave
```bash
$ source /opt/intel/sgxsdk/environment
$ cd ${PyTorch_ROOT}/third_party/sgx/linux-sgx
$ git am ../0001*
$ cd external/dnnl
$ make
$ sudo cp sgx_dnnl/lib/libsgx_dnnl.a /opt/intel/sgxsdk/lib64/libsgx_dnnl2.a
$ sudo cp sgx_dnnl/include/* /opt/intel/sgxsdk/include/
```

#### 4.2 Compile enclave used by PyTorch
```bash
$ source /opt/intel/sgxsdk/environment
$ cd ${PyTorch_ROOT}/enclave_ops/ideep-enclave
$ make
```
The enclave of PyTorch with SGX provides model parameter decryption and reference calculations.
Note: There are 8 logical processors by default in Enclave/Enclave.config.xml. If the actual machine is greater than 8, the \<TCSNum\> needs to update manually.

#### 4.3 Compile PyTorch
```bash
$ cd ${PyTorch_ROOT}
$ pip uninstall torch (uninstall the Pytorch installed on the system, the self-compiled Pytorch will be installed)
$ source /opt/intel/sgxsdk/environment
$ python setup.py develop --cmake-only
$ sudo python setup.py develop && python -c "import torch"
```

#### 4.4 Compile PyTorch secure operators
```bash
$ source /opt/intel/sgxsdk/environment
$ cd ${PyTorch_ROOT}/enclave_ops/secure_op && mkdir build && cd build
$ cmake -DCMAKE_PREFIX_PATH="$(python -c'import torch.utils; print(torch.utils.cmake_prefix_path)')" ..
$ make
```

### 5. ResNet-based test case
```bash
$ cd ${PyTorch_ROOT}/enclave_ops/test
$ sudo python whole_resnet.py
```
The ciphertext parameters of the Pytorch model will be decrypted in the SGX enclave, and the key will be obtained from the deployproxy service in the second step and encrypted and transmitted to the enclave.
In this use case, the model predicts the following data:
```bash
Samoyed 0.8732958436012268
Pomeranian 0.030270852148532867
white wolf 0.019671205431222916
keeshond 0.011073529720306396
Eskimo dog 0.009204281494021416
```


## Usage Documentation
PyTorch based on SGX provides some Python APIs to encrypt, store and load models.
```python
model.to_secure_mkldnn(key=bytes(16), model_id=bytes(4))
```
Model parameter encryption method, encrypt the model parameters according to the given key, the key and model_id are both 0 by default.
```python
torch.save(model.state_dict(), PATH)
```
Save the encrypted model parameters
```python
model.load_state_dict(torch.load(PATH))
```
Load the encrypted model parameters


### An example (refer to ${PyTorch_ROOT}/enclave_ops/test/whole_resnet.py, resnet_save.py, and resnet_load.py):

1. Locally, add following code in your PyTorch model code:
```python
model.to_secure_mkldnn(key=bytes(16), model_id=bytes(4))
torch.save(model.state_dict(), PATH)
```

2. Write key and model_id to the key server

3. On public cloud side, add following code in your PyTorch model code:
```python
model.to_secure_mkldnn()
model.load_state_dict(torch.load(PATH))
```

