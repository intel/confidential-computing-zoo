### With SGX
```python
test-sgx.sh ps0
test-sgx.sh worker0
test-sgx.sh worker1
test-sgx.sh worker2
test-sgx.sh worker3
```

### Native
```python
taskset -c 0-11 python3 ps0.py
taskset -c 12-23 python3 worker0.py
taskset -c 24-35 python3 worker1.py
taskset -c 36-47 python3 worker2.py
taskset -c 48-59 python3 worker3.py
```
