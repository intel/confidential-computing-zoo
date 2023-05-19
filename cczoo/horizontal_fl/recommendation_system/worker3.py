import time

import tensorflow._api.v2.compat.v1 as tf
import pandas as pd
from sklearn import preprocessing
import numpy as np

from tensorflow.keras.utils import to_categorical
import matplotlib.pyplot as plt

import pickle
import random
import os

tf.disable_eager_execution()

tf.app.flags.DEFINE_string("job_name", "worker", "'ps' or 'worker'")
tf.app.flags.DEFINE_integer("task_index", 3, "Index of task within the job")
tf.app.flags.DEFINE_string("ps_hosts", "['localhost:70002']", "ps hosts")
tf.app.flags.DEFINE_string("worker_hosts", "['localhost:71002','localhost:71003','localhost:71004','localhost:71005']", "worker hosts")

FLAGS = tf.app.flags.FLAGS

ps_hosts = eval(FLAGS.ps_hosts)
worker_hosts = eval(FLAGS.worker_hosts)

cluster = tf.train.ClusterSpec({"ps": ps_hosts, "worker": worker_hosts})


def criteo_dataprocessing_sample():
    columns = ['label', *(f'I{i}' for i in range(1, 14)), *(f'C{i}' for i in range(1, 27))]
    df = pd.read_csv('dataset/train.txt', sep='\t', names=columns).fillna(0)
    print(df)

    # Preprocess Dense Features
    dense_cols = [c for c in columns if 'I' in c]
    df[dense_cols] = preprocessing.StandardScaler().fit_transform(df[dense_cols])
    print(df)

    # Preprocess Categorical Features
    cat_cols = [c for c in columns if 'C' in c]
    mappings = {
        col: dict(zip(values, range(len(values))))
        for col, values in map(lambda col: (col, df[col].unique()), cat_cols)
    }
    for col, mapping in mappings.items():
        df[col] = df[col].map(mapping.get)

    print(df)

    label_counts = df.groupby('label')['I1'].count()
    print(f'Baseline: {max(label_counts.values) / sum(label_counts.values) * 100}%')

    dense_cols = [c for c in df.columns if 'I' in c]
    cat_cols = [c for c in df.columns if 'C' in c]
    emb_counts = [len(df[c].unique()) for c in cat_cols]

    df_train = df[int(len(df) / 7):]
    df_train = df_train[int(len(df_train) / 2):-1]
    df_val = df[0:int(len(df) / 7)]
    df_test = df_val
    print(f"Train size: {len(df_train)}, Val Size: {len(df_val)}")

    ds = tf.data.Dataset.zip((
        tf.data.Dataset.from_tensor_slices((
            tf.cast(df_train[dense_cols].values, tf.float32),
            tf.cast(df_train[cat_cols].values, tf.int32),
        )),
        tf.data.Dataset.from_tensor_slices((
            tf.cast(to_categorical(df_train['label'].values, num_classes=2), tf.float32)
        ))
    )).shuffle(buffer_size=2048)

    ds_val = tf.data.Dataset.zip((
        tf.data.Dataset.from_tensor_slices((
            tf.cast(df_val[dense_cols].values, tf.float32),
            tf.cast(df_val[cat_cols].values, tf.int32),
        )),
        tf.data.Dataset.from_tensor_slices((
            tf.cast(to_categorical(df_val['label'].values, num_classes=2), tf.float32)
        ))
    )).shuffle(buffer_size=2048)

    ds_test = tf.data.Dataset.zip((
        tf.data.Dataset.from_tensor_slices((
            tf.cast(df_test[dense_cols].values, tf.float32),
            tf.cast(df_test[cat_cols].values, tf.int32),
        )),
        tf.data.Dataset.from_tensor_slices((
            tf.cast(to_categorical(df_test['label'].values, num_classes=2), tf.float32)
        ))
    )).shuffle(buffer_size=2048)

    len_train = len(df_train)
    len_val = len(df_val)
    len_test = len(df_test)

    return emb_counts, len_train, len_val, len_test, ds, ds_val, ds_test


def MLP(arch, activation='relu', out_activation=None):
    mlp = tf.keras.Sequential()

    for units in arch[:-1]:
        mlp.add(tf.keras.layers.Dense(units, activation=activation))

    mlp.add(tf.keras.layers.Dense(arch[-1], activation=out_activation))

    return mlp


class SecondOrderFeatureInteraction(tf.keras.layers.Layer):
    def __init__(self, self_interaction=False):
        super(SecondOrderFeatureInteraction, self).__init__()
        self.self_interaction = self_interaction

    def call(self, inputs):
        batch_size = tf.shape(inputs[0])[0]
        concat_features = tf.stack(inputs, axis=1)

        dot_products = tf.matmul(concat_features, concat_features, transpose_b=True)

        ones = tf.ones_like(dot_products)
        mask = tf.linalg.band_part(ones, 0, -1)
        out_dim = int(len(inputs) * (len(inputs) + 1) / 2)

        if not self.self_interaction:
            mask = mask - tf.linalg.band_part(ones, 0, 0)
            out_dim = int(len(inputs) * (len(inputs) - 1) / 2)

        flat_interactions = tf.reshape(tf.boolean_mask(dot_products, mask), (batch_size, out_dim))
        return flat_interactions


