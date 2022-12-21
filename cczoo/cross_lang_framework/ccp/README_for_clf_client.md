# 在CCP平台上运行clf_server服务
本文档是关于在CCP平台上构建CLF框架中的clf_server镜像并运行该镜像的说明文档,阐述了用户在CCP平台上运行clf_server镜像服务的过程.

## CLF技术架构
Cross language Framework（CLF），基于Gramine和Intel SGX技术，是提供不同机器之间的非C语言程序的远程认证和数据/密钥读写和传输服务的框架. 多个参与方各自拥有部分机密数据进行合作共同运算而不泄露数据给对方,做到数据可用不可见. CLF框架主要由clf_server端和clf_client端两部分构成：
- **clf_client端**，具备Intel SGX功能的可以提供可信执行环境的为clf_client端, clf_client端只有一个, 运行着多方机密计算的程序；
- **clf_server端**，保存有机密数据的为clf_server端，供clf_client读写数据。每次读写数据都会先自动验证clf_client的合法性，即为SGX的可信执行环境（enclave），认证通过之后才会运行数据的读写。一套解决方案中可以同时存在多个clf_server端

## 环境配置信息
- Kernel: 版本5.11及以上.
- 需安装Docker: 请参考 [引导](https://docs.docker.com/engine/install/ubuntu/#install-using-the-convenience-script)来安装Docker服务.
- 规格: 选择内存型中的M6ce机型，加密内存>=4G

## 基于CCP部署CLF框架之客户端
### 1. 准备工作
在机器上,首先下载如下开源库:
```
git clone https://github.com/intel/confidential-computing-zoo.git
```

### 2. 创建clf_client镜像
 ```
 cd <confidential-computing-zoo dir>/confidential-computing-zoo/cczoo/cross_lang_framework/docker/
 ./build_clf_client_docker_image.sh        #生成clf_client sdk镜像
 ./build_clf_client_app_docker_image.sh    #生成sample app镜像，**实际应用中此处应该替换成用户实际的基于clf_client sdk开发的app**
 ```

### 3. 打包成CCP镜像
 ```
 ccp-cli pack --app-entry="/usr/bin/java"
             --memsize=8192M --thread=64
             --tmpl=clf_client
             --secret-id=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
             --secret-key=kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk
             --capp-id=capp-ODdjZWZhOWYt
             --app-image=clf-client:gramine1.3-ubuntu20.04
             --app-type=image
             --start=/clf/cczoo/cross_lang_framework/clf_client/app
 ```
 - `memsize`和`thread`可以根据用户APP实际需求自己定义
 - `secret-key`，`secret-id`，`capp-id`根据用户在CCP平台上的账户和实例ID填写
 - 其余参数保持默认即可
 
 ### 4. 运行clf_client镜像 
 ```
 docker run -ti --device /dev/sgx_enclave --device /dev/sgx_provision
             --add-host=<clf_server_hostname>:<clf_server_ip> clf-client:gramine1.3-ubuntu20.04
             -Xmx4G clf_test <clf_server_hostname>
 ```
 这个指令的作用是将CCP平台上的clf-client镜像运行起来
 - `--device`, CCP镜像依赖于intel的SGX, 需要将设备`/dev/sgx_enclave和/dev/sgx_provision`映射进container.
 - `add-host`，为了让容器识别clf_server的主机名, 需要根据自己的需要将主机名和ip地址的匹配关系映射进container
 - ` -Xmx4G clf_test <clf_server_hostname>` app具体需要的参数, 用户需要根据自己的APP参数对这部分进行修改
 
 CLF开发和配置细节请参考 [CLF文档](https://github.com/intel/confidential-computing-zoo/blob/main/cczoo/cross_lang_framework/README.md)
