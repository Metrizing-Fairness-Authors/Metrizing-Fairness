# Baseline Fair KDE : https://proceedings.neurips.cc//paper/2020/file/ac3870fcad1cfc367825cda0101eee62-Paper.pdf
import cvxpy as cp
import numpy as np
import argparse
import pandas as pd
import torch
import fairness_metrics
import data_loader
from tqdm import tqdm
from collections import namedtuple
from sklearn.metrics import log_loss
from copy import deepcopy
import os, sys
import time
import pickle
import random
import matplotlib.pyplot as plt
import torch.optim as optim
from Fair_KDE.models import Classifier
import matplotlib.pyplot as plt
import torch.nn as nn
from torch.utils.data import DataLoader
from Fair_KDE.dataloader import CustomDataset
import time

"""
% Metrizing Fairness
% NeurIPS 2022 Submission
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
This script provides implementation of https://proceedings.neurips.cc/paper/2020/file/ac3870fcad1cfc367825cda0101eee62-Paper.pdf
An example usage python fair_KDE.py --dataset {} --seed {} --nlambda {}
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
"""
tau = 0.5

# Approximation of Q-function given by López-Benítez & Casadevall (2011) based on a second-order exponential function & Q(x) = 1- Q(-x):
a = 0.4920
b = 0.2887
c = 1.1893
Q_function = lambda x: torch.exp(-a*x**2 - b*x - c) 
    
def CDF_tau(Yhat, h=0.01, tau=0.5):
    m = len(Yhat)
    Y_tilde = (tau-Yhat)/h
    sum_ = torch.sum(Q_function(Y_tilde[Y_tilde>0])) \
           + torch.sum(1-Q_function(torch.abs(Y_tilde[Y_tilde<0]))) \
           + 0.5*(len(Y_tilde[Y_tilde==0]))
    return sum_/m

def Huber_loss(x, delta):
    if x.abs() < delta:
        return (x ** 2) / 2
    return delta * (x.abs() - delta / 2)
# act on experiment parameters:

def run(args):
    # act on experiment parameters:
    seed = args.seed
    data_loader.set_seed(args.seed)
    ##### Other training hyperparameters #####
    lr = 2e-4
    n_epochs = 200
    lr_decay = 1.0
    batch_size = 2048
    n_epochs = 500
    lambda_candidates = np.logspace(args.lambda_min, args.lambda_max, num=args.nlambda)
    if args.dataset == 'CommunitiesCrimeClassification':
        ds = data_loader.CommunitiesCrimeClassification(a_inside_x=0)
        batch_size = 128
    if args.dataset == 'Compas':
        ds = data_loader.Compas(a_inside_x=0)
        lr = 5e-4
        batch_size = 2048
    if args.dataset == 'LawSchool':
        ds = data_loader.LawSchool(a_inside_x=0)
        lr = 2e-4
        batch_size = 2048
    if args.dataset == 'Credit':
        ds = data_loader.Credit(a_inside_x=0)
        lr = 5e-4
        n_batch =  2048
    if args.dataset == 'Adult':
        ds = data_loader.Adult(0)
        train_test_split_fin = 1
        batch_size = 2048
        lr = 1e-1
        lr_decay - 0.98
    if args.dataset == 'Drug':
        ds = data_loader.Drug(a_inside_x=0)
        batch_size = 128

    if args.dataset != 'Adult':
        ds.split_test()
    k = ds.get_k()

    metrics = {
        'statistical_parity' : fairness_metrics.statistical_parity,
        'statistical_parity_classification' : fairness_metrics.statistical_parity_classification,
        'bounded_group_loss_L1' : lambda y1_hat, y2_hat, y1, y2: fairness_metrics.bounded_group_loss(y1_hat, y2_hat, y1, y2, loss='L1'),
        'bounded_group_loss_L2' : fairness_metrics.bounded_group_loss,
        'group_fair_expect' : fairness_metrics.group_fair_expect,
        'l1_dist' : lambda y1_hat, y2_hat, y1, y2: fairness_metrics.lp_dist(y1_hat, y2_hat, y1, y2, p=1),
        'l2_dist' : lambda y1_hat, y2_hat, y1, y2: fairness_metrics.lp_dist(y1_hat, y2_hat, y1, y2, p=2),
        'MSE' : fairness_metrics.MSE,
        'MAE' : fairness_metrics.MAE,
        'accuracy' : fairness_metrics.accuracy
    }
    # storage of results
    results_train = []
    results_test = []

    ##### Which fairness notion to consider (Demographic Parity / Equalized Odds) #####
    fairness = 'DP' # ['DP', 'EO']

    ##### Model specifications #####
    n_layers = 2 # [positive integers]
    n_hidden_units = 16 # [positive integers]

    ##### Our algorithm hyperparameters #####
    h = 0.1 # Bandwidth hyperparameter in KDE [positive real numbers]
    delta = 1.0 # Delta parameter in Huber loss [positive real numbers]
    lambda_ = 0.05 # regularization factor of DDP/DEO; Positive real numbers \in [0.0, 1.0]

    

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    ##### Whether to enable GPU training or not
    device = torch.device('cpu') # or torch.device('cpu')
    # Import dataset
    # dataset = FairnessDataset(dataset=dataset_name, device=device)
    # dataset.normalize()
    input_dim = k + 1

    net = Classifier(n_layers=n_layers, n_inputs=input_dim, n_hidden_units=n_hidden_units)
    net = net.to(device)

    # Set an optimizer
    optimizer = optim.Adam(net.parameters(), lr=lr)
    lr_scheduler = optim.lr_scheduler.ExponentialLR(optimizer, gamma=lr_decay) # None

    #     X, Y, A = ds.get_data()
    #     X_test, Y_test, A_test = ds.get_test_data()
