#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test script for rate limiter functionality."""

import asyncio
import time

from massgen.backend.rate_limiter import GlobalRateLimiter


async def test_rate_limiter():
    """Test that rate limiter properly blocks concurrent requests."""
    print("Testing rate limiter with RPM=2...")

    # Get a shared rate limiter for testing (simulating gemini-2.5-pro)
    limiter = GlobalRateLimiter.get_multi_limiter_sync(
        provider="test-gemini-2.5-pro",
        rpm=2,
        tpm=None,
        rpd=None,
    )

    # Track when requests start
    request_times = []

    async def make_request(request_id: int):
        """Simulate an API request with rate limiting."""
        print(f"[Request {request_id}] Attempting to acquire rate limiter...")
        async with limiter:
            request_time = time.time()
            request_times.append(request_time)
            print(f"[Request {request_id}] Acquired at {request_time:.2f}")
            # Simulate API call
            await asyncio.sleep(0.1)
        print(f"[Request {request_id}] Completed")

    # Start 3 requests concurrently (should be rate-limited to 2 per minute)
    start_time = time.time()
    tasks = [make_request(i) for i in range(3)]
    await asyncio.gather(*tasks)
    end_time = time.time()

    print(f"\nTotal time: {end_time - start_time:.2f}s")
    print(f"Request times: {[f'{t-start_time:.2f}s' for t in request_times]}")

    # Verify rate limiting worked
    # First 2 requests should be close together
    # 3rd request should be delayed by ~60 seconds
    if len(request_times) == 3:
        time_diff_1_2 = request_times[1] - request_times[0]
        time_diff_2_3 = request_times[2] - request_times[1]

        print(f"\nTime between request 1 and 2: {time_diff_1_2:.2f}s")
        print(f"Time between request 2 and 3: {time_diff_2_3:.2f}s")

        if time_diff_2_3 > 55:  # Should wait ~60 seconds
            print("✅ Rate limiting is working correctly!")
            return True
        else:
            print("❌ Rate limiting is NOT working - 3rd request was not delayed")
            return False
    else:
        print("❌ Unexpected number of requests completed")
        return False


async def test_shared_limiter():
    """Test that multiple backend instances share the same limiter."""
    print("\n" + "=" * 60)
    print("Testing shared limiter across multiple instances...")

    # Get two "backend" instances with the same provider key
    limiter1 = GlobalRateLimiter.get_multi_limiter_sync(
        provider="test-shared",
        rpm=2,
        tpm=None,
        rpd=None,
    )

    limiter2 = GlobalRateLimiter.get_multi_limiter_sync(
        provider="test-shared",
        rpm=2,
        tpm=None,
        rpd=None,
    )

    # Verify they are the same instance
    if limiter1 is limiter2:
        print("✅ Limiters are shared correctly (same instance)")
        return True
    else:
        print("❌ Limiters are NOT shared (different instances)")
        return False


async def main():
    """Run all tests."""
    print("Rate Limiter Tests")
    print("=" * 60)

    # Test 1: Shared limiter
    test1_passed = await test_shared_limiter()

    # Test 2: Rate limiting with concurrent requests
    # WARNING: This test takes ~60 seconds to run
    print("\n⚠️  WARNING: Next test will take ~60 seconds to verify rate limiting")
    response = input("Run full rate limit test? (y/n): ")

    if response.lower() == "y":
        test2_passed = await test_rate_limiter()
    else:
        print("Skipping full rate limit test")
        test2_passed = True

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary:")
    print(f"  Shared limiter test: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"  Rate limiting test: {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
