from tensorflow.keras.applications.resnet50 import ResNet50
from storage import confidential_storage
import pickle


# https://keras.io/api/applications/#usage-examples-for-image-classification-models
# https://www.tensorflow.org/guide/keras/save_and_serialize
# https://www.tensorflow.org/api_docs/python/tf/keras/models/load_model
# https://github.com/keras-team/keras/blob/master/keras/saving/legacy/saved_model/load.py#L72
def load_resnet50_model(path='/resnet50_weights_tf_dim_ordering_tf_kernels.h5'):
    if path == None:
        model = ResNet50(weights='imagenet')
    else:
        model = ResNet50(weights=None)
        model.load_weights(path)
    model.summary()
    return model

def save_keras_model(model, path, encrypt=True):
    cs = confidential_storage()
    if encrypt:
        cs.input_key('Please input key to encrypt model: ')
    cs.save(model, path, encrypt, True)

def load_keras_model(path, encrypt=True):
    cs = confidential_storage()
    if encrypt:
        cs.input_key('Please input key to decrypt model: ')
    model = cs.load(path, encrypt, True)
    model.summary()
    return model


if __name__ == '__main__':
    model = load_resnet50_model()
    save_keras_model(model, '/resnet50.pkl', False)
    save_keras_model(model, '/resnet50.encrypt.pkl', True)
    print('\n\nWeights data:', str(model.weights)[:1000])
