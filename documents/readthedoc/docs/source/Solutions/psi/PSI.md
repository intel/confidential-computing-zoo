# PSI

## Introduction
Private Set Intersection (PSI) is an application hotspot of multi-party secure computing. Its purpose is to calculate the intersection between the two parties through a secure scheme without exposing other information beyond the intersection. There are many implementations of PSI, some of which are based on cryptographic algorithms, such as the RSA algorithm. Our solution is implemented in a trusted execution environment, and its architecture is as follows:

<div align=center>
<img src=images/psi.svg>
</div>

The computing phase can be divided into the following steps:

&emsp;&ensp;**1.** All participants run in the TEE environment. Each client completes two-way authentication with the server through RA-TLS.

&emsp;&ensp;**2.** Clients transmit data securely and upload it to the server.

&emsp;&ensp;**3.** The server side waits for the data upload of all clients to complete, and then calculates the intersection of the data.

&emsp;&ensp;**4.** The server side sends the calculation results back to each participant through secure transmission.

In the above process, the client can only obtain the intersection data, but not the non-intersection data belonging to other clients. The server side is only responsible for computing, and will not save or steal the data sent by clients.

## Build and installation

Currently, we only support building and installation from the source code. It will generate a docker 
images for developing the gRPC RA-TLS application.

1. Setup TEE

   - Gramine

        Refer to `cczoo/common/docker/gramine/README.md`

        ```bash
        cd cczoo/common/docker/gramine
        ./build_docker_image.sh
        ```

   - Occlum

        Occlum provides the docker image in docker registry, no need to build it by self.

        ```bash
        docker pull occlum/occlum:0.26.3-ubuntu18.04
        ```

2. Setup develop environment of gRPC RA-TLS based on TEE

   - Gramine

        ```bash
        cd cczoo/psi/gramine
        ./build_docker_image.sh
        ```

   - Occlum

        In progress.

   - TDX

        In progress.

## Run PSI examples

- Gramine

   	Refer to `cczoo/psi/gramine/README.md`

   	Prepare the docker container

   	```bash
   	cd cczoo/psi
   
   	#start and enter the docker container
   	./start_container.sh ${pccs_service_ip} ${image_tag}
   
   	#Run the aesm service
   	/root/start_aesm_service.sh
   	```
   	
	Run the Python example
	
	```shell
	cd CI-Examples/psi/python
	```
	
	Two parties:

    ```shell
    # Run the server
    gramine-sgx python -u server.py -host localhost:50051 -config dynamic_config.json
    
    # Run the client1
	gramine-sgx python -u data_provider1.py -host localhost:50051 -config dynamic_config.json -is_chief True -data_dir "data1.txt" -client_num 2
    
    # Run the client2
	gramine-sgx python -u data_provider2.py -host localhost:50051 -config dynamic_config.json -is_chief False -data_dir "data2.txt" -client_num 2
    ```

	Three parties:

    ```shell
    # Run the server
    gramine-sgx python -u server.py -host localhost:50051 -config dynamic_config.json
    
    # Run the client1
	gramine-sgx python -u data_provider1.py -host localhost:50051 -config dynamic_config.json -is_chief True -data_dir "data1.txt" -client_num 3
    
    # Run the client2
	gramine-sgx python -u data_provider2.py -host localhost:50051 -config dynamic_config.json -is_chief False -data_dir "data2.txt" -client_num 3
    
    # Run the client3
	gramine-sgx python -u data_provider3.py -host localhost:50051 -config dynamic_config.json -is_chief False -data_dir "data3.txt" -client_num 3
    ```