#     x_train = X.cpu().detach().numpy()
#     Y_train = Y.cpu().detach().numpy().flatten()
#     a_train = A.cpu().detach().numpy().flatten()
#     x_test = X_test.cpu().detach().numpy()
#     y_test = Y_test.cpu().detach().numpy().flatten()
#     a_test = A_test.cpu().detach().numpy().flatten()

# train_tensors, test_tensors = dataset.get_dataset_in_tensor()
# X_train, Y_train, Z_train, XZ_train = train_tensors
# X_test, Y_test, Z_test, XZ_test = test_tensors

# Retrieve train/test splitted numpy arrays for index=split
# train_arrays, test_arrays = dataset.get_dataset_in_ndarray()
# X_train_np, Y_train_np, Z_train_np, XZ_train_np = train_arrays
# X_test_np, Y_test_np, Z_test_np, XZ_test_np = test_arrays
    if args.dataset == 'Adult':
        X_train, Y_train, Z_train, X_test, Y_test, Z_test = ds.get_adult_data()
    else:   
        X_train, Y_train, Z_train = ds.get_data()
        X_test, Y_test, Z_test = ds.get_test_data()
    XZ_test = torch.cat([X_test, Z_test], 1)
    XZ_train = torch.cat([X_train, Z_train], 1)


    custom_dataset = CustomDataset(XZ_train, Y_train, Z_train)
    if batch_size == 'full':
        batch_size_ = XZ_train.shape[0]
    elif isinstance(batch_size, int):
        batch_size_ = batch_size
    generator = DataLoader(custom_dataset, batch_size=batch_size_, shuffle=True)

    pi = torch.tensor(np.pi).to(device)
    phi = lambda x: torch.exp(-0.5*x**2)/torch.sqrt(2*pi) #normal distribution

    # # An empty dataframe for logging experimental results
    # df = pd.DataFrame()
    # df_ckpt = pd.DataFrame()

    loss_function = nn.BCELoss()
    costs = []
    time_track = []
    for lambda_ in lambda_candidates:
        print('Training FKDE method, for lambda: {}/{}, seed:{}'.format(lambda_, args.nlambda, args.seed))

        start_time = time.time()
        for epoch in range(n_epochs):
            for i, (xz_batch, y_batch, z_batch) in enumerate(generator):
                xz_batch, y_batch, z_batch = xz_batch.to(device), y_batch.to(device), z_batch.to(device)
                Yhat = net(xz_batch)
                Ytilde = torch.round(Yhat.squeeze())
                cost = 0
                dtheta = 0
                m = z_batch.shape[0]

                # prediction loss
                p_loss = loss_function(Yhat.squeeze(), y_batch.squeeze())
                cost += (1 - lambda_) * p_loss

                # DP_Constraint
                if fairness == 'DP':
                    Pr_Ytilde1 = CDF_tau(Yhat.detach(), h, tau)
                    for z in range(1):
                        Pr_Ytilde1_Z = CDF_tau(Yhat.detach()[z_batch==z],h,tau)
                        m_z = z_batch[z_batch==z].shape[0]

                        Delta_z = Pr_Ytilde1_Z-Pr_Ytilde1
                        Delta_z_grad = torch.dot(phi((tau-Yhat.detach()[z_batch==z])/h).view(-1), 
                                                  Yhat[z_batch==z].view(-1))/h/m_z
                        Delta_z_grad -= torch.dot(phi((tau-Yhat.detach())/h).view(-1), 
                                                  Yhat.view(-1))/h/m

                        if Delta_z.abs() >= delta:
                            if Delta_z > 0:
                                Delta_z_grad *= lambda_*delta
                                cost += Delta_z_grad
                            else:
                                Delta_z_grad *= -lambda_*delta
                                cost += Delta_z_grad
                        else:
                            Delta_z_grad *= lambda_*Delta_z
                            cost += Delta_z_grad

                # EO_Constraint
                elif fairness == 'EO':
                    for y in [0,1]:
                        Pr_Ytilde1_Y = CDF_tau(Yhat[y_batch==y].detach(),h,tau)
                        m_y = y_batch[y_batch==y].shape[0]
                        for z in range(1):
                            Pr_Ytilde1_ZY = CDF_tau(Yhat[(y_batch==y) & (z_batch==z)].detach(),h,tau)
                            m_zy = z_batch[(y_batch==y) & (z_batch==z)].shape[0]
                            Delta_zy = Pr_Ytilde1_ZY-Pr_Ytilde1_Y
                            Delta_zy_grad = torch.dot(
                                                      phi((tau-Yhat[(y_batch==y) & (z_batch==z)].detach())/h).view(-1), 
                                                      Yhat[(y_batch==y) & (z_batch==z)].view(-1)
                                                      )/h/m_zy
                            Delta_zy_grad -= torch.dot(
                                                       phi((tau-Yhat[y_batch==y].detach())/h).view(-1), 
                                                       Yhat[y_batch==y].view(-1)
                                                       )/h/m_y

                            if Delta_zy.abs() >= delta:
                                if Delta_zy > 0:
                                    Delta_zy_grad *= lambda_*delta
                                    cost += Delta_zy_grad
                                else:
                                    Delta_zy_grad *= lambda_*delta
                                    cost += -lambda_*delta*Delta_zy_grad
                            else:
                                Delta_zy_grad *= lambda_*Delta_zy
                                cost += Delta_zy_grad

                optimizer.zero_grad()
                if (torch.isnan(cost)).any():
                    continue
                cost.backward()
                optimizer.step()
                costs.append(cost.item())

                # Print the cost per 10 batches
