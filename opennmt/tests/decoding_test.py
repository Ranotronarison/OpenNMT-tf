import tensorflow as tf
import numpy as np

from opennmt.utils import decoding


def _generate_logits_fn(vocab_size, to_generate):
  to_generate = tf.convert_to_tensor(to_generate, dtype=tf.int32)

  def _logits_fn(symbols, step, state):
    logits = tf.one_hot(to_generate[:, step], vocab_size, dtype=tf.float32)
    return logits, state

  return _logits_fn


class DecodingTest(tf.test.TestCase):

  def testPenalizeToken(self):
    log_probs = tf.zeros([4, 6])
    token_id = 1
    log_probs = decoding._penalize_token(log_probs, token_id)
    log_probs = self.evaluate(log_probs)
    self.assertTrue(np.all(log_probs[:, token_id] < 0))
    non_penalized = np.delete(log_probs, 1, token_id)
    self.assertEqual(np.sum(non_penalized), 0)

  def testGreedyDecode(self):
    logits_fn = _generate_logits_fn(10, [[4, 5, 6, 2], [3, 8, 2, 8]])
    ids, lengths, _, _, _ = decoding.dynamic_decode(logits_fn, [1, 1], end_id=2)
    self.assertAllEqual(self.evaluate(ids), [[[4, 5, 6, 2]], [[3, 8, 2, 2]]])
    self.assertAllEqual(self.evaluate(lengths), [[3], [2]])

  def testGreedyDecodeWithMaximumIterations(self):
    logits_fn = _generate_logits_fn(10, [[4, 5, 6, 2], [3, 8, 2, 8]])
    ids, lengths, _, _, _ = decoding.dynamic_decode(
        logits_fn, [1, 1], end_id=2, maximum_iterations=2)
    self.assertAllEqual(self.evaluate(ids), [[[4, 5]], [[3, 8]]])
    self.assertAllEqual(self.evaluate(lengths), [[2], [2]])

  def testGreedyDecodeWithMinimumIterations(self):
    logits_fn = _generate_logits_fn(10, [[4, 2, 2, 2], [3, 8, 7, 2]])
    ids, lengths, _, _, _ = decoding.dynamic_decode(
        logits_fn, [1, 1], end_id=2, minimum_iterations=2)
    self.assertAllEqual(self.evaluate(lengths), [[2], [3]])


if __name__ == "__main__":
  tf.test.main()
