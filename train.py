#!/usr/bin/python
#-*- coding: utf-8 -*- 

import tensorflow as tf
from tensorflow.contrib.framework.python.ops.variables import get_or_create_global_step
from tensorflow.python.platform import tf_logging as logging
import inception_preprocessing
from inception_resnet_v2 import inception_resnet_v2, inception_resnet_v2_arg_scope
import os
import time
slim = tf.contrib.slim

#import numpy as np
#设置定量的GPU使用量
config  = tf.ConfigProto()
#config.gpu_options.per_process_gpu_memory_fraction = 0.9
config.gpu_options.allow_growth = True
#session = tf.Session(config=config)
# 设置最小的GPU使用量
"""
config = tf.ConfigProto()
config.gpu_options.allow_growth = True

"""
#================ DATASET INFORMATION ======================
#State dataset directory where the tfrecord files are located
dataset_dir = '.'

#State where your log file is at. If it doesn't exist, create it.
log_dir = './log'

#State where your checkpoint file is
checkpoint_file = './inception_resnet_v2_2016_08_30.ckpt'

#State the image size you're resizing your images to. We will use the default inception size of 299.
img_width = 800
img_height = 600

file_pattern = 'estate_%s_*.tfrecord'
#State the number of classes to predict:
num_classes = 6

#State the labels file and read it
labels_file = './labels.txt'
labels = open(labels_file, 'r')

#Create a dictionary to refer each label to their string name
labels_to_name = {}
for line in labels:
    label, string_name = line.split(':')
    string_name = string_name[:-1] #Remove newline
    labels_to_name[int(label)] = string_name

#Create the file pattern of your TFRecord files so that it could be recognized later on
file_pattern = 'estate_%s_*.tfrecord'

#Create a dictionary that will help people understand your dataset better. This is required by the Dataset class later.

items_to_descriptions = {
    'image': 'A 3-channel RGB coloured real estate image that is either bathroom, bedroom, floorplan, kitchen, or livingroom, other.',
    'label': 'A label that is as such -- 0:bathroom, 1:bedroom, 2:floorplan, 3:kitchen, 4:livingroom, 5:other'
}


#================= TRAINING INFORMATION ==================
#State the number of epochs to train
num_epochs = 1

#State your batch size
batch_size = 1

#Learning rate information and configuration (Up to you to experiment)
initial_learning_rate = 0.0002
learning_rate_decay_factor = 0.7
num_epochs_before_decay = 2

#iteration 

#============== DATASET LOADING ======================
#We now create a function that creates a Dataset class which will give us many TFRecord files to feed in the examples into a queue in parallel.
def get_split(split_name, dataset_dir, file_pattern=file_pattern, file_pattern_for_counting='estate'):
    '''
    Obtains the split - training or validation - to create a Dataset class for feeding the examples into a queue later on. This function will
    set up the decoder and dataset information all into one Dataset class so that you can avoid the brute work later on.
    Your file_pattern is very important in locating the files later. 

    INPUTS:
    - split_name(str): 'train' or 'validation'. Used to get the correct data split of tfrecord files
    - dataset_dir(str): the dataset directory where the tfrecord files are located
    - file_pattern(str): the file name structure of the tfrecord files in order to get the correct data
    - file_pattern_for_counting(str): the string name to identify your tfrecord files for counting

    OUTPUTS:
    - dataset (Dataset): A Dataset class object where we can read its various components for easier batch creation later.
    '''

    #First check whether the split_name is train or validation
    if split_name not in ['train', 'validation']:
        raise ValueError('The split_name %s is not recognized. Please input either train or validation as the split_name' % (split_name))

    #Create the full path for a general file_pattern to locate the tfrecord_files
    file_pattern_path = os.path.join(dataset_dir, file_pattern % (split_name))

    #Count the total number of examples in all of these shard
    num_samples = 0
    file_pattern_for_counting = file_pattern_for_counting + '_' + split_name
    tfrecords_to_count = [os.path.join(dataset_dir, file) for file in os.listdir(dataset_dir) if file.startswith(file_pattern_for_counting)]
    for tfrecord_file in tfrecords_to_count:
        for record in tf.python_io.tf_record_iterator(tfrecord_file):
            num_samples += 1

    #Create a reader, which must be a TFRecord reader in this case
    reader = tf.TFRecordReader

    #Create the keys_to_features dictionary for the decoder
    keys_to_features = {
      'image/encoded': tf.FixedLenFeature((), tf.string, default_value=''),
      'image/format': tf.FixedLenFeature((), tf.string, default_value='jpg'),
      'image/class/label': tf.FixedLenFeature(
          [], tf.int64, default_value=tf.zeros([], dtype=tf.int64)),
    }

    #Create the items_to_handlers dictionary for the decoder.
    items_to_handlers = {
    'image': slim.tfexample_decoder.Image(),
    'label': slim.tfexample_decoder.Tensor('image/class/label'),
    }

    #Start to create the decoder
    decoder = slim.tfexample_decoder.TFExampleDecoder(keys_to_features, items_to_handlers)

    #Create the labels_to_name file
    labels_to_name_dict = labels_to_name

   	 #Actually create the dataset
	#dataset 对象定义了数据集的文件位置，解码方式等元信息
    dataset = slim.dataset.Dataset(
        data_sources = file_pattern_path,
        decoder = decoder,
        reader = reader,
        num_readers = 4,
        num_samples = num_samples,
        num_classes = num_classes,
        labels_to_name = labels_to_name_dict,
        items_to_descriptions = items_to_descriptions)
    return dataset


