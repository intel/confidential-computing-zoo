SERVER_CN=$1
CLIENT_CN=$2
CA_CN="My Cert Authority"

rm -rf ssl_configure
mkdir -p ssl_configure/server
mkdir -p ssl_configure/client

cd ssl_configure

# Generate CA key and certificate
openssl req -x509 -sha256 -nodes -days 356 -newkey rsa:4096 -out ca_cert.pem -keyout ca_key.pem -subj "/CN=${CA_CN}"

openssl req -new -newkey rsa:4096 -keyout server/key.pem -out server/cert.csr -nodes -subj "/CN=${SERVER_CN}"
openssl x509 -req -sha256 -days 365 -in server/cert.csr -CA ca_cert.pem -CAkey ca_key.pem -set_serial 01 -out server/cert.pem

# Generate Client key and certificate signed by CA Certificate
openssl req -new -newkey rsa:4096 -keyout client/key.pem -out client/cert.csr -nodes -subj "/CN=${CLIENT_CN}"
openssl x509 -req -sha256 -days 365 -in client/cert.csr -CA ca_cert.pem -CAkey ca_key.pem -set_serial 01 -out client/cert.pem

# Generate ssl configure
echo "server_key: '`cat server/key.pem | paste -d "" -s`'" >> ssl.cfg
echo "server_cert: '`cat server/cert.pem | paste -d "" -s`'" >> ssl.cfg
echo "custom_ca: '`cat ca_cert.pem | paste -d "" -s`'" >> ssl.cfg
echo "client_verify: true" >> ssl.cfg

sed -i "s/-----BEGIN PRIVATE KEY-----/-----BEGIN PRIVATE KEY-----\\\n/g" ssl.cfg
sed -i "s/-----END PRIVATE KEY-----/\\\n-----END PRIVATE KEY-----/g" ssl.cfg
sed -i "s/-----BEGIN CERTIFICATE-----/-----BEGIN CERTIFICATE-----\\\n/g" ssl.cfg
sed -i "s/-----END CERTIFICATE-----/\\\n-----END CERTIFICATE-----/g" ssl.cfg

cat ssl.cfg

cd -
