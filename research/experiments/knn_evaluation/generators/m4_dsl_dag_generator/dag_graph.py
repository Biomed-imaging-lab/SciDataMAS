from typing import Optional, List, Dict
from pydantic import BaseModel, Field

from .grammar import NODE_TYPES, VALID_EDGES


class DAGNode(BaseModel):
    node_id: str = Field(description="Unique snake_case identifier for this node")
    node_type: str = Field(description="Type from the DSL taxonomy")
    name: str = Field(description="Human-readable name, 3-6 words")
    description: str = Field(
        description="One sentence: what this node represents in the experiment"
    )
    agent: Optional[str] = Field(
        default=None,
        description="Agent performing this node (researcher, instrument model, software+version). "
        "Required for Process and Capture nodes. Omit for others.",
    )
    is_external: Optional[str] = Field(
        default=None,
        description="Boolean flag, attached to 'Signal' or 'Derivative' nodes (Omit for others)."
        "Describes if data retrieved from externa sources",
    )


class DAGEdge(BaseModel):
    source: str = Field(description="node_id of the source node")
    target: str = Field(description="node_id of the target node")


class DAG(BaseModel):
    nodes: Dict[str, DAGNode] = Field(description="All nodes in the DAG")
    edges: List[DAGEdge] = Field(description="All directed edges in the DAG")


def convert_to_DAG(nodes: List[DAGNode], edges: List[DAGEdge]) -> DAG:
    node_dict = {n.node_id: n for n in nodes}
    dag = DAG(nodes=node_dict, edges=edges)
    return dag


class Validator:
    def __init__(self):
        return

    def __indexes_check(self, nodes: List[DAGNode], edges: List[DAGEdge]):
        issues = []

        nodes_set = set()
        for node in nodes:
            if node.node_id in nodes_set:
                issues.append(
                    f'[Node\'s id collision]: id "{node.node_id}" used multiple times (repeared in {node.name} node).'
                )
            else:
                nodes_set.add(node.node_id)

        for edge in edges:
            if edge.source not in nodes_set:
                issues.append(
                    f'[Edges\'s bad id]: some edge have unknown node id a source - "{edge.source}".'
                )
            if edge.target not in nodes_set:
                issues.append(
                    f'[Edges\'s bad id]: some edge have unknown node id a target - "{edge.target}".'
                )

            if edge.target in nodes_set and edge.source in nodes_set:
                self.in_edges[edge.target].append(edge.source)
                self.out_edges[edge.source].append(edge.target)
        return issues

    def __nodes_valid_check(self, nodes: List[DAGNode], edges: List[DAGEdge]):
        issues = []

        for _, node in self.node_dict.items():
            if node.node_type not in NODE_TYPES:
                issues.append(
                    f'[Node\'s bad type]: "{node.node_id}" node has unacceptable type - "{node.node_type}".'
                )
        return issues

    def __edges_valid_check(self, nodes: List[DAGNode], edges: List[DAGEdge]):
        issues = []

        for edge in edges:
            src_id = edge.source
            tgt_id = edge.target

            if (
                src_id not in self.node_dict.keys()
                or tgt_id not in self.node_dict.keys()
            ):
                continue

            edge_type = (
                self.node_dict[src_id].node_type,
                self.node_dict[tgt_id].node_type,
            )
            if edge_type not in VALID_EDGES:
                issues.append(
                    f"[Unaccaptable nodes linkage]: \"{self.node_dict[src_id].node_type}\" -> \"{self.node_dict[tgt_id].node_type}\" can't be linked, but it was detected between nodes '{src_id}' and '{tgt_id}'. Check the rules for available connections."
                )

        return issues

    def __required_connection_check(self, nodes: List[DAGNode], edges: List[DAGEdge]):
        issues = []

        for node in nodes:
            parents = [
                self.node_dict[s]
                for s in self.in_edges[node.node_id]
                if s in self.node_dict
            ]
            children = [
                self.node_dict[t]
                for t in self.out_edges[node.node_id]
                if t in self.node_dict
            ]

            if node.node_type == "Capture":
                # Rule 1: must have >=1 incoming Entity
                if not any(p.node_type == "Entity" for p in parents):
                    issues.append(
                        f"[Bad 'Capture' input] '{node.node_id}' has no input 'Entity' edge."
                    )

                # Rule 2: must have >=1 outgoing Signal or Derivative
                if not any(c.node_type in ("Signal", "Derivative") for c in children):
                    issues.append(
                        f"[Bad 'Capture' output] Capture '{node.node_id}' has no Signal or Derivative output."
                    )

        return issues

    def __loops_check(self):
        visited = set()
        rec_stack = set()
        issues = []

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for nb in self.out_edges.get(node, []):
                if nb not in visited:
                    if has_cycle(nb):
                        return True
                elif nb in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        for nid in self.node_ids:
            if nid not in visited:
                if has_cycle(nid):
                    issues.append(
                        "[Cycled DAG] Graph contains a cycle - DAG must be acyclic"
                    )
                    break
        return issues

    def __check_linkage(self, edges: List[DAGEdge]):
        issues = []

        if len(self.node_ids) <= 1:
            return [
                "[Empty DAG] The list of nodes looks empty. Be sure about correctness of your generating results!"
            ]

        # Build undirected adjacency
        adj = {n: set() for n in self.node_ids}
        for e in edges:
            if e.source in adj and e.target in adj:
                adj[e.source].add(e.target)
                adj[e.target].add(e.source)

        # BFS from any node
        start = next(iter(self.node_ids))
        visited = {start}
        queue = [start]
        while queue:
            node = queue.pop()
            for nb in adj[node]:
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)

        if visited != self.node_ids:
            visited_str = ", ".join([f'"{v}"' for v in visited])
            unvisited = self.node_ids - visited
            unvisited_str = ", ".join([f'"{uv}"' for uv in unvisited])
            issues = [
                f"[Not Single linkage DAG graph] - Some nodes are not linkaged to another: list one ({visited_str}) and list two ({unvisited_str}) are disconnected."
            ]
        return issues

    def __call__(self, nodes: List[DAGNode], edges: List[DAGEdge]):
        self.node_dict = {n.node_id: n for n in nodes}
        self.node_ids = set(self.node_dict)
        self.in_edges = {n: [] for n in self.node_ids}
        self.out_edges = {n: [] for n in self.node_ids}

        total_issues = []
        # 1st - id checking
        # - check dublicates in nodes ids
        # - check that edges have correct nodes' ids in them
        total_issues += self.__indexes_check(nodes, edges)

        # 2nd lvl - nodes checking
        # - validate that node have accaptable types
        total_issues += self.__nodes_valid_check(nodes, edges)

        # 3rd lvl - edges checking
        # - check that all edges satisfies the rules of DAG
        #   (here we watch only restrictions in connections, the necessary connections will be checked on 4th step)
        total_issues += self.__edges_valid_check(nodes, edges)

        # 4th lvl - check all connections are in places
        # - checking like Capture has entities and produce any signals and so on
        total_issues += self.__required_connection_check(nodes, edges)

        # 5th - checking on loops
        total_issues += self.__loops_check()

        # 5th - checking on linkage
        total_issues += self.__check_linkage(edges)

        return total_issues
