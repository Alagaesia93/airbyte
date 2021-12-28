#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#

import pdb
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple
from urllib.parse import parse_qsl, urlparse

import requests
from airbyte_cdk import AirbyteLogger
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream

from .auth import ShopifyAuthenticator

# TODO: import from source-shopify. Be more DRY
from .transform import DataTypeEnforcer
from .utils import EagerlyCachedStreamState as stream_state_cache
from .utils import ShopifyRateLimiter as limiter

# Basic full refresh stream
class ShopifyPartnerStream(HttpStream, ABC):
    # Latest Stable Release
    api_version = "2021-10"
    # Page size
    limit = 250
    # Define primary key as sort key for full_refresh, or very first sync for incremental_refresh
    primary_key = None
    order_field = "occured_at"
    filter_field = "occurred_at_min"

    def __init__(self, config: Dict):
        super().__init__(authenticator=config["authenticator"])
        self._transformer = DataTypeEnforcer(self.get_json_schema())
        self.config = config

    @property
    def url_base(self) -> str:
        return f"https://partners.shopify.com/{self.config['organization_id']}/api/{self.api_version}/graphql"

    @property
    def http_method(self) -> str:
        """
        Override if needed. See get_request_data/get_request_json if using POST/PUT/PATCH.
        """
        return "POST"

    @staticmethod
    def next_page_token(response: requests.Response) -> Optional[Mapping[str, Any]]:
        next_page = response.links.get("next", None)
        if next_page:
            return dict(parse_qsl(urlparse(next_page.get("url")).query))
        else:
            return None

    def request_params(self, next_page_token: Mapping[str, Any] = None, **kwargs) -> MutableMapping[str, Any]:
        params = {"limit": self.limit}
        if next_page_token:
            params.update(**next_page_token)
        else:
            params["order"] = f"{self.order_field} asc"
        return params

    @limiter.balance_rate_limit()
    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        json_response = response.json()
        
        records = json_response['data']['app'][self.data_field]['edges']
        # transform method was implemented according to issue 4841
        # Shopify API returns price fields as a string and it should be converted to number
        # this solution designed to convert string into number, but in future can be modified for general purpose
        if isinstance(records, dict):
            # for cases when we have a single record as dict
            yield self._transformer.transform(records)
        else:
            # for other cases
            for record in records:
                yield self._transformer.transform(record)

    @property
    @abstractmethod
    def data_field(self) -> str:
        """The name of the field in the response which contains the data"""

class IncrementalShopifyPartnerStream(ShopifyPartnerStream, ABC):

    # Setting the check point interval to the limit of the records output
    @property
    def state_checkpoint_interval(self) -> int:
        return super().limit

    # Setting the default cursor field for all streams
    cursor_field = "updated_at"

    def get_updated_state(self, current_stream_state: MutableMapping[str, Any], latest_record: Mapping[str, Any]) -> Mapping[str, Any]:
        
        return {self.cursor_field: max(latest_record.get(self.cursor_field, ""), current_stream_state.get(self.cursor_field, ""))}

    @stream_state_cache.cache_stream_state
    def request_params(self, stream_state: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None, **kwargs):
        params = super().request_params(stream_state=stream_state, next_page_token=next_page_token, **kwargs)
        # If there is a next page token then we should only send pagination-related parameters.
        if not next_page_token:
            params["order"] = f"{self.order_field} asc"
            if stream_state:
                params[self.filter_field] = stream_state.get(self.cursor_field)
        return params

class Events(IncrementalShopifyPartnerStream):
    data_field = "events"
    
    def path(self, **kwargs) -> str:
        return ""

    def request_body_json(
        self,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Optional[Mapping]:
        return {
            "operationName": "Events",
            "query": '''
                query Events($app_id: ID!){
                    app(id: $app_id) {
                        events {
                            edges {
                                node {
                                    type,
                                    occurredAt,
                                    shop {
                                        id,
                                        name,
                                        avatarUrl,
                                        myshopifyDomain
                                    }
                                }
                            }
                        }
                    }
                }
            ''',
            'variables': {
                'app_id': f'gid://partners/App/{self.config["app_id"]}'
            },
        }

# Source
class SourceShopifyPartner(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        config["authenticator"] = ShopifyAuthenticator(config)

        """
        TODO: check if partner exists
        """
        if config["organization_id"] and config["access_token"]:
            return True, None
        else:
            return False, "Missing mandatory fields"

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        config["authenticator"] = ShopifyAuthenticator(config)
        return [Events(config)]
        #Transactions(config)
