"""Baixa a rede viária de uma região no OpenStreetMap e exporta no formato do servidor.

Roda só no Mac (usa osmnx, que é pesado demais para a VM).

Formato do mapa (texto, comprimido com gzip):
    linha 1:          N M                      (quantidade de nós e de arestas)
    N linhas seguintes: lat lon                (o índice da linha é o id do nó, de 0 a N-1)
    M linhas seguintes: origem destino metros segundos

Exemplos:
    python tools/prepare_map.py --lugar "Campina Grande, Paraíba, Brazil" --nome campina_grande
    python tools/prepare_map.py --lugar "Paraíba, Brazil" --nome paraiba --pbf nordeste.osm.pbf

Para áreas grandes (um estado), o Overpass costuma recusar ou limitar as consultas.
Nesse caso, baixe o extrato do Geofabrik e passe com --pbf (precisa do `osmium`,
`brew install osmium-tool`):
    https://download.geofabrik.de/south-america/brazil/nordeste-latest.osm.pbf
"""

import argparse
import gzip
import json
import math
import os
import random
import subprocess
import tempfile

import osmnx as ox

# Tipos de via que entram no mapa quando ele vem do arquivo .pbf.
# Aproxima o filtro network_type="drive" do osmnx (fica de fora: serviço, trilha, pedestre).
VIAS_CARRO = [
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link",
    "unclassified", "residential", "living_street", "road",
]


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Aproximação equiretangular: boa o bastante para distâncias dentro de um estado.
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return 6371.0 * math.hypot(x, y)


def grafo_do_pbf(pbf: str, lugar: str, simplificar: bool):
    """Recorta o .pbf no contorno do lugar, filtra as vias de carro e carrega no osmnx."""
    with tempfile.TemporaryDirectory() as pasta:
        contorno = os.path.join(pasta, "contorno.geojson")
        recorte = os.path.join(pasta, "recorte.osm.pbf")
        vias = os.path.join(pasta, "vias.osm")

        # O contorno vem do Nominatim, que aguenta bem uma consulta só.
        ox.geocode_to_gdf(lugar)[["geometry"]].to_file(contorno, driver="GeoJSON")
        subprocess.run(["osmium", "extract", "-p", contorno, pbf, "-o", recorte], check=True)
        filtro = "w/highway=" + ",".join(VIAS_CARRO)
        subprocess.run(["osmium", "tags-filter", recorte, filtro, "-o", vias], check=True)
        return ox.graph_from_xml(vias, simplify=simplificar)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lugar", required=True, help='Nome do lugar, ex.: "Campina Grande, Paraíba, Brazil"')
    parser.add_argument("--nome", required=True, help="Nome curto usado nos arquivos de saída")
    parser.add_argument("--nao-simplificar", action="store_true",
                        help="Mantém os nós intermediários das ruas (mapa com muito mais nós)")
    parser.add_argument("--pares", type=int, default=300, help="Quantidade de pares de teste")
    parser.add_argument("--dist-max-km", type=float, default=0,
                        help="Distância máxima em linha reta entre origem e destino (0 = sem limite)")
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("--pbf", help="Arquivo .osm.pbf local, em vez de baixar do Overpass")
    args = parser.parse_args()

    if args.pbf:
        print(f"Lendo a rede viária de {args.lugar} a partir de {args.pbf}")
        G = grafo_do_pbf(args.pbf, args.lugar, not args.nao_simplificar)
    else:
        print(f"Baixando a rede viária de: {args.lugar}")
        G = ox.graph_from_place(args.lugar, network_type="drive", simplify=not args.nao_simplificar)
    # Fica só a maior parte fortemente conectada: assim existe caminho entre quaisquer dois nós.
    G = ox.truncate.largest_component(G, strongly=True)
    G = ox.routing.add_edge_speeds(G)
    G = ox.routing.add_edge_travel_times(G)

    # Os ids do OSM são números enormes. O servidor usa ids de 0 a N-1.
    novo_id: dict[int, int] = {}
    lats: list[float] = []
    lons: list[float] = []
    for osm_id, dados in G.nodes(data=True):
        novo_id[osm_id] = len(lats)
        lats.append(dados["y"])
        lons.append(dados["x"])

    arestas: list[str] = []
    for u, v, dados in G.edges(data=True):
        arestas.append(f"{novo_id[u]} {novo_id[v]} {dados['length']:.1f} {dados['travel_time']:.1f}")

    arquivo_mapa = f"data/{args.nome}.map.gz"
    with gzip.open(arquivo_mapa, "wt") as f:
        f.write(f"{len(lats)} {len(arestas)}\n")
        for i in range(len(lats)):
            f.write(f"{lats[i]:.6f} {lons[i]:.6f}\n")
        for linha in arestas:
            f.write(linha + "\n")
    print(f"{arquivo_mapa}: {len(lats)} nós, {len(arestas)} arestas")

    # Pares fixos de origem/destino para o teste de carga ser reproduzível.
    rng = random.Random(args.semente)
    pares: list[dict] = []
    while len(pares) < args.pares:
        a = rng.randrange(len(lats))
        b = rng.randrange(len(lats))
        if a == b:
            continue
        if args.dist_max_km > 0 and distancia_km(lats[a], lons[a], lats[b], lons[b]) > args.dist_max_km:
            continue
        pares.append({"origem": [lats[a], lons[a]], "destino": [lats[b], lons[b]]})

    arquivo_pontos = f"data/pontos_{args.nome}.json"
    with open(arquivo_pontos, "w") as f:
        json.dump(pares, f, indent=1)
    print(f"{arquivo_pontos}: {len(pares)} pares")


if __name__ == "__main__":
    main()
