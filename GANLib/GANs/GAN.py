import tensorflow as tf
import numpy as np

from .. import metrics
from .. import utils
from .. import distances

#                   Generative Adversarial Network
#   Paper: https://arxiv.org/pdf/1406.2661.pdf

#       Description:
#   Takes as input some dataset and by adversarial training two different 
#   networks (generator and discriminator) learn to generate samples 
#   that very similar to given dataset from random noise.


#       To do:
#   Make it possible to pass list of data arrays to any GAN and possible use it as labels, references and so on.

class GAN(object):
    def metric_test(self, set, pred_num = 32):    
        met_arr = np.zeros(pred_num)
        
        n_indx = np.random.choice(set.shape[0],pred_num)
        org_set = set[n_indx]
        
        noise = np.random.uniform(-1, 1, (pred_num, self.latent_dim))
        gen_set = self.predict(noise) 
        met_arr = self.metric_func(org_set, gen_set)
        return met_arr

    def __init__(self, input_shape, latent_dim = 100, optimizer = None, distance = None, metric = None, n_critic = 1):
        self.input_shape = input_shape
        self.latent_dim = latent_dim
        
        self.best_model = None
        self.best_metric = np.inf
        
        self.history = None
        
        #self.epoch = utils.tensor_value(0)
        #self.epochs = utils.tensor_value(0)
        
        self.optimizer = optimizer
        self.distance = distance
        
        self.set_models_params()
        
        if metric is None: self.metric_func = metrics.magic_distance
        else: self.metric_func = metric
        
        self.n_critic = n_critic
        
        self.sess = tf.Session()
        
        
    def set_models_params(self):
        if self.optimizer is None: self.optimizer = tf.train.AdamOptimizer(0.001, 0.5, epsilon = 1e-07)
        if self.distance is None: self.distance = distances.minmax
        
        self.models = ['generator', 'discriminator']
        
    def build_graph(self):
        
        def G(x):
            with tf.variable_scope('G', reuse=tf.AUTO_REUSE) as scope:
                res = self.generator(x)
            return res
            
        def D(x):
            with tf.variable_scope('D', reuse=tf.AUTO_REUSE) as scope:
                logits = self.discriminator(x)
            return logits
        
        self.genr_input = tf.placeholder(tf.float32, shape=(None, self.latent_dim))
        self.disc_input = tf.placeholder(tf.float32, shape=(None,) + self.input_shape)
        
        
        self.genr = G(self.genr_input)
        logit_real = D(self.disc_input)
        logit_fake = D(self.genr)
        
        real = self.disc_input
        fake = self.genr
        
        dist = self.distance(
            optimizer = self.optimizer, 
            logits = [logit_real, logit_fake], 
            examples = [real, fake], 
            models = [G, D],
            vars = [tf.trainable_variables('G'), tf.trainable_variables('D')],
            gan = self
            )
            
        self.train_genr, self.train_disc = dist.get_train_sessions() 
        self.genr_loss, self.disc_loss = dist.get_losses()
        
        self.sess.run(tf.global_variables_initializer())
      
    def prepare_data(self, data_set, validation_split, batch_size):
        if 0. < validation_split < 1.:
            split_at = int(data_set.shape[0] * (1. - validation_split))
            self.train_set = data_set[:split_at]
            self.valid_set = data_set[split_at:]
        else:
            self.train_set = data_set
            self.valid_set = None
    
    def predict(self, noise):  
        imgs = self.sess.run(self.genr, feed_dict = {self.genr_input: noise})
        return imgs
        
    def train_on_batch(self, batch_size):
        for j in range(self.n_critic):
            # Select a random batch of images
            idx = np.random.randint(0, self.train_set.shape[0], batch_size)
            imgs = self.train_set[idx]
        
            # Sample noise as generator input
            noise = np.random.uniform(-1, 1, (batch_size, self.latent_dim))
            self.sess.run(self.train_disc, feed_dict={self.disc_input: imgs, self.genr_input: noise})
                        
        noise = np.random.uniform(-1, 1, (batch_size, self.latent_dim))
        self.sess.run([self.train_genr], feed_dict={self.disc_input: imgs, self.genr_input: noise})
        
        d_loss, g_loss = self.sess.run([self.disc_loss, self.genr_loss], feed_dict={self.disc_input: imgs, self.genr_input: noise})
        return d_loss, g_loss
        
        
    def build_models(self, files = None, custom_objects = None):
        for model in self.models:
            if not hasattr(self, model): raise Exception("%s are not defined!"%(model))
            
        self.build_graph()
      
      
    def test_network(self, batch_size):
        metric = self.metric_test(self.train_set, batch_size)    
        return {'metric': metric}
        
    
    def train(self, data_set, batch_size=32, epochs=1, verbose=True, checkpoint_range = 100, checkpoint_callback = None, validation_split = 0, save_best_model = False, collect_history = True):
        """Trains the model for a given number of epochs (iterations on a dataset).
        # Arguments
            data_set: 
                Numpy array of training data.
            batch_size:
                Number of samples per gradient update.
            epochs: Number of epochs to train the model.
                An epoch is an iteration over batch sized samples of dataset.
            checkpoint_range:
                Range in witch checkpoint callback will be called and history data will be stored.
            verbose: 
                Integer. 0, 1. Verbosity mode.
            checkpoint_callback:
                Callback to apply during training on checkpoint stage.
            validation_split: Float between 0 and 1.
                Fraction of the training data to be used as validation data.
                The model will set apart this fraction of the training data,
                will not train on it, and will evaluate
                the loss and any model metrics
                on this data at the end of each epoch.
                The validation data is selected from the last samples.
            save_best_model:
                Boolean. If True, generator weights will be resigned to best model according to chosen metric.
            collect_history:
                Boolean. If True, all training history will store into 'history' object. Sometimes it might be computationally expensive.
        # Returns
            A history object. 
        """ 

        #mean min max
        max_hist_size = epochs//checkpoint_range + 1
        history = { 'best_metric':0,
                    'hist_size'  :0}
                    
        #self.epoch.set(0)
        #self.epochs.set(epochs)
        
        # Build Network
        
        self.prepare_data(data_set, validation_split, batch_size)
        self.build_models()
        
        # Train Network
        for epoch in range(epochs):
            #self.epoch.set(epoch)
            
            d_loss, g_loss = self.train_on_batch(batch_size)
            
            # Save history
            if epoch % checkpoint_range == 0:
                if not collect_history:
                    if verbose: print('%d [D loss: %f] [G loss: %f]' % (epoch, d_loss, g_loss))
                    exit()
                else:
                    dict_of_vals = self.test_network(128)
                    dict_of_vals['D loss'] = d_loss
                    dict_of_vals['G loss'] = g_loss
                    
                    hist_size = history['hist_size'] = history['hist_size']+1
                    metric = np.mean(dict_of_vals['metric'])
                    
                    for k, v in dict_of_vals.items():
                        if k not in history:
                            history[k] = np.zeros((max_hist_size,3))
                        
                        history[k][hist_size-1] = np.mean(v),  np.min(v),  np.max(v)
                    
                    if verbose: print ("%d [D loss: %f] [G loss: %f] [%s: %f]" % (epoch, d_loss, g_loss, 'metric', metric))
                    
                    if metric < self.best_metric:  #or self.best_model == None:
                        #self.best_model = self.generator.get_weights()
                        self.best_metric = metric
                        history['best_metric'] = self.best_metric
                        
                    self.history = history
                
                if checkpoint_callback is not None:
                    checkpoint_callback()
        
        if save_best_model:
            self.generator.set_weights(self.best_model)    
            
        #self.epoch.set(epochs)
        checkpoint_callback()   
        
        self.sess.close()
        tf.reset_default_graph()
        return self.history   

    def save_history_to_image(self, file):
        utils.save_hist_image(self.history, file, graphs = (['metric'], ['D loss', 'G loss']), scales = ('log', 'linear'))
        
   