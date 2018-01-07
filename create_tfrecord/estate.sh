#!/usr/bin/sh

python gen_tfrecord.py --dataset_dir=../test/estate --tfrecord_filename=estate

python ../lianjia/eval_test.py 

rm ../test/estate/estate_*
