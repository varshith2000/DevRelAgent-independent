"""
Validation Framework — Test and Validate Agent Performance

Implements validation against real incidents:
- Root cause accuracy measurement
- Actionability measurement
- Human work reduction measurement
- Feature pruning
"""

import logging
import json
from typing import Dict, Any, List, Optional, Literal, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ValidationTestCase:
    """Test case for validation."""
    case_id: str
    title: str
    description: str

    # Incident details
    incident_summary: str
    expected_root_cause: str
    expected_solution: str

    # Validation criteria
    min_confidence: float = 0.7
    max_time_to_resolve_seconds: int = 300
    requires_human_followup: bool = False

    # Metrics
    actual_confidence: Optional[float] = None
    actual_time_seconds: Optional[int] = None
    root_cause_correct: Optional[bool] = None
    solution_actionable: Optional[bool] = None
    human_work_saved_hours: Optional[float] = None

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ValidationResult:
    """Result of validation testing."""
    case_id: str
    validation_date: str = field(default_factory=lambda: datetime.now().isoformat())

    # Accuracy metrics
    root_cause_accuracy: Optional[float] = None
    actionability_score: Optional[float] = None
    confidence_calibration: Optional[float] = None

    # Performance metrics
    avg_time_seconds: Optional[float] = None
    success_rate: float = 0.0

    # Human impact
    avg_human_work_saved_hours: Optional[float] = None
    reduction_in_manual_investigation: Optional[float] = None

    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    features_to_improve: List[str] = field(default_factory=list)
    features_to_remove: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "case_id": self.case_id,
            "validation_date": self.validation_date,
            "root_cause_accuracy": self.root_cause_accuracy,
            "actionability_score": self.actionability_score,
            "confidence_calibration": self.confidence_calibration,
            "avg_time_seconds": self.avg_time_seconds,
            "success_rate": self.success_rate,
            "avg_human_work_saved_hours": self.avg_human_work_saved_hours,
            "reduction_in_manual_investigation": self.reduction_in_manual_investigation,
            "recommendations": self.recommendations,
            "features_to_improve": self.features_to_improve,
            "features_to_remove": self.features_to_remove
        }


