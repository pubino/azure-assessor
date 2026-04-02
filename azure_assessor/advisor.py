"""Alternative SKU recommendations with compatibility scoring."""

from __future__ import annotations

from azure_assessor.models import (
    PriceInfo,
    SkuAvailability,
    SkuRecommendation,
    VmSku,
)


class SkuAdvisor:
    """Recommends alternative VM SKUs based on compatibility scoring."""

    def find_alternatives(
        self,
        target: VmSku,
        available_skus: list[VmSku],
        availability_map: dict[str, SkuAvailability] | None = None,
        price_map: dict[str, PriceInfo] | None = None,
        max_results: int = 10,
    ) -> list[SkuRecommendation]:
        """Find alternative SKUs similar to the target, ranked by compatibility."""
        availability_map = availability_map or {}
        price_map = price_map or {}
        recommendations: list[SkuRecommendation] = []

        for candidate in available_skus:
            if candidate.name == target.name:
                continue

            score, reasons = self._compute_score(target, candidate)
            if score < 0.1:
                continue

            avail = availability_map.get(candidate.name)
            if avail and not avail.available:
                continue

            recommendations.append(
                SkuRecommendation(
                    sku=candidate,
                    compatibility_score=score,
                    price=price_map.get(candidate.name),
                    reasons=reasons,
                    availability=avail,
                )
            )

        recommendations.sort(key=lambda r: r.compatibility_score, reverse=True)
        return recommendations[:max_results]

    def _compute_score(
        self, target: VmSku, candidate: VmSku
    ) -> tuple[float, list[str]]:
        """Compute compatibility score between 0.0 and 1.0."""
        scores: list[float] = []
        reasons: list[str] = []

        # vCPU match (weighted heavily)
        vcpu_ratio = min(target.vcpus, candidate.vcpus) / max(target.vcpus, candidate.vcpus) if target.vcpus else 0
        scores.append(vcpu_ratio * 0.30)
        if candidate.vcpus >= target.vcpus:
            reasons.append(f"vCPUs: {candidate.vcpus} (meets {target.vcpus})")
        else:
            reasons.append(f"vCPUs: {candidate.vcpus} (below {target.vcpus})")

        # Memory match (weighted heavily)
        mem_ratio = min(target.memory_gb, candidate.memory_gb) / max(target.memory_gb, candidate.memory_gb) if target.memory_gb else 0
        scores.append(mem_ratio * 0.25)
        if candidate.memory_gb >= target.memory_gb:
            reasons.append(f"Memory: {candidate.memory_gb}GB (meets {target.memory_gb}GB)")
        else:
            reasons.append(f"Memory: {candidate.memory_gb}GB (below {target.memory_gb}GB)")

        # Same family bonus
        if target.family == candidate.family:
            scores.append(0.15)
            reasons.append(f"Same family: {candidate.family}")
        else:
            scores.append(0.0)

        # GPU match
        if target.gpu_count > 0:
            if candidate.gpu_count >= target.gpu_count:
                scores.append(0.15)
                reasons.append(f"GPU: {candidate.gpu_count} (meets {target.gpu_count})")
            elif candidate.gpu_count > 0:
                gpu_ratio = candidate.gpu_count / target.gpu_count
                scores.append(gpu_ratio * 0.15)
                reasons.append(f"GPU: {candidate.gpu_count} (partial match for {target.gpu_count})")
            else:
                scores.append(0.0)
                reasons.append("No GPU (target requires GPU)")
        else:
            scores.append(0.10)  # Non-GPU workload, any candidate fine

        # Data disk match
        if target.max_data_disks > 0:
            disk_ratio = min(target.max_data_disks, candidate.max_data_disks) / max(target.max_data_disks, candidate.max_data_disks)
            scores.append(disk_ratio * 0.05)
        else:
            scores.append(0.05)

        # Accelerated networking match
        if target.accelerated_networking and candidate.accelerated_networking:
            scores.append(0.05)
            reasons.append("Accelerated networking supported")
        elif target.accelerated_networking and not candidate.accelerated_networking:
            scores.append(0.0)
            reasons.append("Missing accelerated networking")
        else:
            scores.append(0.05)

        total = min(1.0, sum(scores))
        return round(total, 3), reasons
