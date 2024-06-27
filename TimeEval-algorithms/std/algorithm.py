#!/usr/bin/env python3
import argparse
import json
import sys
import numpy as np
import pandas as pd
import pickle

from typing import List
from dataclasses import dataclass


@dataclass
class CustomParameters:
    tol: float = 3.0
    random_state: int = 42
    target_channels: List[str] = None
    target_channel_indices: List[int] = None  # do not use, automatically handled


class AlgorithmArgs(argparse.Namespace):
    @staticmethod
    def from_sys_args() -> 'AlgorithmArgs':
        args: dict = json.loads(sys.argv[1])
        custom_parameter_keys = dir(CustomParameters())
        filtered_parameters = dict(filter(lambda x: x[0] in custom_parameter_keys, args.get("customParameters", {}).items()))
        args["customParameters"] = CustomParameters(**filtered_parameters)
        return AlgorithmArgs(**args)


def load_data(config: AlgorithmArgs) -> np.ndarray:
    print(f"Loading: {config.dataInput}")
    columns = pd.read_csv(config.dataInput, index_col="timestamp", nrows=0).columns.tolist()
    anomaly_columns = [x for x in columns if x.startswith("is_anomaly")]
    data_columns = columns[:-len(anomaly_columns)]

    dtypes = {col: np.float32 for col in data_columns}
    dtypes.update({col: np.uint8 for col in anomaly_columns})
    dataset = pd.read_csv(config.dataInput, index_col="timestamp", parse_dates=True, dtype=dtypes)

    if config.customParameters.target_channels is None or len(
            set(config.customParameters.target_channels).intersection(data_columns)) == 0:
        config.customParameters.target_channels = data_columns
        print(
            f"Input channels not given or not present in the data, selecting all the channels: {config.customParameters.target_channels}")
        all_used_channels = [x for x in data_columns if x in set(config.customParameters.target_channels)]
        all_used_anomaly_columns = [f"is_anomaly_{channel}" for channel in all_used_channels]
    else:
        config.customParameters.target_channels = [x for x in config.customParameters.target_channels if x in data_columns]

        # Remove unused columns from dataset
        all_used_channels = [x for x in data_columns if x in set(config.customParameters.target_channels)]
        all_used_anomaly_columns = [f"is_anomaly_{channel}" for channel in all_used_channels]
        if len(anomaly_columns) == 1 and anomaly_columns[0] == "is_anomaly":  # Handle datasets with only one global is_anomaly column
            for c in all_used_anomaly_columns:
                dataset[c] = dataset["is_anomaly"]
            dataset = dataset.drop(columns="is_anomaly")
        dataset = dataset.loc[:, all_used_channels + all_used_anomaly_columns]
        data_columns = dataset.columns.tolist()[:len(all_used_channels)]

    # Change channel names to index for further processing
    config.customParameters.target_channel_indices = [data_columns.index(x) for x in config.customParameters.target_channels]

    labels = dataset[all_used_anomaly_columns].to_numpy()
    dataset = dataset.to_numpy()[:, config.customParameters.target_channel_indices]
    meansOutput = str(config.modelOutput) + ".means.txt"
    stdsOutput = str(config.modelOutput) + ".stds.txt"
    if config.executionType == "train":
        train_means = [np.mean(dataset[:, i][labels[:, i] == 0]) for i in range(dataset.shape[-1])]
        np.savetxt(meansOutput, train_means)

        train_stds = [np.std(dataset[:, i][labels[:, i] == 0].astype(float)) for i in range(dataset.shape[-1])]
        train_stds = np.asarray(train_stds)
        train_stds = np.where(train_stds == 0, 1, train_stds)  # do not divide constant signals by zero
        np.savetxt(stdsOutput, train_stds)
    elif config.executionType == "execute":
        train_means = np.atleast_1d(np.loadtxt(meansOutput))
        train_stds = np.atleast_1d(np.loadtxt(stdsOutput))


    return dataset, train_means, train_stds


def train(config: AlgorithmArgs):
    load_data(config)  # generate train means and stds


def execute(config: AlgorithmArgs):
    data, train_means, train_stds = load_data(config)

    scores = ((data > train_means + config.customParameters.tol * train_stds) |
              (data < train_means - config.customParameters.tol * train_stds)).astype(np.uint8)
    np.savetxt(config.dataOutput, scores, delimiter=",")


if __name__ == "__main__":

    config = AlgorithmArgs.from_sys_args()
    print(f"Config: {config}")

    if config.executionType == "train":
        train(config)
    elif config.executionType == "execute":
        execute(config)
    else:
        raise ValueError(f"Unknown execution type '{config.executionType}'; expected either 'train' or 'execute'!")
