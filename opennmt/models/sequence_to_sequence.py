"""Standard sequence-to-sequence model."""

import tensorflow as tf

import opennmt.constants as constants

from opennmt.models.model import Model
from opennmt.utils.losses import masked_sequence_loss


class SequenceToSequence(Model):

  def __init__(self,
               source_embedder,
               target_embedder,
               encoder,
               decoder,
               name="seq2seq"):
    super(SequenceToSequence, self).__init__(name)

    self.encoder = encoder
    self.decoder = decoder

    self.source_embedder = source_embedder
    self.target_embedder = target_embedder

    self.source_embedder.set_name("source")
    self.target_embedder.set_name("target")

  def _features_length(self, features):
    return self.source_embedder.get_data_field(features, "length")

  def _labels_length(self, labels):
    return self.target_embedder.get_data_field(labels, "length")

  def _shift_target(self, labels):
    """Generate shifted target sequences with <s> and </s>."""
    bos = tf.cast(tf.constant([constants.START_OF_SENTENCE_ID]), tf.int64)
    eos = tf.cast(tf.constant([constants.END_OF_SENTENCE_ID]), tf.int64)

    ids = self.target_embedder.get_data_field(labels, "ids")
    length = self.target_embedder.get_data_field(labels, "length")

    labels = self.target_embedder.set_data_field(
      labels,
      "ids_out",
      tf.concat([ids, eos], axis=0),
      padded_shape=[None])
    labels = self.target_embedder.set_data_field(
      labels,
      "ids",
      tf.concat([bos, ids], axis=0),
      padded_shape=[None])

    # Increment length accordingly.
    self.target_embedder.set_data_field(labels, "length", length + 1)

    return labels

  def _build_features(self, features_file):
    dataset = self.source_embedder.make_dataset(features_file)
    return dataset, self.source_embedder.padded_shapes

  def _build_labels(self, labels_file):
    dataset = self.target_embedder.make_dataset(labels_file)
    dataset = dataset.map(self._shift_target)
    return dataset, self.target_embedder.padded_shapes

  def _build(self, features, labels, params, mode):
    batch_size = tf.shape(self.source_embedder.get_data_field(features, "length"))[0]

    with tf.variable_scope("encoder"):
      source_inputs = self.source_embedder.embed_from_data(
        features,
        mode,
        log_dir=params.get("log_dir"))

      encoder_outputs, encoder_states, encoder_sequence_length = self.encoder.encode(
        source_inputs,
        sequence_length=self.source_embedder.get_data_field(features, "length"),
        mode=mode)

    with tf.variable_scope("decoder") as decoder_scope:
      if mode != tf.estimator.ModeKeys.PREDICT:
        target_inputs = self.target_embedder.embed_from_data(
          labels,
          mode,
          log_dir=params.get("log_dir"))

        decoder_outputs, _, decoded_length = self.decoder.decode(
          target_inputs,
          self.target_embedder.get_data_field(labels, "length"),
          self.target_embedder.vocabulary_size,
          encoder_states,
          mode=mode,
          memory=encoder_outputs,
          memory_sequence_length=encoder_sequence_length)
      else:
        decoder_outputs, _, decoded_length = self.decoder.dynamic_decode_and_search(
          lambda x: self.target_embedder.embed(x, mode, scope=decoder_scope, reuse_next=True),
          tf.fill([batch_size], constants.START_OF_SENTENCE_ID),
          constants.END_OF_SENTENCE_ID,
          self.target_embedder.vocabulary_size,
          encoder_states,
          beam_width=params.get("beam_width") or 5,
          length_penalty=params.get("length_penalty") or 0.0,
          maximum_iterations=params.get("maximum_iterations") or 250,
          mode=mode,
          memory=encoder_outputs,
          memory_sequence_length=encoder_sequence_length)

    if mode != tf.estimator.ModeKeys.PREDICT:
      loss = masked_sequence_loss(
        decoder_outputs,
        self.target_embedder.get_data_field(labels, "ids_out"),
        self.target_embedder.get_data_field(labels, "length"))

      return tf.estimator.EstimatorSpec(
        mode,
        loss=loss,
        train_op=self._build_train_op(loss, params))
    else:
      target_vocab_rev = tf.contrib.lookup.index_to_string_table_from_file(
        self.target_embedder.vocabulary_file,
        vocab_size=self.target_embedder.vocabulary_size - self.target_embedder.num_oov_buckets,
        default_value=constants.UNKNOWN_TOKEN)
      predictions = {}
      predictions["tokens"] = target_vocab_rev.lookup(tf.cast(decoder_outputs, tf.int64))
      predictions["length"] = decoded_length

      return tf.estimator.EstimatorSpec(
        mode,
        predictions=predictions)

  def format_prediction(self, prediction, params=None):
    n_best = params and params.get("n_best")
    n_best = n_best or 1

    if n_best > len(prediction["tokens"]):
      raise ValueError("n_best cannot be greater than beam_width")

    all_preds = []
    for i in range(n_best):
      tokens = prediction["tokens"][i][:prediction["length"][i] - 1] # Ignore </s>.
      sentence = b' '.join(tokens)
      sentence = sentence.decode('utf-8')
      all_preds.append(sentence)

    return all_preds