class DLRM(tf.keras.Model):
    def __init__(
            self,
            embedding_sizes,
            embedding_dim,
            arch_bot,
            arch_top,
            self_interaction,
    ):
        super(DLRM, self).__init__()
        self.emb = [tf.keras.layers.Embedding(size, embedding_dim) for size in embedding_sizes]
        self.bot_nn = MLP(arch_bot, out_activation='relu')
        self.top_nn = MLP(arch_top, out_activation='sigmoid')
        self.interaction_op = SecondOrderFeatureInteraction(self_interaction)

    def call(self, input):
        input_dense, input_cat = input
        emb_x = [E(x) for E, x in zip(self.emb, tf.unstack(input_cat, axis=1))]
        dense_x = self.bot_nn(input_dense)

        Z = self.interaction_op(emb_x + [dense_x])
        z = tf.concat([dense_x, Z], axis=1)
        p = self.top_nn(z)

        return p

def seed_tensorflow(seed=42):

    random.seed(seed)

    os.environ['PYTHONHASHSEED'] = str(seed)

    np.random.seed(seed)

    tf.set_random_seed(seed)

def run():
    server = tf.train.Server(cluster,
                             job_name=FLAGS.job_name,
                             task_index=FLAGS.task_index)
    if FLAGS.job_name == "ps":
        server.join()
    elif FLAGS.job_name == "worker":
        with tf.device(tf.train.replica_device_setter(
                worker_device="/job:worker/task:%d" % FLAGS.task_index,
                cluster=cluster)):

            # Training settings
            PRINT_FREQ = 100  # Iterations to print
            BATCH_SIZE = 128
            EPO = 5
            VAL_PER_EPO = 5

            emb_counts, len_train, len_val, len_test, ds, ds_val, ds_test = criteo_dataprocessing_sample()

            # Train
            ds = ds.batch(BATCH_SIZE)
            ds = ds.repeat(EPO)
            t_itr = ds.make_initializable_iterator()
            next = t_itr.get_next()
            input_dense = next[0][0]
            input_cat = next[0][1]
            input_label = next[1]

            # Test
            ds_test = ds_test.batch(BATCH_SIZE)
            test_itr = ds_test.make_initializable_iterator()
            test_next = test_itr.get_next()
            test_dense = test_next[0][0]
            test_cat = test_next[0][1]
            test_label = test_next[1]

            model = DLRM(
                embedding_sizes=emb_counts,
                embedding_dim=16,
                arch_bot=[512, 256, 64, 16],
                arch_top=[512, 256, 2],
                self_interaction=False
            )

            # Train
            out = model.call((input_dense, input_cat))
            global_step = tf.train.get_or_create_global_step()
            loss = tf.keras.losses.binary_crossentropy(input_label, out, from_logits=True)
            optimz = tf.train.AdagradOptimizer(learning_rate=0.1, ).minimize(loss, global_step=global_step)

            # Accuracy calculation
            train_acc = tf.keras.metrics.categorical_accuracy(out, input_label)
            config = tf.ConfigProto(intra_op_parallelism_threads=12, inter_op_parallelism_threads=12)
            init_op = tf.global_variables_initializer()

        if len_train % BATCH_SIZE == 0:
            batch_num = int(len_train / BATCH_SIZE)
        else:
            batch_num = int(len_train / BATCH_SIZE) + 1

        if FLAGS.task_index == 0:
            scf = tf.train.Scaffold(init_op=init_op, saver=None)
        else:
            scf = None

        # Calculate loss printing frequency
        temp_loss_list = []
        print_loss_dict = {}
        print_loss_list = []
        print_loss_batch_num = []
        print_loss_batch_numprint_loss_batch_num = PRINT_FREQ

        print_train_acc = {}

        with tf.train.MonitoredTrainingSession(master="grpc://" + worker_hosts[FLAGS.task_index],
                                               is_chief=(FLAGS.task_index == 0),
                                               checkpoint_dir="model",
                                               scaffold=scf,
                                               save_checkpoint_steps=5000,
                                               config=config,
                                               ) as mon_sess:

            mon_sess.run([t_itr.initializer])

            for i in range(EPO):
                loss_list = []
                train_acc_list = []

                itr_time = 0
                itr_num = 0
                try:
                    for j in range(batch_num):
                        beg = time.time()
                        ret, ret_loss, ret_label, ret_acc, ret_input_label, ret_step = mon_sess.run([optimz, loss, out, train_acc, input_label, global_step])
                        loss_list.append(np.mean(ret_loss))
                        train_acc_list.append(np.count_nonzero(ret_acc) / len(ret_acc))
                        itr_time += time.time() - beg
                        itr_num += 1

                        print_loss_dict[beg] = np.mean(ret_loss)
                        temp_loss_list.append(np.mean(ret_loss))
                        if itr_num % print_loss_batch_numprint_loss_batch_num == 0:
                            print_loss_list.append(np.mean(temp_loss_list))
                            temp_loss_list.clear()
                            print_loss_batch_num.append(itr_num + i * batch_num)

                        print_train_acc[beg] = np.mean(ret_acc)

                except tf.errors.OutOfRangeError:
                    pass

                print(f"Loss: {np.mean(loss_list).astype(np.float).round(3)}, acc: {np.mean(train_acc_list).round(3)}, batch time: {round(itr_time/itr_num, 7)} ms, batch num: {itr_num}")


        with open("plts/worker3_loss.pkl", "wb") as pkf:
            pickle.dump(print_loss_dict, pkf)
        plt.plot(print_loss_batch_num, print_loss_list)
        plt.savefig('plts/plt_worker3.png')

        with open("plts/worker3_train_acc.pkl", "wb") as pkf1:
            pickle.dump(print_train_acc, pkf1)

if __name__ == "__main__":

    seed_tensorflow()
    run()
    print("DLRM training finished.")
