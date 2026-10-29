"""
load_kg.py
==========
Builds the urban knowledge-graph modality used by the Reasoning Agent's
R-GCN encoder (Stage A block "Urban KG subgraph" in Figure 2 of the DA1
report), following the UUKG-style construction approach cited as [14].

Source: OpenStreetMap, via `osmnx` (no API key required; polite rate-limited
public Overpass API calls).

What it builds
--------------
For a given place name (e.g. a city or district), this script pulls:
  - the road network (nodes = intersections, edges = road segments)
  - points of interest tagged as infrastructure (hospitals, fire stations,
    schools, transit stops) as additional entity nodes attached to their
    nearest road node via a `near` relation

...and serializes the result two ways:
  1. An RDF graph (Turtle format) for SPARQL-style querying, matching the
     "urban knowledge graph" framing in the report's literature survey.
  2. A `torch_geometric.data.Data` object (node features + edge_index +
     edge_type) ready for the R-GCN encoder in Figure 2.

Usage
-----
    python data/load_kg.py --place "Koramangala, Bengaluru, India"
    python data/load_kg.py --place "Downtown, Austin, Texas, USA" --out ./cache/kg
"""
import argparse
import sys
from pathlib import Path


def _require(pkg_name, pip_name=None):
    try:
        return __import__(pkg_name)
    except ImportError:
        pip_name = pip_name or pkg_name
        print(f"[load_kg] Missing dependency '{pkg_name}'. Install with:\n    pip install {pip_name}",
              file=sys.stderr)
        sys.exit(1)


INFRA_TAGS = {
    "amenity": ["hospital", "fire_station", "school", "police"],
    "highway": ["bus_stop"],
    "railway": ["station"],
}


def build_graph(place: str):
    osmnx = _require("osmnx")
    networkx = _require("networkx")

    osmnx.settings.log_console = False

    # Road network -> base graph (nodes = intersections, edges = roads)
    G_road = osmnx.graph_from_place(place, network_type="drive")

    # Infrastructure points of interest -> extra entity nodes
    tags = {k: v for k, v in INFRA_TAGS.items()}
    try:
        gdf_infra = osmnx.features_from_place(place, tags=tags)
    except Exception as e:  # osmnx raises if nothing matches
        print(f"[load_kg] Warning: could not fetch POIs ({e}); continuing with road graph only.")
        gdf_infra = None

    G = networkx.MultiDiGraph(G_road)

    if gdf_infra is not None and len(gdf_infra) > 0:
        for idx, row in gdf_infra.iterrows():
            geom = row.geometry
            if geom is None:
                continue
            centroid = geom.centroid
            infra_id = f"infra_{idx}"
            infra_type = next((row[k] for k in INFRA_TAGS if k in row and pd_notna(row.get(k))), "infrastructure")
            nearest_node = osmnx.distance.nearest_nodes(G_road, centroid.x, centroid.y)
            G.add_node(infra_id, x=centroid.x, y=centroid.y, entity_type=infra_type)
            G.add_edge(infra_id, nearest_node, relation="near")

    return G


def pd_notna(val):
    try:
        import pandas as pd
        return pd.notna(val)
    except Exception:
        return val is not None


def to_rdf(G, out_path: str):
    rdflib = _require("rdflib")
    from rdflib import Graph, Namespace, Literal, URIRef, RDF

    ns = Namespace("http://example.org/urbankg#")
    g = Graph()
    g.bind("urbankg", ns)

    for node, data in G.nodes(data=True):
        node_uri = URIRef(ns[f"node/{node}"])
        entity_type = data.get("entity_type", "road_node")
        g.add((node_uri, RDF.type, ns[entity_type]))
        if "x" in data and "y" in data:
            g.add((node_uri, ns.longitude, Literal(data["x"])))
            g.add((node_uri, ns.latitude, Literal(data["y"])))

    for u, v, data in G.edges(data=True):
        u_uri = URIRef(ns[f"node/{u}"])
        v_uri = URIRef(ns[f"node/{v}"])
        relation = data.get("relation", "connects_to")
        g.add((u_uri, ns[relation], v_uri))

    g.serialize(destination=out_path, format="turtle")
    return out_path


def to_pyg(G):
    torch = _require("torch")
    from torch_geometric.data import Data
    import networkx as nx

    node_list = list(G.nodes())
    node_idx = {n: i for i, n in enumerate(node_list)}

    # crude entity-type one-hot as placeholder node features
    types = sorted({G.nodes[n].get("entity_type", "road_node") for n in node_list})
    type_idx = {t: i for i, t in enumerate(types)}
    x = torch.zeros(len(node_list), len(types))
    for n in node_list:
        t = G.nodes[n].get("entity_type", "road_node")
        x[node_idx[n], type_idx[t]] = 1.0

    edges = []
    for u, v in G.edges():
        edges.append([node_idx[u], node_idx[v]])
    edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous() if edges else torch.empty((2, 0), dtype=torch.long)

    return Data(x=x, edge_index=edge_index)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--place", required=True, help='e.g. "Koramangala, Bengaluru, India"')
    ap.add_argument("--out", default="./cache/kg", help="output directory")
    args = ap.parse_args()

    Path(args.out).mkdir(parents=True, exist_ok=True)

    print(f"[load_kg] Building graph for '{args.place}' ...")
    G = build_graph(args.place)
    print(f"[load_kg] Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

    ttl_path = str(Path(args.out) / "urban_kg.ttl")
    to_rdf(G, ttl_path)
    print(f"[load_kg] Saved RDF graph to {ttl_path}")

    data = to_pyg(G)
    print(f"[load_kg] PyG Data object: x={tuple(data.x.shape)}, edge_index={tuple(data.edge_index.shape)}")
    print("[load_kg] OK.")
