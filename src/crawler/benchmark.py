"""Performance benchmark for crawler with and without caching."""

import time

from . import cache as page_cache
from .conf import ConfCrawler
from .core import fetch_html


def measure_fetch_time(url, use_cache=False, iterations=3):
    """Fetch *url* repeatedly and return timing stats.

    :param url: URL to benchmark.
    :param use_cache: Whether to use the file-based page cache.
    :param iterations: Number of fetches.
    :rtype: dict
    """
    times = []
    total_bytes = 0

    for _ in range(iterations):
        start = time.time()

        if use_cache:
            cached = page_cache.get(url)
            if cached:
                success, html = True, cached
            else:
                success, html = fetch_html(url, timeout=5, max_retries=1)
                if success:
                    page_cache.put(url, html)
        else:
            success, html = fetch_html(url, timeout=5, max_retries=1)

        elapsed = time.time() - start
        if success:
            times.append(elapsed)
            total_bytes = len(html)

    if not times:
        return {"success": False, "fetch_count": 0}

    return {
        "success": True,
        "fetch_count": len(times),
        "total_time": sum(times),
        "avg_time": sum(times) / len(times),
        "min_time": min(times),
        "max_time": max(times),
        "bytes_per_fetch": total_bytes,
    }


def benchmark_conference(conf_abbr, conf_name, year=2025):
    """Benchmark cached vs uncached fetching for one conference.

    :param conf_abbr: Conference abbreviation (e.g. ``'AAAI'``).
    :param conf_name: Full conference name.
    :param year: Target year.
    """
    print("\n" + "=" * 80)
    print(f"BENCHMARK: {conf_abbr} {year}")
    print("=" * 80)

    crawler = ConfCrawler()
    print(f"\n[1] Finding homepage for {conf_abbr} {year}...")
    start = time.time()
    homepage = crawler.search_homepage(conf_abbr, conf_name, year, max_results=5)
    search_time = time.time() - start

    if not homepage:
        print("  [!] Could not find homepage")
        return

    print(f"  [+] Homepage: {homepage}")
    print(f"  [+] Search time: {search_time:.2f}s")

    print("\n[2] Fetching homepage 3 times WITHOUT cache (baseline)...")
    stats_without = measure_fetch_time(homepage, use_cache=False, iterations=3)
    if not stats_without["success"]:
        print("  [!] Failed to fetch")
        return

    print(f"  [+] Avg per fetch: {stats_without['avg_time']:.2f}s")

    print("\n[3] Fetching homepage 3 times WITH cache (optimized)...")
    stats_with = measure_fetch_time(homepage, use_cache=True, iterations=3)
    if not stats_with["success"]:
        print("  [!] Failed to fetch")
        return

    print(f"  [+] Avg per fetch: {stats_with['avg_time']:.2f}s")

    time_saved = stats_without["total_time"] - stats_with["total_time"]
    speedup = stats_without["total_time"] / stats_with["total_time"]

    print("\n[4] Performance Comparison:")
    print(
        f"  [+] Time saved: {time_saved:.2f}s "
        f"({time_saved / stats_without['total_time'] * 100:.1f}%)"
    )
    print(f"  [+] Speedup: {speedup:.1f}x faster")


def main():
    """Run benchmarks on sample conferences."""
    conferences = [
        ("AAAI", "AAAI Conference on Artificial Intelligence"),
        ("ICML", "International Conference on Machine Learning"),
        ("NeurIPS", "Neural Information Processing Systems"),
    ]

    for conf_abbr, conf_name in conferences:
        benchmark_conference(conf_abbr, conf_name, year=2025)

    print("\n" + "=" * 80)
    print("BENCHMARK COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
