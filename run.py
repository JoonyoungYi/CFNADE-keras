import glob
import os
import random
import numpy as np
from data_gen import DataSet
from nade import NADE

from keras.layers import Dense, Input, LSTM, Embedding, Dropout, Activation, Lambda, add
from keras import backend as K
from keras.models import Model
from keras.callbacks import Callback
import keras.regularizers
from keras.optimizers import Adam
from keras.callbacks import EarlyStopping
import tensorflow as tf


def prediction_layer(x):
    # x.shape = (?,6040,5)
    x_cumsum = K.cumsum(x, axis=2)
    # x_cumsum.shape = (?,6040,5)
    output = K.softmax(x_cumsum)
    # output = (?,6040,5)
    return output


def prediction_output_shape(input_shape):
    return input_shape


def d_layer(x):
    return K.sum(x, axis=1)


def d_output_shape(input_shape):
    return (input_shape[0], )


def D_layer(x):
    return K.sum(x, axis=1)


def D_output_shape(input_shape):
    return (input_shape[0], )


def _get_cost_func(args):
    def _get_cost(i):
        pred_score, true_ratings, input_masks, output_masks, D, d = i
        # input_masks and output_masks are unused.

        lambda_ordinal = args.lambda_ordinal
        lambda_regular = 1.0 - lambda_ordinal

        # cumulate and sum weights for parameter sharing.
        pred_score_cum = K.cumsum(pred_score, axis=2)

        # this is probability.
        prob_item_ratings = K.softmax(pred_score_cum)

        # calculate ordinal cost.
        accu_prob_1N = K.cumsum(prob_item_ratings, axis=2)
        accu_prob_N1 = K.cumsum(
            prob_item_ratings[:, :, ::-1], axis=2)[:, :, ::-1]
        mask1N = K.cumsum(true_ratings[:, :, ::-1], axis=2)[:, :, ::-1]
        maskN1 = K.cumsum(true_ratings, axis=2)
        cost_ordinal_1N = -K.sum(
            (K.log(prob_item_ratings) - K.log(accu_prob_1N)) * mask1N, axis=2)
        cost_ordinal_N1 = -K.sum(
            (K.log(prob_item_ratings) - K.log(accu_prob_N1)) * maskN1, axis=2)
        ord_costs = cost_ordinal_1N + cost_ordinal_N1

        # calculate crossentropy_loss (reconstruction loss)
        # The CFNADE paper denotes this term as reg_cost (regular cost)
        reg_costs = K.sum(-(true_ratings * K.log(prob_item_ratings)), axis=2)

        # hybrid_losses. mix two losses.
        hyb_costs = lambda_regular * K.sum(
            reg_costs, axis=1) + lambda_ordinal * K.sum(
                ord_costs, axis=1)
        # hyb_costs = hyb_costs * D / (D - d + 1e-6)
        # O: 1, X;2

        # print(hyb_costs)
        cost = K.mean(hyb_costs)
        # print(cost)

        cost = K.expand_dims(cost, 0)
        # print(cost)
        # assert False
        return cost

    return _get_cost


def _calculate_rmse(data_set, model, new_items):
    rate_score = np.array([1, 2, 3, 4, 5], np.float32)

    squared_error = []
    n_samples = []
    for i, batch in enumerate(data_set.generate(max_iters=1)):
        inp_r = batch[0]['input_ratings']
        out_r = batch[0]['output_ratings']
        inp_m = batch[0]['input_masks']
        out_m = batch[0]['output_masks']

        pred_batch = model.predict(batch[0])[1]
        true_r = out_r.argmax(axis=2) + 1
        pred_r = (pred_batch * rate_score[np.newaxis, np.newaxis, :]).sum(
            axis=2)

        pred_r[:, new_items] = 3
        mask = out_r.sum(axis=2)
        # '''
        # if i == 0:
        # 	print [true_r[0][j] for j in np.nonzero(true_r[0]* mask[0])[0]]
        # 	print [pred_r[0][j] for j in np.nonzero(pred_r[0]* mask[0])[0]]
        # '''

        se = np.sum(np.square(true_r - pred_r) * mask)
        n = np.sum(mask)
        squared_error.append(se)
        n_samples.append(n)

    total_squared_error = np.array(squared_error).sum()
    total_n_samples = np.array(n_samples).sum()
    rmse = np.sqrt(total_squared_error / (total_n_samples * 1.0))
    return rmse


