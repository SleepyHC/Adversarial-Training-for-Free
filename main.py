'''Train CIFAR10 with PyTorch.'''
from __future__ import print_function

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torch.backends.cudnn as cudnn

import torchvision
import torchvision.transforms as transforms

import os
import argparse

from tqdm import tqdm
import random
import numpy as np
from models.wideresnet import *
from models.resnet import *
from advertorch.attacks import LinfPGDAttack, FGSM

parser = argparse.ArgumentParser(description='PyTorch CIFAR10 Training')
parser.add_argument('--seed', default=11111, type=int)
parser.add_argument('--momentum', default=0.9, type=float)
parser.add_argument('--weight_decay', default=5e-4, type=float)
parser.add_argument('--epsilon', default=8.0/255, type=float)
parser.add_argument('--m', default=8, type=int)
parser.add_argument('--batch_size', default=128, type=int)
parser.add_argument('--resume', '-r', default=None, type=int, help='resume from checkpoint')
parser.add_argument('--datasets', '-d', default='CIFAR10', type=str, help='datasets')
args = parser.parse_args()

device = 'cuda:2' if torch.cuda.is_available() else 'cpu'
start_epoch = 0  # start from epoch 0 or last checkpoint epoch

seed = args.seed
random.seed(seed)
torch.manual_seed(seed)
torch.cuda.manual_seed(seed)
np.random.seed(seed)
torch.backends.cudnn.deterministic=True
torch.backends.cudnn.benchmark = False

# Data
print('==> Preparing data..')
transform_train = transforms.Compose([
    transforms.RandomCrop(32, padding=4),
    transforms.RandomHorizontalFlip(),
    transforms.ToTensor(),
    # transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
    # Normalization messes with l-inf bounds.
])
transform_test = transforms.Compose([
    transforms.ToTensor(),
])

if args.datasets=='CIFAR10':
    number_classes=10
    testset = torchvision.datasets.CIFAR10(root='./data', train=False, download=True, transform=transform_test)
    testloader = torch.utils.data.DataLoader(testset, batch_size=args.batch_size, shuffle=False, num_workers=2)

    trainset = torchvision.datasets.CIFAR10(root='./data', train=True, download=True, transform=transform_train)
    trainloader = torch.utils.data.DataLoader(trainset, batch_size=args.batch_size, shuffle=True, drop_last=True)
else:
    number_classes=100
    testset = torchvision.datasets.CIFAR100(root='./data', train=False, download=True, transform=transform_test)
    testloader = torch.utils.data.DataLoader(testset, batch_size=args.batch_size, shuffle=False, num_workers=2)

    trainset = torchvision.datasets.CIFAR100(root='./data', train=True, download=True, transform=transform_train)
    trainloader = torch.utils.data.DataLoader(trainset, batch_size=args.batch_size, shuffle=True, drop_last=True)


print('==> Building model..')
net = PreActResNet18(number_classes)
epsilon = args.epsilon
m = args.m
delta = torch.zeros(args.batch_size, 3, 32, 32)
delta = delta.to(device)
net = net.to(device)


if args.resume is not None:
    # Load checkpoint.
    print('==> Resuming from checkpoint..')
    assert os.path.isdir('checkpoint'), 'Error: no checkpoint directory found!'
    checkpoint = torch.load('./checkpoint/ckpt.{}'.format(args.resume))
    net.load_state_dict(checkpoint['net'])
    start_epoch = checkpoint['epoch'] + 1
    torch.set_rng_state(checkpoint['rng_state'])

optimizer = optim.SGD(net.parameters(), lr=0.1, momentum=args.momentum, weight_decay=args.weight_decay)

adversary = LinfPGDAttack(
    net, loss_fn=nn.CrossEntropyLoss(reduction="sum"), eps=8./255,
    nb_iter=20, eps_iter=2./255, rand_init=True, clip_min=0.0, clip_max=1.0,
    targeted=False)

adversary_50 = LinfPGDAttack(
    net, loss_fn=nn.CrossEntropyLoss(reduction="sum"), eps=8./255,
    nb_iter=50, eps_iter=2./255, rand_init=True, clip_min=0.0, clip_max=1.0,
    targeted=False)

