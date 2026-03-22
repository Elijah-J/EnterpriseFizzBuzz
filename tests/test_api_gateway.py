"""
Enterprise FizzBuzz Platform - API Gateway Tests

Comprehensive test suite for the API Gateway with Routing, Versioning &
Request Transformation, ensuring that every aspect of the non-existent
REST API gateway is thoroughly tested. Because untested infrastructure
for a fictional API is the only thing worse than tested infrastructure
for a fictional API.

Tests cover:
- APIRequest and APIResponse dataclasses
- Request ID generation (must be exactly 340 characters)
- Route and RouteTable path matching with version filtering
- VersionRouter: version resolution, deprecation warnings, Sunset headers
- Request transformers: normalizer, enricher, validator, deprecation injector
- Response transformers: compressor (-847% savings), pagination, HATEOAS
- RequestTransformerChain and ResponseTransformerChain
- APIKeyManager: generate, validate, revoke, quota tracking
- RequestReplayJournal: append, replay, capacity
- APIGateway: full request processing pipeline
- GatewayMiddleware: integration with FizzBuzz pipeline
- GatewayDashboard: ASCII rendering
- Gateway exception hierarchy (EFP-GW00 through EFP-GW09)
- EventType entries for gateway events
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from enterprise_fizzbuzz.domain.exceptions import (
    APIKeyInvalidError,
    APIKeyQuotaExceededError,
    FizzBuzzError,
    GatewayDashboardRenderError,
    GatewayError,
    RequestReplayError,
    RequestTransformationError,
    ResponseTransformationError,
    RouteNotFoundError,
    VersionDeprecatedError,
    VersionNotSupportedError,
)
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext
from enterprise_fizzbuzz.infrastructure.api_gateway import (
    APIGateway,
    APIKeyManager,
    APIRequest,
    APIResponse,
    DeprecationInjector,
    GatewayDashboard,
    GatewayMiddleware,
    HATEOASEnricher,
    PaginationWrapper,
    RequestEnricher,
    RequestNormalizer,
    RequestReplayJournal,
    RequestTransformerChain,
    RequestValidator,
    ResponseCompressor,
    ResponseTransformerChain,
    Route,
    RouteTable,
    VersionRouter,
    _REQUEST_ID_TARGET_LENGTH,
    generate_enterprise_request_id,
)


# ---------------------------------------------------------------------------
# Test: Request ID Generation
# ---------------------------------------------------------------------------

class TestRequestIDGeneration(unittest.TestCase):
    """Tests for the 340-character enterprise request ID generator."""

    def test_request_id_is_exactly_340_characters(self):
        """The request ID must be exactly 340 characters. No more, no less."""
        rid = generate_enterprise_request_id()
        self.assertEqual(len(rid), 340)

    def test_request_id_target_length_constant(self):
        """The target length constant must be 340."""
        self.assertEqual(_REQUEST_ID_TARGET_LENGTH, 340)

    def test_request_ids_are_unique(self):
        """Each generated request ID should be unique (with high probability)."""
        ids = {generate_enterprise_request_id() for _ in range(50)}
        self.assertEqual(len(ids), 50)

    def test_request_id_is_string(self):
        """Request IDs must be strings."""
        rid = generate_enterprise_request_id()
        self.assertIsInstance(rid, str)


# ---------------------------------------------------------------------------
# Test: APIRequest / APIResponse
# ---------------------------------------------------------------------------

class TestAPIRequest(unittest.TestCase):
    """Tests for the APIRequest dataclass."""

    def test_default_request_has_340_char_id(self):
        """Default requests should auto-generate a 340-char ID."""
        req = APIRequest()
        self.assertEqual(len(req.request_id), 340)

    def test_custom_request_id(self):
        """Custom request IDs should be preserved."""
        req = APIRequest(request_id="custom-id")
        self.assertEqual(req.request_id, "custom-id")

    def test_default_method_is_get(self):
        """Default method should be GET."""
        req = APIRequest()
        self.assertEqual(req.method, "GET")

    def test_metadata_is_mutable(self):
        """Metadata dict should be mutable."""
        req = APIRequest()
        req.metadata["test"] = "value"
        self.assertEqual(req.metadata["test"], "value")

    def test_warnings_list(self):
        """Warnings should be an appendable list."""
        req = APIRequest()
        req.warnings.append("test warning")
        self.assertEqual(len(req.warnings), 1)

    def test_timestamp_is_set(self):
        """Timestamp should be set on creation."""
        req = APIRequest()
        self.assertIsInstance(req.timestamp, datetime)


class TestAPIResponse(unittest.TestCase):
    """Tests for the APIResponse dataclass."""

    def test_default_status_code(self):
        """Default status code should be 200."""
        resp = APIResponse()
        self.assertEqual(resp.status_code, 200)

    def test_headers_are_mutable(self):
        """Headers dict should be mutable."""
        resp = APIResponse()
        resp.headers["x-test"] = "value"
        self.assertEqual(resp.headers["x-test"], "value")


# ---------------------------------------------------------------------------
# Test: Route / RouteTable
# ---------------------------------------------------------------------------

class TestRoute(unittest.TestCase):
    """Tests for the Route frozen dataclass."""

    def test_exact_match(self):
        """Routes should match exact paths with correct method and version."""
        route = Route(
            path_pattern="/api/{version}/fizzbuzz/{number}",
            method="GET",
            handler_name="evaluate",
            versions=("v1", "v2"),
        )
        result = route.matches("/api/v2/fizzbuzz/15", "GET", "v2")
        self.assertIsNotNone(result)
        self.assertEqual(result["version"], "v2")
        self.assertEqual(result["number"], "15")

    def test_wrong_method_no_match(self):
        """Routes should not match on wrong method."""
        route = Route(
            path_pattern="/api/{version}/fizzbuzz/{number}",
            method="GET",
            handler_name="evaluate",
            versions=("v2",),
        )
        result = route.matches("/api/v2/fizzbuzz/15", "POST", "v2")
        self.assertIsNone(result)

    def test_wrong_version_no_match(self):
        """Routes should not match on unsupported version."""
        route = Route(
            path_pattern="/api/{version}/fizzbuzz/{number}",
            method="GET",
            handler_name="evaluate",
            versions=("v2",),
        )
        result = route.matches("/api/v1/fizzbuzz/15", "GET", "v1")
        self.assertIsNone(result)

    def test_path_mismatch_returns_none(self):
        """Routes should return None for non-matching paths."""
        route = Route(
            path_pattern="/api/{version}/fizzbuzz/{number}",
            method="GET",
            handler_name="evaluate",
            versions=("v2",),
        )
        result = route.matches("/api/v2/health", "GET", "v2")
        self.assertIsNone(result)


class TestRouteTable(unittest.TestCase):
    """Tests for the RouteTable."""

    def setUp(self):
        self.table = RouteTable()
        self.route = Route(
            path_pattern="/api/{version}/fizzbuzz/{number}",
            method="GET",
            handler_name="evaluate",
            versions=("v1", "v2", "v3"),
        )
        self.table.register(self.route)

    def test_resolve_matching_route(self):
        """Should resolve a matching route and return params."""
        route, params = self.table.resolve("/api/v2/fizzbuzz/15", "GET", "v2")
        self.assertEqual(route.handler_name, "evaluate")
        self.assertEqual(params["number"], "15")

    def test_resolve_increments_match_count(self):
        """Successful resolution should increment match count."""
        self.table.resolve("/api/v2/fizzbuzz/15", "GET", "v2")
        self.assertEqual(self.table.total_matches, 1)

    def test_resolve_no_match_raises(self):
        """Should raise RouteNotFoundError when no route matches."""
        with self.assertRaises(RouteNotFoundError):
            self.table.resolve("/api/v2/unknown", "GET", "v2")

    def test_miss_increments_miss_count(self):
        """Failed resolution should increment miss count."""
        try:
            self.table.resolve("/api/v2/unknown", "GET", "v2")
        except RouteNotFoundError:
            pass
        self.assertEqual(self.table.total_misses, 1)

    def test_get_routes_for_version(self):
        """Should return routes available for a specific version."""
        routes = self.table.get_routes_for_version("v2")
        self.assertEqual(len(routes), 1)
        routes_v4 = self.table.get_routes_for_version("v4")
        self.assertEqual(len(routes_v4), 0)

    def test_routes_property(self):
        """Routes property should return all registered routes."""
        self.assertEqual(len(self.table.routes), 1)


# ---------------------------------------------------------------------------
# Test: VersionRouter
# ---------------------------------------------------------------------------

class TestVersionRouter(unittest.TestCase):
    """Tests for the VersionRouter."""

    def setUp(self):
        self.config = {
            "v1": {"status": "DEPRECATED", "sunset_date": "2025-12-31", "deprecation_urgency": "CRITICAL"},
            "v2": {"status": "ACTIVE", "sunset_date": None, "deprecation_urgency": None},
            "v3": {"status": "ACTIVE", "sunset_date": None, "deprecation_urgency": None},
        }
        self.router = VersionRouter(self.config, default_version="v2")

    def test_resolve_explicit_version(self):
        """Should resolve explicitly requested version."""
        self.assertEqual(self.router.resolve_version("v2"), "v2")

    def test_resolve_default_version(self):
        """Should resolve to default when None is passed."""
        self.assertEqual(self.router.resolve_version(None), "v2")

    def test_unsupported_version_raises(self):
        """Should raise VersionNotSupportedError for unknown versions."""
        with self.assertRaises(VersionNotSupportedError):
            self.router.resolve_version("v99")

    def test_supported_versions(self):
        """Should list all configured versions."""
        self.assertEqual(set(self.router.supported_versions), {"v1", "v2", "v3"})

    def test_active_versions(self):
        """Should list only ACTIVE versions."""
        self.assertEqual(set(self.router.active_versions), {"v2", "v3"})

    def test_deprecated_versions(self):
        """Should list only DEPRECATED versions."""
        self.assertEqual(self.router.deprecated_versions, ["v1"])

    def test_deprecation_warnings_escalate(self):
        """Deprecation warnings should escalate with each request."""
        w1 = self.router.get_deprecation_warnings("v1")
        self.assertEqual(len(w1), 1)
        self.assertIn("NOTICE", w1[0])

        w2 = self.router.get_deprecation_warnings("v1")
        self.assertIn("WARNING", w2[0])

        # After 3 requests, extra warnings appear
        w3 = self.router.get_deprecation_warnings("v1")
        self.assertGreater(len(w3), 1)

    def test_no_warnings_for_active_versions(self):
        """Active versions should generate no deprecation warnings."""
        self.assertEqual(self.router.get_deprecation_warnings("v2"), [])

    def test_sunset_header_for_deprecated(self):
        """Deprecated versions should have a Sunset header."""
        sunset = self.router.get_sunset_header("v1")
        self.assertIsNotNone(sunset)
        self.assertIn("2025-12-31", sunset)

    def test_no_sunset_header_for_active(self):
        """Active versions should not have a Sunset header."""
        self.assertIsNone(self.router.get_sunset_header("v2"))

    def test_is_deprecated(self):
        """Should correctly identify deprecated versions."""
        self.assertTrue(self.router.is_deprecated("v1"))
        self.assertFalse(self.router.is_deprecated("v2"))

    def test_version_request_counts(self):
        """Should track request counts per version."""
        self.router.resolve_version("v2")
        self.router.resolve_version("v2")
        self.router.resolve_version("v3")
        counts = self.router.version_request_counts
        self.assertEqual(counts["v2"], 2)
        self.assertEqual(counts["v3"], 1)


# ---------------------------------------------------------------------------
# Test: Request Transformers
# ---------------------------------------------------------------------------

class TestRequestNormalizer(unittest.TestCase):
    """Tests for the RequestNormalizer transformer."""

    def test_normalizes_negative_number(self):
        """Negative numbers should be converted to their absolute value."""
        req = APIRequest(query_params={"number": "-15"})
        result = RequestNormalizer().transform(req)
        self.assertEqual(result.query_params["number"], "15")
        self.assertTrue(result.metadata.get("normalized"))

    def test_positive_number_unchanged(self):
        """Positive numbers should remain unchanged."""
        req = APIRequest(query_params={"number": "15"})
        result = RequestNormalizer().transform(req)
        self.assertEqual(result.query_params["number"], "15")

    def test_lowercases_headers(self):
        """Headers should be lowercased."""
        req = APIRequest(headers={"Content-Type": "application/json"})
        result = RequestNormalizer().transform(req)
        self.assertIn("content-type", result.headers)

    def test_normalizer_applied_metadata(self):
        """Should set transformer_normalizer_applied metadata."""
        req = APIRequest()
        result = RequestNormalizer().transform(req)
        self.assertTrue(result.metadata.get("transformer_normalizer_applied"))


class TestRequestEnricher(unittest.TestCase):
    """Tests for the RequestEnricher transformer."""

    def test_enriches_with_27_fields(self):
        """Should add exactly 27 enrichment fields."""
        req = APIRequest()
        result = RequestEnricher().transform(req)
        self.assertEqual(result.metadata["enrichment_field_count"], 27)

    def test_lunar_phase_present(self):
        """Should include lunar_phase in metadata."""
        req = APIRequest()
        result = RequestEnricher().transform(req)
        self.assertIn("lunar_phase", result.metadata)

    def test_golden_ratio_present(self):
        """Should include golden_ratio in metadata."""
        req = APIRequest()
        result = RequestEnricher().transform(req)
        self.assertAlmostEqual(result.metadata["golden_ratio"], 1.618, places=2)

    def test_gateway_mood_present(self):
        """Should include gateway_mood in metadata."""
        req = APIRequest()
        result = RequestEnricher().transform(req)
        self.assertIn("gateway_mood", result.metadata)

    def test_enricher_applied_metadata(self):
        """Should set transformer_enricher_applied metadata."""
        req = APIRequest()
        result = RequestEnricher().transform(req)
        self.assertTrue(result.metadata.get("transformer_enricher_applied"))


class TestRequestValidator(unittest.TestCase):
    """Tests for the RequestValidator transformer."""

    def test_valid_request_passes(self):
        """Valid requests should pass validation."""
        req = APIRequest(path="/api/v2/fizzbuzz/15", method="GET")
        result = RequestValidator().transform(req)
        self.assertTrue(result.metadata.get("validation_passed"))

    def test_empty_path_raises(self):
        """Empty path should raise RequestTransformationError."""
        req = APIRequest(path="", method="GET")
        with self.assertRaises(RequestTransformationError):
            RequestValidator().transform(req)

    def test_empty_method_raises(self):
        """Empty method should raise RequestTransformationError."""
        req = APIRequest(path="/test", method="")
        with self.assertRaises(RequestTransformationError):
            RequestValidator().transform(req)

    def test_non_standard_id_length_warns(self):
        """Non-340-char request IDs should generate a warning."""
        req = APIRequest(request_id="short-id", path="/test", method="GET")
        result = RequestValidator().transform(req)
        self.assertGreater(len(result.warnings), 0)


class TestDeprecationInjector(unittest.TestCase):
    """Tests for the DeprecationInjector transformer."""

    def setUp(self):
        self.router = VersionRouter({
            "v1": {"status": "DEPRECATED", "sunset_date": "2025-12-31"},
            "v2": {"status": "ACTIVE", "sunset_date": None},
        })
        self.injector = DeprecationInjector(self.router)

    def test_injects_warnings_for_v1(self):
        """Should inject deprecation warnings for deprecated versions."""
        req = APIRequest(version="v1")
        result = self.injector.transform(req)
        self.assertGreater(len(result.warnings), 0)
        self.assertTrue(result.metadata.get("deprecated_version"))

    def test_no_warnings_for_v2(self):
        """Should not inject warnings for active versions."""
        req = APIRequest(version="v2")
        result = self.injector.transform(req)
        self.assertEqual(len(result.warnings), 0)
        self.assertFalse(result.metadata.get("deprecated_version", False))

    def test_sunset_header_injected(self):
        """Should inject Sunset header for deprecated versions."""
        req = APIRequest(version="v1")
        result = self.injector.transform(req)
        self.assertIn("sunset", result.headers)


# ---------------------------------------------------------------------------
# Test: Response Transformers
# ---------------------------------------------------------------------------

class TestResponseCompressor(unittest.TestCase):
    """Tests for the ResponseCompressor (-847% space savings)."""

    def test_compresses_response(self):
        """Should compress response body with gzip+base64."""
        resp = APIResponse(body="Fizz")
        result = ResponseCompressor().transform(resp)
        self.assertIn("compression", result.metadata)
        self.assertEqual(result.metadata["compression"]["algorithm"], "gzip+base64")

    def test_compression_makes_response_larger(self):
        """For small payloads, compression should INCREASE size (negative savings)."""
        resp = APIResponse(body="Fizz")
        result = ResponseCompressor().transform(resp)
        savings = result.metadata["compression"]["savings_percent"]
        self.assertLess(savings, 0)  # Negative savings = response got bigger

    def test_compressed_data_in_transformed_body(self):
        """Compressed data should be in transformed_body."""
        resp = APIResponse(body="FizzBuzz")
        result = ResponseCompressor().transform(resp)
        self.assertIn("compressed_data", result.transformed_body)

    def test_content_encoding_header(self):
        """Should set content-encoding header."""
        resp = APIResponse(body="test")
        result = ResponseCompressor().transform(resp)
        self.assertEqual(result.headers["content-encoding"], "gzip+base64")

    def test_none_body_passes_through(self):
        """None body should pass through unchanged."""
        resp = APIResponse(body=None)
        result = ResponseCompressor().transform(resp)
        self.assertNotIn("compression", result.metadata)


class TestPaginationWrapper(unittest.TestCase):
    """Tests for the PaginationWrapper (page 1 of 1, always)."""

    def test_wraps_in_pagination(self):
        """Should wrap response in pagination metadata."""
        resp = APIResponse(body="Fizz")
        result = PaginationWrapper().transform(resp)
        self.assertIn("pagination", result.transformed_body)

    def test_page_is_always_one(self):
        """Page should always be 1."""
        resp = APIResponse(body="Fizz")
        result = PaginationWrapper().transform(resp)
        self.assertEqual(result.transformed_body["pagination"]["page"], 1)

    def test_total_pages_is_always_one(self):
        """Total pages should always be 1."""
        resp = APIResponse(body="Fizz")
        result = PaginationWrapper().transform(resp)
        self.assertEqual(result.transformed_body["pagination"]["total_pages"], 1)

    def test_per_page_is_always_one(self):
        """Per page should always be 1."""
        resp = APIResponse(body="Fizz")
        result = PaginationWrapper().transform(resp)
        self.assertEqual(result.transformed_body["pagination"]["per_page"], 1)

    def test_next_cursor_is_null(self):
        """Next cursor should always be None."""
        resp = APIResponse(body="Fizz")
        result = PaginationWrapper().transform(resp)
        self.assertIsNone(result.transformed_body["pagination"]["next_cursor"])

    def test_has_more_is_false(self):
        """has_more should always be False."""
        resp = APIResponse(body="Fizz")
        result = PaginationWrapper().transform(resp)
        self.assertFalse(result.transformed_body["pagination"]["has_more"])

    def test_pagination_headers_set(self):
        """Should set pagination-related headers."""
        resp = APIResponse(body="Fizz")
        result = PaginationWrapper().transform(resp)
        self.assertEqual(result.headers["x-total-pages"], "1")


class TestHATEOASEnricher(unittest.TestCase):
    """Tests for the HATEOAS link enricher."""

    def test_adds_links(self):
        """Should add _links to transformed_body."""
        resp = APIResponse(body="Fizz")
        result = HATEOASEnricher().transform(resp, version="v2", number=15)
        self.assertIn("_links", result.transformed_body)

    def test_includes_feelings_endpoint(self):
        """_links MUST include a /feelings endpoint."""
        resp = APIResponse(body="Fizz")
        result = HATEOASEnricher().transform(resp, version="v2", number=15)
        links = result.transformed_body["_links"]
        self.assertIn("feelings", links)
        self.assertIn("/feelings", links["feelings"]["href"])

    def test_includes_self_link(self):
        """Should include a 'self' link."""
        resp = APIResponse(body="Fizz")
        result = HATEOASEnricher().transform(resp, version="v2", number=15)
        self.assertIn("self", result.transformed_body["_links"])

    def test_link_count(self):
        """Should include 10 HATEOAS link relations."""
        resp = APIResponse(body="Fizz")
        result = HATEOASEnricher().transform(resp, version="v2", number=15)
        self.assertEqual(result.metadata["hateoas_link_count"], 10)

    def test_hateoas_header_set(self):
        """Should set x-hateoas-enriched header."""
        resp = APIResponse(body="Fizz")
        result = HATEOASEnricher().transform(resp, version="v2", number=15)
        self.assertEqual(result.headers["x-hateoas-enriched"], "true")


# ---------------------------------------------------------------------------
# Test: Transformer Chains
# ---------------------------------------------------------------------------

class TestRequestTransformerChain(unittest.TestCase):
    """Tests for the RequestTransformerChain."""

    def test_chain_applies_all_transformers(self):
        """All transformers in the chain should be applied in order."""
        chain = RequestTransformerChain()
        chain.add(RequestNormalizer())
        chain.add(RequestEnricher())
        chain.add(RequestValidator())

        req = APIRequest(path="/test", method="GET", query_params={"number": "-5"})
        result = chain.transform(req)
        self.assertEqual(result.query_params["number"], "5")
        self.assertTrue(result.metadata.get("transformer_enricher_applied"))
        self.assertTrue(result.metadata.get("validation_passed"))

    def test_chain_transformer_names(self):
        """Should track transformer names in order."""
        chain = RequestTransformerChain()
        chain.add(RequestNormalizer())
        chain.add(RequestValidator())
        self.assertEqual(chain.transformer_names, ["RequestNormalizer", "RequestValidator"])


class TestResponseTransformerChain(unittest.TestCase):
    """Tests for the ResponseTransformerChain."""

    def test_chain_applies_all_transformers(self):
        """All response transformers should be applied."""
        chain = ResponseTransformerChain()
        chain.add(ResponseCompressor())
        chain.add(PaginationWrapper())
        chain.add(HATEOASEnricher())

        resp = APIResponse(body="Fizz")
        result = chain.transform(resp, version="v2", number=3)
        self.assertIn("compression", result.metadata)
        self.assertIn("pagination", result.transformed_body)
        self.assertIn("_links", result.transformed_body)

    def test_chain_transformer_names(self):
        """Should track transformer names."""
        chain = ResponseTransformerChain()
        chain.add(ResponseCompressor())
        chain.add(PaginationWrapper())
        self.assertEqual(chain.transformer_names, ["ResponseCompressor", "PaginationWrapper"])


# ---------------------------------------------------------------------------
# Test: APIKeyManager
# ---------------------------------------------------------------------------

class TestAPIKeyManager(unittest.TestCase):
    """Tests for the APIKeyManager."""

    def setUp(self):
        self.manager = APIKeyManager(default_quota=5, key_prefix="efp_", key_length=16)

    def test_generate_key_with_prefix(self):
        """Generated keys should start with the configured prefix."""
        key = self.manager.generate_key()
        self.assertTrue(key.startswith("efp_"))

    def test_validate_valid_key(self):
        """Valid keys should be accepted."""
        key = self.manager.generate_key()
        data = self.manager.validate_key(key)
        self.assertIsNotNone(data)
        self.assertEqual(data["quota_used"], 1)

    def test_validate_invalid_key_raises(self):
        """Invalid keys should raise APIKeyInvalidError."""
        with self.assertRaises(APIKeyInvalidError):
            self.manager.validate_key("efp_nonexistent")

    def test_quota_exceeded_raises(self):
        """Exceeding quota should raise APIKeyQuotaExceededError."""
        key = self.manager.generate_key(quota=2)
        self.manager.validate_key(key)
        self.manager.validate_key(key)
        with self.assertRaises(APIKeyQuotaExceededError):
            self.manager.validate_key(key)

    def test_revoke_key(self):
        """Revoked keys should be rejected."""
        key = self.manager.generate_key()
        self.assertTrue(self.manager.revoke_key(key))
        with self.assertRaises(APIKeyInvalidError):
            self.manager.validate_key(key)

    def test_revoke_nonexistent_key(self):
        """Revoking a non-existent key should return False."""
        self.assertFalse(self.manager.revoke_key("efp_fake"))

    def test_total_keys(self):
        """Should track total key count."""
        self.manager.generate_key()
        self.manager.generate_key()
        self.assertEqual(self.manager.total_keys, 2)

    def test_active_keys(self):
        """Should track active (non-revoked) key count."""
        k1 = self.manager.generate_key()
        self.manager.generate_key()
        self.manager.revoke_key(k1)
        self.assertEqual(self.manager.active_keys, 1)

    def test_total_quota_consumed(self):
        """Should track total quota consumed across all keys."""
        k1 = self.manager.generate_key()
        k2 = self.manager.generate_key()
        self.manager.validate_key(k1)
        self.manager.validate_key(k2)
        self.manager.validate_key(k2)
        self.assertEqual(self.manager.total_quota_consumed, 3)

    def test_get_key_info(self):
        """Should return key metadata."""
        key = self.manager.generate_key(owner="test-user")
        info = self.manager.get_key_info(key)
        self.assertEqual(info["owner"], "test-user")

    def test_get_nonexistent_key_info(self):
        """Should return None for non-existent keys."""
        self.assertIsNone(self.manager.get_key_info("efp_fake"))


# ---------------------------------------------------------------------------
# Test: RequestReplayJournal
# ---------------------------------------------------------------------------

class TestRequestReplayJournal(unittest.TestCase):
    """Tests for the RequestReplayJournal."""

    def setUp(self):
        self.journal = RequestReplayJournal(max_entries=5)

    def test_append_entry(self):
        """Should append entries to the journal."""
        req = APIRequest(path="/test", method="GET", version="v2")
        resp = APIResponse(status_code=200)
        self.journal.append(req, resp)
        self.assertEqual(self.journal.total_entries, 1)

    def test_max_entries_respected(self):
        """Should not exceed max entries."""
        for i in range(10):
            self.journal.append(
                APIRequest(path=f"/test/{i}", method="GET", version="v2"),
                APIResponse(status_code=200),
            )
        self.assertEqual(self.journal.total_entries, 5)

    def test_is_full(self):
        """Should report when full."""
        for i in range(5):
            self.journal.append(
                APIRequest(path=f"/test/{i}", method="GET", version="v2"),
                APIResponse(status_code=200),
            )
        self.assertTrue(self.journal.is_full)

    def test_get_entries(self):
        """Should return recent entries."""
        for i in range(3):
            self.journal.append(
                APIRequest(path=f"/test/{i}", method="GET", version="v2"),
                APIResponse(status_code=200),
            )
        entries = self.journal.get_entries(limit=2)
        self.assertEqual(len(entries), 2)

    def test_replay(self):
        """Should replay all journal entries through a handler."""
        for i in range(3):
            self.journal.append(
                APIRequest(path=f"/test/{i}", method="GET", version="v2"),
                APIResponse(status_code=200),
            )

        def handler(req: APIRequest) -> APIResponse:
            return APIResponse(status_code=200, body="replayed")

        responses = self.journal.replay(handler)
        self.assertEqual(len(responses), 3)
        self.assertEqual(self.journal.replay_count, 3)

    def test_replay_error_raises(self):
        """Should raise RequestReplayError on handler failure."""
        self.journal.append(
            APIRequest(path="/test", method="GET", version="v2"),
            APIResponse(status_code=200),
        )

        def failing_handler(req: APIRequest) -> APIResponse:
            raise ValueError("replay boom")

        with self.assertRaises(RequestReplayError):
            self.journal.replay(failing_handler)


# ---------------------------------------------------------------------------
# Test: APIGateway (Full Pipeline)
# ---------------------------------------------------------------------------

class TestAPIGateway(unittest.TestCase):
    """Tests for the full API Gateway pipeline."""

    def setUp(self):
        self.route_table = RouteTable()
        self.route_table.register(Route(
            path_pattern="/api/{version}/fizzbuzz/{number}",
            method="GET",
            handler_name="evaluate_number",
            versions=("v1", "v2", "v3"),
        ))
        self.route_table.register(Route(
            path_pattern="/api/{version}/fizzbuzz/feelings",
            method="GET",
            handler_name="get_feelings",
            versions=("v2", "v3"),
        ))

        self.version_router = VersionRouter({
            "v1": {"status": "DEPRECATED", "sunset_date": "2025-12-31"},
            "v2": {"status": "ACTIVE", "sunset_date": None},
            "v3": {"status": "ACTIVE", "sunset_date": None},
        })

        self.request_chain = RequestTransformerChain()
        self.request_chain.add(RequestNormalizer())
        self.request_chain.add(RequestEnricher())
        self.request_chain.add(RequestValidator())
        self.request_chain.add(DeprecationInjector(self.version_router))

        self.response_chain = ResponseTransformerChain()
        self.response_chain.add(ResponseCompressor())
        self.response_chain.add(PaginationWrapper())
        self.response_chain.add(HATEOASEnricher())

        self.key_manager = APIKeyManager()
        self.journal = RequestReplayJournal()

        self.gateway = APIGateway(
            route_table=self.route_table,
            version_router=self.version_router,
            request_chain=self.request_chain,
            response_chain=self.response_chain,
            key_manager=self.key_manager,
            journal=self.journal,
        )

    def test_process_valid_request(self):
        """Should process a valid request through the full pipeline."""
        req = APIRequest(
            path="/api/v2/fizzbuzz/15",
            method="GET",
            version="v2",
            query_params={"number": "15"},
        )
        resp = self.gateway.process_request(req)
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(resp.processing_time_ms, 0)

    def test_total_requests_incremented(self):
        """Should track total request count."""
        req = APIRequest(path="/api/v2/fizzbuzz/15", method="GET", version="v2")
        self.gateway.process_request(req)
        self.assertEqual(self.gateway.total_requests, 1)

    def test_journal_records_request(self):
        """Should record request in the replay journal."""
        req = APIRequest(path="/api/v2/fizzbuzz/15", method="GET", version="v2")
        self.gateway.process_request(req)
        self.assertEqual(self.journal.total_entries, 1)

    def test_deprecated_version_adds_warnings(self):
        """Should add deprecation warnings for v1 requests."""
        req = APIRequest(path="/api/v1/fizzbuzz/15", method="GET", version="v1")
        resp = self.gateway.process_request(req)
        self.assertIn("x-deprecated", resp.headers)

    def test_route_not_found_raises(self):
        """Should raise RouteNotFoundError for unknown routes."""
        req = APIRequest(path="/api/v2/unknown", method="GET", version="v2")
        with self.assertRaises(RouteNotFoundError):
            self.gateway.process_request(req)

    def test_api_key_validation(self):
        """Should validate API keys when provided."""
        key = self.key_manager.generate_key()
        req = APIRequest(
            path="/api/v2/fizzbuzz/15", method="GET",
            version="v2", api_key=key,
        )
        resp = self.gateway.process_request(req)
        self.assertEqual(resp.status_code, 200)

    def test_invalid_api_key_raises(self):
        """Should raise APIKeyInvalidError for invalid keys."""
        req = APIRequest(
            path="/api/v2/fizzbuzz/15", method="GET",
            version="v2", api_key="efp_invalid_key",
        )
        with self.assertRaises(APIKeyInvalidError):
            self.gateway.process_request(req)

    def test_response_has_compression_metadata(self):
        """Response should have compression metadata when handler returns data."""
        def evaluate_number(req, params):
            return "FizzBuzz"

        req = APIRequest(path="/api/v2/fizzbuzz/15", method="GET", version="v2")
        resp = self.gateway.process_request(req, handler_registry={
            "evaluate_number": evaluate_number,
        })
        self.assertIn("compression", resp.metadata)

    def test_response_has_pagination(self):
        """Response should have pagination metadata."""
        req = APIRequest(path="/api/v2/fizzbuzz/15", method="GET", version="v2")
        resp = self.gateway.process_request(req)
        self.assertIn("pagination", resp.transformed_body)

    def test_response_has_hateoas_links(self):
        """Response should have HATEOAS _links including /feelings."""
        req = APIRequest(path="/api/v2/fizzbuzz/15", method="GET", version="v2")
        resp = self.gateway.process_request(req)
        self.assertIn("_links", resp.transformed_body)
        self.assertIn("feelings", resp.transformed_body["_links"])

    def test_handler_registry(self):
        """Should call handler from registry when provided."""
        called_with = {}

        def evaluate_number(req, params):
            called_with["number"] = params.get("number")
            return "FizzBuzz"

        req = APIRequest(path="/api/v2/fizzbuzz/15", method="GET", version="v2")
        self.gateway.process_request(req, handler_registry={
            "evaluate_number": evaluate_number,
        })
        self.assertEqual(called_with["number"], "15")


# ---------------------------------------------------------------------------
# Test: GatewayMiddleware
# ---------------------------------------------------------------------------

class TestGatewayMiddleware(unittest.TestCase):
    """Tests for the GatewayMiddleware integration."""

    def setUp(self):
        route_table = RouteTable()
        route_table.register(Route(
            path_pattern="/api/{version}/fizzbuzz/{number}",
            method="GET",
            handler_name="evaluate_number",
            versions=("v2",),
        ))
        version_router = VersionRouter(
            {"v2": {"status": "ACTIVE", "sunset_date": None}},
        )
        self.gateway = APIGateway(
            route_table=route_table,
            version_router=version_router,
            request_chain=RequestTransformerChain(),
            response_chain=ResponseTransformerChain(),
            key_manager=APIKeyManager(),
            journal=RequestReplayJournal(),
        )
        self.middleware = GatewayMiddleware(self.gateway, version="v2")

    def test_get_name(self):
        """Should return 'GatewayMiddleware'."""
        self.assertEqual(self.middleware.get_name(), "GatewayMiddleware")

    def test_get_priority(self):
        """Should return priority 12."""
        self.assertEqual(self.middleware.get_priority(), 12)

    def test_adds_metadata_to_context(self):
        """Should add gateway metadata to processing context."""
        ctx = ProcessingContext(number=15, session_id="test-session")

        def next_handler(c):
            return c

        result = self.middleware.process(ctx, next_handler)
        self.assertIn("gateway_request_id", result.metadata)
        self.assertEqual(result.metadata["gateway_version"], "v2")

    def test_continues_pipeline_on_error(self):
        """Should continue pipeline even if gateway routing fails."""
        # Number 15 won't match the path template exactly since we
        # build it dynamically, but the middleware handles errors gracefully
        ctx = ProcessingContext(number=15, session_id="test-session")

        def next_handler(c):
            c.metadata["pipeline_continued"] = True
            return c

        result = self.middleware.process(ctx, next_handler)
        self.assertTrue(result.metadata.get("pipeline_continued"))


# ---------------------------------------------------------------------------
# Test: GatewayDashboard
# ---------------------------------------------------------------------------

class TestGatewayDashboard(unittest.TestCase):
    """Tests for the ASCII gateway dashboard."""

    def setUp(self):
        route_table = RouteTable()
        route_table.register(Route(
            path_pattern="/api/{version}/fizzbuzz/{number}",
            method="GET",
            handler_name="evaluate",
            versions=("v1", "v2"),
        ))
        version_router = VersionRouter({
            "v1": {"status": "DEPRECATED", "sunset_date": "2025-12-31"},
            "v2": {"status": "ACTIVE", "sunset_date": None},
        })
        self.gateway = APIGateway(
            route_table=route_table,
            version_router=version_router,
            request_chain=RequestTransformerChain(),
            response_chain=ResponseTransformerChain(),
            key_manager=APIKeyManager(),
            journal=RequestReplayJournal(),
        )

    def test_renders_dashboard(self):
        """Should render an ASCII dashboard string."""
        output = GatewayDashboard.render(self.gateway)
        self.assertIsInstance(output, str)
        self.assertGreater(len(output), 100)

    def test_dashboard_contains_sections(self):
        """Dashboard should contain key sections."""
        output = GatewayDashboard.render(self.gateway)
        self.assertIn("API GATEWAY DASHBOARD", output)
        self.assertIn("REQUEST STATISTICS", output)
        self.assertIn("API VERSIONS", output)
        self.assertIn("REGISTERED ROUTES", output)
        self.assertIn("API KEY MANAGEMENT", output)
        self.assertIn("REQUEST REPLAY JOURNAL", output)
        self.assertIn("GATEWAY STATUS", output)

    def test_dashboard_shows_deprecated_version(self):
        """Dashboard should show deprecated version status."""
        output = GatewayDashboard.render(self.gateway)
        self.assertIn("DEPRECATED", output)

    def test_dashboard_custom_width(self):
        """Should respect custom width parameter."""
        output = GatewayDashboard.render(self.gateway, width=80)
        self.assertIsInstance(output, str)


# ---------------------------------------------------------------------------
# Test: Exception Hierarchy
# ---------------------------------------------------------------------------

class TestGatewayExceptions(unittest.TestCase):
    """Tests for the gateway exception hierarchy."""

    def test_gateway_error_inherits_fizzbuzz_error(self):
        """GatewayError should inherit from FizzBuzzError."""
        self.assertTrue(issubclass(GatewayError, FizzBuzzError))

    def test_route_not_found_error_code(self):
        """RouteNotFoundError should have error code EFP-GW01."""
        err = RouteNotFoundError("/test", "GET")
        self.assertEqual(err.error_code, "EFP-GW01")

    def test_version_not_supported_error_code(self):
        """VersionNotSupportedError should have error code EFP-GW02."""
        err = VersionNotSupportedError("v99", ["v1", "v2"])
        self.assertEqual(err.error_code, "EFP-GW02")

    def test_version_deprecated_error_code(self):
        """VersionDeprecatedError should have error code EFP-GW03."""
        err = VersionDeprecatedError("v1", "2025-12-31")
        self.assertEqual(err.error_code, "EFP-GW03")

    def test_request_transformation_error_code(self):
        """RequestTransformationError should have error code EFP-GW04."""
        err = RequestTransformationError("TestTransformer", "boom")
        self.assertEqual(err.error_code, "EFP-GW04")

    def test_response_transformation_error_code(self):
        """ResponseTransformationError should have error code EFP-GW05."""
        err = ResponseTransformationError("TestTransformer", "boom")
        self.assertEqual(err.error_code, "EFP-GW05")

    def test_api_key_invalid_error_code(self):
        """APIKeyInvalidError should have error code EFP-GW06."""
        err = APIKeyInvalidError("efp_abc", "not found")
        self.assertEqual(err.error_code, "EFP-GW06")

    def test_api_key_quota_exceeded_error_code(self):
        """APIKeyQuotaExceededError should have error code EFP-GW07."""
        err = APIKeyQuotaExceededError("efp_abc", 100, 100)
        self.assertEqual(err.error_code, "EFP-GW07")

    def test_request_replay_error_code(self):
        """RequestReplayError should have error code EFP-GW08."""
        err = RequestReplayError("replay failed")
        self.assertEqual(err.error_code, "EFP-GW08")

    def test_gateway_dashboard_render_error_code(self):
        """GatewayDashboardRenderError should have error code EFP-GW09."""
        err = GatewayDashboardRenderError("render failed")
        self.assertEqual(err.error_code, "EFP-GW09")

    def test_all_gateway_exceptions_are_gateway_error(self):
        """All gateway exceptions should inherit from GatewayError."""
        self.assertTrue(issubclass(RouteNotFoundError, GatewayError))
        self.assertTrue(issubclass(VersionNotSupportedError, GatewayError))
        self.assertTrue(issubclass(VersionDeprecatedError, GatewayError))
        self.assertTrue(issubclass(RequestTransformationError, GatewayError))
        self.assertTrue(issubclass(ResponseTransformationError, GatewayError))
        self.assertTrue(issubclass(APIKeyInvalidError, GatewayError))
        self.assertTrue(issubclass(APIKeyQuotaExceededError, GatewayError))
        self.assertTrue(issubclass(RequestReplayError, GatewayError))
        self.assertTrue(issubclass(GatewayDashboardRenderError, GatewayError))


# ---------------------------------------------------------------------------
# Test: EventType entries
# ---------------------------------------------------------------------------

class TestGatewayEventTypes(unittest.TestCase):
    """Tests for the gateway EventType entries."""

    def test_gateway_request_received(self):
        self.assertIsNotNone(EventType.GATEWAY_REQUEST_RECEIVED)

    def test_gateway_request_routed(self):
        self.assertIsNotNone(EventType.GATEWAY_REQUEST_ROUTED)

    def test_gateway_request_transformed(self):
        self.assertIsNotNone(EventType.GATEWAY_REQUEST_TRANSFORMED)

    def test_gateway_response_transformed(self):
        self.assertIsNotNone(EventType.GATEWAY_RESPONSE_TRANSFORMED)

    def test_gateway_version_resolved(self):
        self.assertIsNotNone(EventType.GATEWAY_VERSION_RESOLVED)

    def test_gateway_deprecation_warning(self):
        self.assertIsNotNone(EventType.GATEWAY_DEPRECATION_WARNING)

    def test_gateway_api_key_validated(self):
        self.assertIsNotNone(EventType.GATEWAY_API_KEY_VALIDATED)

    def test_gateway_api_key_rejected(self):
        self.assertIsNotNone(EventType.GATEWAY_API_KEY_REJECTED)

    def test_gateway_quota_exceeded(self):
        self.assertIsNotNone(EventType.GATEWAY_QUOTA_EXCEEDED)

    def test_gateway_request_replayed(self):
        self.assertIsNotNone(EventType.GATEWAY_REQUEST_REPLAYED)

    def test_gateway_dashboard_rendered(self):
        self.assertIsNotNone(EventType.GATEWAY_DASHBOARD_RENDERED)


if __name__ == "__main__":
    unittest.main()
