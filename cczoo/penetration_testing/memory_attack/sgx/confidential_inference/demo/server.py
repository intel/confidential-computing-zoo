import os, pickle, argparse
import numpy as np
from flask import Flask, request, jsonify
from tensorflow.keras.preprocessing import image
from tensorflow.keras.applications.resnet50 import preprocess_input, decode_predictions

from storage import confidential_storage
from models import load_keras_model
from utils import *


class infer_engine(object):
    def __init__(self):
        self.model = None
        self.model_weights_str = None

    def load_model(self):
        if not self.model:
            try:
                path = '/resnet50.encrypt.pkl'
                self.model = load_keras_model(path, False)
                print('load model:', path)
            except:
                print('Can not load this model, please input key to decrypt it!\n')

        if not self.model:
            try:
                path = '/resnet50.encrypt.pkl'
                self.model = load_keras_model(path, True)
                print('load model:', path)
            except:
                print('This is a wrong model, please re-pickle it!\n')
                exit()

        self.model_weights_str = str(self.model.weights)

    def predict(self, x, n=3):
        x = np.expand_dims(x, axis=0)
        y = self.model.predict(x)
        y = decode_predictions(y, top=n)[0]
        top_n =[]
        for top_x in y:
            top_list = []
            for arg in top_x:
                top_list.append(str(arg))
            top_n.append(top_list)
        return top_n

    def local_predict(self, path='/dataset/goldfish.jfif'):
        y = self.predict(load_image(path))
        print('Predicted:', y)
        return y

def register_service(app, engine):
    @app.route("/", methods=['POST', 'GET'])
    def app_index():
        return 'AI Inferernce Service'

    @app.route('/infer', methods=['POST'])
    def app_predict():
        img_str = request.form.get('image')
        x = decode_image(img_str)
        y = engine.predict(x)
        response = {'class': y}
        # print(response)
        return response

def main(args):
    print("PID: %s\n" % (os.getpid()))

    engine = infer_engine()
    engine.load_model()

    app = Flask(__name__)
    register_service(app, engine)

    if args.cert != 'none' and args.key != 'none':
        print('Start with SSL/TLS.')
        app.run(host=args.host, port=args.port, ssl_context=(args.cert, args.key))
    else:
        print('Start without SSL/TLS.')
        app.run(host=args.host, port=args.port)

def command_arguments():
    parser = argparse.ArgumentParser(description='AI Inference Server.')
    parser.add_argument(
        '-host',
        '--host',
        type=str,
        required=False,
        default='0.0.0.0',
        help='The server listen address'
    )
    parser.add_argument(
        '-port',
        '--port',
        type=int,
        required=False,
        default=8091,
        help='The server listen port'
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
        '-key',
        '--key',
        type=str,
        required=False,
        default='/key.pem',
        help='The server key'
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = command_arguments()
    main(args)
