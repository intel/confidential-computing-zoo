# 在CCP平台上运行clf_client服务
本文档是关于在CCP平台上构建CLF中的clf_client镜像并运行该镜像的说明文档,详细阐述了用户在CCP平台上运行clf_client镜像服务的过程.

## 背景信息
- Cross-language Framework(基于Gramine和Intel SGX的跨数据框架)是提供不同机器之间的非C语言程序的远程认证和数据/密钥传输服务的框架.但多方用户各自拥有部分机密数据,需要在不泄露数据的前提下,进行合作共同运算模型的时候,用户可以使用该框架.CLF框架主要由clf_server端和clf_client端两部分构成,具备Intel SGX功能的可以提供可信执行环境的为clf_client端,clf_client端只有一个, 保存有机密数据的为clf_server端,可以同时存在多个clf_server端.
- CLF主要就是实现了以下功能,一是对于非C语言的程序的远程认证,clf_server端确定clf_client端处于安全环境中,才能进行数据传输,二是提供对数据和密钥及密钥进行加解密的模块.方便用户使用.
- 使用过程中,clf_client端会主动向clf_server端发出传输数据的请求,并且将对数据进行处理的可信执行环境的信息(enclave)发给clf_server端,让clf_server进行校验,在校验通过后,clf_server会将本地机密数据加密,通过安全信道传输给clf_client,随后,来自一方或者多方clf_server的数据,在clf_client端的enclave中进行解密和运算,再将最后结果加密传输回clf_server端.
## 环境配置信息
- 操作系统:Ubuntu 20.04或者Ubuntu18.04.
- Docker引擎: Docker是一个开源的容器服务,可以将您的应用程序容器化,请参考 [引导](https://docs.docker.com/engine/install/ubuntu/#install-using-the-convenience-script)来安装Docker服务.
- 规格:加密内存>=4G
## 技术架构
图片1(ps1.png "技术架构")
本框架的实践依赖于两个角色,保存有原始数据的服务端以及具备SGX能力的对数据进行运算的客户端.
- **客户端** 客户端是具备SGX能力的,可以在enclave环境中,对来自服务端的数据进行运算,并将运算结果加密传输回服务端.但有需要的时候,客户端会向服务端发出请求,请求中包含远程认证所需要的身份信息,以及请求的数据文件的目录和大小,在服务端通过远程认证后,将对应的数据和密钥通过安全信道传输给客户端,然后客户端在可行执行环境中,对数据进行运算,最后再将结果进行加密,传输回服务端.
- **服务端** 每个服务端拥有一部分的机密的数据,多个服务端可以在经过远程认证的值得信赖的客户端上,服务端在对客户端的远程认证通过之后,才会将数据和密钥传输给客户端,每次传输数据结束后,和客户端的链接会断开,在下次收到客户端的请求后,重新对客户端进行远程认证,再进行链接.
## 基于CCP部署CLF框架
### 1. 准备工作
在机器上,首先下载如下开源文件:
```
git clone https://github.com/intel/confidential-computing-zoo.git
```

### 2. 创建clf_client镜像
 ```
 cd <confidential-computing-zoo dir>/confidential-computing-zoo/cczoo/cross_lang_framework/docker/
 ./build_clf_client_docker_image.sh
 ```
请注意,目录 `<confidential-computing-zoo dir>/confidential-computing-zoo/cczoo/cross_lang_framework/docker/`下的`clf_client.dockerfile`文件所创建的Docker镜像只能运行CLF
提供的应用程序Java样例.在实际使用中,用户需要对该dockerfile文件进行修改,替换成自己所需要的应用程序,具体需要修改的地方位于dockerfile文件末尾,为
 ```
    && cd ${CLF_PATH}/cczoo/cross_lang_framework/clf_client/app \
    && git diff clf_test.java \
    && GRAMINEDIR=/gramine SGX_SIGNER_KEY=${HOME}/.config/gramine/enclave-key.pem make SGX=1
 ```
文件`build_clf_server_docker_image.sh`可接受两个用户传递的参数,第一个参数是镜像的操作系统版本(现在只可以是ubuntu:18.04或者ubuntu20.04),在不指定参数的情况下默认为ubuntu:20.04,
第二个参数是镜像的标签名,默认为`clf-server:gramine1.3-ubuntu20.04`,
如果您的应用程序对于操作系统有要求的话,可以更换成ubuntu18.04(暂时只支持ubuntu20.04和Ubuntu18.04),指定操作系统和同步更换镜像标签的操作步骤如下,
 ```
 os_version=ubuntu:18.04
 image_tag= clf-server:gramine1.3-ubuntu18.04
 ./build_clf_server_docker_image.sh ${os_version} ${image_tag}
 ```

 另外,如果你想要直接运行clf_client镜像,你可以直接运行指令 `./start_clf_client_conatiner.sh`.

### 3. 打包clf_client镜像

 如果用户想要在CCP平台上使用clf_client镜像,首先需要使用`ccp-cli pack`对刚刚创建的镜像进行打包.
 
 请进入目录 `<confidential-computing-zoo dir>/confidential-computing-zoo/cczoo/cross_lang_framework/ccp/`, 
 该目录下存在可执行文件`converct_clf_client_to_ccp_image.sh`.直接运行该文件,会直接输出两个指令,输出的第一个指令实现打包clf-client镜像的功能

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
 在使用这个指令的时候,参数`app-entry`,`app-type`和`start`是和用户需要运行的应用程序相关的,`memsize`和`thread`都可以是用户根据需求自己定义的,
 而参数`secret-key`和`secret-id`则是和用户的腾讯云平台上的账户和密码相关,参数`capp-id`是该镜像在CCP平台上所对应实例的ID,
 参数`app-image`是用户之间创建的`clf-client`镜像的标签, 默认是`clf-client:gramine1.3-ubuntu20.04`.
 ### 4. 运行clf_client镜像 
 运行脚本`converct_clf_client_to_ccp_image.sh`输出的第二个指令实现运行clf-client镜像的功能
 ``` 
 docker run -ti --device /dev/sgx_enclave --device /dev/sgx_provision
             --add-host=VM-30-8-ubuntu:10.0.30.8 clf-client:gramine1.3-ubuntu20.04
             -Xmx4G clf_test VM-30-8-ubuntu
 ```
 这个指令的作用是将CCP平台上的clf-client镜像运行起来,
 - 参数`p`是端口号,默认是4433端口,由于clf-server的镜像功能实现依赖于intel的SGX,
 所以需要将设备`/dev/sgx_enclave和/dev/sgx_provision`映射进去.
 - 参数`add-host`则是为了让容器识别主机,当用户使用时,需要根据自己的需要替换主机的用户名和ip地址.
 - ` -Xmx4G clf_test`则是需要运行的具体程序,用户需要根据自己的需求对这部分进行修改.
  
 
