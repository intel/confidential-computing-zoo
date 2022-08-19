#
# Copyright (c) 2021 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import numpy as np
import tempfile
import tensorflow.compat.v1 as tf
import resnet_model
import cifar10_input
import math
import time

tf.disable_eager_execution()

# Configuration of cluster 

tf.app.flags.DEFINE_string("job_name", "worker", "'ps' or 'worker'")
tf.app.flags.DEFINE_integer("task_index", 0, "Index of task within the job")
tf.app.flags.DEFINE_string("ps_hosts", "['localhost:60002']", "ps hosts")
tf.app.flags.DEFINE_string("worker_hosts", "['localhost:61002','localhost:61003']", "worker hosts")

FLAGS = tf.app.flags.FLAGS

ps_hosts = eval(FLAGS.ps_hosts)
worker_hosts = eval(FLAGS.worker_hosts)

# cluster = tf.train.ClusterSpec({"ps": ps_hosts, "worker": worker_hosts})
cluster = tf.train.ClusterSpec({"ps": ps_hosts, "worker": worker_hosts})


def get_batch(x_train, y_train, batch_size):
    # num_epochs = 128
    train_dataset = tf.data.Dataset.from_tensor_slices((x_train,y_train))
    train_dataset = (train_dataset
                .shuffle(50000)
                .batch(batch_size, drop_remainder=True))
                # .repeat(num_epochs))
    print(train_dataset)
    return train_dataset

def get_data():
    cifar10 = tf.keras.datasets.cifar10
    (x_train,y_train),(x_test,y_test) = cifar10.load_data()
    # x_train = preprocess_image(x_train)
    return x_train, y_train

def preprocess_image(image):
    """Preprocess a single image of layout [height, width, depth]."""
    HEIGHT = 32
    WIDTH = 32
    NUM_CHANNELS = 3
    # Resize the image to add four extra pixels on each side.
    image = tf.image.resize_image_with_crop_or_pad(
        image, HEIGHT + 8, WIDTH + 8)

    # Randomly crop a [HEIGHT, WIDTH] section of the image.
    image = tf.random_crop(image, [HEIGHT, WIDTH, NUM_CHANNELS])

    # Randomly flip the image horizontally.
    image = tf.image.random_flip_left_right(image)

    # Subtract off the mean and divide by the variance of the pixels.
    image = tf.image.per_image_standardization(image)
    return image

def generate_data(batch_size):
    x_batch = np.random.rand(batch_size, 24, 24, 3).astype(np.float32)
    arr = np.random.randint(low=0,high=9,size=batch_size)
    y_batch = np.eye(10)[arr]
    return x_batch, y_batch

class Cifar10Model(resnet_model.Model):
    """Model class with appropriate defaults for CIFAR-10 data."""
    def __init__(self, resnet_size=56, data_format=None, num_classes=10,
                resnet_version=resnet_model.DEFAULT_VERSION,
                dtype=resnet_model.DEFAULT_DTYPE):
        """These are the parameters that work for CIFAR-10 data.

        Args:
        resnet_size: The number of convolutional layers needed in the model.
        data_format: Either 'channels_first' or 'channels_last', specifying which
            data format to use when setting up the model.
        num_classes: The number of output classes needed from the model. This
            enables users to extend the same model to their own datasets.
        resnet_version: Integer representing which version of the ResNet network
        to use. See README for details. Valid values: [1, 2]
        dtype: The TensorFlow dtype to use for calculations.

        Raises:
        ValueError: if invalid resnet_size is chosen
        """
        if resnet_size % 6 != 2:
            raise ValueError('resnet_size must be 6n + 2:', resnet_size)

        num_blocks = (resnet_size - 2) // 6

        super(Cifar10Model, self).__init__(
            resnet_size=resnet_size,
            bottleneck=False,
            num_classes=num_classes,
            num_filters=16,
            kernel_size=3,
            conv_stride=1,
            first_pool_size=None,
            first_pool_stride=None,
            block_sizes=[num_blocks] * 3,
            block_strides=[1, 2, 2],
            resnet_version=resnet_version,
            data_format=data_format,
            dtype=dtype
        )

