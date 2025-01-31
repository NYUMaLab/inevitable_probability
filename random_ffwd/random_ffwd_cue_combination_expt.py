# -*- coding: utf-8 -*-
"""
Created on Thu Apr 28 16:52:18 2016 by emin
"""
import os
import sys
import theano
import theano.tensor as T
import numpy as np
from lasagne.layers import InputLayer, ReshapeLayer, DenseLayer
from generators import CueCombinationTaskFFWD
import lasagne.layers
import lasagne.nonlinearities
import lasagne.updates
import lasagne.objectives
import lasagne.init
import scipy.io as sio

os.chdir(os.path.dirname(sys.argv[0]))
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0) 
job_idx    = int(os.getenv('PBS_ARRAYID'))
np.random.seed(job_idx)

def model(input_var, batch_size=1, n_in=100, n_out=1, n_hid=200):

    # Input Layer
    l_in         = InputLayer((batch_size, n_in), input_var=input_var)
    # Hidden layer
    l_in_hid     = DenseLayer(l_in, n_hid, W=lasagne.init.GlorotNormal(), b=lasagne.init.Normal(std=0.1), nonlinearity=lasagne.nonlinearities.rectify)
    # Output Layer
    l_shp        = ReshapeLayer(l_in_hid, (-1, n_hid))
    l_dense      = DenseLayer(l_shp, num_units=n_out, nonlinearity=lasagne.nonlinearities.linear)
    # To reshape back to our original shape, we can use the symbolic shape variables we retrieved above.
    l_out        = ReshapeLayer(l_dense, (batch_size, n_out))

    return l_out, l_in_hid

if __name__ == '__main__':
    # Define the input and expected output variable
    input_var, target_var = T.fmatrices('input', 'target')
    # The generator to sample examples from
    tr_cond               = 'two_gains'
    test_cond             = 'all_gains'
    generator             = CueCombinationTaskFFWD(max_iter=25001, batch_size=100, n_in=50, n_out=1, sigma_sq=100.0, tr_cond=tr_cond)
    test_generator        = CueCombinationTaskFFWD(max_iter=2501,  batch_size=100, n_in=50, n_out=1, sigma_sq=100.0, tr_cond=test_cond)

    # The model 
    l_out, l_rec          = model(input_var, batch_size=generator.batch_size, n_in=2*generator.n_in, n_out=generator.n_out, n_hid=200)
    # The generated output variable and the loss function
    pred_var              = lasagne.layers.get_output(l_out)
    loss                  = T.mean(lasagne.objectives.squared_error(pred_var, target_var)) 
    
    # Create the update expressions
    params                = lasagne.layers.get_all_params(l_out, trainable=True)
    trainable_params      = params[-2:]
    updates               = lasagne.updates.adam(loss, trainable_params, learning_rate=0.001)
    
    # Compile the function for a training step, as well as the prediction function and a utility function to get the inner details of the RNN
    train_fn              = theano.function([input_var, target_var], loss, updates=updates, allow_input_downcast=True)
    pred_fn               = theano.function([input_var], pred_var, allow_input_downcast=True)
    rec_layer_fn          = theano.function([input_var], lasagne.layers.get_output(l_rec, get_details=True), allow_input_downcast=True)

    # If you want to continue training an old model, uncomment below
#    npzfile_lout          = np.load('cc_lout_trained_model.npz')
#    npzfile_lrec          = np.load('cc_lrec_trained_model.npz')
#    lasagne.layers.set_all_param_values(l_out,[npzfile_lout['arr_0'],npzfile_lout['arr_1'],npzfile_lout['arr_2'],npzfile_lout['arr_3'],npzfile_lout['arr_4'],npzfile_lout['arr_5']])
#    lasagne.layers.set_all_param_values(l_rec,[npzfile_lout['arr_0'],npzfile_lout['arr_1'],npzfile_lout['arr_2'],npzfile_lout['arr_3'],npzfile_lout['arr_4']])
    
    # TRAINING
    s_vec, opt_s_vec, ex_pred_vec, frac_rmse_vec = [], [], [], []
    for i, (example_input, example_output, g1, g2, s, opt_s) in generator:
        score              = train_fn(example_input, example_output)
        example_prediction = pred_fn(example_input)
        s_vec.append(s)
        opt_s_vec.append(opt_s)
        ex_pred_vec.append(example_prediction.squeeze())
        if i % 500 == 0:
            rmse_opt  = np.sqrt(np.nanmean((np.asarray(s_vec) - np.asarray(opt_s_vec))**2))
            rmse_net  = np.sqrt(np.nanmean((np.asarray(s_vec) - np.asarray(ex_pred_vec))**2))
            frac_rmse = (rmse_net - rmse_opt) / rmse_opt
            frac_rmse_vec.append(frac_rmse)
            print 'Batch #%d; Frac. RMSE: %.6f; Opt. RMSE: %.6f; Net. RMSE: %.6f' % (i, frac_rmse, rmse_opt, rmse_net)
            s_vec       = []
            opt_s_vec   = []
            ex_pred_vec = []
    
    # TESTING
    s_vec, opt_s_vec, ex_pred_vec, ex_hid_vec, ex_inp_vec = [], [], [], [], []
    for i, (example_input, example_output, g1, g2, s, opt_s) in test_generator:
        example_prediction = pred_fn(example_input)
        example_hidden     = rec_layer_fn(example_input)
        s_vec.append(s)
        opt_s_vec.append(opt_s)
        ex_pred_vec.append(example_prediction.squeeze())
        if i % 100 == 0:
            ex_hid_vec.append(example_hidden)
            ex_inp_vec.append(example_input)
        
    rmse_opt       = np.sqrt(np.nanmean((np.asarray(s_vec) - np.asarray(opt_s_vec))**2))
    rmse_net       = np.sqrt(np.nanmean((np.asarray(s_vec) - np.asarray(ex_pred_vec))**2))
    frac_rmse_test = (rmse_net - rmse_opt) / rmse_opt
    print 'Test data; Frac. RMSE: %.6f; Opt. RMSE: %.6f; Net. RMSE: %.6f' % (frac_rmse_test, rmse_opt, rmse_net)

    ex_hid_vec = np.asarray(ex_hid_vec)  
    ex_hid_vec = np.reshape(ex_hid_vec,(-1,200))    
    
    ex_inp_vec = np.asarray(ex_inp_vec)    
    ex_inp_vec = np.reshape(ex_inp_vec,(-1,100))    

    # SAVE TRAINED MODEL  
    sio.savemat('cc_testfrmse_twogains_run%i.mat'%job_idx, {'frac_rmse_test':frac_rmse_test, 'opt_vec':np.asarray(opt_s_vec), 'net_vec':np.asarray(ex_pred_vec) } )      
#    sio.savemat('cc_everything_allgains_run%i.mat'%job_idx, {'W_hid': lasagne.layers.get_all_param_values(l_out)[0], 
#                                                             'b_hid': lasagne.layers.get_all_param_values(l_out)[1],
#                                                             'w_out': lasagne.layers.get_all_param_values(l_out)[2],
#                                                             'b_out': lasagne.layers.get_all_param_values(l_out)[3],
#                                                             'frac_rmse_vec':np.asarray(frac_rmse_vec), 
#                                                             'inpResps':ex_inp_vec, 
#                                                             'hidResps':ex_hid_vec} )       