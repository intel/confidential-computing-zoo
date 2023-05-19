import time

import tensorflow._api.v2.compat.v1 as tf
import pandas as pd
from sklearn import preprocessing
import numpy as np

from tensorflow.keras.utils import to_categorical


tf.disable_eager_execution()

tf.app.flags.DEFINE_string("job_name", "ps", "'ps' or 'worker'")
tf.app.flags.DEFINE_integer("task_index", 0, "Index of task within the job")
tf.app.flags.DEFINE_string("ps_hosts", "['localhost:70002']", "ps hosts")
tf.app.flags.DEFINE_string("worker_hosts", "['localhost:71002','localhost:71003','localhost:71004','localhost:71005']", "worker hosts")

FLAGS = tf.app.flags.FLAGS

ps_hosts = eval(FLAGS.ps_hosts)
worker_hosts = eval(FLAGS.worker_hosts)

cluster = tf.train.ClusterSpec({"ps": ps_hosts, "worker": worker_hosts})

def run():
    server = tf.train.Server(cluster,
        job_name=FLAGS.job_name,
        task_index=FLAGS.task_index)
    if FLAGS.job_name == "ps":
        server.join()


if __name__ == "__main__":

    run()

    print("Dlrm tf v1")
