SERVER_CN=$1

rm -rf ssl_configure
mkdir -p ssl_configure/server

cd ssl_configure

# https://kubernetes.github.io/ingress-nginx/examples/PREREQUISITES/#client-certificate-authentication

# Generate Server key and certificate
openssl req -x509 -sha256 -nodes -days 365 -newkey rsa:2048 -out server/cert.pem -keyout server/key.pem -subj "/CN=${SERVER_CN}"

# Generate ssl configure
echo "server_key: '`cat server/key.pem | paste -d "" -s`'" >> ssl.cfg
echo "server_cert: '`cat server/cert.pem | paste -d "" -s`'" >> ssl.cfg
echo "custom_ca: ''" >> ssl.cfg
echo "client_verify: false" >> ssl.cfg

sed -i "s/-----BEGIN PRIVATE KEY-----/-----BEGIN PRIVATE KEY-----\\\n/g" ssl.cfg
sed -i "s/-----END PRIVATE KEY-----/\\\n-----END PRIVATE KEY-----/g" ssl.cfg
sed -i "s/-----BEGIN CERTIFICATE-----/-----BEGIN CERTIFICATE-----\\\n/g" ssl.cfg
sed -i "s/-----END CERTIFICATE-----/\\\n-----END CERTIFICATE-----/g" ssl.cfg

cat ssl.cfg

cd -