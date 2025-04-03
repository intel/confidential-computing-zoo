# Apply patch on open-webui

1.download open-webui
   ```sh
   git clone https://github.com/xxxxx/open-webui.git
   ```

2.download patchfile and put it in the same directory as open-webui
   ```sh
   git apply --directory=open-webui/ xxx.patch
   ```
 
**NOTE**
Please make sure you open-webui is basic on feature/v0.5.20-cllm.
