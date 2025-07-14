## Intel TDX RA-TLS Validation

## Introduction

This paper present a method to quickly verify the capability of TDX RA-TLS.
In TDX TEE(TD-VM), the client generates and sends quotes to the remote server on the host side via the RA-TLS protocol.
The server will verify quotes and measurements by accessing the PCCS service.

## Get docker image

- Build tdx-ratls docker image

    ```
    image_name=tdx-ratls:ubuntu22.04-dcap1.19-latest
    base_image=ubuntu:22.04
    ./build_docker_image.sh ${image_name} ${base_image}
    ```

- Or pull from registry

    ```
    docker pull intelcczoo/{image_name}
    docker tag intelcczoo/${image_name} ${image_name}
    ```

## Start quick test

1. Start server

    ```
    endpoint=0.0.0.0:18501
    ./start_container.sh <pccs_ip_addr> ${endpoint} ${image_tag}
    ```

2. Start client container to get TDX mesurements

    Start TDX TEE and run client container in TD-VM:

    ```
    endpoint=<remote server ip>:18501
    ./start_container.sh <pccs_ip_addr> ${endpoint} ${image_tag}
    ```

    Get TDX mesurements from output:

    ```
    ...

    TD info
    attributes: 0x0000000010000000 (NO_DEBUG SEPT_VE_DISABLE)
    xfam: 0x0000000000061ae7
    mr_td: 53bb889497b94d99f006db2c9fa35b0504a0c19d52d16cbf780e5c5ed88be1dab3f4cba9224da0742865236d74e889a8
    mr_config_id: 000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    mr_owner: 000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    mr_owner_config: 000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    rtmr0: ef723411793cfbe3239def9384ba05d0fa5c8fa5e1154df62729cc6d6eeb50005c14572637b2d664963950c79ab43a94
    rtmr1: dbf0be1536a62a90a8a8222b55ef81f4b53046d8b96174120e1e2c5c26ff799b00f8d3be40815759f88990385dd3bbaa
    rtmr2: cc76503e991ef1cab9610f1da4f78e87fb36b6b286942f5a67ed343686344bb8f105f9f5e0e7e9d4db8e3bb86a2796f5
    rtmr3: 000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000

    ...
    ```

3. Setup server's config file to verify client's measurements

    Write client's measurements and options to `${WORK_SPACE_PATH}/dynamic_config.json` in server container.

    ```
    {
        "verify_mr_seam" : "off",
        "verify_mrsigner_seam" : "off",
        "verify_mr_td" : "on",
        "verify_mr_config_id" : "off",
        "verify_mr_owner" : "off",
        "verify_mr_owner_config" : "off",
        "verify_rt_mr0" : "on",
        "verify_rt_mr1" : "on",
        "verify_rt_mr2" : "on",
        "verify_rt_mr3" : "on",
        "tdx_mrs": [
            {
                "mr_seam" : "",
                "mrsigner_seam" : "",
                "mr_td" : "53bb889497b94d99f006db2c9fa35b0504a0c19d52d16cbf780e5c5ed88be1dab3f4cba9224da0742865236d74e889a8",
                "mr_config_id" : "",
                "mr_owner" : "",
                "mr_owner_config" : "",
                "rt_mr0" : "ef723411793cfbe3239def9384ba05d0fa5c8fa5e1154df62729cc6d6eeb50005c14572637b2d664963950c79ab43a94",
                "rt_mr1" : "dbf0be1536a62a90a8a8222b55ef81f4b53046d8b96174120e1e2c5c26ff799b00f8d3be40815759f88990385dd3bbaa",
                "rt_mr2" : "cc76503e991ef1cab9610f1da4f78e87fb36b6b286942f5a67ed343686344bb8f105f9f5e0e7e9d4db8e3bb86a2796f5",
                "rt_mr3" : "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            }
        ]
    }
    ```

    Then restart server container.

    ```
    docker restart ratls-server
    ```

5. Start client to test TDX RA-TLS.

    Start client:

    ```
    ./start_container.sh <pccs_ip_addr> ${endpoint} ${image_tag}
    ```

    Client output:

    ```
    Start client ...
    Try to get TDX measurements ...

    TD info
    attributes: 0x0000000010000000 (NO_DEBUG SEPT_VE_DISABLE)
    xfam: 0x0000000000061ae7
    mr_td: 53bb889497b94d99f006db2c9fa35b0504a0c19d52d16cbf780e5c5ed88be1dab3f4cba9224da0742865236d74e889a8
    mr_config_id: 000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    mr_owner: 000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    mr_owner_config: 000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    rtmr0: ef723411793cfbe3239def9384ba05d0fa5c8fa5e1154df62729cc6d6eeb50005c14572637b2d664963950c79ab43a94
    rtmr1: dbf0be1536a62a90a8a8222b55ef81f4b53046d8b96174120e1e2c5c26ff799b00f8d3be40815759f88990385dd3bbaa
    rtmr2: cc76503e991ef1cab9610f1da4f78e87fb36b6b286942f5a67ed343686344bb8f105f9f5e0e7e9d4db8e3bb86a2796f5
    rtmr3: 000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000

    load config json if need to verify remote endpoint.
    {
            "verify_mr_seam":       "off",
            "verify_mrsigner_seam": "off",
            "verify_mr_td": "on",
            "verify_mr_config_id":  "off",
            "verify_mr_owner":      "off",
            "verify_mr_owner_config":       "off",
            "verify_rt_mr0":        "on",
            "verify_rt_mr1":        "on",
            "verify_rt_mr2":        "on",
            "verify_rt_mr3":        "off",
            "tdx_mrs":      [{
                            "mr_seam":      "",
                            "mrsigner_seam":        "",
                            "mr_td":        "",
                            "mr_config_id": "",
                            "mr_owner":     "",
                            "mr_owner_config":      "",
                            "rt_mr0":       "",
                            "rt_mr1":       "",
                            "rt_mr2":       "",
                            "rt_mr3":       ""
                    }]
    }

    Greeter received: hello a! hello b!
    ```

    Note: The `dynamic_config.json` is only worked in server side.

    Server output:

    ```
    Info: tdx_qv_get_quote_supplemental_data_size successfully returned.
    Info: App: tdx_qv_verify_quote successfully returned.
    Info: App: Verification completed successfully.
    remote attestation
    |- mr_td          :  53bb889497b94d99f006db2c9fa35b0504a0c19d52d16cbf780e5c5ed88be1dab3f4cba9224da0742865236d74e889a8
    |- rt_mr0         :  ef723411793cfbe3239def9384ba05d0fa5c8fa5e1154df62729cc6d6eeb50005c14572637b2d664963950c79ab43a94
    |- rt_mr1         :  dbf0be1536a62a90a8a8222b55ef81f4b53046d8b96174120e1e2c5c26ff799b00f8d3be40815759f88990385dd3bbaa
    |- rt_mr2         :  cc76503e991ef1cab9610f1da4f78e87fb36b6b286942f5a67ed343686344bb8f105f9f5e0e7e9d4db8e3bb86a2796f5
    |- rt_mr3         :  000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    |- verify result  :  success
    ```