def load_batch(dataset, batch_size, height=img_height, width=img_width, is_training=True):
    '''
    Loads a batch for training.

    INPUTS:
    - dataset(Dataset): a Dataset class object that is created from the get_split function
    - batch_size(int): determines how big of a batch to train
    - height(int): the height of the image to resize to during preprocessing
    - width(int): the width of the image to resize to during preprocessing
    - is_training(bool): to determine whether to perform a training or evaluation preprocessing

    OUTPUTS:
    - images(Tensor): a Tensor of the shape (batch_size, height, width, channels) that contain one batch of images
    - labels(Tensor): the batch's labels with the shape (batch_size,) (requires one_hot_encoding).

    '''
    #First create the data_provider object
    data_provider = slim.dataset_data_provider.DatasetDataProvider(
        dataset,
        common_queue_capacity = 24 + 3 * batch_size,
        common_queue_min = 24)

    #Obtain the raw image using the get method
    raw_image, label = data_provider.get(['image', 'label'])

    #Perform the correct preprocessing for this image depending if it is training or evaluating
    image = inception_preprocessing.preprocess_image(raw_image, height, width, is_training)
    #As for the raw images, we just do a simple reshape to batch it up
    image = tf.expand_dims(image, 0)
    """
    raw_image = tf.image.resize_nearest_neighbor(raw_image, [height, width])
    #modify due to data type
    raw_image = tf.cast(raw_image, tf.float32)
    raw_image = tf.squeeze(raw_image)

    #Batch up the image by enqueing the tensors internally in a FIFO queue and dequeueing many elements with tf.train.batch.
    images, raw_images, labels = tf.train.batch(
        [image, raw_image, label],
        batch_size = batch_size,
        num_threads = 1,
        capacity = 4 * batch_size,
        allow_smaller_final_batch = True)
    """
    return image,  label


#sess = tf.Session()


        #Create the log directory here. Must be done here otherwise import will activate this unneededly.
if not os.path.exists(log_dir):
    os.mkdir(log_dir)
#======================= TRAINING PROCESS =========================
#Now we start to construct the graph and build our model
tf.logging.set_verbosity(tf.logging.INFO) #Set the verbosity to INFO level
dataset = get_split('train', dataset_dir, file_pattern=file_pattern)
print(dataset.num_samples)
#First create the dataset and load one batch
x = tf.placeholder(tf.float32, shape=[None, img_height, img_width,3], name='x')
#y_true = tf.placeholder(tf.int32, shape=[None, num_classes], name='y_true')
y_true = tf.placeholder(tf.int32, shape=[num_classes], name='y_true')
#images = tf.reshape(x, [-1, 800, 600, 1])

