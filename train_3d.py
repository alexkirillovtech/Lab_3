import argparse
import glob
import numpy as np
import tensorflow as tf
import time
from tensorflow.python import keras as keras
from tensorflow.python.keras.callbacks import LearningRateScheduler
from datetime import datetime

LOG_DIR = './logs'
SHUFFLE_BUFFER = 10
BATCH_SIZE = 100
NUM_CLASSES = 50
PARALLEL_CALLS=4
RESIZE_TO = 224
TRAINSET_SIZE = 5216
VALSET_SIZE=624

def parse_proto_example(proto):
    keys_to_features = {
        'image/encoded': tf.FixedLenFeature((), tf.string, default_value=''),
        'image/class/label': tf.FixedLenFeature([], tf.int64, default_value=tf.zeros([], dtype=tf.int64))
    }
    example = tf.parse_single_example(proto, keys_to_features)
    example['image'] = tf.image.decode_jpeg(example['image/encoded'], channels=3)
    example['image'] = tf.image.convert_image_dtype(example['image'], dtype=tf.float32)
    example['image'] = tf.image.resize_images(example['image'], tf.constant([RESIZE_TO, RESIZE_TO]))
    return example['image'], example['image/class/label']


def normalize(image, label):
    return tf.image.per_image_standardization(image), label

def resize(image, label):
    return tf.image.resize_images(image, tf.constant([RESIZE_TO, RESIZE_TO])), label

def create_dataset(filenames, batch_size):
    """Create dataset from tfrecords file
    :tfrecords_files: Mask to collect tfrecords file of dataset
    :returns: tf.data.Dataset
    """
    return tf.data.TFRecordDataset(filenames)\
        .map(parse_proto_example)\
        .map(resize)\
        .map(normalize)\
        .shuffle(buffer_size=5 * batch_size)\
        .repeat()\
        .batch(batch_size)\
        .prefetch(2 * batch_size)


class Validation(tf.keras.callbacks.Callback):
    def __init__(self, log_dir, validation_files, batch_size):
        self.log_dir = log_dir
        self.batch_size = batch_size
        validation_dataset = create_dataset(validation_files, batch_size)
        self.validation_images, validation_labels = validation_dataset.make_one_shot_iterator().get_next()
        self.validation_labels = tf.one_hot(validation_labels, NUM_CLASSES)

    def on_epoch_end(self, epoch, logs=None):
        print('The average loss for epoch {} is {:7.2f} '.format(
            epoch, logs['loss']
        ))

        result = self.model.evaluate(
            self.validation_images,
            self.validation_labels,
            steps=int(np.ceil(VALSET_SIZE / float(BATCH_SIZE)))
        )
        callback = tf.keras.callbacks.TensorBoard(log_dir=self.log_dir, update_freq='epoch', batch_size=self.batch_size)

        callback.set_model(self.model)
        callback.on_epoch_end(epoch, {
            'val_' + self.model.metrics_names[i]: v for i, v in enumerate(result)
        })

train_path = './xray/train*'
test_path = './xray/test*'

model = keras.models.load_model('weight_model3.h5')
model.summary()

train_dataset = create_dataset(glob.glob(train_path), BATCH_SIZE)
train_images, train_labels = train_dataset.make_one_shot_iterator().get_next()
train_labels = tf.one_hot(train_labels, NUM_CLASSES)


model.compile(
    optimizer=keras.optimizers.sgd(lr=0.154, momentum=0.9),
    loss=tf.keras.losses.categorical_crossentropy,
    metrics=[tf.keras.metrics.categorical_accuracy],
    target_tensors=[train_labels]
)

log_dir='{}/xray-{}'.format(LOG_DIR, datetime.now())
model.fit(
    (train_images, train_labels),
    epochs=100,
    steps_per_epoch=int(np.ceil(TRAINSET_SIZE / float(BATCH_SIZE))),
    callbacks=[
        tf.keras.callbacks.TensorBoard(log_dir),
        Validation(log_dir, validation_files=glob.glob(test_path), batch_size=BATCH_SIZE)
    ]
)
