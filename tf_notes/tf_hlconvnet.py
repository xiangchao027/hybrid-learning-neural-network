# tf_hlconvnet.py
# Hybrid Learning Convolutional Network implementation
# Algorithm and implementation are intrinscally authorized
# by Chao Xiang

# -*- coding:utf8 -*-

import numpy as np
import PIL.Image as pi
import matplotlib.pyplot as pl

import tensorflow as tf
import tf_hlconv as hl

import sys
import os
import time

# configurations
N_DIGITS = 28
N, H, W, C = 8, 256, 256, 3

class hlconvnet(object):
    def __init__(self):
        # a batch of images [nbatch, height, width, channel]
        self.graph = tf.Graph()
        self.saver = None
        self.sess = None
        self.summ = None
        self.learning_rate = 0.01
        self.stop_level = 0.01

        with self.graph.as_default():
            # data feed in and back
            self.x = tf.placeholder(
                    dtype=tf.float32, 
                    shape=[N, H, W, C]
            )
            self.y = tf.placeholder(
                    dtype=tf.int32,
                    shape=[N]
            )

            # containers for layers and parameters
            self.hlc = [] # hybrid conv operators
            self.uws = [] # unsupervised weights
            self.sws = [] # supervised weights
            self.sbs = [] # supervised biases
            self.uts = [] # unsupervised training ops
            self.layers = [] # layers 
            self.energies = [] # unsupervised energies

##################### LAYER #1 ########################

            # generate the first hlconv layer
            # with kernel size 3x3
            # with kernel number 16
            ksizes = [1,3,3,1]
            n = 16
            
            uw,sw = hl.hlconv_make_params(
                    n = n,
                    depth = self.x.shape.as_list()[3],
                    ksizes = ksizes
            )
            
            self.uws.append(uw)
            self.sws.append(sw)
            
            hlconv, utrain_op, energy = hl.hlconv(
                    x = self.x,
                    uw = uw,
                    sw = sw,
                    ksizes = ksizes,
                    strides = [1,1,1,1],
                    padding = 'VALID',
                    name = 'hlconv-1'
            )
            
            self.hlc.append(hlconv)
            self.uts.append(utrain_op)
            self.energies.append(energy)

            # add bias
            bias = tf.Variable(
                    tf.random_uniform(
                        [hlconv.shape.as_list()[3]]
                    )
            )
            add_bias = tf.nn.bias_add(
                    hlconv,
                    bias
            )
            self.sbs.append(bias)

            # apply activation function
            apply_act = tf.nn.relu(add_bias)
            self.layers.append(apply_act)

#################### LAYER #2 ########################

            # the final layer is still a hlconv
            # however it is an inception operator
            # it must contains $N_DIGITS filters
            # to convert the tensor into output shape
            ksizes = [1,1,1,1]
            n = N_DIGITS
            uw, sw = hl.hlconv_make_params(
                    n = n,
                    depth = hlconv.shape.as_list()[3],
                    ksizes = ksizes
            )

            self.uws.append(uw)
            self.sws.append(sw)

            hlconv, utrain_op, energy = hl.hlconv(
                    x = apply_act,
                    uw = uw,
                    sw = sw,
                    ksizes = ksizes,
                    strides = [1,1,1,1],
                    padding = 'VALID',
                    name = 'hlconv-2'
            )

            self.hlc.append(hlconv)
            self.uts.append(utrain_op)
            self.energies.append(energy)

            # add bias
            bias = tf.Variable(
                    tf.random_uniform(
                        [hlconv.shape.as_list()[3]]
                    )
            )
            self.sbs.append(bias)
            add_bias = tf.nn.bias_add(
                    hlconv,
                    bias
            )
            
            # apply activation function
            apply_act = tf.nn.relu(add_bias)
            self.layers.append(apply_act)

####################### OUTPUT LAYER #######################
            # using maxpooling to get the output vector
            ksizes = [
                    1,
                    apply_act.shape.as_list()[1],
                    apply_act.shape.as_list()[2],
                    1
            ]
            self.logits = tf.nn.max_pool(
                    apply_act,
                    ksizes,
                    strides = ksizes,
                    padding = 'VALID'
            )
            self.logits = tf.reshape(self.logits, [N, N_DIGITS])

