# Apply patch on trustee

1.download trustee
   ```sh
   git clone https://github.com/confidential-containers/trustee.git
   ```

2.download patchfile and put it in the same directory as open-webui
   ```sh
   git apply --directory=trustee/ xxx.patch
   ```
 
**NOTE**
Please make sure you trustee is basic on feature/v0.13.0
