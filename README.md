# CFNADE-keras

## Paper Description

* Paper: "A Neural Autoregressive Approach to Collaborative Filtering" [LINK](https://arxiv.org/pdf/1605.09477.pdf)
* Unofficial Slide: [LINK](https://www.slideshare.net/ssuser62b35f/a-neural-autoregressive-approach-to-collaborative-filtering-cfnade-slide)
* Keras implementation of CF-NADE.
* The CFNADE is the model applying [NADE](https://arxiv.org/abs/1605.02226) model to the collaborative filtering problem. NADE is the modified version of the auto-encoder to estimate probabilistic distribution.

## Limitation

* This repository only works with Movielens 1M data.
* This repository force you to use "tensorflow" backend.


## How to run

* I used `python3`.
```
git clone git@github.com:JoonyoungYi/CFNADE-keras.git
cd CFNADE-keras
virtualenv .venv -p python3
. .venv/bin/activate
pip install -r requirements.txt
python data_prep.py
python run.py
```
* I setup my environment by this [docker image](https://hub.docker.com/r/jihong/keras-gpu/).


## Performance

### Setting 1.

* default setting.
```
--hidden_dim=250
```

* 1st Attempt.
```
training set RMSE for epoch 29 is 0.858837
validation set RMSE for epoch 29 is 0.872606
Testing...
test set RMSE is 0.820515
```
* 2nd Attempt.
```
training set RMSE for epoch 29 is 0.882864
validation set RMSE for epoch 29 is 0.874668
val_nade_loss_loss: 0.0000e+00
Testing...
test set RMSE is 0.823059
```
* 3rd Attempt.
```
training set RMSE for epoch 29 is 0.868767
validation set RMSE for epoch 29 is 0.874799
Testing...
test set RMSE is 0.824332
```

### Setting 2.
```
--hidden_dim=500
```
* 1st Attempt.
```
training set RMSE for epoch 29 is 0.844765
validation set RMSE for epoch 29 is 0.873419
Testing...
test set RMSE is 0.793768
```

## Repository History

* keras implementation of CF-NADE based on the implementation of [Ian09/CF-NADE](https://github.com/Ian09/CF-NADE)
* Forked from [AlexGidiotis/keras-CF-NADE](https://github.com/AlexGidiotis/keras-CF-NADE)
