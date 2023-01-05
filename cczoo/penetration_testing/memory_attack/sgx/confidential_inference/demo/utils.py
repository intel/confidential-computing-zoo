from tensorflow.keras.preprocessing import image

import random, string, base64, io, cv2
from PIL import Image
import numpy as np


def gen_id(length=32):
    return ''.join(random.sample(string.ascii_letters + string.digits, length))

def load_image(path='/dataset/goldfish.jfif'):
    img = image.load_img(path, target_size=(224, 224))
    return image.img_to_array(img)

def encode_image(path):
    img = load_image(path)
    img_str = base64.b64encode(img).decode('utf-8')
    return img_str

def decode_image(img_str):
    img_str = base64.b64decode(img_str)
    nparr = np.frombuffer(img_str, np.float32)
    nparr = nparr.reshape(224,224,3)
    return nparr