adversary_FGSM = FGSM(
        net, loss_fn=nn.CrossEntropyLoss(reduction="sum"), eps=8./255,
        clip_min=0.0, clip_max=1.0, targeted=False
    )
    

def test(epoch):
    net.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        iterator = tqdm(testloader, ncols=0, leave=False)
        for batch_idx, (inputs, targets) in enumerate(iterator):
            inputs, targets = inputs.to(device), targets.to(device)   
            with torch.enable_grad(): 
                adv = adversary.perturb(inputs, targets)
            outputs = net(adv)
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()
            iterator.set_description(str(predicted.eq(targets).sum().item()/targets.size(0)))


    # Save checkpoint.
    acc = 100.*correct/total
    print('Test Acc of ckpt.{}: {}'.format(epoch, acc))
    return acc

def test_50(epoch):
    net.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        iterator = tqdm(testloader, ncols=0, leave=False)
        for batch_idx, (inputs, targets) in enumerate(iterator):
            inputs, targets = inputs.to(device), targets.to(device)   
            with torch.enable_grad(): 
                adv = adversary_50.perturb(inputs, targets)
            outputs = net(adv)
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()
            iterator.set_description(str(predicted.eq(targets).sum().item()/targets.size(0)))


    # Save checkpoint.
    acc = 100.*correct/total
    print('Test Acc of ckpt.{}: {}'.format(epoch, acc))
    return acc

def test_fgsm(epoch):
    net.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        iterator = tqdm(testloader, ncols=0, leave=False)
        for batch_idx, (inputs, targets) in enumerate(iterator):
            inputs, targets = inputs.to(device), targets.to(device)   
            with torch.enable_grad(): 
                adv = adversary_FGSM.perturb(inputs, targets)
            outputs = net(adv)
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()
            iterator.set_description(str(predicted.eq(targets).sum().item()/targets.size(0)))


    # Save checkpoint.
    acc = 100.*correct/total
    print('Test Acc of ckpt.{}: {}'.format(epoch, acc))
    return acc

def train(epoch):
    print('\nEpoch: %d' % epoch)
    net.train()
    train_loss = 0
    correct = 0
    total = 0
    iterator = tqdm(trainloader, ncols=0, leave=False)
    global delta

    for batch_idx, (inputs, targets) in enumerate(iterator):
        inputs, targets = inputs.to(device), targets.to(device)
        for i in range(m):
            optimizer.zero_grad()
            adv = (inputs+delta).detach()
            adv.requires_grad_()
            outputs = net(adv)
            loss = F.cross_entropy(outputs, targets)
            loss.backward()
            optimizer.step()
            grad = adv.grad.data
            delta = delta.detach() + epsilon * torch.sign(grad.detach())
            delta = torch.clamp(delta, -epsilon, epsilon)

            train_loss += loss.item()
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()
            iterator.set_description(str(predicted.eq(targets).sum().item()/targets.size(0)))

    acc = 100.*correct/total
    print('Train acc:', acc)
    global max_acc
    tmp_acc=test(epoch)
    if max_acc<tmp_acc:
        max_acc=tmp_acc
        
    
        print('Saving..')
        state = {
            'net': net.state_dict(),
            'acc': acc,
            'epoch': epoch,
            'rng_state': torch.get_rng_state()
        }
        if not os.path.isdir('checkpoint'):
            os.mkdir('checkpoint')
        torch.save(state, './checkpoint/best'+args.datasets)
    best_acc = acc


def adjust_learning_rate(optimizer, epoch):
    if epoch < 12:
        lr = 0.1
    elif epoch >= 12 and epoch < 22:
        lr = 0.01
    elif epoch >= 22: 
        lr = 0.001
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr

max_acc=0

for epoch in range(start_epoch, 27):
    adjust_learning_rate(optimizer, epoch)
    train(epoch)
    
for i in [1]:
    checkpoint = torch.load('./checkpoint/best'+args.datasets)
    net.load_state_dict(checkpoint['net'])
    net = net.to(device)
    net.eval()
    test(111)
    test_50(111)
    test_fgsm(111)

    
