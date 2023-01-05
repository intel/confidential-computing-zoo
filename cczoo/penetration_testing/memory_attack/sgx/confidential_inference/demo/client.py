import argparse
import urllib.request, ssl

from utils import *


def main(args):
    if args.cert != 'none':
        print('Start with SSL/TLS.')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(args.cert)
    else:
        print('Start without SSL/TLS.')
        context = None

    try:
        request = urllib.request.Request(args.host, method='GET')
        response = urllib.request.urlopen(request, context=context)
        print('Status: %d, Response: %s' % (response.code, response.read().decode("utf-8")))
    except Exception as ex:
        print("Found Error in auth phase: %s" % str(ex))

    try:
        img_str = encode_image(args.image)
        data = urllib.parse.urlencode({ 'image': img_str }).encode('utf-8')
        request = urllib.request.Request(args.host+'/infer', data=data, method='POST')
        response = urllib.request.urlopen(request, context=context)
        print('Status: %d, Response: %s' % (response.code, response.read().decode("utf-8")))
        print('image strings:', img_str[:150])
    except Exception as ex:
        print("Found Error in auth phase:%s" % str(ex))

def command_arguments():
    parser = argparse.ArgumentParser(description='AI Inference client.')
    parser.add_argument(
        '-host',
        '--host',
        type=str,
        required=False,
        default='https://infer.service.com:8091',
        help='The server address'
    )
    parser.add_argument(
        '-cert',
        '--cert',
        type=str,
        required=False,
        default='/cert.pem',
        help='The server Certificate'
    )
    parser.add_argument(
        '-image',
        '--image',
        type=str,
        required=False,
        default='/dataset/goldfish.jfif',
        help='The image path'
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = command_arguments()
    main(args)