class ValidationFramework:
    """
    Validation framework for agent testing.

    Tests agent against real incidents to measure:
    - Root cause accuracy
    - Actionability
    - Human work reduction
    """

    def __init__(self, storage_path: str = "data/validation"):
        """Initialize validation framework."""
        self.storage_path = storage_path
        Path(storage_path).mkdir(parents=True, exist_ok=True)

        self.test_cases: List[ValidationTestCase] = []
        self.results: List[ValidationResult] = []

    def load_test_cases(self, test_cases_file: str = "data/validation/test_cases.json"):
        """Load test cases from file."""
        try:
            with open(test_cases_file, 'r') as f:
                data = json.load(f)

            self.test_cases = [
                ValidationTestCase(**case) for case in data.get("test_cases", [])
            ]

            logger.info(f"Loaded {len(self.test_cases)} test cases")

        except FileNotFoundError:
            logger.warning(f"Test cases file not found: {test_cases_file}")
            # Create sample test cases
            self._create_sample_test_cases()
        except Exception as e:
            logger.error(f"Failed to load test cases: {e}")

    def _create_sample_test_cases(self):
        """Create sample test cases for validation."""
        self.test_cases = [
            ValidationTestCase(
                case_id="test_001",
                title="API Error Rate Spike",
                description="API error rate increased from 2% to 15% over 30 minutes",
                incident_summary="Users reported API errors starting at 10:00 UTC. Error rate jumped from normal 2% to 15%.",
                expected_root_cause="Database connection pool exhaustion",
                expected_solution="Increase database connection pool size and implement retry logic",
                min_confidence=0.7,
                max_time_to_resolve_seconds=180
            ),
            ValidationTestCase(
                case_id="test_002",
                title="High Latency on Checkout",
                description="Checkout endpoint showing P95 latency of 5 seconds",
                incident_summary="Customers complaining about slow checkout. P95 latency normally 200ms, now 5s.",
                expected_root_cause="Inefficient database query in checkout flow",
                expected_solution="Add database index and optimize query",
                min_confidence=0.8,
                max_time_to_resolve_seconds=240
            ),
            ValidationTestCase(
                case_id="test_003",
                title="Cache Miss Storm",
                description="High cache miss rate causing database overload",
                incident_summary="Cache miss rate increased to 80%, causing database overload and slow responses.",
                expected_root_cause="Cache TTL too low, causing frequent evictions",
                expected_solution="Increase cache TTL and implement cache warming",
                min_confidence=0.75,
                max_time_to_resolve_seconds=120
            )
        ]

    async def run_validation(
        self,
        agent_func: callable,
        sample_size: Optional[int] = None
    ) -> List[ValidationResult]:
        """
        Run validation against test cases.

        Args:
            agent_func: Agent function to test (takes query, returns response)
            sample_size: Number of test cases to run (None for all)

        Returns:
            List of validation results
        """
        results = []

        test_cases = self.test_cases[:sample_size] if sample_size else self.test_cases

        logger.info(f"Running validation on {len(test_cases)} test cases")

        for test_case in test_cases:
            logger.info(f"Testing: {test_case.title}")

            try:
                start_time = datetime.now()

                # Run agent
                response = await agent_func(test_case.incident_summary)

                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()

                # Extract confidence if structured response
                confidence = response.get("confidence", 0.5) if isinstance(response, dict) else 0.5

                # Validate result
                result = await self._validate_result(
                    test_case=test_case,
                    response=response,
                    duration_seconds=int(duration)
                )

                result.case_id = test_case.case_id
                results.append(result)

            except Exception as e:
                logger.error(f"Validation failed for {test_case.case_id}: {e}")

                result = ValidationResult(
                    case_id=test_case.case_id,
                    success_rate=0.0
                )
                results.append(result)

        # Save results
        self.results = results
        self._save_results()

        # Generate recommendations
        recommendations = self._generate_recommendations(results)
        self._save_recommendations(recommendations)

        return results

    async def _validate_result(
        self,
        test_case: ValidationTestCase,
        response: Any,
        duration_seconds: int
    ) -> ValidationResult:
        """
        Validate single test case result.

        Args:
            test_case: Test case that was run
            response: Agent response
            duration_seconds: Time taken

        Returns:
            Validation result
        """
        result = ValidationResult(case_id=test_case.case_id)

        # Check confidence calibration
        result.confidence_calibration = self._calculate_confidence_calibration(
            test_case,
            response
        )

        # Check if completed in time
        result.success_rate = 1.0 if duration_seconds <= test_case.max_time_to_resolve_seconds else 0.0

        # Extract and validate root cause
        # This would need manual verification or automated checks
        # For now, set to None (requires human validation)

        # Extract actionability
        result.actionability_score = self._calculate_actionability(response)

        # Calculate time performance
        result.avg_time_seconds = duration_seconds

        # Generate initial recommendations
        result.recommendations = self._generate_case_recommendations(
            test_case,
            response,
            duration_seconds
        )

        return result

    def _calculate_confidence_calibration(
        self,
        test_case: ValidationTestCase,
        response: Any
    ) -> float:
        """Calculate confidence calibration score."""
        # Extract confidence from response
        confidence = 0.5

        if isinstance(response, dict):
            confidence = response.get("confidence", 0.5)

        # Check if confidence meets minimum
        meets_minimum = confidence >= test_case.min_confidence

        # Calibration: actual vs expected confidence
        # In production, this would compare with human-rated confidence
        return confidence if meets_minimum else 0.0

    def _calculate_actionability(self, response: Any) -> float:
        """Calculate actionability score."""
        if not isinstance(response, dict):
            return 0.0

        # Check for suggested actions
        suggested_actions = response.get("suggested_actions", [])
        next_steps = response.get("next_steps", [])

        total_actions = len(suggested_actions) + len(next_steps)

        if total_actions == 0:
            return 0.0

        # Actionability based on:
        # - Number of actions
        # - Specificity of actions
        # - Clarity of actions

        score = min(total_actions * 0.2, 1.0)

        # Boost for specific, actionable items
        action_keywords = ["create", "update", "add", "configure", "restart"]
        for action_list in [suggested_actions, next_steps]:
            for action in action_list:
                if any(keyword in action.lower() for keyword in action_keywords):
                    score += 0.1

        return min(score, 1.0)

    def _generate_case_recommendations(
        self,
        test_case: ValidationTestCase,
        response: Any,
        duration_seconds: int
    ) -> List[str]:
        """Generate recommendations for a single test case."""
        recommendations = []

        # Time-based recommendations
        if duration_seconds > test_case.max_time_to_resolve_seconds:
            recommendations.append(
                f"⚠️ Resolution time ({duration_seconds}s) exceeded target ({test_case.max_time_to_resolve_seconds}s)"
            )

        # Confidence-based recommendations
        if isinstance(response, dict):
            confidence = response.get("confidence", 0.0)
            if confidence < test_case.min_confidence:
                recommendations.append(
                    f"⚠️ Confidence ({confidence}) below minimum ({test_case.min_confidence})"
                )

        # Actionability recommendations
        actionability = self._calculate_actionability(response)
        if actionability < 0.5:
            recommendations.append(
                "⚠️ Response lacks specific actionable steps. Improve with concrete suggestions."
            )

        return recommendations

    def _generate_recommendations(self, results: List[ValidationResult]) -> Dict[str, Any]:
        """Generate overall recommendations from validation results."""
        overall_recommendations = {
            "features_to_improve": [],
            "features_to_remove": [],
            "overall_assessment": "",
            "metrics": {}
        }

        # Calculate metrics
        if results:
            # Success rate
            success_rate = sum(r.success_rate for r in results) / len(results)
            overall_recommendations["metrics"]["success_rate"] = round(success_rate, 2)

            # Average confidence calibration
            calibrations = [r.confidence_calibration for r in results if r.confidence_calibration is not None]
            if calibrations:
                avg_calibration = sum(calibrations) / len(calibrations)
                overall_recommendations["metrics"]["avg_confidence_calibration"] = round(avg_calibration, 2)

            # Average actionability
            actionabilities = [r.actionability_score for r in results if r.actionability_score is not None]
            if actionabilities:
                avg_actionability = sum(actionabilities) / len(actionabilities)
                overall_recommendations["metrics"]["avg_actionability_score"] = round(avg_actionability, 2)

            # Generate assessment
            if success_rate >= 0.8:
                overall_recommendations["overall_assessment"] = "✅ GOOD - Agent performing well"
            elif success_rate >= 0.6:
                overall_recommendations["overall_assessment"] = "⚠️ FAIR - Agent needs improvement"
            else:
                overall_recommendations["overall_assessment"] = "❌ POOR - Agent needs significant work"

            # Feature recommendations
            overall_recommendations["features_to_improve"] = [
                "Low actionability scores" if overall_recommendations["metrics"].get("avg_actionability_score", 0) < 0.5 else None,
                "Low confidence calibration" if overall_recommendations["metrics"].get("avg_confidence_calibration", 0) < 0.7 else None,
                "Slow performance" if any(r.avg_time_seconds and r.avg_time_seconds > 300 for r in results) else None
            ]

            # Remove None values
            overall_recommendations["features_to_improve"] = [
                f for f in overall_recommendations["features_to_improve"] if f
            ]

        return overall_recommendations

    def _save_results(self):
        """Save validation results."""
        try:
            results_file = os.path.join(self.storage_path, "validation_results.json")

            with open(results_file, 'w') as f:
                json.dump([r.to_dict() for r in self.results], f, indent=2, default=str)

            logger.info(f"Saved {len(self.results)} validation results")

        except Exception as e:
            logger.error(f"Failed to save validation results: {e}")

    def _save_recommendations(self, recommendations: Dict[str, Any]):
        """Save recommendations."""
        try:
            rec_file = os.path.join(self.storage_path, "recommendations.json")

            with open(rec_file, 'w') as f:
                json.dump(recommendations, f, indent=2)

            logger.info("Saved validation recommendations")

        except Exception as e:
            logger.error(f"Failed to save recommendations: {e}")

    def get_underused_intents(self, usage_data: Dict[str, int], threshold: float = 0.05) -> List[str]:
        """
        Identify underused intents for feature pruning.

        Args:
            usage_data: Dictionary mapping intents to usage counts
            threshold: Usage threshold (below this = underused)

        Returns:
            List of underused intents to consider removing
        """
        total_usage = sum(usage_data.values())

        if total_usage == 0:
            return []

        underused = []

        for intent, count in usage_data.items():
            usage_rate = count / total_usage

            if usage_rate < threshold:
                underused.append(intent)

        return underused


# ============== Global Instance ==============

_default_validator: Optional[ValidationFramework] = None


def get_validation_framework() -> ValidationFramework:
    """Get the global validation framework instance."""
    global _default_validator
    if _default_validator is None:
        _default_validator = ValidationFramework()
    return _default_validator
