"""
TSP to JSON Converter
---------------------

This script converts TSPLIB-formatted Traveling Salesman Problem (TSP) instances
into compact, self-contained JSON files. It loads each `.tsp` file in a given
directory, extracts its metadata and distance matrix using `tsplib95`, and writes
a normalized JSON version suitable for downstream data processing or visualization.

Author: Skander Kort
License: Apache License 2.0
"""

import csv
import json
import os.path
from typing import Dict, List, Any

import tsplib95
import typer
from rich import print
from tqdm import tqdm

# Config
INCLUDE_DIST_THRESHOLD = 15000  # Distances matrix is not included in the result JSON if dimension is greater this value and if requested by user.
TSP_SRC_DIR = "./benchmarks/original"  # Directory containing the original '.tsp' files and a solution best known costs file.
TSP_OUT_DIR = "./benchmarks/json"  # Directory to store the converted TSP instances.
UNKNOWN_BEST_COST = -1  # Used when no best cost is know for some TSP instance.


# Init app.
app = typer.Typer()


@app.command()
def to_json(
    src_directory: str = TSP_SRC_DIR,
    out_directory: str = TSP_OUT_DIR,
    include_distances: bool = True,
    inc_dist_threshold: int = INCLUDE_DIST_THRESHOLD,
):
    """Converts all the TSP instances in a source directory and saves the results in
        some output directory.

    Args:
        src_directory (str, optional): Directory containing the original TSP files. Defaults to TSP_SRC_DIR.
        out_directory (str, optional): Directory where the converted JSON files are saved. Defaults to TSP_OUT_DIR.
        include_distances (bool, optional): Controls whether distances matrix should be included in the output file.
        inc_dist_threshold: (int, optional): Apllies when inc_dist_matrix=True. Distinces matrix is not included in output file
        for instances where the number of nodes is greater than this threshold.
    """
    print(
        f"[bold yellow]Started converting TSP instances in {src_directory} to JSON...[/bold yellow]"
    )

    tsp_inst_filenames = collect_tsp_inst_filenames(src_directory)
    print(f"[green]found {len(tsp_inst_filenames)} TSP instances.[/green]")

    best_cost_by_inst = load_solutions_costs(src_directory)
    print("[green]Loaded solutions file.[/green]")

    os.makedirs(out_directory, exist_ok=True)
    for tsp_inst_filename in tsp_inst_filenames:
        try:
            instance_to_json(
                tsp_inst_filename,
                best_cost_by_inst,
                out_directory,
                include_distances,
                inc_dist_threshold,
            )
        except Exception as e:
            print(
                f"[red]Failed to convert TSP instance {tsp_inst_filename} with error {e}[/red]"
            )

    print(
        f"[bold yellow]Done converting TSP instances in '{src_directory}' to JSON, results written in directory '{out_directory}'[/bold yellow]"
    )


def collect_tsp_inst_filenames(src_directory: str) -> List[str]:
    """Collects the file names of all TSP instances under some directory.

    Args:
        src_directory (str): Parent directory.

    Returns:
        List[str]: File names.
    """
    return [fname for fname in os.listdir(src_directory) if fname.endswith(".tsp")]


def load_solutions_costs(src_directory: str) -> Dict[str, float]:
    """Loads and parses the best known solutions file of TSPLIB.

    Args:
        src_directory (str): Parent directory.

    Raises:
        ValueError: when the solutions file does not exist.

    Returns:
        Dict[str, float]: the cost of the best known solution for each TSP instance.
    """
    sol_filepath = os.path.join(src_directory, "solutions")
    if not os.path.exists(sol_filepath):
        raise ValueError(f"Solutions file {sol_filepath} does not exist!")

    with open(sol_filepath, "r") as file:
        sol_records = list(csv.reader(file, delimiter=":", skipinitialspace=True))

    cost_by_instance = {rec[0].strip(): float(rec[1]) for rec in sol_records}

    return cost_by_instance