#                 if (i + 1) % 10 == 0 or (i + 1) == len(generator):
#                     print('Lambda:{}, Epoch [{}/{}], Batch [{}/{}], Cost: {:.4f}'.format(lambda_, epoch+1, n_epochs,
#                                                                               i+1, len(generator),
#                                                                               cost.item()), end='\r')
            if lr_scheduler is not None:
                lr_scheduler.step()
        stop_time = time.time()
        def predict(XZ):
            Y_hat_ = net(XZ)
            Y_hat_[Y_hat_>=0.5] = 1
            Y_hat_[Y_hat_ < 0.5] = 0
            return Y_hat_
        
        # metrics on train set
        y_hat = predict(XZ_train).flatten()
        y_hat = y_hat.unsqueeze(1)
        y_hat_1 = y_hat[Z_train==1]
        y_hat_0 = y_hat[Z_train==0]
        y_1 = Y_train[Z_train==1]
        y_0 = Y_train[Z_train==0]
        train_results = {}
        for key in metrics.keys():
            train_results[key] = metrics[key](y_hat_1, y_hat_0, y_1, y_0).data.item()
        train_results['time'] = stop_time - start_time

        # metrics on test set
        y_hat = predict(XZ_test).flatten()
        y_hat = y_hat.unsqueeze(1)
        y_hat_1 = y_hat[Z_test==1]
        y_hat_0 = y_hat[Z_test==0]
        y_1 = Y_test[Z_test==1]
        y_0 = Y_test[Z_test==0]
        test_results = {}
        for key in metrics.keys():
            test_results[key] = metrics[key](y_hat_1, y_hat_0, y_1, y_0).data.item()
        

        train_results['lambda_'] = lambda_
        test_results['lambda_'] = lambda_
        print(train_results)
        results_train.append(train_results)
        results_test.append(test_results)

# df_train = pd.DataFrame(data=results_train)
# df_test = pd.DataFrame(data=results_test)

# df_train.to_csv('results/{}_zafar_{}_train.csv'.format(args.dataset, 0))

# df_test.to_csv('results/{}_zafar_{}_test.csv'.format(args.dataset, 0))

    df_train = pd.DataFrame(data=results_train)
    df_test = pd.DataFrame(data=results_test)

    df_train.to_csv('results/FKDE/{}_FKDE_{}_train.csv'.format(args.dataset, args.seed))

    df_test.to_csv('results/FKDE/{}_FKDE_{}_test.csv'.format(args.dataset, args.seed))
    
    PARAMS = {'dataset':args.dataset, 
              'batch_size':batch_size,
               'lr':lr, 'epochs':n_epochs,
              'seed':args.seed, 
              'method':'FKDE',
              'nlambda': args.nlambda, 
              'lambda_min':args.lambda_min,
              'lambda_max':args.lambda_max,
             'algorihtm':'adam', 
              'L':'BCE_cross_entropy',
              'lr_decay':lr_decay,
              'a_inside_x': True
             }
    with open('results/FKDE/{}_FKDE_{}.pkl'.format(args.dataset, args.seed), 'wb') as f:
            pickle.dump({**PARAMS}, f, protocol=pickle.HIGHEST_PROTOCOL)



if __name__=='__main__':
    parser = argparse.ArgumentParser(description='Experiment Inputs')
    parser.add_argument('--seed', default=0, help='Randomness seed', type=int)
    parser.add_argument('--lambda_min', default=-5, type=int, help='Minimum value of lambda: 10^x')
    parser.add_argument('--lambda_max', default=2, type=int, help='Maximum value of lambda: 10^x')
    parser.add_argument('--dataset', help='Dataset to use', choices=['CommunitiesCrimeClassification', 'LawSchool', 'Compas', 'Adult', 'Credit', 'Drug'])
    parser.add_argument('--nlambda', help='Number of lambda candidates', type=int, default=50)
    args = parser.parse_args()
    run(args)