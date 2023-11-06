#!/bin/bash

git clone -b v1.38.1 https://github.com/grpc/grpc temp
cp -r common/* temp/
cp -r v1.38.1/* temp/
cd temp
git add -A
git diff -p --staged > ../grpc_ratls.patch
cd ..
rm -rf temp
