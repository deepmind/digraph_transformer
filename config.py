# Copyright 2022 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Graph Property Prediction Config oor OGB Code2 and Sorting Network Task."""
import collections
import dataclasses
from typing import Mapping, Optional

from jaxline import base_config
from ml_collections import config_dict

import presets


@dataclasses.dataclass
class Dataset:
  """For all important information that are dataset specific.

  Attributes:
    name: unique name of dataset. This name determines e.g. the bahavior of how
      the model encodes the data and how data is preprocessed.
    path: relative storage location.
    sequence_length: number of predictions in target sequence.
    num_classes: number of classes per predicitno in target sequence.
    ast_depth: maximal distance from root node to leaf node that will be
      considered (OGB specific).
    num_nodetypes: number of node types (OGB specific).
    num_nodeattributes: number of node attributes.
    edge_df_types: number of edge types (OGB data-flow specific).
    edge_ast_types: number of edge types (OGB data-flow specific).
    num_train_samples: number of training samples (i.e., samples per epoch).
    idx2vocab: maps id in target vocabulary to ids.
    vocab2idx: maps id in target vocabulary to ids.
  """
  name: str
  path: str
  sequence_length: int
  num_classes: int
  ast_depth: int
  num_nodetypes: int
  num_nodeattributes: int
  edge_df_types: Optional[int]
  edge_ast_types: Optional[int]
  num_train_samples: int
  idx2vocab: Optional[Mapping[int, str]]
  vocab2idx: Optional[Mapping[str, int]]


# Standard OGB Code2 dataset
OGBG_CODE2 = Dataset('ogbg-code2', 'ogbg-code2', 5, 5002, 20, 98, 10030, None,
                     None, 407_976, None, None)

# Standard OGB Code2 dataset with edges only in one direction
OGBG_CODE2_NOREV = Dataset('ogbg-code2-norev', 'ogbg-code2-norev', 5, 5002, 20,
                           98, 10030, None, None, 407_976, None, None)

# Data-Flow centric OGB Code2 dataset
OGBG_CODE2_NOREV_DF = Dataset('ogbg-code2-norev-df', 'ogbg-code2-norev-df', 5,
                              5002, 20, 113, 11973, 12, 51, 407_976, None, None)

# Sorting network dataset dataset
SORTING_NETWORKS = Dataset('sn', '7to11_12_13to16', 1, 2, -1, -1, 13, None,
                           None, 800_000, None, None)

datasets = {
    'ogbg-code2': OGBG_CODE2,
    'ogbg-code2-norev': OGBG_CODE2_NOREV,
    'ogbg-code2-norev-df': OGBG_CODE2_NOREV_DF,
    'sn-7to11-12-13to16': SORTING_NETWORKS
}


def get_config(preset=''):
  """Return config object for training."""
  config = get_default_config()

  # E.g. '/data/pretrained_models'
  config.restore_path = config_dict.placeholder(str)

  if preset:
    unique_presets = list(collections.OrderedDict.fromkeys(preset.split(',')))
    config = presets.apply_presets(config, unique_presets)

  config.experiment_kwargs.config.dataset = datasets[
      config.experiment_kwargs.config.dataset_name]

  # Adjust for presets
  effective_batch_size = config.experiment_kwargs.config.training.batch_size
  if config.experiment_kwargs.config.dataset_config.do_bucket_by_size:
    # Manually determined constant for OGB
    effective_batch_size *= 3.5
  steps_per_epoch = int(
      config.experiment_kwargs.config.dataset.num_train_samples /
      effective_batch_size / 8)
  config.training_steps = config.epochs * steps_per_epoch

  lr_schedule = config.experiment_kwargs.config.optimizer.lr_schedule
  lr_schedule.warmup_steps = config.warmup_epochs * steps_per_epoch
  lr_schedule.decay_steps = config.training_steps

  batch_size = config.experiment_kwargs.config.training.batch_size
  lr_schedule.init_value *= batch_size
  lr_schedule.peak_value *= batch_size
  lr_schedule.end_value *= batch_size

  return config