def instance_to_json(
    tsp_inst_filename: str,
    best_cost_by_inst: Dict[str, float],
    out_directory: str,
    include_distances: bool,
    inc_distances_threshold: int,
) -> None:
    """Converts a TSP instance to a self-contained JSON object and saves the result in a file.

    Args:
        tsp_inst_filename (str): Name of the file containing the TSP instance.
        best_cost_by_inst (Dict[str, float]): Best known solution cost for each TSP instance in this benchmark.
        out_directory (str): Directory where the JSON conversion are saved.
        inc_dist_threshold: (int, optional): Apllies when inc_dist_matrix=True. Distinces matrix is not included in output file
        for instances where the number of nodes is greater than this threshold.

    Raises:
        ValueError: when the instance file does not exist.
    """
    filepath = os.path.join(TSP_SRC_DIR, tsp_inst_filename)
    if not os.path.exists(filepath):
        raise ValueError(f"File {filepath} does not exist!")

    tsp_inst_name = os.path.splitext(os.path.basename(tsp_inst_filename))[0]
    print(f"[blue]Converting TSP instance {tsp_inst_name} to JSON format...[blue]")

    tsp_instance = tsplib95.load(filepath)
    print(f"[green]Loaded instance {tsp_instance.name}[/green]")
    tsp_dict = tsp_instance.as_keyword_dict()

    tsp_dict["best_known_cost"] = best_cost_by_inst.get(
        tsp_instance.name, UNKNOWN_BEST_COST
    )

    if should_collect_distances(tsp_dict, include_distances, inc_distances_threshold):
        tsp_dict["distances_matrix"] = collect_distances_matrix(tsp_instance)

    # Delete the now-redundent edge weights to reduce the size of the resulting JSON file.
    tsp_dict.pop("EDGE_WEIGHT_SECTION", None)

    tsp_dict_norm = {to_camel_case(k): v for k, v in tsp_dict.items()}
    tsp_json = json.dumps(tsp_dict_norm)

    out_filepath = os.path.join(out_directory, tsp_inst_name + ".json")
    with open(out_filepath, "w") as file:
        file.write(tsp_json)

    print(
        f"[cyan]Done converting TSP instance {tsp_inst_name},  result saved in {out_filepath}[/cyan]"
    )


def should_collect_distances(
    tsp_dict: Dict[str, Any], include_distances: bool, inc_distances_threshold: int
) -> bool:
    """Decides whether the converter should add the distances matrix to the json output file.

    Args:
        tsp_dict (Dict[str, Any]): TSP instance as a dictionary.
        include_distances (bool): TRUE iff user requested the inclusion of distances in the output file.
        inc_distances_threshold (int): Nodes count beyond which distances will not be included regardless of user choice.

    Returns:
        bool: TRUE iff distances should be collected.
    """

    return (
        include_distances and tsp_dict["DIMENSION"] <= inc_distances_threshold
    ) or tsp_dict["EDGE_WEIGHT_TYPE"] == "EXPLICIT"


def collect_distances_matrix(tsp_instance) -> List[List[float]]:
    """Collects the upper right distance matrix (excluding the principal diagonal)

    Args:
        tsp_instance (Problem): A TSP instance.

    Returns:
        List[List[float]]: Upper-right distance matrix (excluding the principal diagonal).
    """
    print(
        f"[bold]collecting distances for TSP instance {tsp_instance.name}, dimension={tsp_instance.dimension}, distance type = {tsp_instance.edge_weight_type}[/bold]"
    )

    dim = tsp_instance.dimension
    distances: List[List[float]] = []
    # We use method Problem::get_nodes() to retrieve node indexes.
    # Node indexes start at 0 for some instances and at 1 for other instances.
    # c.f. https://tsplib95.readthedocs.io/en/stable/pages/usage.html#working-with-problems
    node_idxs = list(tsp_instance.get_nodes())
    if node_idxs[0] == 0:
        end_idx = dim
    else:
        end_idx = dim + 1
    for i in tqdm(node_idxs):
        row = [tsp_instance.get_weight(i, j) for j in range(i + 1, end_idx)]
        distances.append(row)

    return distances


def to_camel_case(snake_case_str: str) -> str:
    """
    Converts a string in snake-case to camel-case.
    """
    parts = snake_case_str.split("_")

    words = [w.title() for w in parts[1:]]
    words.insert(0, parts[0].lower())
    return "".join(words)


if __name__ == "__main__":
    app()