################### PREDICTION AND TRAINING ##############

            # get predicted label and its probability
            self.pred = tf.argmax(self.logits, 1)
            self.prob = tf.nn.softmax(self.logits)

            # for training, convert from labels into one-hot vector
            self.onehot = tf.one_hot(
                    tf.cast(self.y, tf.int32),
                    N_DIGITS,
                    1,
                    0
            )

            # training loss
            #self.loss = tf.reduce_sum(tf.square(self.y - feeds))
            self.loss = tf.losses.softmax_cross_entropy(
                    onehot_labels=self.onehot,
                    logits=self.logits
            )
            
            # optimizer for supervised learning
            self.opt = tf.train.AdagradOptimizer(
                    learning_rate = self.learning_rate
            )

            # the only supervised training operator
            self.st = self.opt.minimize(self.loss)

    ################# DATA PREPARATION ##################
    # this will load all samples into memory for 
    # supervised training, test, or prediction
    # @path : path for data, it must be a dir containing 
    #         subdirs; for training or test, samples with 
    #         same labels have to be in same subdir.
    def offline_supervised(self, path):
        _subdirs = os.listdir(path)
        self.labels = [] # unicode strings
        self.sx_samples = []
        self.sy_samples = []
        
        for _subdir in _subdirs:
            self.labels.append(_subdir.decode('utf-8'))
        
        # to ensure an absolute mapping from id to label
        self.labels.sort()

        # check datasets
        assert len(self.labels)==N_DIGITS
        
        for _i in xrange(len(self.labels)):
            _label = self.labels[_i]
            _path = os.path.join(path, _label)
            _files = os.listdir(_path)
            for _file in _files:
                _im_path = os.path.join(
                        _path, 
                        _file.decode('utf-8')
                )
                _im = pi.open(_im_path)
                _im = _im.resize([W,H])
                self.sx_samples.append(np.array(_im))
                self.sy_samples.append(_i)
                #pl.imshow(_im)
                #pl.show()
                #break
        # set up random generator(supervised)
        self.svol = len(self.sx_samples) # volume of samples
        self.sseq = np.arange(self.svol) # random sequence of samples
        self.sidx = 0 # current index in sequence
        
        # check if data is enough for a batch
        if self.svol < N:
            raise NameError('Samples not enough for a batch!')

        # construct supervised batch(x,y)
        self.sbatch_x = np.zeros([N,H,W,C], np.float32)
        self.sbatch_y = np.zeros([N], np.int32)

    # Generate a batch of samples(x,y) to feed the network
    def batch_supervised(self):
        if self.sidx+N > self.svol: # rest samples not enough for a batch
            np.random.shuffle(self.sseq)
            self.sidx = 0

        for _i in xrange(N):
            _idx = self.sseq[self.sidx + _i]
            self.sbatch_x[_i] = self.sx_samples[_idx]/255.0
            self.sbatch_y[_i] = self.sy_samples[_idx]

        self.sidx += N

    # this will load all samples into memory for 
    # unsupervised training and prediction
    # @path : ensure only images in current path
    def offline_unsupervised(self, path):
        self.ux_samples = [] 
        _files = os.listdir(path)
        
        for _file in _files:
            _im_path = os.path.join(
                    path, 
                    _file.decode('utf-8')
            )
            _im = pi.open(_im_path)
            _im = _im.resize([W,H])
            self.ux_samples.append(np.array(_im))
            #pl.imshow(_im)
            #pl.show()
            #break
        
        # set up random generator(unsupervised)
        self.uvol = len(self.ux_samples) # volume of samples
        self.useq = np.arange(self.uvol) # random sequence of samples
        self.uidx = 0 # current index in sequence
        
        # check if data is enough for a batch
        if self.uvol < N:
            raise NameError('Samples not enough for a batch!')

        # construct supervised batch(x)
        self.ubatch_x = np.zeros([N,H,W,C], np.float32)

    # Generate a batch of samples(x) to feed the network
    def batch_unsupervised(self):
        if self.uidx+N > self.uvol: # rest samples not enough for a batch
            np.random.shuffle(self.useq)
            self.uidx = 0

        for _i in xrange(N):
            _idx = self.useq[self.uidx + _i]
            self.ubatch_x[_i] = self.ux_samples[_idx]/255.0

        self.uidx += N

    # @nalt : number of alternation
    # @uepo : unsupervised iterations within an epoch
    # @sepo : supervised iterations within an epoch
    def train(self, nalt, uepo, sepo):
        print 'Training begin...'
        path = time.strftime('MODEL_%Y%m%d_%H%M%S')
        os.mkdir(path)
        print 'models saved in ', path

        with self.graph.as_default():
            if self.saver==None:
                self.saver = tf.train.Saver()
            if self.sess==None:
                self.sess = tf.Session()

            # initialization
            self.sess.run(tf.global_variables_initializer())
            
            for i in xrange(nalt):
                # run unsupervised training epoch
                for ui in xrange(uepo):
                    self.batch_unsupervised()
                    self.sess.run(
                            self.uts,
                            feed_dict={
                                self.x : self.ubatch_x
                            }
                    )
                for si in xrange(sepo):
                    self.batch_supervised()
                    self.sess.run(
                            self.st,
                            feed_dict={
                                self.x : self.sbatch_x,
                                self.y : self.sbatch_y
                            }
                    )
                # for each alternation, print the training losses
                # and the unsupervised energy level
                if __debug__:
                    print 'Training loss:', self.sess.run(
                            self.loss, 
                            feed_dict={
                                self.x : self.sbatch_x,
                                self.y : self.sbatch_y
                            })
                    print 'Unsupervised energies:', self.sess.run(
                            self.energies, 
                            feed_dict={
                                self.x : self.ubatch_x
                            })
                # every 100 steps to save a copy of the model
                if i%100 == 0 or i==nalt-1:
                    _model = os.path.join(path, 'hlconvnet')
                    self.saver.save(self.sess, _model, global_step=i)
    
    # @model : the trained model path
    def predict(self, model):
        self.saver = tf.Saver()
        with self.graph.as_default():
            print 'hello'