#Know the number steps to take before decaying the learning rate and batches per epoch
num_batches_per_epoch = int(dataset.num_samples / batch_size)
num_steps_per_epoch = num_batches_per_epoch #Because one step is one batch processed
decay_steps = int(num_epochs_before_decay * num_steps_per_epoch)

#Create the model inference
with slim.arg_scope(inception_resnet_v2_arg_scope()):
    logits, end_points = inception_resnet_v2(x, num_classes = dataset.num_classes, is_training = True)

y_pred = tf.nn.softmax(logits, name='y_pred')
#Define the scopes that you want to exclude for restoration
exclude = ['InceptionResnetV2/Logits', 'InceptionResnetV2/AuxLogits']
variables_to_restore = slim.get_variables_to_restore(exclude = exclude)

#Perform one-hot-encoding of the labels (Try one-hot-encoding within the load_batch function!)
one_hot_labels = slim.one_hot_encoding(y_true, dataset.num_classes)

#Performs the equivalent to tf.nn.sparse_softmax_cross_entropy_with_logits but enhanced with checks
loss = tf.losses.softmax_cross_entropy(onehot_labels = one_hot_labels, logits = logits)
total_loss = tf.losses.get_total_loss()    #obtain the regularization losses as well

#Create the global step for monitoring the learning_rate and training.
global_step = get_or_create_global_step()

#Define your exponentially decaying learning rate
lr = tf.train.exponential_decay(
    learning_rate = initial_learning_rate,
    global_step = global_step,
    decay_steps = decay_steps,
    decay_rate = learning_rate_decay_factor,
    staircase = True)

#Now we can define the optimizer that takes on the learning rate
optimizer = tf.train.AdamOptimizer(learning_rate = lr)

#Create the train_op.
train_op = slim.learning.create_train_op(total_loss, optimizer)

#State the metrics that you want to predict. We get a predictions that is not one_hot_encoded.
predictions = tf.argmax(end_points['Predictions'], 1)
probabilities = end_points['Predictions']
accuracy, accuracy_update = tf.contrib.metrics.streaming_accuracy(predictions, y_true)
metrics_op = tf.group(accuracy_update, probabilities)



#Now finally create all the summaries you need to monitor and group them into one summary op.
tf.summary.scalar('losses/Total_Loss', total_loss)
tf.summary.scalar('accuracy', accuracy)
tf.summary.scalar('learning_rate', lr)
my_summary_op = tf.summary.merge_all()


#Now we need to create a training step function that runs both the train_op, metrics_op and updates the global_step concurrently.
def train_step(sess, train_op, global_step):
    '''
    Simply runs a session for the three arguments provided and gives a logging on the time elapsed for each global step
    '''
    #Check the time for each sess run
    start_time = time.time()
    total_loss, global_step_count, _ = sess.run([train_op, global_step, metrics_op])
    time_elapsed = time.time() - start_time

    #Run the logging to print some results
    if global_step_count % 10 == 0:
        logging.info('global step %s: loss: %.4f (%.2f sec/step)', global_step_count, total_loss, time_elapsed)
    return total_loss, global_step_count
    
with tf.Session(config=config) as sess:
    sess.run(tf.global_variables_initializer())
    #Now we create a saver function that actually restores the variables from a checkpoint file in a sess
    saver = tf.train.Saver(variables_to_restore)
    saver.restore(sess, checkpoint_file)
    
    coord = tf.train.Coordinator()
    threads = tf.train.start_queue_runners(sess=sess, coord=coord)
    
    for i in range(num_steps_per_epoch*num_epochs):
        image, label = load_batch(dataset, batch_size=batch_size)
        print('x shape',tf.shape(x))
        print('y_true', tf.shape(y_true))
        print('========================')
        sess.run(train_op, feed_dict={x: image.eval(session=sess), y_true: label(session=sess)})
        print('------------------------')
        print('x shape',tf.shape(x))
        print('y_true', tf.shape(y_true))
        print(x.eval())
        print(y_true.eval())
        saver.save(sess,  global_step = global_step)
    coord.request_stop()
    coord.join(threads)

                

