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

nnn              = np.ceil(np.logspace(.5,2.5,14))
nhu_vec, nin_vec = np.meshgrid(nnn, nnn) 
nhu_vec          = nhu_vec.flatten()
nin_vec          = nin_vec.flatten()
n_in             = int(nin_vec[job_idx-1])
n_hid            = int(nhu_vec[job_idx-1])

def model(input_var, batch_size=1, n_in=100, n_out=1, n_hid=200):

    # Input Layer
    l_in         = InputLayer((batch_size, n_in), input_var=input_var)
    # Hidden layer
    l_in_hid     = DenseLayer(l_in, n_hid, nonlinearity=lasagne.nonlinearities.rectify)
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
    tr_cond               = 'all_gains'
    test_cond             = 'all_gains'
    generator             = CueCombinationTaskFFWD(max_iter=50001, batch_size=100, n_in=n_in, n_out=1, sigma_sq=100.0, tr_cond=tr_cond)

    # The model 
    l_out, l_rec          = model(input_var, batch_size=generator.batch_size, n_in=2*generator.n_in, n_out=generator.n_out, n_hid=n_hid)
    # The generated output variable and the loss function
#    all_layers            = lasagne.layers.get_all_layers(l_out)
#    l2_penalty            = lasagne.regularization.regularize_layer_params(all_layers, lasagne.regularization.l2) * 1e-6
    pred_var              = lasagne.layers.get_output(l_out)
    loss                  = T.mean(lasagne.objectives.squared_error(pred_var, target_var)) #+ l2_penalty
    
    # Create the update expressions
    params                = lasagne.layers.get_all_params(l_out, trainable=True)
    updates               = lasagne.updates.adam(loss, params, learning_rate=0.001)
    
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
    success = 0.0
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
            if frac_rmse < 0.1:
                success = 1.0
                break;            
            s_vec       = []
            opt_s_vec   = []
            ex_pred_vec = []
        
    # SAVE RESULTS 
    sio.savemat('cc_nin%i_nhu%i_jobidx%i.mat'%(n_in,n_hid,job_idx), {'frac_rmse':frac_rmse, 'frac_rmse_vec':np.asarray(frac_rmse_vec), 'success':success } )      