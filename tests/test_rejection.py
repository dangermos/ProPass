"""Cosine gates retain SKU conditioning and deterministic multimodal banks."""
import pytest
import torch
from torch.nn import functional as F

from vision.rejection import cosine_cluster_bank, prototype_distance


def test_legacy_single_prototypes_keep_original_cosine_distances():
    features = F.normalize(torch.tensor([[1., 2., 0.], [0., 2., 3.]]), dim=1)
    prototypes = F.normalize(torch.tensor([[2., 1., 0.], [0., 1., 2.]]), dim=1)
    predicted = torch.tensor([0, 1])
    expected = 1-(features*prototypes[predicted]).sum(1)
    assert torch.allclose(prototype_distance(features, predicted, prototypes), expected)


def test_bank_preserves_distinct_views_that_the_single_mean_rejects():
    features = torch.eye(2)
    means = F.normalize(torch.tensor([[1., 1.]]), dim=1)
    bank = torch.eye(2)[None]
    predicted = torch.zeros(2, dtype=torch.long)
    assert (prototype_distance(features, predicted, means)>.25).all()
    assert torch.equal(prototype_distance(features, predicted, means, bank), torch.zeros(2))


def test_predicted_class_is_enforced_instead_of_searching_all_skus():
    bank = torch.tensor([[[1., 0.]], [[0., 1.]]])
    assert prototype_distance(torch.tensor([[0., 1.]]), torch.tensor([0]), None, bank).item() == 1


def test_direct_three_dimensional_prototypes_work_without_explicit_bank():
    bank = torch.eye(2)[None]
    assert prototype_distance(torch.tensor([[0., 1.]]), torch.tensor([0]), bank).item() == 0


def test_explicit_bank_has_priority_over_the_legacy_prototype():
    old = torch.tensor([[0., 1.]])
    bank = torch.tensor([[[1., 0.]]])
    assert prototype_distance(torch.tensor([[1., 0.]]), torch.tensor([0]), old, bank).item() == 0


@pytest.mark.parametrize("feature", [[[0., 0.]], [[float('nan'), 1.]], [[float('inf'), 0.]]])
def test_invalid_features_fail_closed(feature):
    distance = prototype_distance(torch.tensor(feature), torch.tensor([0]), torch.tensor([[1., 0.]]))
    assert torch.isinf(distance).all()


def test_invalid_prototypes_do_not_create_a_false_match():
    bank = torch.tensor([[[float('nan'), 1.], [0., 0.], [1., 0.]]])
    assert prototype_distance(torch.tensor([[1., 0.]]), torch.tensor([0]), None, bank).item() == 0


def test_empty_prediction_batch_is_supported():
    assert prototype_distance(torch.empty(0, 2), torch.empty(0, dtype=torch.long), torch.eye(2)).shape == (0,)


def test_no_prototypes_disable_only_the_distance_gate():
    assert torch.equal(prototype_distance(torch.eye(2), torch.tensor([0, 1]), None), torch.zeros(2))


@pytest.mark.parametrize("predicted", [torch.tensor([-1]), torch.tensor([2])])
def test_out_of_range_class_indices_raise(predicted):
    with pytest.raises(ValueError, match="outside"):
        prototype_distance(torch.tensor([[1., 0.]]), predicted, torch.eye(2))


def test_dimension_mismatch_raises():
    with pytest.raises(ValueError, match="matching features"):
        prototype_distance(torch.tensor([[1., 0.]]), torch.tensor([0]), torch.eye(3))


def test_cluster_bank_is_deterministic_and_unit_normalized():
    features = torch.tensor([[1., 0., 0.], [.9, .1, 0.], [0., 1., 0.], [.1, .9, 0.],
                             [0., 0., 1.], [0., .1, .9], [0., -.1, .9]])
    labels = torch.tensor([0, 0, 0, 0, 1, 1, 1])
    first, details = cosine_cluster_bank(features, labels, 2, clusters=2)
    second, _ = cosine_cluster_bank(features, labels, 2, clusters=2)
    assert torch.equal(first, second)
    assert torch.allclose(first.norm(dim=2), torch.ones(2, 2))
    assert details[0]["samples"] == 4
    assert details[1]["samples"] == 3
    assert prototype_distance(torch.tensor([[1., 0., 0.], [0., 1., 0.]]),
                              torch.tensor([0, 0]), None, first).max() < .01


def test_classes_smaller_than_k_keep_a_valid_rectangular_bank():
    bank, details = cosine_cluster_bank(torch.eye(2), torch.tensor([0, 1]), 2, clusters=8)
    assert bank.shape == (2, 8, 2)
    assert torch.equal(bank[0], torch.tensor([[1., 0.]]).repeat(8, 1))
    assert details[0]["active_clusters"] == 1


def test_missing_training_classes_fail_instead_of_making_zero_prototypes():
    with pytest.raises(ValueError, match="no training features"):
        cosine_cluster_bank(torch.tensor([[1., 0.]]), torch.tensor([0]), 2)
