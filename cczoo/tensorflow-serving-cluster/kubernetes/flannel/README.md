# Flannel
Flannel is a simple and easy way to configure a layer 3 network fabric designed
for Kubernetes. Before pods using the pod network are started, Kubernetes will
add flannel to the Kubernetes cluster.

# Deploy service

```
kubectl apply -f ./deploy.yaml
```

# Delete service

```
kubectl delete -f ./deploy.yaml
```
