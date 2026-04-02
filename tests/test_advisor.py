"""Tests for the SKU advisor module."""

import pytest

from azure_assessor.advisor import SkuAdvisor
from azure_assessor.models import SkuAvailability, VmSku


@pytest.fixture
def advisor() -> SkuAdvisor:
    return SkuAdvisor()


@pytest.fixture
def candidate_skus(sample_sku_d8s_v3, sample_sku_e4s_v5, sample_sku_nc6) -> list[VmSku]:
    return [sample_sku_d8s_v3, sample_sku_e4s_v5, sample_sku_nc6]


class TestSkuAdvisor:
    def test_find_alternatives_basic(self, advisor, sample_sku_d4s_v3, candidate_skus):
        results = advisor.find_alternatives(sample_sku_d4s_v3, candidate_skus)
        assert len(results) > 0
        assert all(r.compatibility_score > 0 for r in results)

    def test_alternatives_sorted_by_score(self, advisor, sample_sku_d4s_v3, candidate_skus):
        results = advisor.find_alternatives(sample_sku_d4s_v3, candidate_skus)
        scores = [r.compatibility_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_same_family_gets_bonus(self, advisor, sample_sku_d4s_v3):
        """Same-family candidates get a family bonus in their score."""
        same_family = VmSku(
            name="Standard_D4_v3", family="standardDSv3Family", size="D4_v3",
            tier="Standard", vcpus=4, memory_gb=16.0, max_data_disks=8,
            os_disk_size_gb=1023, max_nics=2, accelerated_networking=True,
        )
        diff_family = VmSku(
            name="Standard_E4_v3", family="standardESv3Family", size="E4_v3",
            tier="Standard", vcpus=4, memory_gb=16.0, max_data_disks=8,
            os_disk_size_gb=1023, max_nics=2, accelerated_networking=True,
        )
        results = advisor.find_alternatives(sample_sku_d4s_v3, [same_family, diff_family])
        same_score = next(r for r in results if r.sku.name == "Standard_D4_v3").compatibility_score
        diff_score = next(r for r in results if r.sku.name == "Standard_E4_v3").compatibility_score
        assert same_score > diff_score, "Same-family SKU should score higher when specs are equal"

    def test_excludes_target_sku(self, advisor, sample_sku_d4s_v3, candidate_skus):
        # Add target to candidates
        all_skus = [sample_sku_d4s_v3] + candidate_skus
        results = advisor.find_alternatives(sample_sku_d4s_v3, all_skus)
        result_names = {r.sku.name for r in results}
        assert "Standard_D4s_v3" not in result_names

    def test_excludes_unavailable_skus(self, advisor, sample_sku_d4s_v3, candidate_skus):
        avail_map = {
            "Standard_D8s_v3": SkuAvailability(
                sku_name="Standard_D8s_v3", region="eastus", available=False,
                restrictions=["NotAvailableForSubscription"],
            ),
            "Standard_E4s_v5": SkuAvailability(
                sku_name="Standard_E4s_v5", region="eastus", available=True,
            ),
        }
        results = advisor.find_alternatives(
            sample_sku_d4s_v3, candidate_skus, availability_map=avail_map
        )
        result_names = {r.sku.name for r in results}
        assert "Standard_D8s_v3" not in result_names

    def test_max_results(self, advisor, sample_sku_d4s_v3, candidate_skus):
        results = advisor.find_alternatives(
            sample_sku_d4s_v3, candidate_skus, max_results=1
        )
        assert len(results) <= 1

    def test_score_range(self, advisor, sample_sku_d4s_v3, candidate_skus):
        results = advisor.find_alternatives(sample_sku_d4s_v3, candidate_skus)
        for r in results:
            assert 0.0 <= r.compatibility_score <= 1.0

    def test_reasons_populated(self, advisor, sample_sku_d4s_v3, candidate_skus):
        results = advisor.find_alternatives(sample_sku_d4s_v3, candidate_skus)
        for r in results:
            assert len(r.reasons) > 0

    def test_gpu_workload_recommendation(self, advisor, sample_sku_nc6):
        """GPU SKUs should score poorly against non-GPU candidates."""
        non_gpu = VmSku(
            name="Standard_D16s_v3", family="standardDSv3Family", size="D16s_v3",
            tier="Standard", vcpus=16, memory_gb=64.0, max_data_disks=32,
            os_disk_size_gb=1023, max_nics=8, accelerated_networking=True,
        )
        results = advisor.find_alternatives(sample_sku_nc6, [non_gpu])
        # Non-GPU candidate should get penalized for GPU workloads
        assert results[0].compatibility_score < 0.9

    def test_empty_candidates(self, advisor, sample_sku_d4s_v3):
        results = advisor.find_alternatives(sample_sku_d4s_v3, [])
        assert results == []


class TestComputeScore:
    def test_identical_specs_high_score(self, advisor):
        sku_a = VmSku(
            name="A", family="familyA", size="A", tier="Standard",
            vcpus=4, memory_gb=16.0, max_data_disks=8, os_disk_size_gb=1023,
            max_nics=2, accelerated_networking=True,
        )
        sku_b = VmSku(
            name="B", family="familyA", size="B", tier="Standard",
            vcpus=4, memory_gb=16.0, max_data_disks=8, os_disk_size_gb=1023,
            max_nics=2, accelerated_networking=True,
        )
        score, reasons = advisor._compute_score(sku_a, sku_b)
        assert score >= 0.9

    def test_very_different_specs_low_score(self, advisor):
        sku_a = VmSku(
            name="A", family="familyA", size="A", tier="Standard",
            vcpus=64, memory_gb=256.0, max_data_disks=32, os_disk_size_gb=1023,
            max_nics=8, accelerated_networking=True, gpu_count=4,
        )
        sku_b = VmSku(
            name="B", family="familyB", size="B", tier="Standard",
            vcpus=2, memory_gb=4.0, max_data_disks=4, os_disk_size_gb=1023,
            max_nics=1, accelerated_networking=False,
        )
        score, reasons = advisor._compute_score(sku_a, sku_b)
        assert score < 0.5
