import os, base64, pickle, argparse
from cryptography.fernet import Fernet

class confidential_storage(object):
    '''
        https://cryptography.io/en/latest/fernet/#csementation
        AES in CBC mode with a 128-bit key for encryption; using PKCS7 padding.
        HMAC using SHA256 for authentication.
    '''
    def __init__(self):
        self.fernet = None
        pass

    def input_key(self, msg):
        self.get_key(input(msg))

    def get_key(self, key):
        print("Get key: %s" % (key))
        key = key.rjust(32, ' ')
        key = base64.urlsafe_b64encode(bytes(key, encoding='utf8'))
        print("Parse key: %s" % (key))
        self.fernet = Fernet(key)

    def load(self, path, decrypt=True, pickling=False):
        with open(path, 'rb') as fp:
            data = fp.read()
            print("Load data from %s" % (path))
        if decrypt:
            data = self.decrypt(data)
        # print(data)
        instance = None
        if pickling:
            instance = pickle.loads(data)
        return instance if instance else data

    def save(self, data, path, encrypt=True, pickling=False):
        if data:
            if pickling:
                data = pickle.dumps(data)
            if encrypt:
                data = self.encrypt(data)
            with open(path, 'wb') as fp:
                fp.write(data)
                print("Save data to %s" % (path))

    def encrypt(self, data):
        if data:
            if self.fernet:
                print("Encrypt data.")
                return self.fernet.encrypt(data)
            else:
                print("Wrong fernet.")

    def decrypt(self, data):
        if data:
            if self.fernet:
                print("Decrypt data.")
                return self.fernet.decrypt(data)
            else:
                print("Wrong fernet.")

def command_arguments():
    parser = argparse.ArgumentParser(description='confidential storage.')
    parser.add_argument(
        '-src',
        '--src',
        type=str,
        required=False,
        default='MovieLens.tags.csv',
        help='The input data path.'
    )
    parser.add_argument(
        '-dst',
        '--dst',
        type=str,
        required=False,
        default='MovieLens.tags.csv.tmp',
        help='The output data path.'
    )
    parser.add_argument(
        '-mode',
        '--mode',
        type=str,
        required=True,
        default='e2o',
        help='Data process mode: e2o(encrypted data to unencrypted original data), e2e, o2e, o2o'
    )
    parser.add_argument(
        '-pickling',
        '--pickling',
        type=int,
        required=True,
        default=False,
        help='File pickling: None, pickle'
    )
    return parser.parse_args()

def main():
    args = command_arguments()
    cs = confidential_storage()

    print("PID:", os.getpid())
    if args.mode == 'o':
        data = cs.load(args.src, False)
        input('Press any key to exit.')
    elif args.mode == 'o2o':
        data = cs.load(args.src, False)
        input('Press any key to exit.')
        if args.src != args.dst:
            cs.save(data, args.dst, False, args.pickling)
    else:
        cs.input_key('Please input symmetric encryption key: ')
        if args.mode == 'e':
            data = cs.load(args.src, True)
            input('Press any key to exit.')
        elif args.mode == 'e2e':
            data = cs.load(args.src, True)
            input('Press any key to exit.')
            if args.src != args.dst:
                cs.save(data, args.dst, True, args.pickling)
        elif args.mode == 'e2o':
            data = cs.load(args.src, True)
            input('Press any key to exit.')
            cs.save(data, args.dst, False, args.pickling)
        elif args.mode == 'o2e':
            data = cs.load(args.src, False)
            input('Press any key to exit.')
            cs.save(data, args.dst, True, args.pickling)

if __name__ == '__main__':
    main()
