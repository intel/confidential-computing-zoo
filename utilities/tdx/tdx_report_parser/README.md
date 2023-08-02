# TDX Report Generate and Parse Tool

## Setup Compile Dependencies

For Ubuntu 22.04

```
echo "deb [arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu jammy main" > /etc/apt/sources.list.d/intel-sgx.list
apt update
apt install -y libtdx-attest libtdx-attest-dev
```

For RHEL 8.x

```
wget https://download.01.org/intel-sgx/sgx-dcap/${DCAP_VERSION}/linux/distro/rhel8.6-server/sgx_rpm_local_repo.tgz

tar -zxvf sgx_rpm_local_repo.tar.gz
mv sgx_rpm_local_repo /srv/sgx_rpm_local_repo

# Setup local RPM repository
cat <<EOF >> /etc/yum.repos.d/tdx-attestation.repo
[tdx-attestation-local]
name=tdx-attestation-local
baseurl=file:///srv/sgx_rpm_local_repo
enabled=1
gpgcheck=0
module_hotfixes=true
EOF

dnf check-update
dnf install -y libtdx-attest libtdx-attest-devel
```

## Build

```
make
```

## Program Flags

"-p" or "--path": load or save tdx report file path.

"-m" or "--mode": run mode.
- gen mode (-m=0): generate tdx report to file, must be executed in the TDX enabled ENV.
- gen and parse mode (-m=1): generate and parse tdx report, must be executed in the TDX enabled ENV.
- parse mode (-m=2): parse tdx report from file, could be executed in the TDX enabled and disabled ENV.

## Get TDX Report

One step to get TDX report:
1. gen and parse tdx report (TDX enabled ENV)

    ```
    ./tdx_report.out
    # or
    ./tdx_report.out -m=1
    ```

Two steps to get TDX report:
1. gen tdx report to file (TDX enabled ENV)

    ```
    ./tdx_report.out -m=0 -p="tdx_report.data"
    ```

2. parse tdx report from file (TDX enabled and disabled ENV)

    ```
    ./tdx_report.out -m=2 -p="tdx_report.data"
    ```