def learning_rate_with_decay(
    batch_size, batch_denom, num_images, boundary_epochs, decay_rates,
    base_lr=0.1, warmup=False):
    """Get a learning rate that decays step-wise as training progresses.

    Args:
        batch_size: the number of examples processed in each training batch.
        batch_denom: this value will be used to scale the base learning rate.
        `0.1 * batch size` is divided by this number, such that when
        batch_denom == batch_size, the initial learning rate will be 0.1.
        num_images: total number of images that will be used for training.
        boundary_epochs: list of ints representing the epochs at which we
        decay the learning rate.
        decay_rates: list of floats representing the decay rates to be used
        for scaling the learning rate. It should have one more element
        than `boundary_epochs`, and all elements should have the same type.
        base_lr: Initial learning rate scaled based on batch_denom.
        warmup: Run a 5 epoch warmup to the initial lr.
    Returns:
        Returns a function that takes a single argument - the number of batches
        trained so far (global_step)- and returns the learning rate to be used
        for training the next batch.
    """
    initial_learning_rate = base_lr * batch_size / batch_denom
    batches_per_epoch = num_images / batch_size

    # Reduce the learning rate at certain epochs.
    # CIFAR-10: divide by 10 at epoch 100, 150, and 200
    # ImageNet: divide by 10 at epoch 30, 60, 80, and 90
    boundaries = [int(batches_per_epoch * epoch) for epoch in boundary_epochs]
    vals = [initial_learning_rate * decay for decay in decay_rates]

    def learning_rate_fn(global_step):
        """Builds scaled learning rate function with 5 epoch warm up."""
        lr = tf.train.piecewise_constant(global_step, boundaries, vals)
        if warmup:
            warmup_steps = int(batches_per_epoch * 5)
            warmup_lr = (
                initial_learning_rate * tf.cast(global_step, tf.float32) / tf.cast(
                    warmup_steps, tf.float32))
            return tf.cond(global_step < warmup_steps, lambda: warmup_lr, lambda: lr)
        return lr
    return learning_rate_fn
    
def train():
    server = tf.train.Server(cluster,
        job_name=FLAGS.job_name,
        task_index=FLAGS.task_index)
    if FLAGS.job_name == "ps":
        server.join()
    elif FLAGS.job_name == "worker":
        with tf.device(tf.train.replica_device_setter(
            worker_device="/job:worker/task:%d" % FLAGS.task_index,
            cluster=cluster)):
            load_start_time = time.time()
            path = "cifar-10-batches-bin"
            batch_size = 128
            images_train,labels_train = cifar10_input.distorted_inputs(path,batch_size=batch_size)
            
            features = tf.placeholder(tf.float32, [None, 24, 24, 3])
            labels = tf.placeholder(tf.int64, [None])
            model = Cifar10Model()
            logits = model(features, training=True)
            logits = tf.cast(logits, tf.float32)

            cross_entropy = tf.losses.sparse_softmax_cross_entropy(
                logits=logits, labels=labels)
            weight_decay = 2e-4
            
            loss_filter_fn = None
            def exclude_batch_norm(name):
                return 'batch_normalization' not in name
            loss_filter_fn = loss_filter_fn or exclude_batch_norm

            # Add weight decay to the loss.
            l2_loss = weight_decay * tf.add_n(
                # loss is computed using fp32 for numerical stability.
                [tf.nn.l2_loss(tf.cast(v, tf.float32)) for v in tf.trainable_variables()
                if loss_filter_fn(v.name)])
            tf.summary.scalar('l2_loss', l2_loss)
            loss = cross_entropy + l2_loss

            learning_rate_fn = learning_rate_with_decay(batch_size=batch_size, batch_denom=128,
            num_images=50000, boundary_epochs=[91, 136, 182], decay_rates=[1, 0.1, 0.01, 0.001])

            global_step = tf.train.get_or_create_global_step()
            learning_rate = learning_rate_fn(global_step)
            train_epochs=20

            optimizer = tf.train.MomentumOptimizer(learning_rate=learning_rate, momentum=0.9)
            train_op = optimizer.minimize(loss, global_step=global_step)

            graph_location = tempfile.mkdtemp()
            print('Saving graph to: %s' % graph_location)
            train_writer = tf.summary.FileWriter(graph_location)
            train_writer.add_graph(tf.get_default_graph())
            init_op = tf.global_variables_initializer()

        config = tf.ConfigProto(intra_op_parallelism_threads=4, inter_op_parallelism_threads=4)

        with tf.train.MonitoredTrainingSession(master="grpc://" + worker_hosts[FLAGS.task_index],
                                            is_chief=(FLAGS.task_index==0),
                                            checkpoint_dir="model",
                                            save_checkpoint_steps=400,
                                            config=config,
                                            ) as mon_sess:
            load_end_time = time.time()
            load_time = load_end_time - load_start_time
            print("load time: %.3f" %load_time) 
            for i in range(int(train_epochs/len(worker_hosts))):
                for _ in range(int(50000/batch_size)):
                    iter_start_time = time.time()
                    x_batch, y_batch = mon_sess.run([images_train,labels_train])
                    _, step, loss_v, logits_, labels_, = mon_sess.run([train_op, global_step, loss, logits, labels], feed_dict={features: x_batch, labels: y_batch})
                    iter_end_time = time.time()
                    iter_time = iter_end_time-iter_start_time
                    if step % 1 == 0:
                        print("step: %d, loss: %f, iter time: %.3f" %(step, loss_v, iter_time))
            print("Optimization finished.")

def main(_):
    train()

if __name__ == '__main__':
    tf.app.run(main=main)