class EvaluationCallback(Callback):
    def __init__(self, data_set, new_items, training_set):
        self.data_set = data_set
        self.rmses = []
        self.new_items = new_items
        self.training_set = training_set

    def eval_rmse(self):
        return _calculate_rmse(self.data_set, self.model, self.new_items)

    def on_epoch_end(self, epoch, logs={}):
        score = self.eval_rmse()
        if self.training_set:
            print("training set RMSE for epoch %d is %f" % (epoch, score))
        else:
            print("validation set RMSE for epoch %d is %f" % (epoch, score))

        self.rmses.append(score)


def _train(args):
    if K.backend() != 'tensorflow':
        print("This repository only support tensorflow backend.")
        raise NotImplementedError()

    batch_size = 64
    num_users = 6040
    num_items = 3706
    data_sample = 1.0
    input_dim0 = 6040
    input_dim1 = 5

    print('Loading data...')
    train_file_list = sorted(
        glob.glob(os.path.join(('data/train_set'), 'part*')))
    val_file_list = sorted(glob.glob(os.path.join(('data/val_set/'), 'part*')))
    test_file_list = sorted(
        glob.glob(os.path.join(('data/test_set/'), 'part*')))
    train_file_list = [
        dfile for dfile in train_file_list if os.stat(dfile).st_size != 0
    ]
    val_file_list = [
        dfile for dfile in val_file_list if os.stat(dfile).st_size != 0
    ]
    test_file_list = [
        dfile for dfile in test_file_list if os.stat(dfile).st_size != 0
    ]
    random.shuffle(train_file_list)
    random.shuffle(val_file_list)
    random.shuffle(test_file_list)
    train_file_list = train_file_list[:max(
        int(len(train_file_list) * data_sample), 1)]

    train_set = DataSet(
        train_file_list,
        num_users=num_users,
        num_items=num_items,
        batch_size=batch_size,
        mode=0)
    val_set = DataSet(
        val_file_list,
        num_users=num_users,
        num_items=num_items,
        batch_size=batch_size,
        mode=1)
    test_set = DataSet(
        test_file_list,
        num_users=num_users,
        num_items=num_items,
        batch_size=batch_size,
        mode=2)

    rating_freq = np.zeros((6040, 5))
    init_b = np.zeros((6040, 5))
    for batch in val_set.generate(max_iters=1):
        inp_r = batch[0]['input_ratings']
        out_r = batch[0]['output_ratings']
        inp_m = batch[0]['input_masks']
        out_m = batch[0]['output_masks']
        rating_freq += inp_r.sum(axis=0)

    log_rating_freq = np.log(rating_freq + 1e-8)
    log_rating_freq_diff = np.diff(log_rating_freq, axis=1)
    init_b[:, 1:] = log_rating_freq_diff
    init_b[:, 0] = log_rating_freq[:, 0]

    new_items = np.where(rating_freq.sum(axis=1) == 0)[0]

    input_layer = Input(shape=(input_dim0, input_dim1), name='input_ratings')
    output_ratings = Input(
        shape=(input_dim0, input_dim1), name='output_ratings')
    input_masks = Input(shape=(input_dim0, ), name='input_masks')
    output_masks = Input(shape=(input_dim0, ), name='output_masks')

    # from keras import backend as K
    # print(K.tensorflow_backend._get_available_gpus())
    # input('Enter >>')

    # nade_layer = Dropout(0.0)(input_layer)
    nade_layer = input_layer
    nade_layer = NADE(
        hidden_dim=args.hidden_dim,
        activation='tanh',
        bias=True,
        W_regularizer=keras.regularizers.l2(args.lambda_w),
        V_regularizer=keras.regularizers.l2(args.lambda_v),
        b_regularizer=keras.regularizers.l2(args.lambda_b),
        c_regularizer=keras.regularizers.l2(args.lambda_c),
        args=args)(nade_layer)

    predicted_ratings = Lambda(
        prediction_layer,
        output_shape=prediction_output_shape,
        name='predicted_ratings')(nade_layer)

    # QUESTION: There is no data in input mask and output mask.
    d = Lambda(d_layer, output_shape=d_output_shape, name='d')(input_masks)
    sum_masks = add([input_masks, output_masks])
    D = Lambda(D_layer, output_shape=D_output_shape, name='D')(sum_masks)

    loss_out = Lambda(
        _get_cost_func(args), output_shape=(1, ), name='nade_loss')(
            [nade_layer, output_ratings, input_masks, output_masks, D, d])

    cf_nade_model = Model(
        inputs=[input_layer, output_ratings, input_masks, output_masks],
        outputs=[loss_out, predicted_ratings])
    cf_nade_model.summary()

    adam = Adam(lr=args.learning_rate, beta_1=0.9, beta_2=0.999, epsilon=1e-8)

    cf_nade_model.compile(
        loss={'nade_loss': lambda y_true, y_pred: y_pred}, optimizer=adam)

    train_evaluation_callback = EvaluationCallback(
        data_set=train_set, new_items=new_items, training_set=True)
    valid_evaluation_callback = EvaluationCallback(
        data_set=val_set, new_items=new_items, training_set=False)

    print('Training...')
    early_stopping = EarlyStopping(patience=args.iter_early_stop)

    cf_nade_model.fit_generator(
        train_set.generate(),
        steps_per_epoch=(train_set.get_corpus_size() // batch_size),
        epochs=args.n_epoch,
        validation_data=val_set.generate(),
        validation_steps=(val_set.get_corpus_size() // batch_size),
        shuffle=True,
        callbacks=[
            train_set,
            val_set,
            train_evaluation_callback,
            valid_evaluation_callback,
            early_stopping,
        ],
        verbose=1)

    print('Testing...')
    rmse = _calculate_rmse(test_set, cf_nade_model, new_items)
    print("test set RMSE is %f" % (rmse))


def main():
    import argparse

    parser = argparse.ArgumentParser(description='CFNADE-keras')
    parser.add_argument(
        '--hidden_dim',
        type=int,
        default=500,
        help='hidden dimension for NADE')
    parser.add_argument(
        '--normalize_1st_layer',
        type=bool,
        default=False,
        help='whether normalize 1st layer')
    parser.add_argument(
        '--lambda_w', type=float, default=0.015, help='The lambda for W')
    parser.add_argument(
        '--lambda_v', type=float, default=0.015, help='The lambda for V')
    parser.add_argument(
        '--lambda_b', type=float, default=0.0, help='The lambda for b')
    parser.add_argument(
        '--lambda_c', type=float, default=0.0, help='The lambda for c')

    def _restricted_float(x):
        x = float(x)
        if x < 0.0 or x > 1.0:
            raise argparse.ArgumentTypeError("%r not in range [0.0, 1.0]" %
                                             (x, ))
        return x

    parser.add_argument(
        '--lambda_ordinal',
        type=_restricted_float,
        default=1.0,
        help='The lambda for ordinal cost')
    parser.add_argument(
        '--learning_rate',
        type=float,
        default=1e-3,
        help='learning rate for optimizer.')
    parser.add_argument(
        '--n_epoch', type=int, default=1000, help='The number of epoch')
    parser.add_argument(
        '--iter_early_stop',
        type=int,
        default=100,
        help='the number of iteration for early stop.')

    # parser.add_argument(
    #     '--iter_validation',
    #     type=int,
    #     default=10,
    #     help='Iteration unit for validation')
    # parser.add_argument(
    #     '--max_iter', type=int, default=10000000, help='Max Iteration')
    # parser.add_argument(
    #     '--n_hidden_unit',
    #     type=int,
    #     default=500,
    #     help='The number of hidden unit')
    # parser.add_argument(
    #     '--parameter_sharing',
    #     type=bool,
    #     default=False,
    #     help='parameter sharing')
    # parser.add_argument(
    #     '--lambda_1',
    #     type=float,
    #     default=0.015,
    #     help='lambda for weight decay.')
    # parser.add_argument(
    #     '--lambda_2',
    #     type=float,
    #     default=0.015,
    #     help='lambda for weight decay.')
    # parser.add_argument(
    #     '--dropout_rate', type=float, default=0., help='dropout_rate')
    # parser.add_argument(
    #     '--data_seed', type=int, default=1, help='the seed for dataset')

    args = parser.parse_args()
    _train(args)


if __name__ == '__main__':
    main()
