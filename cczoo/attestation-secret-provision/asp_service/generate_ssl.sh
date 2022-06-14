CA_CN="My Cert Authority"
SERVER_CN=""

while getopts ":a:s:" opt
do
    case $opt in
        a)
        echo "////////CA CN:$OPTARG////////"
        CA_CN=$OPTARG
        ;;
        s)
        echo "////////Server CN:$OPTARG////////"
        SERVER_CN=$OPTARG
        ;;
        ?)
        echo "////////Undefined:$OPTARG////////"
        exit 1;;
    esac
done

# Generate CA Key and Certificate
openssl req -x509 -sha256 -newkey rsa:4096 -keyout ca.key -out ca.crt -days 356 -nodes -subj "/CN=${CA_CN}"

# Generate Server Key
openssl req -new -newkey rsa:4096 -keyout server.key -out server.csr -nodes -subj "/CN=${SERVER_CN}"

# Sign Server Certificate with CA Certificate
openssl x509 -req -sha256 -days 365 -in server.csr -CA ca.crt -CAkey ca.key -set_serial 01 -out server.crt

chmod 600 -R *.key
