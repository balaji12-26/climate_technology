"""Layer 1c - explicit road graph + Dijkstra.

Closed roads are removed from the edge list before this module sees them,
so an unreachable zone is simply absent from the distance map.
"""
from __future__ import annotations

import heapq
from collections import defaultdict

INF = float("inf")


def build_graph(edges: list[dict]) -> dict[str, list[tuple[str, float]]]:
    g: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for e in edges:
        g[e["a"]].append((e["b"], float(e["km"])))
        g[e["b"]].append((e["a"], float(e["km"])))
    return g


def dijkstra(edges: list[dict], source: str) -> tuple[dict[str, float], dict[str, str | None]]:
    g = build_graph(edges)
    dist: dict[str, float] = {source: 0.0}
    prev: dict[str, str | None] = {source: None}
    pq: list[tuple[float, str]] = [(0.0, source)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, INF):
            continue
        for v, w in g[u]:
            nd = d + w
            if nd < dist.get(v, INF):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def path_to(prev: dict[str, str | None], target: str) -> list[str]:
    if target not in prev:
        return []
    path: list[str] = []
    node: str | None = target
    while node is not None:
        path.append(node)
        node = prev[node]
    return list(reversed(path))


def shortest_paths(sc: dict) -> tuple[dict[str, float], dict[str, list[str]]]:
    """dist[z] in km from the depot and route[z] as a node list, for reachable zones only."""
    dist, prev = dijkstra(sc["edges"], sc["depot"]["id"])
    out_d: dict[str, float] = {}
    out_p: dict[str, list[str]] = {}
    for z in sc["zones"]:
        zid = z["id"]
        if zid in dist:
            out_d[zid] = dist[zid]
            out_p[zid] = path_to(prev, zid)
    return out_d, out_p
