"""Regression: the two 'excluded config params' lists share one source of truth.

Historically ``LLMBackend.get_base_excluded_config_params`` and
``APIParamsHandlerBase.get_base_excluded_params`` were hand-duplicated (104/105
entries), so a param added to one but not the other would leak to the provider
API. Both now derive from ``backend._excluded_params.BASE_EXCLUDED_CONFIG_PARAMS``;
this test fails if they ever drift apart again.
"""

from __future__ import annotations

from massgen.api_params_handler._api_params_handler_base import APIParamsHandlerBase
from massgen.backend._excluded_params import BASE_EXCLUDED_CONFIG_PARAMS
from massgen.backend.base import LLMBackend


def test_backend_base_uses_canonical_set():
    assert LLMBackend.get_base_excluded_config_params() == set(BASE_EXCLUDED_CONFIG_PARAMS)


def test_api_params_handler_uses_canonical_set_plus_upload_files():
    # The method ignores ``self``; call it unbound with None.
    apih = APIParamsHandlerBase.get_base_excluded_params(None)
    assert apih == set(BASE_EXCLUDED_CONFIG_PARAMS) | {"upload_files"}


def test_two_sources_differ_only_by_upload_files():
    base = LLMBackend.get_base_excluded_config_params()
    apih = APIParamsHandlerBase.get_base_excluded_params(None)
    assert apih - base == {"upload_files"}
    assert base - apih == set()
