set -ex

# Need to execute before build ${GRPC_PATH} source code

cd ${GRPC_PATH}

echo "build/
*.patch" >> .gitignore

git add .gitignore

git add BUILD
git add setup.py
git add CMakeLists.txt
git add bazel

git add include
git add src
git add examples

git add *.sh
git add *.json

git config user.name "CCZOO"
git config user.email "None"

git commit -m 'Add RA-TLS support'
git format-patch HEAD^
git reset --soft HEAD^

cd -
