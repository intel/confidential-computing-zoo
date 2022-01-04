# Ingress Nginx
Kubernetes has a built in configuration object for HTTP load balancing, called
[Ingress Nginx](https://kubernetes.io/docs/concepts/services-networking/ingress/)
, that defines rules for external connectivity to the pods represented by one
or more Kubernetes services. When you need to provide external access to your
Kubernetes services, you can create an Ingress resource that defines the connectivity
rules, including the URI path, backing service name, and other information.
The Ingress controller then automatically configures a frontend load balancer to
implement the Ingress rules.

# Deploy service
```
kubectl apply -f ./deploy-nodeport.yaml
```

# Delete service
```
kubectl delete -f ./deploy-nodeport.yaml
```

# Check status
```
kubectl get -n ingress-nginx service/ingress-nginx-controller -o yaml

kubectl get -n ingress-nginx deployment.apps/ingress-nginx-controller -o yaml
```
