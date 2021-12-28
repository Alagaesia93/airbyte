#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#


import sys

from airbyte_cdk.entrypoint import launch
from source_shopify_partner import SourceShopifyPartner

if __name__ == "__main__":
    source = SourceShopifyPartner()
    launch(source, sys.argv[1:])
