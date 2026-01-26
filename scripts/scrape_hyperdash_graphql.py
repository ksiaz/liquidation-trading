#!/usr/bin/env python3
"""Query Hyperdash GraphQL API for whale addresses."""
import asyncio
import sys
import json
import aiohttp

async def query_hyperdash_graphql():
    """Query Hyperdash GraphQL for top traders."""

    print("=" * 80)
    print("QUERYING HYPERDASH GRAPHQL API")
    print("=" * 80)
    print()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://hyperdash.info",
        "Referer": "https://hyperdash.info/top-traders",
    }

    # Common GraphQL queries for trader data
    queries = [
        # Try common query patterns
        {
            "operationName": "GetTopTraders",
            "variables": {"limit": 50},
            "query": """
                query GetTopTraders($limit: Int) {
                    topTraders(limit: $limit) {
                        address
                        pnl
                        volume
                    }
                }
            """
        },
        {
            "operationName": "traders",
            "variables": {"first": 50},
            "query": """
                query traders($first: Int) {
                    traders(first: $first) {
                        edges {
                            node {
                                address
                                totalPnl
                            }
                        }
                    }
                }
            """
        },
        {
            "operationName": None,
            "variables": {},
            "query": "{ __schema { types { name } } }"  # Introspection query
        },
        {
            "operationName": "GetAlphaTraders",
            "variables": {},
            "query": """
                query GetAlphaTraders {
                    alphaTraders {
                        address
                        pnl
                        winRate
                    }
                }
            """
        },
    ]

    async with aiohttp.ClientSession() as session:
        # Try each query
        for i, query in enumerate(queries, 1):
            print(f"Trying query {i}...")
            try:
                async with session.post(
                    "https://api.hyperdash.com/graphql",
                    headers=headers,
                    json=query,
                    timeout=10
                ) as response:
                    print(f"  Status: {response.status}")
                    if response.status == 200:
                        data = await response.json()
                        print(f"  Response keys: {list(data.keys())}")

                        if "data" in data and data["data"]:
                            print(f"  Data: {json.dumps(data['data'])[:200]}...")

                            # Look for addresses in response
                            data_str = json.dumps(data)
                            import re
                            addresses = re.findall(r'0x[a-fA-F0-9]{40}', data_str)
                            if addresses:
                                print(f"  Found {len(set(addresses))} addresses!")
                                for addr in list(set(addresses))[:10]:
                                    print(f"    {addr}")

                        elif "errors" in data:
                            print(f"  Errors: {data['errors']}")

            except Exception as e:
                print(f"  Error: {e}")

            print()

        # Try introspection to discover schema
        print("\n" + "=" * 80)
        print("Trying schema introspection...")
        print("=" * 80)

        introspection = {
            "query": """
                query IntrospectionQuery {
                    __schema {
                        queryType { name }
                        types {
                            name
                            kind
                            fields {
                                name
                                type { name kind }
                            }
                        }
                    }
                }
            """
        }

        try:
            async with session.post(
                "https://api.hyperdash.com/graphql",
                headers=headers,
                json=introspection,
                timeout=10
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if "data" in data and data["data"]:
                        schema = data["data"].get("__schema", {})
                        types = schema.get("types", [])
                        print(f"Found {len(types)} types in schema")

                        # Look for trader-related types
                        for t in types:
                            name = t.get("name", "")
                            if any(kw in name.lower() for kw in ["trader", "user", "address", "pnl", "alpha"]):
                                print(f"\n  Type: {name}")
                                fields = t.get("fields", [])
                                if fields:
                                    for f in fields[:5]:
                                        print(f"    - {f.get('name')}: {f.get('type', {}).get('name')}")
                    else:
                        print(f"Response: {data}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(query_hyperdash_graphql())