def get_default_config():
  """Return config object for reproducing SAT on ogbn-code2."""
  config = base_config.get_base_config()

  training_batch_size = 48
  train_devices = 8
  eval_batch_size = 48

  ## Experiment config.
  loss_kwargs = dict(only_punish_first_end_of_sequence_token=False)

  posenc_config = dict(
      posenc_type='',
      exclude_canonical=False,
      relative_positional_encodings=True,
      # RW/PPR
      do_also_reverse=True,
      ppr_restart_probaility=0.2,
      random_walk_steps=3,
      top_k_eigenvectors=10,
      # MagLap
      excl_k_eigenvectors=1,
      concatenate_eigenvalues=False,
      maglap_q=0.25,
      maglap_q_absolute=True,
      maglap_symmetric_norm=False,
      maglap_transformer=False,
      maglap_use_signnet=True,
      maglap_use_gnn=False,
      maglap_norm_comps_sep=False,
      maglap_l2_norm=True,
      maglap_dropout_p=0.,
      maglap_sign_rotate=True)

  dataset_config = dict(
      do_bucket_by_size=False,
      exclude_control_flow_edges=True,  # Only relevant with df graph
      exclude_next_syntax_edges=True  # Only relevant with df graph
  )

  gnn_config = dict(
      gnn_type='gcn',
      k_hop=2,
      mlp_layers=2,  # Does not have any effect on the GCN
      se='gnn',
      tightening_factor=1,
      use_edge_attr=True,
      bidirectional=False,  # has not effect on `gcn``
      residual=False,
      concat=True)

  attention_config = dict(
      num_heads=4,
      dense_widening_factor=4,
      with_bias=False,
      dropout_p=0.2,
      with_attn_dropout=True,
      re_im_separate_projection=False,
      with_posenc_residual=False)

  encoder_config = dict(attribute_dropout=0.)

  model_config = dict(
      model_type='sat',
      num_layers=4,
      d_model=256,
      global_readout='mean',  # other options 'sum_n', 1 (func def node)
      activation='relu',
      batch_norm=False,  # Use LayerNorm otherwise
      deg_sensitive_residual=True,
      attention_config=attention_config,
      encoder_config=encoder_config,
      loss_kwargs=loss_kwargs,
      posenc_config=posenc_config,
      with_pre_gnn=False,
      gnn_config=gnn_config)

  evaluation_config = dict(
      eval_also_on_test=True,
      batch_size=eval_batch_size,
      max_number_of_instances=-1,
      unk_offset=0.,
      eos_offset=0.)

  ## Training loop config.
  config.warmup_epochs = 2
  config.epochs = 32
  steps_per_epoch = int(405_000 / training_batch_size / train_devices)

  config.training_steps = config.epochs * steps_per_epoch
  config.log_train_data_interval = 60
  config.log_tensors_interval = 60
  config.save_checkpoint_interval = 300
  config.save_initial_train_checkpoint = False
  config.checkpoint_dir = '/tmp/checkpoint/digraph_transformer'
  config.eval_specific_checkpoint_dir = ''
  config.best_model_eval_metric = 'F1'
  config.best_model_eval_metric_higher_is_better = True

  config.experiment_kwargs = config_dict.ConfigDict(
      dict(
          config=dict(
              # Must be set
              data_root=config_dict.placeholder(str),
              debug=False,
              # Gets overwritten later
              dataset_name='ogbg-code2',
              pmap_axis='i',
              optimizer=dict(
                  name='adamw',
                  optimizer_kwargs=dict(b1=.9, b2=.999, weight_decay=1e-6),
                  lr_schedule=dict(
                      warmup_steps=config.warmup_epochs,
                      decay_steps=config.training_steps,
                      init_value=0.,
                      peak_value=1e-4 / 32,
                      end_value=0.,
                  ),
                  use_agc=False,  # adaptive gradient clipping
                  agc_kwargs=dict(clipping=0.1),
              ),
              model=model_config,
              dataset_config=dataset_config,
              training=dict(batch_size=training_batch_size),
              evaluation=evaluation_config)))

  return config
